# v1.0.3 changes (built 2026-09-24)

## 1. AI33 Pro key no longer disappears after Save — FIXED
Root cause: the main window loaded secrets once at startup; the Settings
dialog saved to disk but the window kept serving its stale in-memory copy,
so reopening Settings showed an empty field (and queued jobs used the old
keys until restart).
Fix: SettingsDialog.save() writes the fresh secrets back into the caller's
dict AND WizardWindow.open_settings() reloads config+secrets from disk
after the dialog closes. Verified by offscreen functional test.

## 2. Local image upload from PC — ADDED (Settings → Images)
New section "Your own images (upload from PC)": per-channel enable checkbox
+ "Choose folder…" picker. When enabled for the channel, the pipeline uses
the user's own images for scenes (alphabetical order, cycled when scenes
outnumber images), each fitted to 1920x1080. Order is now:
PC images → Grok → Gemini → free local. Empty/missing folder falls back
to AI automatically. Verified end-to-end offscreen (5 scenes from 2 images,
correct cycling, correct size).

## Files changed
- mib/ui/settings.py (secrets write-back; PC-images UI + save)
- mib/ui/wizard.py (reload config+secrets after Settings closes)
- mib/providers/genimages.py (local_pool helper)
- mib/stages/images.py (channel_id param; PC pool first)
- mib/pipeline.py (pass channel_id to images stage)
- run_app.py entry shim unchanged (v1.0.2 fix retained)
