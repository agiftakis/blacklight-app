# Blacklight

**See what Windows quietly records about you — and clear it, locally.**

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform: Windows 10/11](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6)
![Release](https://img.shields.io/badge/Release-v1.0.0-9FEF00)

Blacklight is a local-first, open-source Windows privacy-transparency dashboard. It reads the hidden "forensic artifacts" (records Windows keeps about how you've used your PC) and shows them to you in plain language — then lets you clear specific ones, safely and reversibly.

Everything runs 100% on your machine. No accounts, no telemetry, no cloud. Nothing ever leaves your PC.

<!-- Add a screenshot here once you have one: ![Blacklight dashboard](docs/screenshot.png) -->

## What it surfaces

- **GDID** — a hidden device identifier Windows uses that can tie activity back to your machine. Masked by default so it never sits exposed on your screen.
- **UserAssist** — a log of which programs you've launched and how often. Includes a guarded **Clear + Backup** action.
- **BAM / DAM** — a record of recent background app activity (read-only in v1.0.0).

## Principles

- **100% local.** No network calls, no accounts, no data collection.
- **Reversible by default.** Before any clear action, Blacklight automatically exports a full `.reg` backup, so you can always undo it.
- **Honest scope.** This is a transparency and privacy-hygiene tool — it shows and cleans up specific local artifacts. It can make you "invisible" or untrackable, with consistent registry wipes (NOT advisable however).

## Download & install

Grab the latest installer from the [**Releases**](https://github.com/agiftakis/blacklight-app/releases/latest) page:

➡️ **[Blacklight v1.0.0 (Windows 10/11, 64-bit)](https://github.com/agiftakis/blacklight-app/releases/tag/v1.0.0)**

Download `Blacklight_1.0.0_x64-setup.exe` and run it. No Python or other dependencies required.

> **Note:** Blacklight is a new, independent app and isn't code-signed yet, so Windows SmartScreen may show an *"unknown publisher"* warning on first launch. Click **More info → Run anyway** to proceed. This is expected for new indie software — and since the source is public, you can verify exactly what it does.

Website: [blacklight.tools](https://blacklight.tools)

## Usage

1. Launch Blacklight and click **Run Scan**.
2. Review each panel — GDID, UserAssist, and BAM/DAM.
3. For UserAssist, click **Clear + Backup** to reset it. A `.reg` backup is saved first to `%LOCALAPPDATA%\Blacklight\backups`; the exact path is shown right after it saves.
4. To restore, double-click the saved `.reg` backup file.

GDID and UserAssist read from your user profile and don't need admin rights. Reading BAM fully requires running as administrator.

## How it works

Blacklight is a lightweight desktop app — no Electron.

- **Engine** (`engine/`) — a Python backend that reads the registry artifacts and returns them as structured JSON. It's frozen into a single standalone `.exe` (a "sidecar" — a small helper program the app launches) with PyInstaller, so end users don't need Python installed.
- **Shell** (`shell/`) — a [Tauri v2](https://tauri.app) app (Rust core + a plain HTML/CSS/JS webview). The Rust layer calls the engine sidecar and renders its JSON into the dashboard.

## Build from source

Prerequisites: Rust, Node.js, Python 3, and PyInstaller (`pip install pyinstaller`).

The frozen engine binary is **not** committed to the repo (it's a rebuildable artifact), so freeze it yourself before building the app:

```bash
# 1. Freeze the Python engine into a sidecar .exe (recipe is committed as a .spec)
cd engine
pyinstaller blacklight-engine-x86_64-pc-windows-msvc.spec

# 2. Copy the resulting .exe into the Tauri sidecar folder
copy dist\blacklight-engine-x86_64-pc-windows-msvc.exe ..\shell\src-tauri\binaries\

# 3. Build the app
cd ..\shell
npm install
npm run tauri build
```

The installer is written to `shell/src-tauri/target/release/bundle/`.

## Roadmap

- Guarded clear for GDID (v1.1)
- Additional artifacts: SRUM, Prefetch
- Bundled local fonts for a fully offline UI

## Contributing

Feedback, bug reports, and ideas for new artifacts are very welcome — open an [issue](https://github.com/agiftakis/blacklight-app/issues). This is an early PeachTree Apps release, so real-world testing helps a lot.

## License

Licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE).

---

*Blacklight is a privacy-hygiene and transparency tool. It helps you see and clean up specific local Windows artifacts. It is not anti-forensic software and does not make your system untraceable.*
