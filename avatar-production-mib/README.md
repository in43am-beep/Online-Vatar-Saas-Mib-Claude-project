# Avatar Production by MIB

Fresh PySide6 desktop app — **Mode → Channel → Presenter → Title → finished video**.
Frontier dark+gold theme. Free local pipeline by default; paid providers are optional.

## Install (Windows)

1. Install Python 3.11 from python.org (tick **"Add python.exe to PATH"**).
2. Download and unzip the `AvatarProductionByMIB-windows` artifact.
3. Run `AvatarProductionByMIB\AvatarProductionByMIB.exe`.

Or run from source:

```bat
pip install -r requirements.txt
python -m mib.app
```

## How it works

1. **Mode** — FRONTIER PRODUCTION (documentary style) or AI AVATAR (presenter intro + pictures).
2. **Channel** — pick one of your channels. Each card shows the per-minute cost up front (`$0.00/min` when fully local).
3. **Presenter** (avatar mode) — pick a presenter, set intro seconds, appearances, and the locked voice.
4. **Title** — one per line makes several videos.
5. **Generate** — watch progress + live log; open the output folder when done.

Output per video: `output/<channel>/<slug>/` → `final.mp4`, `title.txt`,
`description.txt` (with AI disclosure), `tags.txt`, `thumbnail-prompt.txt`,
`costs.json`, `qc-report.json`. Failures go to `quarantine/` with a reason —
a bad run never kills the batch.

## Providers (Settings)

| Need | Free default | Paid option |
|---|---|---|
| Voiceover | Edge TTS (no key) | AI33 Pro key → voice library + **voice clone** (auto-locked per channel) |
| Images | Pillow title cards | Grok (xAI) key, Gemini key — your own images instead of paid stock |
| Script | Local rules engine | AI33 Pro LLM (same key, Settings → Script tab) |
| Subtitles | Off (per-channel toggle, Channels tab) | burned in via ffmpeg when ON |

Keys live only in `config/secrets.yaml` (never committed, never in code).

## Tests

```bat
python -m py_compile (all files)
set QT_QPA_PLATFORM=offscreen && python -m mib.app --smoke
python -m mib.selftest
```

The selftest runs the FULL pipeline headless (1-minute video) and asserts a
real 1920×1080 mp4 with video+audio ≥ 60s. If Edge TTS is unreachable it
falls back to local tone audio and still passes with a warning.
