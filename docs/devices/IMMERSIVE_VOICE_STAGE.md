> **Superseded visual direction (2026-10-29):** the current energy-humanoid implementation and verification notes live in [HUMANOID.md](HUMANOID.md). This file is retained as historical context for the earlier contour-bust iteration.

# Immersive voice stage

Owner-requested follow-up to the previously merged reference correction (PR #64).
Base: 8fdc4c9, latest integration branch at implementation time.

Voice mode now opens a native modal dialog covering the full dynamic viewport,
including the sidebar/header area. The existing WebGL holographic bust fills that
scene; there is no separate lower settings panel. Captions are bounded overlays
near the bottom. Volume, language, camera/clap consent and diagnostics live in a
collapsed settings disclosure. Camera/microphone status stays visible when it is
closed. Offline mode remains visibly identified. X or Escape returns to writing;
unmounting uses the existing speech/perception cleanup. The modal makes the
background inert and confines keyboard focus without changing browser fullscreen
permissions. Sensors still require explicit activation.

No renderer geometry, provider, model, backend or production configuration change.
The supplied video is visual reference only; no footage or third-party marks are
shipped. This reproduces the requested full-window composition, not an assertion
that the procedural avatar is pixel-identical to the video.

Screenshots: img/immersive-desktop.png (1440×900) and
img/immersive-mobile.png (390×844), actual local app, idle/offline, no physical
camera or paid provider. This does not validate physical tracking or voice quality.

Validation: web TypeScript and ESLint pass; 101 web unit tests pass.
Voice/browser regressions: 6 passed, 0 failed (29.7 s).
Browser tests use synthetic speech and cover full viewport geometry at desktop
and mobile widths, hidden settings, visible sensor status, Escape, conversation
history, server voice ordering, fallback, interruption and language selection.
Existing perception tests now explicitly open settings before camera consent;
physical/model-backed tests require reviewed model assets and device hardware.
