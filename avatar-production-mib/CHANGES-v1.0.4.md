# v1.0.4 changes (built 2026-09-24)

## 1. Avatar upload from PC — ADDED (Presenter step)
The "Presenter preview" dialog now has an "Upload avatar from PC…" button.
Pick any image (png/jpg/webp/bmp) — it is saved as the presenter's avatar
(assets/avatars/<id>.png) and used in every video that presenter opens.
Preview + picker cards refresh immediately. Works in the frozen exe too
(writes to %APPDATA%/AvatarProductionByMIB).

## 2. Appearances made clear + better control (Presenter step)
"Intro only / 2× / 4× / 6×" was confusing. Now:
- Buttons read "Intro only", "Intro + 1", "Intro + 2", "Intro + 3",
  "Intro + 5" (added 3-appearance option).
- A plain-language line under the buttons explains exactly what happens,
  with real timestamps from the channel's video length, e.g.:
  "The avatar opens the video and comes back 3 more times, spread evenly
  through the video — about at 0:00, 7:30, 15:00, 22:30 of a 30-min video.
  Each time it speaks the script at that point, so viewers stay connected."
- Cost line now reads per-appearance ("6s per appearance × 4").

No pipeline change needed: the renderer already spaces rejoins evenly and
each rejoin speaks the voiceover slice at that point.

## Files changed
- mib/ui/wizard.py (PresenterPage: upload_avatar, clearer appearance
  buttons, update_appear_info, per-appearance cost line)
- mib/stages/assemble.py (avatar-spoken slices are cut OUT of the beat
  audio — each appearance speaks new, continuing script; nothing repeats)

## 3. No repeated script at avatar appearances — FIXED (the key change)
Bug found: the avatar's rejoin clips contained voiceover slices that ALSO
stayed in the main timeline — viewers heard the same words twice (once
from the avatar, once over the images). Same for the intro (first seconds
heard twice).
Fix: assemble.py now subtracts every avatar-spoken interval (intro +
rejoins, in voiceover time) from the beat audio before rendering. The
story continues THROUGH each appearance — every avatar entry speaks fresh,
continuing lines, exactly like the reference pattern (Elias Gardener
video: avatar returns several times, script changes every time).
Verified by integration test with distinct audio tones: final duration ==
voiceover duration (nothing duplicated), and frequency probes at 6
timestamps confirm each slice is heard exactly once, in order.

## 4. Per-channel Pattern profiles — ADDED (the 10-channel answer)

One fixed script formula for all channels was wrong. Now every channel
carries its OWN content formula — a "Pattern": hook style, story beats,
avatar re-entry lines, CTA, image style. Ten channels, ten different
topics, ten different patterns, zero code changes.

- New module `mib/patterns.py`: pattern data model + built-in
  "Classic Story" default + `normalize_pattern()` (bad input can never
  crash the writer) + free YouTube title lookup for the reference field.
- Script engine (`mib/stages/script.py`) now writes from the channel's
  pattern: beat count/map, hook templates, CTA templates, image style
  all come from the pattern. Rejoin count (appearances - 1) is passed in
  from the pipeline, and each mid-video rejoin opens with a transition
  line baked into that beat's narration (evenly spaced beats, never
  beat 0) — so the avatar returns with a fresh, pattern-correct line.
- New "Pattern" tab in Settings: per-channel editor — pattern name,
  competitor reference video URL (one-click title fetch), hook templates,
  visual beat editor (add/update/remove beats with lines + scene),
  re-entry lines, CTA templates, image style, style notes, Save/Reset.
- Nothing breaks: channels without a custom pattern get the exact old
  "Classic Story" formula (6 beats, same output as before) — except
  `kustorez-amish`, which now ships a trained built-in preset
  **"Elias Gardener (Amish How-To)"** decoded from the studied 22-min
  reference video: hook shape, 6-beat map
  (problem → method → process → patience → proof → closing), 5 rejoin
  transitions, CTA templates, image style. Structure only — never the
  competitor's sentences. A channel's own saved pattern always wins.

Tested: 5 functional checks (default regression, custom 4-beat pattern
with transitions at beats 1+3, channel-carried pattern, garbage-input
fallback, defaults) + 5 offscreen UI checks (tab present, beat add, save
to channel, persistence across reopen, reset) + full selftest green
(real 114s mp4, QC passed, $0.00).

## API key rotation pools (auto-failover on limit hit)

- New `mib/keypool.py`: `KeyPool` tries keys in order; on a 429/quota
  (`KeyExhausted`) the key cools down 1h and the next key is used
  instantly; on a 401/403 (`KeyRejected`) the key is parked 24h.
  Cooldown state is metadata-only on disk (last4 + timers + counters —
  raw keys never touch the disk).
- Paste as many keys as you like (one per line) in the new Settings
  → "API Keys" tab: Gemini (image), AI33 Pro (voice + script LLM),
  Grok (image). Per-service Save + Test buttons and a masked stats
  line (key last4 + ready/cooling + used/failed counts).
- Wired everywhere: Gemini + Grok image generation, AI33 Pro voiceover,
  and the script LLM all rotate automatically. Old single-key fields
  keep working (they seed the pool as its only key).
- Tested: 6 pool unit checks (failover, cooldown skip, 24h reject park,
  all-exhausted summary error, metadata-only state file) + 3 wiring
  checks (image + voiceover + script LLM rotation) + 4 offscreen UI
  checks (tab, editors, masked stats, per-service save). Full
  `run_selftest.py` green (real 114s mp4, QC passed, $0.00).

## Generate presenter avatar with Gemini (on demand)

- Presenter preview dialog now has "Generate avatar with Gemini…"
  next to "Upload avatar from PC…": type a short description
  (e.g. "elderly Amish man with a long grey beard") and the app
  generates a photorealistic head-and-shoulders portrait through your
  Gemini key pool, saves it as that presenter's locked avatar, and
  the normal pipeline pairs it with the channel's locked voice —
  fully automatic from there.
- Core is unit-testable: `avatar_prompt()` + `generate_avatar_image()`
  in `mib/providers/genimages.py` (pool rotation, RGB PNG normalize,
  clean error when no keys). Generation runs in a background thread
  so the UI stays responsive; without keys you get a plain message
  pointing at Settings → API Keys.
- Tested: prompt builder, pool rotation on fake 429 (K1→K2), PNG
  normalize, no-pool error, offscreen UI (no-key warning + dialog
  button click wired to generate_avatar).

## Key pools: unlimited keys, live status board, per-key reports, backend alerts

- No key limit: paste as many keys per service as you want, one per
  line. The pool tries them in order with instant failover.
- Live status board in Settings → API Keys: one row per key with a
  color dot — green = live, amber = cooling after a limit hit
  (with minutes left), red = parked 24h after rejection — plus per-key
  counters: total uses, Images / Voice / Script / Avatar breakdown,
  last-used time. Header shows "N keys · X live · Y cooling · Z parked".
- "Usage report" button per service: a copyable report naming each key
  (last-4 only), what it did (images/voice/script/avatar counts),
  total uses, failures, last-used time, and the last event with
  timestamp ("limit hit 24-Sep 14:32", "rejected …", "back live …").
- Backend messages: every failover now writes a prominent log line
  ("⚠ BACKEND [gemini-image]: key …1234 hit its limit/quota — resting
  1h, switching to next key", "⛔ … REJECTED … parked 24h",
  "✓ … now live on key …5678") AND flashes the same message in the
  app's status bar for 10 seconds, so a dying key is impossible to miss
  mid-run.
- The script LLM now shares the ai33-voice pool state file, so the
  AI33 report covers voiceover + script work together.
- State files stay metadata-only (last-4, timers, counters) and two
  pools sharing a service merge counters instead of clobbering them.
- Tested: 8 pool unit checks (25-key unlimited, op tracking, events,
  backend log lines, reject→park, all-down, merge-save, revived) +
  5 offscreen UI checks (dots, per-op columns, summary line, report
  dialog content, save flow) + full selftest (real 114s mp4, QC passed,
  $0.00).

## Script pipeline: Gemini writes, Claude reviews, character stays consistent

- Script provider "gemini" (Settings → Script): Gemini writes the
  competitor-level script from your title — original writing, never
  copied — following the channel's Pattern (beat arc, hook style,
  image style are fed into the prompt). Uses the same Gemini key pool
  as images (usage shows as "Script" in the key report). Falls back to
  the free local rules engine on any failure.
- Claude review (Settings → Script → "Claude proofreads every script"):
  after the script is written, Claude acts as a strict editor —
  grammar, repeated words/ideas, timeline contradictions, over-long
  spoken sentences, weak hook — and returns mistake list + corrected
  script; fixes are auto-applied before voiceover. Every issue is
  logged ("claude review: 3 issue(s) found …"). Base URL + model are
  configurable (works with a custom Antigravity endpoint); keys rotate
  through the "claude-review" pool with the same live dots + usage
  report as other services. Any Claude failure keeps the original
  script — the pipeline never crashes.
- Character sheet (Settings → Channels → "Character sheet…",
  one-time per channel): upload a full character sheet image OR 4–5
  full-body reference photos + the character's complete details
  (name, age, hair, outfit, key traits…). You also set in how many
  scenes per video (0–4) the character appears. Those scenes are
  generated with the sheet as visual reference input (Gemini) and an
  identity-lock prompt block (face / hair / body / outfit locked —
  only pose, camera, lighting, environment follow the scene), so the
  same person appears fully visible and identical across the whole
  30-minute video.
- Tested: 14 unit checks (character save/load, identity block,
  cameo spread, Gemini prompt/parse/generate, Claude review/fix/
  malformed-fix/429-rotation, Gemini ref-image parts, claude pool)
  + 6 offscreen UI checks + full selftest.
