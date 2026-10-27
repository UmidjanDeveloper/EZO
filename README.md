<div align="center">

# EZO OS

**SEN BILAN O‘SADIGAN SUN’IY INTELLEKT**

*One intelligence. Every device. Real work.*

[**Get started**](#-quick-start) · [**Explore features**](#-built-for-real-work) · [**Architecture**](#-architecture) · [**Desktop & Mobile**](#-devices--installation)

<img src="docs/devices/img/humanoid-web.jpg" width="780" alt="Actual EZO humanoid WebGL rendering captured in the project's browser test environment" />

<sub>Actual EZO WebGL humanoid render from the project test environment — not a physical-device screenshot.</sub>

**Uzbek-first** · **Voice-driven** · **Multi-agent** · **Web / Windows / Android**

[Implementation status](IMPLEMENTATION_STATUS.md) · [Full technical guide](docs/README_DETAILED.md)

</div>

---

## Meet EZO

**A personal AI operating platform — not another chat window.** Talk naturally, work with documents, learn from sources, create professional files and coordinate approved actions. EZO combines specialized capabilities behind one conversation and prioritizes Uzbek alongside English and Russian.

> **Project stage: alpha.** Functionality differs by platform, provider and deployment configuration. A successful test or build is not proof of real-device acceptance. Features requiring cameras, cloud credentials, mobile permissions or external delivery providers must be verified separately. No production deployment or paid resource is implied by this repository.

## ✦ Built for real work

| Experience | What it is designed to do |
|:--|:--|
| **Natural conversation & voice** | Uzbek / English / Russian text and turn-based speech, with provider-dependent quality and availability |
| **EZO Humanoid** | Procedural WebGL avatar with distinct listening, thinking and speaking visuals; reduced-motion and fallback support |
| **Knowledge & Student** | Read permitted documents, retrieve source-grounded answers and support learning workflows |
| **Office & Presentations** | Generate and work with DOCX, XLSX, PPTX, PDF and versioned artifacts where supported |
| **Personal intelligence** | Consent-controlled memory, user preferences, projects and conversational continuity |
| **JARVIS-style tasks** | Authorized, auditable device/browser actions subject to real provider permissions and verification |
| **Desktop & mobile** | Windows Electron, Android Capacitor and browser experiences built on a shared backend |

**Not a capability claim:** Real-time camera-guided avatar motion, uninterrupted multi-device workflows, iOS installation and external messaging require the acceptance evidence described in the project documentation.

## ◇ Actual code-rendered interface samples

These images are produced from the repository's UI in browser/test environments. **They are not photos of a physical phone or PC.**

| Web humanoid | Android-layout voice stage | Windows floating pill |
|:--:|:--:|:--:|
| ![EZO web avatar](docs/devices/img/humanoid-web.jpg) | ![EZO Android-layout avatar](docs/devices/img/humanoid-android.jpg) | ![EZO Windows pill](docs/devices/img/humanoid-pill.jpg) |

[Humanoid implementation, technical details and test limitations](docs/devices/HUMANOID.md)

## ⚡ Quick start

**Prerequisites:** Docker Desktop and a Git checkout of this repository.

```bash
cp .env.example .env
docker compose up --build
```

Visit **http://localhost:3000** for the web interface; API reference is at **http://localhost:8000/docs**.

Windows PowerShell: use `Copy-Item .env.example .env` instead of `cp` if needed.

- Never commit provider keys or personal credentials.
- Without an authorized provider configuration, model-dependent features may be unavailable or operate in an explicitly limited offline mode.
- Avoid `docker compose down -v` unless you intend to delete Docker-stored data.

For developer tooling, database modes, configuration, voice engines, Office use cases and troubleshooting, read the **[full technical guide](docs/README_DETAILED.md)**.

## ▦ Architecture

```text
                  EZO OS
       ┌──────────┼───────────┐
       │          │           │
   Web / UI   Windows     Android
              Electron    Capacitor
       └──────────┼───────────┘
             EZO API (FastAPI)
                    │
         Auth · Consent · Task audit
                    │
     AI routing · Voice · Agent capabilities
                    │
   Memory · Knowledge · Projects · Artifacts
                    │
       PostgreSQL / pgvector / Storage
```

Key code: [API](apps/api) · [Web](apps/web) · [Desktop](apps/desktop) · [Mobile](apps/mobile) · [Humanoid](packages/avatar) · [Roadmap](docs/master/OWNER_ROADMAP_P0_P9.md).

## ▣ Devices & installation

| Platform | Codebase | Verification |
|:--|:--|:--|
| Web | `apps/web` | Local/browser tests; live deployment is separate |
| Windows | `apps/desktop` | Electron and installer pipeline; physical PC testing required |
| Android | `apps/mobile` | Capacitor APK/emulator path; real handset testing required |
| iOS | Planned / platform-specific integration | Do not assume a signed/tested iPhone release |
| Chrome | Extension source | Permissioned browsing only; install and behavior need validation |

Refer to [device documentation](docs/devices/README.md) and [implementation status](IMPLEMENTATION_STATUS.md) for current evidence.

## ✓ Trust & release principles

1. **Permission before action:** device, camera and external messaging capabilities must be deliberately authorized.
2. **Grounded output:** distinguish source-backed results from generated content and simulated demonstrations.
3. **No fake success:** build/test pass, installer generation and real-device validation are different stages.
4. **Isolation by design:** untrusted documents and generated code do not receive unrestricted host execution.
5. **Owner-controlled release:** no automatic PR merges, paid provisioning, production secrets or production deployment without approval.

## Documentation

**[Complete user/developer documentation](docs/README_DETAILED.md)** · **[Current implementation](IMPLEMENTATION_STATUS.md)** · **[P0–P9 roadmap](docs/master/OWNER_ROADMAP_P0_P9.md)** · **[Humanoid](docs/devices/HUMANOID.md)** · **[Windows setup](SETUP_WINDOWS.md)**

---

<div align="center">
<sub>Built as one connected product. One identity. One memory. One EZO.</sub>
</div>
