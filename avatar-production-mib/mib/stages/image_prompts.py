"""mib/stages/image_prompts.py — Bulk Scene Image Prompt Generator.

WORKFLOW:
  Script (beats) + Character Sheet + Master Prompt
        ↓
  Gemini generates a BATCH of rich, visually-specific image prompts
        ↓
  One prompt per sub-scene (45-second chunks)
        ↓
  Used by images.py when calling Grok / Gemini image generation

This replaces the basic "{beat.image_prompt} Scene: {excerpt}" system
with high-quality, cinematically described prompts that are:
  • Visually specific (lighting, angle, composition)
  • Character-consistent (identity lock injected from master prompt)
  • Scene-context-aware (narration excerpt included)
  • Negative-prompt-aware (avoids specified artifacts)

Usage:
    from mib.stages.image_prompts import generate_bulk_prompts
    prompts = generate_bulk_prompts(script, channel_cfg, secrets, logger)
    # Returns: list of {"scene_id", "prompt", "negative", "beat_name"} dicts
"""
import json
from typing import Any


_WPS = 140 / 60.0          # words per second at 140 wpm
_IMAGE_EVERY_SECS = 45     # one image every 45 seconds
_WORDS_PER_SUB = max(60, int(_WPS * _IMAGE_EVERY_SECS))  # ~105 words


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT for Gemini
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM = """You are an expert cinematic image prompt writer for AI image generation.

Your job:
Given a video script split into scenes, generate ONE high-quality image generation
prompt for EACH scene. Each prompt must be:

1. VISUALLY SPECIFIC — describe lighting, camera angle, composition, mood, time of day
2. CHARACTER CONSISTENT — inject the master character description EXACTLY as provided
3. SCENE-CONTEXT AWARE — match the visual content to the narration text
4. CINEMATIC — use terms like: golden hour, shallow depth of field, rule of thirds,
   warm bokeh, 24mm lens, film grain, natural light, etc.
5. APPROPRIATE LENGTH — 60-100 words per prompt. Not too short, not too long.

Output FORMAT (strictly follow this JSON):
{
  "prompts": [
    {
      "scene_id": "hook-sub00",
      "beat_name": "hook",
      "prompt": "FULL IMAGE GENERATION PROMPT HERE",
      "negative": "optional extra negatives for this specific scene"
    },
    ...
  ]
}

RULES:
- Output ONLY valid JSON, no markdown, no extra text
- Include ALL scenes in the input, in order
- Keep character description EXACTLY from master_prompt
- For avatar/presenter scenes: include the character prominently
- For landscape/B-roll scenes: character can be absent or small
- Match aspect ratio hint if provided (16:9, 1:1, or 9:16)
"""


def _build_user_message(script: dict, channel_cfg: dict) -> str:
    """Build the user message for Gemini with all scene data."""
    char = channel_cfg.get("character") or {}
    prompts_cfg = channel_cfg.get("prompts") or {}
    master_prompt = prompts_cfg.get("master", "")
    short_prompt = prompts_cfg.get("short", "")
    negative = prompts_cfg.get("negative", "")
    title = script.get("title", "Untitled")
    channel_name = channel_cfg.get("name", "")
    niche = channel_cfg.get("niche", "")
    aspect = script.get("_aspect_ratio", "16:9")

    # Build character identity description from character sheet
    char_desc = ""
    if char.get("name"):
        parts = [
            f"Character: {char['name']}",
            f"Age: {char.get('age_desc', '')}",
            f"Gender: {char.get('gender', '')}",
            f"Ethnicity: {char.get('ethnicity', '')}",
            f"Build: {char.get('build', '')}",
            f"Occupation: {char.get('occupation', '')}",
            f"Outfit: {char.get('outfit', '')}",
            f"Traits: {char.get('traits', '')}",
            f"Background setting: {char.get('background', '')}",
        ]
        char_desc = " | ".join(p for p in parts if p.split(": ")[1])

    # Collect all sub-scenes
    scenes = []
    raw_items = [("hook", script.get("hook", ""), "Opening scene")]
    for i, b in enumerate(script.get("beats", [])):
        raw_items.append((
            b.get("name", f"beat-{i}"),
            b.get("narration", ""),
            b.get("image_prompt", ""),
        ))
    raw_items.append(("cta", script.get("cta", ""), "Warm closing call to action"))

    global_idx = 0
    for beat_name, narration, base_prompt in raw_items:
        words = (narration or "").split()
        if not words:
            scenes.append({
                "scene_id": f"{beat_name}-sub00",
                "beat_name": beat_name,
                "narration_excerpt": base_prompt[:200],
                "base_hint": base_prompt[:200],
            })
            global_idx += 1
            continue
        for i in range(0, len(words), _WORDS_PER_SUB):
            chunk = " ".join(words[i:i + _WORDS_PER_SUB])
            excerpt = " ".join(words[i:i + 30])  # first 30 words for context
            sub_n = i // _WORDS_PER_SUB
            scenes.append({
                "scene_id": f"{beat_name}-sub{sub_n:02d}",
                "beat_name": beat_name,
                "narration_excerpt": excerpt,
                "base_hint": base_prompt[:150] if base_prompt else "",
            })
            global_idx += 1

    msg = f"""VIDEO TITLE: {title}
CHANNEL: {channel_name} — {niche}
ASPECT RATIO: {aspect}

MASTER CHARACTER PROMPT (inject in character scenes):
{master_prompt or char_desc or "No specific character — use relevant B-roll imagery"}

GLOBAL NEGATIVE PROMPT (avoid in all scenes):
{negative or "cartoon, anime, plastic skin, neon colors, logo, watermark"}

SCENES TO GENERATE PROMPTS FOR ({len(scenes)} total):
{json.dumps(scenes, indent=2)}

Generate ONE rich image prompt for EACH scene above.
Remember: maintain character consistency across all scenes where the character appears.
"""
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def generate_bulk_prompts(
    script: dict,
    channel_cfg: dict,
    secrets: dict,
    logger=None,
    fallback_on_error: bool = True,
) -> list[dict[str, Any]]:
    """Generate bulk image prompts for all scenes using Gemini.

    Args:
        script:       The script dict (hook, beats, cta).
        channel_cfg:  Channel config dict (character, prompts, name, niche).
        secrets:      Secrets dict (gemini_api_key etc.).
        logger:       Optional logger with .log() method.
        fallback_on_error: If True, return simple prompts if Gemini fails.

    Returns:
        List of dicts: [{"scene_id", "beat_name", "prompt", "negative"}, ...]
        In the same order as scenes in the script.
    """
    def _log(msg):
        if logger:
            try:
                logger.log(msg)
            except Exception:
                pass

    try:
        api_key = (secrets.get("gemini_api_key") or "").strip()
        if not api_key:
            raise ValueError("No Gemini API key — cannot generate bulk prompts")

        user_msg = _build_user_message(script, channel_cfg)
        _log(f"    image prompts: generating bulk prompts via Gemini…")

        from google import genai as _genai
        _client = _genai.Client(api_key=api_key)

        response = _client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_msg,
            config=_genai.types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
                system_instruction=_SYSTEM,
            ),
        )
        raw = response.text.strip()

        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        prompts = parsed.get("prompts") or []

        _log(f"    image prompts: {len(prompts)} prompts generated ✓")
        return prompts

    except Exception as e:
        _log(f"    image prompts: Gemini failed ({e}) — using fallback prompts")
        if fallback_on_error:
            return _fallback_prompts(script, channel_cfg)
        return []


def _fallback_prompts(script: dict, channel_cfg: dict) -> list[dict]:
    """Simple fallback: use existing beat image_prompts + master prompt prefix."""
    prompts_cfg = channel_cfg.get("prompts") or {}
    master = prompts_cfg.get("master", "")
    negative = prompts_cfg.get("negative", "cartoon, anime, plastic skin")
    title = script.get("title", "")

    results = []
    raw_items = [("hook", script.get("hook", ""), "Opening cinematic scene")]
    for i, b in enumerate(script.get("beats", [])):
        raw_items.append((
            b.get("name", f"beat-{i}"),
            b.get("narration", ""),
            b.get("image_prompt", f"Scene about {title}"),
        ))
    raw_items.append(("cta", script.get("cta", ""), "Warm closing hopeful scene"))

    global_idx = 0
    for beat_name, narration, base_prompt in raw_items:
        words = (narration or "").split()
        if not words:
            prompt = f"{master} {base_prompt}".strip() if master else base_prompt
            results.append({
                "scene_id": f"{beat_name}-sub00",
                "beat_name": beat_name,
                "prompt": prompt,
                "negative": negative,
            })
            global_idx += 1
            continue
        for i in range(0, len(words), _WORDS_PER_SUB):
            excerpt = " ".join(words[i:i + 25])
            sub_n = i // _WORDS_PER_SUB
            base = base_prompt or f"Scene from: {title}"
            prompt = f"{base} {excerpt}".strip()
            if master and sub_n == 0:
                prompt = f"{master} {prompt}".strip()
            results.append({
                "scene_id": f"{beat_name}-sub{sub_n:02d}",
                "beat_name": beat_name,
                "prompt": prompt[:400],
                "negative": negative,
            })
            global_idx += 1

    return results


# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW / DEBUG TOOL (run standalone)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    """Quick test: python -m mib.stages.image_prompts"""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2]))
    from mib.config import load_config, load_secrets

    cfg = load_config()
    sec = load_secrets()

    # Use first channel with a master prompt set
    ch_id = None
    ch_cfg = {}
    for cid, ch in (cfg.get("channels") or {}).items():
        if (ch.get("prompts") or {}).get("master"):
            ch_id = cid
            ch_cfg = ch
            break

    if not ch_id:
        print("No channel with master prompt found. Set it in Channel Setup -> AI Prompt.")
        sys.exit(1)

    print(f"Testing bulk prompts for channel: {ch_id} - {ch_cfg.get('name')}")
    print(f"Master prompt: {(ch_cfg.get('prompts') or {}).get('master','')[:100]}...")

    # Minimal test script
    test_script = {
        "title": "What I Always Put in My Garlic Beds: The Secret to Huge Bulbs",
        "hook": "Most people waste years planting garlic wrong. Today I share the single most important thing I add to my garlic beds every single autumn — and it costs almost nothing.",
        "beats": [
            {"name": "beat-1", "narration": "The secret starts with the soil. Before anything else, I work in a thick layer of aged compost — not fresh, not bagged, but properly composted material that has broken down for at least six months. This feeds the garlic slowly all winter long.", "image_prompt": "Close-up of rich dark compost being worked into garden soil with weathered hands"},
            {"name": "beat-2", "narration": "Next comes bone meal. A light dusting across the bed, raked gently into the top two inches. Garlic is a heavy feeder of phosphorus and calcium — bone meal delivers both slowly over months.", "image_prompt": "Overhead shot of gardener sprinkling white bone meal powder over dark soil bed"},
        ],
        "cta": "Try this in your garden this autumn and watch what happens next spring. Subscribe for more old-fashioned growing wisdom that actually works.",
    }

    class _Log:
        def log(self, m): print(m)

    prompts = generate_bulk_prompts(test_script, ch_cfg, sec, _Log())
    print(f"\n{'='*60}")
    print(f"Generated {len(prompts)} prompts:")
    print('='*60)
    for p in prompts:
        print(f"\n[{p['scene_id']}] {p['beat_name']}")
        print(f"  PROMPT: {p['prompt'][:200]}...")
        if p.get('negative'):
            print(f"  NEG:    {p['negative'][:80]}")
