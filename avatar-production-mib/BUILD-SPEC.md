# BUILD-SPEC — "Avatar Production by MIB"

Fresh, standalone PySide6 desktop app. Takes IDEAS from `~/workspace/avatar-video-factory/factory/`
(design tokens, ai33voice client, cost engine, wizard concept) but is NEW code in a new package.
User's order (2026-09-24): same wizard as the Frontier reference video —
Mode → Channel → Presenter → Title → finished video — with his own channels,
plus provider options below. Test → run → test until fully working, then Windows exe.

## 1. Product identity
- App name: **Avatar Production by MIB** (window title, header, exe name `AvatarProductionByMIB.exe`)
- Language: UI English. Code comments English.
- Python 3.11, PySide6. All media work via pip-only deps (no system installs):
  - `imageio-ffmpeg` → ffmpeg binary path for assembly/probe
  - `edge-tts` → FREE default voiceover (no key, needs internet)
  - `requests`, `pyyaml`, `Pillow`
- Secrets NEVER in code: `config/secrets.yaml` (gitignored). `config/config.yaml` for channels/presenters/providers.

## 2. Reuse (copy these files INTO the new package, adapt imports)
- `~/workspace/avatar-video-factory/factory/ai33voice.py` → `mib/providers/ai33voice.py`
  (proven AI33 Pro client: `https://api.ai33.pro`, header `xi-api-key`, v3 voice
  library + TTS + `clone_` voice cloning + `/v1/credits`). KEEP AS-IS, only repackage.
- `~/workspace/avatar-video-factory/factory/costs.py` → `mib/costs.py` (keep, extend
  with `("grok-image","image")` and `("gemini-image","image")` unit prices as ESTIMATES).
- `~/workspace/avatar-video-factory/factory/app_style.py` → `mib/ui/theme.py`
  (copy ONLY the token block + stylesheet function; BG #14161c, PANEL #1c1f26,
  GOLD #d4a24e, TEXT #e8e4da, MUTED #8a8f9e — the Frontier dark+gold DNA).
- Concepts (do NOT copy verbatim, re-implement simplified):
  - `app_wizard.py` step flow → new `mib/ui/wizard.py` (5 steps, see §4)
  - `script.py`/`decider.py` rules → `mib/stages/script.py` (local rules engine, §6)

## 3. Provider options (Settings page — the user's explicit requirements)
Every provider has: enable toggle, status dot, "Test" button. Free default always works with zero keys.

### 3a. Voiceover
1. **AI33 Pro** (user: "ai33pro ki api voice over ke liye attach kar dun"):
   Key field → `ai33voice.py` client. "Browse voices" → voice library list
   (elevenlabs_/minimax_/clone_/edge_/kokoro_/vbee_/fishaudio_ prefixes with
   PROVIDER_LABELS). **One-time select per channel**: Channel settings → Voice →
   pick a voice → saved to `config.yaml` under that channel (`voice.provider=ai33pro`,
   `voice.voice_id=...`). Every video for that channel uses it — no re-picking.
2. **Voice clone** (user: "voice clone kar ke de dun, same avatar me wohi voice use ho"):
   Settings → Voice Clone → pick channel → upload sample (mp3/wav/m4a, 1–3 min,
   "clear speech, no music") → "Create clone" via ai33pro clone API → returned
   `clone_` voice id auto-locked to that channel's avatar. Show clone name +
   delete option. If ai33pro key absent: store sample, show "key needed" hint.
3. **Free fallback**: Edge TTS (`edge-tts`), voice per channel (default `en-US-AvaNeural`
   warm female / `en-US-AndrewNeural` male). Speed 85 ≈ rate `-15%`.

### 3b. Script
- **Local rules engine** (default, free): title → hook + beats + CTA (see §6).
- **AI33 Pro LLM** (same key as voice — one entry, like the old factory).

### 3c. AI images — own images instead of paid stock footage (user's requirement)
1. **Google AI (Gemini)** — key field, model select default `gemini-2.5-flash-image`
   (note in UI: "same model family that powers Google Flow").
   REST: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
   header `x-goog-api-key: KEY`, body `{"contents":[{"parts":[{"text": prompt}]}],
   "generationConfig":{"responseModalities":["TEXT","IMAGE"]}}` → find
   `candidates[0].content.parts[].inlineData.data` (base64) → save PNG.
2. **Grok (xAI)** — key field, model select default `grok-imagine-image`
   (fallback `grok-2-image`). REST: `POST https://api.x.ai/v1/images/generations`
   header `Authorization: Bearer KEY`, body `{"model":..., "prompt":...,
   "aspect_ratio":"16:9", "response_format":"b64_json"}` → `data[0].b64_json`.
   NOTE: image URLs from xAI are ephemeral — always use `b64_json`.
3. **Local fallback** (free): Pillow gradient + title text card (never crashes the pipeline).

Image prompts: scene-based, photorealistic, 16:9, no text/watermarks in image.

### 3d. Avatar presenter
- Static avatar PNG + slow zoom (Ken Burns via ffmpeg zoompan) + intro voiceover
  = presenter clip. `assets/avatars/` ships 3 placeholder PNGs (Pillow-generated,
  labeled "replace with your avatar"); UI has "Upload avatar" per presenter.
- Seconds slider (2–15s) with LIVE cost label; Appearances pills: Intro only / 2× / 4× / 6×.

## 4. Wizard UI (the reference-video flow — this is the MAIN window)
Header: "Type a title. Get a finished video." + "Avatar Production by MIB" + gold accents.
Left: circled step numbers ①②③④⑤ with Hide/Show toggle pills (like the video).
"Stuck? Read the log" help strip at bottom (log viewer button — no external AI dependency).

- **Step 0 — Mode** (two big cards):
  - FRONTIER PRODUCTION — "Documentaries and edited videos: AI images, maps-style graphics, captions."
  - AI AVATAR — "A real-looking presenter opens every video, then the pictures take over."
- **Step 1 — Channel** (card grid, "Watch sample" opens sample mp4 if present):
  - `behind-the-hug` — "Emotional soldier-dog reunion stories for a 65+ audience." 30 min default.
  - `kustorez-amish` — "Amish gardening & self-reliant home wisdom for seniors." 15 min default.
  - Each card: description + per-minute cost in GOLD, computed live from enabled
    providers (`$0.00/min` when all-local). "+" card → Add channel (name, niche, default minutes).
- **Step 2 — Presenter** (Avatar mode only; skipped in Frontier mode):
  Avatar grid (name + image), click → fullscreen preview modal → "Use this presenter".
  Filters row (All / Women / Men). Seconds slider + live cost. Appearances pills.
  Voice shown as locked chip: "🔒 Voice: <name> (ai33pro)" → "Change" opens voice picker.
- **Step 3 — Title**: big text box, "one per line makes several". Validate non-empty.
- **Step 4 — Generate**: per-video progress bars + live log tail → Done screen with
  "Open output folder" per video.
- Nav: Back / Continue gold buttons; step dots.

## 5. Pipeline (per title) — `mib/pipeline.py` orchestrates stages
`output/<channel>/<slug>/` per video. Stages:
1. `stages/script.py` → `script.json` {hook, beats[{narration, image_prompt}], cta,
   est_minutes}. Local rules engine: hook from title (curiosity+emotion, ≤18s),
   6 beats (problem→setback→twist→payoff skeleton), CTA (subscribe+comment).
   Narration ~140 wpm. Sanitize: no headers/stage directions in TTS text.
2. `stages/voiceover.py` → per-beat mp3 in `audio/` + `voiceover.mp3` (concat).
   Provider order: channel locked voice (ai33pro/clone) → ai33pro default → edge-tts.
   Verify first 10s exists & non-silent (ffprobe).
3. `stages/images.py` → per-beat `scene-N.png` in `images/`. Provider order:
   grok → gemini → local fallback. 1920×1080 (resize/crop whatever returns).
4. `stages/avatar.py` → `intro.mp4` (presenter PNG zoompan + intro narration =
   first ~2 beats or `presenter_seconds`). Appearances>1: also `mid-N.mp4` rejoins.
5. `stages/assemble.py` → `final.mp4`: intro + per-beat segments
   (image zoompan, duration = beat audio duration, audio = beat mp3),
   1920×1080, libx264 yuv420p, aac. Subtitles: per-channel toggle, DEFAULT OFF.
6. `stages/package.py` → `title.txt`, `description.txt` (with AI-disclosure line),
   `tags.txt`, `thumbnail-prompt.txt`, `costs.json`, `qc-report.json`.
7. `mib/qc.py`: mp4 exists, duration ≥ 60s (or ≥ est*0.8), has audio+video streams
   (ffprobe). Fail → `quarantine/` + reason in report. NEVER crash the batch.

## 6. Config
`config/config.yaml`:
```yaml
channels:
  behind-the-hug: {name, niche, default_minutes: 30, mode: avatar,
                   presenter: maria, voice: {provider: edge, voice_id: en-US-AvaNeural},
                   subtitles: false}
  kustorez-amish: {name, niche, default_minutes: 15, mode: avatar,
                   presenter: walter, voice: {provider: edge, voice_id: en-US-AndrewNeural},
                   subtitles: false}
presenters: [{id: maria, name: Maria, image: assets/avatars/maria.png, gender: f}, ...]
```
`config/secrets.yaml` (gitignored): `ai33pro_api_key`, `gemini_api_key`, `xai_api_key`.

## 7. Cost display
`mib/costs.py`: `estimate_per_minute(channel_cfg, providers)` → "$X.XX/min".
Channel cards show it in gold. Free pipeline → "$0.00/min (all local, free)".
Log every paid call to job `costs.json` (never break a run on logging errors).

## 8. Testing (MUST be green before handoff)
- `python -m py_compile` clean on all files.
- `QT_QPA_PLATFORM=offscreen python -m mib.app --smoke` → opens wizard, walks
  steps 0→3 programmatically, exits 0 (no crash).
- `python -m mib.selftest` → FULL headless pipeline on title "The Dog Who Waited
  400 Days" with all-free providers (local script, edge-tts, local images):
  asserts `output/selftest/.../final.mp4` exists, ffprobe shows video+audio,
  duration ≥ 60s. Edge-tts needs internet — if unreachable, selftest falls back
  to silent-tone audio + still passes with a warning (pipeline must never die
  on provider failure).
- Builder runs all three, fixes failures, repeats until green.

## 9. Exe build
- `build-exe.spec` (PyInstaller, windowed, name `AvatarProductionByMIB`,
  collect PySide6, include `config/`, `assets/`).
- `.github/workflows/build-windows.yml`: windows-latest, Python 3.11,
  `pip install -r requirements.txt pyinstaller`, `pyinstaller build-exe.spec`,
  upload `dist/` as artifact `AvatarProductionByMIB-windows`.
- `requirements.txt`: PySide6, requests, pyyaml, Pillow, edge-tts, imageio-ffmpeg.
- `README.md`: install/run instructions for Windows.

## 10. Non-goals (do NOT build)
No timeline editor, no book funnel, no dashboard graphs, no Ollama/reasoning,
no HeyGen, no multi-account logic. Wizard + Settings + pipeline. Lean and working.
