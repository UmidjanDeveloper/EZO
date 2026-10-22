# Voice provider response resource boundary

OpenAI/VoiceStudio previously allowed the SDK to buffer the entire response before
returning it. Input recording limits do not constrain response bytes or a slow
provider. `voice/http_limits.py` now caps bytes before SDK buffering using the
installed SDK's HTTPX2 send/stream interface. No upstream VoiceStudio code copied.

- Audio response bound: existing `EZO_VOICE_MAX_AUDIO_MB` (default10, maximum25MiB).
- Transcript JSON and provider error bodies: <=256000bytes (audio errors may have
  a smaller configured audio bound). Declared oversize rejected before reading;
  missing/lying Content-Length still faces counted streaming bytes.
- Request Accept-Encoding identity; other response encodings rejected before
  decoding. No redirects followed. HTTPX2 default proxy/TLS trust retained.
- Existing `EZO_VOICE_TIMEOUT_SECONDS` applies to the whole operation, including
  retry/backoff/body reads, rather than only an individual socket inactivity gap.
- Context cancellation propagates and closes the active response. No partial audio
  is returned as successful when a bound, timeout or cancellation is reached.
- SDK retry policy remains <=one retry; limits are per response/attempt. This is
  not provider-side billing enforcement or a guaranteed dollar cap. Existing
  explicit provider configuration/fallback/privacy behavior is preserved.
- The OpenAI SDK already installs httpx2 2.13.1. It is now declared directly at the
  same locked version; no additional distribution or package upgrade introduced.

`tests/unit/test_voice_http_limits.py` uses the actual installed SDK and controlled
HTTPX2 byte streams: chunked and falsely declared sizes, large transcript JSON,
compressed/error responses, redirects, exact-boundary success, slow drip, external
cancellation/closure and invalid configuration. Existing VoiceStudio HTTP wire and
provider fallback tests remain. No model/server, provider account or paid API is
contacted. These tests do not demonstrate Uzbek acoustic quality or live engines.
