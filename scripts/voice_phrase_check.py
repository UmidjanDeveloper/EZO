#!/usr/bin/env python3
"""Owner-run voice round trip: synthesise each test phrase with the real EZO API, transcribe
the audio with the real EZO API, and report WER/CER per phrase and language.

Needs a running EZO API with real provider keys (OPENAI_API_KEY and/or ELEVENLABS_API_KEY) —
this repository never holds them, so CI never runs this; the numbers it prints are
PENDING OWNER TEST evidence for scenario B (Uzbek voice) and belong in the owner's report.
A low WER proves that the synthesised voice is *intelligible to the recogniser*; whether it
sounds natural is still a listening test.

Usage:
  python scripts/voice_phrase_check.py --api http://localhost:8000 --token <EZO token> \
      [--languages uz,en,ru]
Exit status 1 when any language's mean WER exceeds --max-wer (default 0.25).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))
from ezo_api.voice.phrases import TEST_PHRASES, compare


def _request(url: str, token: str, data: bytes, content_type: str) -> tuple[bytes, dict[str, str]]:
    if not url.startswith(("http://", "https://")):
        raise ValueError("--api must be an http(s) URL")
    request = urllib.request.Request(url, data=data, method="POST")  # noqa: S310 - scheme checked
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", content_type)
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - owner-provided URL
        return response.read(), {k.lower(): v for k, v in response.headers.items()}


def speak(api: str, token: str, text: str, language: str) -> tuple[bytes, str, str]:
    body = json.dumps({"text": text, "language": language}).encode()
    audio, headers = _request(f"{api}/api/voice/speak", token, body, "application/json")
    return (
        audio,
        headers.get("x-ezo-voice-provider", "?"),
        headers.get("content-type", "audio/mpeg"),
    )


def transcribe(api: str, token: str, audio: bytes, mime: str, language: str) -> str:
    boundary = f"----ezo{uuid.uuid4().hex}"
    ext = "wav" if "wav" in mime else "mp3"
    parts = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'
        ).encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; '
            f'filename="phrase.{ext}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        + audio
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body, _ = _request(
        f"{api}/api/voice/transcribe",
        token,
        b"".join(parts),
        f"multipart/form-data; boundary={boundary}",
    )
    return str(json.loads(body).get("text", ""))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", required=True, help="EZO API base URL, e.g. http://localhost:8000")
    parser.add_argument("--token", required=True, help="EZO API token (EZO_AUTH_MODE=token)")
    parser.add_argument("--languages", default="uz,en,ru")
    parser.add_argument("--max-wer", type=float, default=0.25)
    args = parser.parse_args()
    failed = False
    for language in [part.strip() for part in args.languages.split(",") if part.strip()]:
        rates: list[float] = []
        print(f"\n== {language} ==")
        for phrase in TEST_PHRASES[language]:
            try:
                audio, provider, mime = speak(args.api, args.token, phrase, language)
                heard = transcribe(args.api, args.token, audio, mime, language)
            except urllib.error.HTTPError as error:
                print(f"  HTTP {error.code} for {phrase!r}: {error.read()[:200]!r}")
                failed = True
                continue
            result = compare(phrase, heard, language)
            rates.append(result.wer)
            mark = "ok " if result.wer <= args.max_wer else "BAD"
            print(
                f"  [{mark}] WER {result.wer:.2f} CER {result.cer:.2f} ({provider}) "
                f"{phrase!r} -> {heard!r}"
            )
        if rates:
            mean = sum(rates) / len(rates)
            print(f"  mean WER {mean:.2f} over {len(rates)} phrases")
            failed = failed or mean > args.max_wer
    print(
        "\nResult:",
        "FAIL" if failed else "PASS",
        "(recogniser intelligibility only; naturalness is a listening test)",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
