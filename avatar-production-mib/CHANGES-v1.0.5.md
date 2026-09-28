# v1.0.5 changes (built 2026-09-28)

## 1. Voiceover tab rebuilt — FREE + PAID sections clearly separated

The Voiceover tab is now split into two clearly labelled sections:

### FREE Voice Options (no subscription)
- **Option 1: Gemini TTS** — Human-quality, 1,500 req/day free.
  - Dedicated key field (paste the same Gemini API key as images).
  - "Test" button synthesizes a short phrase live and shows file size.
  - Lists all 7 voices: Puck (energetic), Charon (authoritative), Kore (warm),
    Fenrir (dramatic), Aoede (friendly), Orbit (neutral), Zephyr (gentle).
- **Option 2: Edge TTS** — Robotic fallback, no key, auto-used when Gemini fails.

### PAID Voice Options (API key required)
- **AI33 Pro** — ElevenLabs, MiniMax, Kokoro, Fish Audio, Voice Clone.
  - All models accessible with a single ai33.pro API key.
  - Same Test + Browse buttons as before.

## 2. Avatar Clip Mode — 3 options per channel (backend-locked)

Channels tab now has an "Avatar Clip Mode" selector locked per channel:

- **Option 1 (static):** Static PNG + Ken Burns zoom (free, current default).
- **Option 2 (card):** Character Lock Card — visual ID sheet overlay on intro clip.
  Upload character sheet in "Character sheet..." to activate.
- **Option 3 (video):** AI Video Clips — 5-15s natural talking avatar via Gemini Veo.
  Requires Gemini API key. Clip duration controlled by spinner (5-15s).

The mode and clip duration are saved to the channel config (avatar_clip_mode,
avatar_clip_secs) and locked — new channel, new mode selection.

Voice provider dropdown now includes "gemini-tts" as first/default option.
Status message after save shows full lock state:
  "Saved -- Channel Name locked: voice=gemini-tts, avatar=Static PNG, 8s clips."

## 3. Google Drive connector — auto-upload after each video

New "Google Drive" tab in Settings:
- Connect with OAuth2 (browser window opens, one-time setup).
- Choose credentials file (client_secret_*.json from Google Cloud Console).
- Storage usage display (email, GB used/total, %).
- "Auto-upload each finished video" checkbox saved to config.
- Disconnect button to remove the saved token.

After connecting, every finished video auto-uploads to:
  Channel Name / YYYY-MM-DD / title-slug /
    video.mp4   title.txt   description.txt   tags.txt
    thumbnail-prompt.txt   metadata.docx (combined Word file)

New module: mib/gdrive.py — OAuth2, folder creation, file upload, Word doc build.
Never crashes the pipeline — Drive upload errors are logged and skipped.

Install (if not already): pip install google-auth google-auth-oauthlib
  google-api-python-client python-docx

## 4. Video-ready notification (Windows)

When a video finishes (success or failure), a Windows desktop toast notification
is sent using plyer (pip install plyer). Shows title, status, and Drive folder URL.
Falls back silently if plyer is not installed — pipeline never crashes.

## Files changed
- mib/ui/settings.py  (voice tab rebuilt, channels tab + avatar clip mode,
  gdrive tab + methods added, save() updated for Gemini TTS key)
- mib/pipeline.py     (stage 8: Google Drive upload, stage 9: notification,
  _notify_done() helper added)
- mib/gdrive.py       (NEW — Google Drive connector module)

