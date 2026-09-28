# MIB Avatar Production System

> **AI-powered YouTube video factory** — type a title, get a finished video.

![Version](https://img.shields.io/badge/version-4.0-gold)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.x-green)

---

## What It Does

Fully automated video production pipeline:

```
Title Input
    ↓
Script (Gemini / AI33 Pro LLM)
    ↓
Claude Script Review (optional quality check)
    ↓
Voiceover (Gemini TTS / AI33 Pro / Edge TTS)
    ↓
Bulk Image Prompts (Gemini — character-consistent per scene)
    ↓
Scene Images (Grok / Gemini image gen / local fallback)
    ↓
Avatar Presenter (static PNG / character card / Veo video clips)
    ↓
Video Assembly (ffmpeg — Ken Burns, subtitles, SFX)
    ↓
Thumbnail + Package + Google Drive Upload
```

---

## Two Production Modes

| Mode | Description |
|------|-------------|
| **Frontier Production** | Documentaries, maps, real footage, graphics |
| **AI Avatar** | Real-looking presenter opens every video, then pictures take over |

---

## Web Dashboard (v4 — Wizard UI)

```bash
python web_app.py
# Open: http://localhost:7860
```

### Wizard Flow:
1. **Mode** — Frontier or AI Avatar
2. **Channel** — select from your channels
3. **Presenter** — avatar grid with video thumbnails, gender filter, seconds slider, appearances
4. **Title** — one per line = multiple videos in bulk
5. **Length** — 5/10/20/30 min + real-time cost estimate
6. **[CREATE VIDEO]** — big gold button

### Channel Setup:
- 🎭 **Avatar Clips** — upload MP4 presenter clips (auto-thumbnail generated)
- 🪪 **Character Sheet** — identity card with **Quick Paste Auto-Fill** (paste any description → Gemini extracts all fields)
- 🤖 **AI Prompt** — master prompt + negative prompt for image consistency
- 🎙️ **Voice** — per-channel voice selection
- ⚙️ **Info** — mode, niche, default length

---

## Quick Start

### 1. Install
```bash
cd avatar-production-mib
pip install -r requirements.txt
```

### 2. Add API Keys
```bash
# Edit config/secrets.json (copy from secrets.example.json)
{
  "gemini_api_key": "AIza...",
  "ai33pro_api_key": "ai33-...",
  "xai_api_key": "xai-...",
  "anthropic_api_key": "sk-ant-..."
}
```

Or set them in the web UI → **Settings → API Keys**

### 3. Run
```bash
python web_app.py
# OR double-click START-APP.bat
```

---

## Project Structure

```
avatar-production-mib/
├── web_app.py              # Flask web dashboard (v4 Wizard UI)
├── START-APP.bat           # Windows one-click launcher
├── requirements.txt
├── config/
│   ├── competitors.json    # Channel database (92 channels decoded)
│   └── secrets.example.json
├── mib/
│   ├── pipeline.py         # Main orchestrator
│   ├── config.py           # Config loader
│   ├── character.py        # Character sheet / identity lock
│   ├── patterns.py         # Channel pattern recognition
│   ├── thumbnail.py        # Thumbnail generator
│   ├── sfx.py              # Sound effects
│   ├── gdrive.py           # Google Drive upload
│   ├── providers/
│   │   ├── geminillm.py    # Gemini LLM script generation
│   │   ├── scriptllm.py    # AI33 Pro script generation
│   │   ├── claudereview.py # Claude script quality review
│   │   ├── geminitts.py    # Gemini Text-to-Speech
│   │   ├── ai33voice.py    # AI33 Pro TTS
│   │   ├── edgevoice.py    # Microsoft Edge TTS (free)
│   │   └── genimages.py    # Image generation (Grok/Gemini)
│   └── stages/
│       ├── script.py       # Script building
│       ├── voiceover.py    # TTS orchestration
│       ├── images.py       # Scene image generation
│       ├── image_prompts.py # Bulk Gemini image prompt generator
│       ├── avatar.py       # Static presenter (Ken Burns)
│       ├── avatar_card.py  # Character card overlay
│       ├── avatar_veo.py   # AI video clip presenter
│       ├── assemble.py     # ffmpeg video assembly
│       └── package.py      # Output packaging
├── assets/
│   └── avatars/            # Per-channel MP4 presenter clips
└── output/                 # Generated videos (git-ignored)
```

---

## Key Features

- ✅ **Bulk video generation** — paste 10 titles, generate 10 videos overnight
- ✅ **Character consistency** — identity lock with master prompt across all scenes
- ✅ **Quick Paste Auto-Fill** — paste any character description → Gemini fills all fields
- ✅ **Competitor intelligence** — 92 channels decoded with Gemini AI
- ✅ **Multiple TTS providers** — Gemini, AI33 Pro, Edge TTS fallback chain
- ✅ **Multiple image providers** — Grok → Gemini → local Pillow fallback
- ✅ **Auto thumbnails** — extracted from avatar clips at startup
- ✅ **Google Drive upload** — auto-upload finished videos
- ✅ **Real-time streaming logs** — SSE progress in browser
- ✅ **Windows desktop notifications** — when video is ready

---

## API Keys Needed

| Service | Used For | Free? |
|---------|----------|-------|
| Google Gemini | Script, images, TTS, competitor decode | Free tier available |
| AI33 Pro | Premium TTS voices | Paid |
| xAI / Grok | High-quality image generation | Paid |
| Anthropic Claude | Script quality review | Optional |

---

## License

Private — for personal/business use only.
