# Visual Agent (Phase 2) — alpha

EZO creates images, edits them, draws diagrams and lays out social graphics and logo concepts.
It also puts generated pictures on presentation slides. Everything it makes is a versioned
**image artifact**. There is no separate tool to open: just ask EZO.

## Try it

| Say or type | What happens |
|---|---|
| “Kosmosdagi mushuk rasmini chiz” | A generated image (needs an image provider) |
| “Sayt uchun hero rasm, 16:9” / “Mahsulot rasmi, vertikal” | A hero or product visual in that format |
| “Fonini to'q ko'k qil” (after an image) | The same image is edited → **version 2** |
| *upload a photo* + “Bu rasmning fonini olib tashla” | The upload is edited into a new image artifact (the original file is untouched) |
| “EZO arxitekturasi diagrammasini chiz” | A diagram drawn by EZO (PNG + SVG), **no image provider needed** |
| “AI kursi uchun Instagram story tayyorla” | A 1080×1920 social graphic; also `post` (1:1), `poster` (4:5), `LinkedIn` / `banner` (16:9) |
| “Nur Academy uchun logo yarat, 3 ta variant” | Three logo concept sheets (symbol + wordmark) |
| “AI startup uchun investor presentation qil” | The deck's hero slides get generated images |
| “… taqdimot qil, rasmsiz” | A deck without generated images |

Images appear as cards with a preview under EZO's answer. The **Yaratilganlar** page shows
the preview, how the image was made, every version, and the files (PNG, SVG for diagrams, the
original picture of a graphic, and the plan as JSON).

## Providers and configuration

Image generation uses the keys you already have:

| Setting | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | — | Either one turns image generation and editing on |
| `EZO_IMAGE_PROVIDERS` | `auto` | Order to try: `auto` (= openai, then gemini), e.g. `gemini,openai`, or `none` |
| `EZO_OPENAI_IMAGE_MODEL` | `gpt-image-2` | Exact OpenAI image model ID |
| `EZO_GEMINI_IMAGE_MODEL` | `gemini-2.5-flash-image` | Exact Gemini image model ID |
| `EZO_IMAGE_QUALITY` | `medium` | `low` / `medium` / `high` (higher costs more) |
| `EZO_IMAGE_MAX_PER_REQUEST` | `4` | Most variants for one request |
| `EZO_IMAGE_MAX_PER_DECK` | `4` | Most generated images in one presentation (`0` = none) |

Model IDs change over time. Check your provider's current list and update the setting; EZO
does not hardcode them anywhere else. `GET /api/status` → `image_providers` shows what is
active. A new vendor or a local model is one class implementing `ImageProvider` (and
optionally `ImageEditProvider`) in `apps/api/src/ezo_api/visual/`, plus a line in
`build_visual_service`.

## Honesty rules (enforced in code, covered by tests)

- **No provider, no pretending.** A request that needs a generated picture is not attempted:
  no model call is made, nothing is stored, and EZO says that no image was generated and which
  key would enable it.
- **Diagrams never need a provider.** EZO's own slide engine draws them, so every label is
  exact text.
- **Social graphics and logo sheets** always get EZO-rendered text. Without a provider, or if
  generation fails, the picture is an abstract composition. The artifact is then marked
  `placeholder: true` with a reason, the page shows a red notice, and EZO's reply says so.
- **Words are never drawn by an image model** (image models misspell text). Prompts ask for
  "no text, letters or logos", and EZO adds all words itself.
- **A refusal is final.** If a provider declines a request under its content policy, EZO
  does not retry it with another provider or a reworded prompt. It reports the refusal.
- **Presentations:** a hero slide without a generated image keeps the abstract visual. The QA
  then records `image_placeholder`, and EZO's summary says "abstract visual (not a real
  image)".

## What is stored

Every image is an artifact of type `image`. Its versions are immutable: an edit adds a version,
and the old one stays restorable. Each version records:

| Field (`generation_metadata`) | Content |
|---|---|
| `kind` | `image`, `hero`, `product`, `presentation`, `diagram`, `social`, `logo` |
| `provider`, `model` | Who made the picture (`ezo` / `layout-engine` for diagrams) |
| `prompt`, `revised_prompt` | The prompt sent, and the provider's rewrite when it reports one |
| `width`, `height`, `aspect_ratio`, `quality` | Dimensions and settings |
| `placeholder`, `placeholder_reason` | Whether the picture is an abstract stand-in, and why |
| `attempts` | Each provider tried, with the error kind if it failed |
| `spec` / `used_in` | The graphic's text and layout plan; the deck an image was made for |

The artifact belongs to the current conversation and project. An edited upload keeps a source
reference to the original file. Presentation story scenes link the image they use.

## Security

- Provider output and uploads are untrusted. Pillow must decode them as PNG, JPEG, WebP or
  GIF, under 25 MB and 40 megapixels (checked before decoding). Every image is then re-encoded
  as PNG, which removes EXIF/location metadata and anything appended to the file.
- SVG (diagrams) is only ever downloaded as an attachment, under a `sandbox` CSP. Only PNG
  previews are shown inline.
- Image IDs inside a deck are set by EZO, never by the model. When building a deck, EZO only
  loads image artifacts that belong to the same user.
- Image calls are paid: limits per request and per deck, a 120-second timeout, and edited
  decks reuse their existing images instead of paying again.

## Known limitations

- Kind, format and edit detection are rule-based (uz/en/ru). Unusual phrasing may give an
  ordinary image instead of, say, a social graphic.
- Diagrams use the slide engine's flow/architecture, process and timeline layouts (up to 8
  nodes / 6 steps). Data charts from a spreadsheet belong to the Document Agent and, later,
  the Data Analyst (Phase 10).
- Masks / selective in-painting, upscaling and background-transparent exports are not
  exposed yet.
- Only hero slides get generated images. Other layouts use icons, charts and shapes.
- Long image generations run inside the chat request; durable background jobs arrive in
  Phase 5.
