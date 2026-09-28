"""mib/patterns.py — per-channel Pattern profiles.

A Pattern is the *content formula* of one channel: how its scripts are built,
how the hook sounds, which story beats it follows, what the avatar says when
it re-appears mid-video, and what the images look like. Every channel carries
its own pattern, so 10 channels on 10 different topics can each follow their
own competitor's formula without touching any code.

Pattern dict shape:
{
  "name": "Classic Story",
  "reference_url": "",        # competitor video this pattern was decoded from
  "reference_title": "",
  "hook_templates": [...],    # {topic} placeholder; one picked per video
  "beats": [{"name":..., "lines":[...], "scene":...}, ...],
  "rejoin_transitions": [...],# lines the avatar opens with on mid-video
                              # re-appearances (baked into that beat's narration)
  "cta_templates": [...],
  "image_style": "...",       # appended to every image prompt
  "style_notes": "",          # vocabulary / tone notes (for the writer)
  "soft_promo_line": "",      # optional one-liner spoken once mid-video
                              # (audio + captions only, never on-screen text),
                              # e.g. a soft affiliate/description-link mention
}
"""

HOOKS = [
    "What if everything you believed about {topic} was only half the story? "
    "Stay with me for the next few minutes, because what you are about to "
    "hear changed everything for one family.",
    "Nobody expected what happened next. Not the neighbors, not the experts, "
    "and certainly not the people living through it. This is the story of "
    "{topic}, and it starts with a single quiet moment.",
    "They say some moments choose you. This one began like any ordinary day, "
    "until {topic} turned it into something nobody will ever forget.",
    "If you have ever wondered whether {topic} could really change a life, "
    "this story will answer that question \u2014 and the answer surprised everyone.",
]

BEAT_DEFS = [
    ("problem",
     ["Life had settled into a quiet rhythm, and then {topic} arrived without warning.",
      "Nobody knew what to do first. The days felt heavier, and every small decision carried weight.",
      "Neighbors whispered, experts disagreed, and the family at the center of it all just tried to hold on.",
      "What looked simple from the outside was anything but. Every morning brought a new question with no easy answer."],
     "a quiet home interior at dawn, warm lamp light, empty chair by the window, cinematic photorealistic"),
    ("complication",
     ["Just when things seemed stable, a second problem surfaced, and it was bigger than the first.",
      "Doors that used to open easily began to close. Help was promised, then delayed, then questioned.",
      "The family learned a hard truth: waiting changes nothing. Only action moves the story forward.",
      "So they made a choice that nobody around them understood \u2014 and that choice set everything in motion."],
     "a person standing at a crossroads at dusk, dramatic sky, cinematic photorealistic"),
    ("setback",
     ["Then came the setback that nearly ended everything. One phone call, one letter, one moment of bad timing.",
      "Hope, which had been growing quietly, suddenly felt fragile. The nights grew longer and the doubts louder.",
      "Even the people who believed the most began to wonder if they had been wrong all along.",
      "But sometimes the darkest hour is simply the hour before the turn."],
     "rain on a window at night, blurred warm lights outside, melancholic cinematic photorealistic"),
    ("twist",
     ["And then, the twist nobody saw coming. A stranger, a letter, a coincidence too perfect to be coincidence.",
      "In a single afternoon, the whole picture changed. What seemed impossible in the morning felt inevitable by evening.",
      "The family would later say this was the moment they stopped surviving and started believing again.",
      "Because {topic} was never really about the problem. It was about what the problem revealed."],
     "sunlight breaking through storm clouds over a small town, hopeful cinematic photorealistic"),
    ("payoff",
     ["What happened next is the part people tell and retell. Step by step, the pieces fell into place.",
      "There were tears, there was laughter, and there was a quiet that felt like peace arriving at last.",
      "The neighbors who had whispered now stood in the yard, watching, smiling, some of them crying too.",
      "This is why the story matters: it proves that patience and heart still win."],
     "an emotional reunion in warm golden light, tears of joy, cinematic photorealistic"),
    ("landing",
     ["Looking back now, every hard day makes sense. Every delay had a reason. Every tear watered something good.",
      "The family keeps one photograph from that season on the mantel \u2014 not of the struggle, but of the morning after.",
      "Because the real lesson of {topic} is simple: hold on a little longer than feels reasonable.",
      "And if this story found you at the right moment, maybe that is no accident either."],
     "a framed photograph on a wooden mantel, morning light, peaceful cinematic photorealistic"),
]

CTAS = [
    "If this story moved you, subscribe and turn on notifications, so you never miss the next one. "
    "And tell me in the comments: what moment in your own life felt like this? I read every single one.",
    "Subscribe for more stories like this one, made for hearts that still believe. "
    "Comment below with the word HOPE if this story found you at the right time.",
]

DEFAULT_TRANSITIONS = [
    "But before we go on, there is something you need to hear.",
    "Now, here is the part most people miss entirely.",
    "Stay with me, because what happened next changed everything.",
    "And just when it seemed the story was over, it took a turn nobody expected.",
]

IMG_SUFFIX = ("Photorealistic, cinematic 16:9 composition, warm natural light, "
              "rich detail, no text, no watermark, no logo.")


def default_pattern():
    """The built-in 'Classic Story' pattern. Returns a fresh dict."""
    return {
        "name": "Classic Story",
        "reference_url": "",
        "reference_title": "",
        "hook_templates": list(HOOKS),
        "beats": [{"name": n, "lines": list(lines), "scene": scene}
                  for n, lines, scene in BEAT_DEFS],
        "rejoin_transitions": list(DEFAULT_TRANSITIONS),
        "cta_templates": list(CTAS),
        "image_style": IMG_SUFFIX,
        "style_notes": "",
        "soft_promo_line": "",
    }


def normalize_pattern(p):
    """Fill missing keys / bad values with defaults. Never raises."""
    try:
        base = default_pattern()
        if not isinstance(p, dict):
            return base
        out = dict(base)
        for k in ("name", "reference_url", "reference_title",
                  "image_style", "style_notes", "soft_promo_line"):
            v = p.get(k)
            if isinstance(v, str):
                out[k] = v
        for k in ("hook_templates", "rejoin_transitions", "cta_templates"):
            v = p.get(k)
            if isinstance(v, list):
                items = [str(x) for x in v if str(x).strip()]
                if items:
                    out[k] = items
        beats = p.get("beats")
        if isinstance(beats, list):
            clean = []
            for b in beats:
                if not isinstance(b, dict):
                    continue
                lines = [str(x) for x in (b.get("lines") or [])
                         if str(x).strip()]
                if not lines:
                    continue
                clean.append({
                    "name": str(b.get("name") or f"beat-{len(clean)+1}"),
                    "lines": lines,
                    "scene": str(b.get("scene") or ""),
                })
            if clean:
                out["beats"] = clean
        return out
    except Exception:  # noqa: BLE001
        return default_pattern()


def get_pattern(channel, channel_id=None):
    """Return the channel's pattern (normalized). Never raises.

    Priority: the channel's own saved pattern > a built-in preset for this
    channel id (decoded from a studied competitor) > the default pattern.
    """
    try:
        ch = channel or {}
        custom = ch.get("pattern")
        if isinstance(custom, dict) and custom.get("beats"):
            return normalize_pattern(custom)
        if channel_id and channel_id in BUILTIN_PATTERNS:
            return normalize_pattern(BUILTIN_PATTERNS[channel_id])
        return normalize_pattern(custom if isinstance(custom, dict) else None)
    except Exception:  # noqa: BLE001
        return default_pattern()


def builtin_pattern_name(channel_id):
    """Name of the built-in preset for a channel id, or ''."""
    try:
        return BUILTIN_PATTERNS.get(channel_id, {}).get("name", "")
    except Exception:  # noqa: BLE001
        return ""


def save_pattern(channel_id, pattern, cfg):
    """Save a pattern dict into cfg['channels'][channel_id]['pattern'].

    Normalises the pattern before saving.
    Updates cfg in-place; caller is responsible for calling save_config(cfg).
    Never raises.
    """
    try:
        pat = normalize_pattern(pattern) if pattern else {}
        channels = cfg.setdefault("channels", {})
        if channel_id not in channels:
            channels[channel_id] = {}
        channels[channel_id]["pattern"] = pat
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Built-in presets — patterns decoded from studied competitor videos.
# Only the *structure* is captured (hook shape, beat map, transitions);
# never the competitor's sentences.
# ---------------------------------------------------------------------------

ELIAS_GARDENER_PATTERN = {
    "name": "Elias Gardener (Amish How-To)",
    "reference_url": "https://www.youtube.com/watch?v=G6RiBDCGv5w",
    "reference_title": ("The Secret Liquid That Melts Leaves Into Compost "
                        "in Just Days!"),
    "hook_templates": [
        "Every autumn the same mountain of leaves, and every spring the same "
        "tired soil. But what if those leaves were never trash at all? Stay "
        "with me, because one bucket of simple liquid changed this whole "
        "garden \u2014 and {topic} can do the same for yours.",
        "The neighbors burn their leaves. The town hauls them away. But the "
        "old-timers knew something most folks forgot: {topic} turns that "
        "fall pile into the richest soil on the road, in just days.",
        "If your garden soil is hard as a brick and leaves pile up every "
        "fall, this is for you. There is a plain homemade liquid that melts "
        "leaves into black compost in days \u2014 and {topic} starts with "
        "what is already in your kitchen.",
    ],
    "beats": [
        {"name": "problem",
         "lines": [
             "Every fall the leaves come down by the bushel, and every spring "
             "the garden soil is just as tired as the year before.",
             "Folks rake and bag and burn, working hard and getting nowhere. "
             "The pile grows, the soil stays hungry.",
             "But {topic} begins with a different thought: what if the pile "
             "is not the problem at all?",
             "What if those leaves are the very food your soil has been "
             "waiting for?"],
         "scene": "a huge pile of autumn leaves in a plain Amish garden, "
                  "wooden fence, morning light, cinematic photorealistic"},
        {"name": "method",
         "lines": [
             "The secret is a simple liquid, and there is nothing fancy in "
             "it. Just nitrogen, water, and a little old-time patience.",
             "Leaves are all carbon \u2014 brown, dry, slow. What wakes them "
             "up is nitrogen, the green spark that starts the fire.",
             "The old-timers called it liquid fire, though there is no fire "
             "in it at all. Just kitchen scraps soaked, stirred, and poured.",
             "{topic} works because it feeds the tiny workers in the pile "
             "that do the real labor."],
         "scene": "a plain bucket of dark liquid beside a leaf pile, "
                  "weathered hands pouring, Amish garden, cinematic "
                  "photorealistic"},
        {"name": "process",
         "lines": [
             "First shred the leaves \u2014 a mower does it in minutes. Small "
             "pieces melt faster than whole ones, that is the whole trick.",
             "Then layer: leaves, a sprinkle of soil, a pour of the liquid. "
             "Again leaves, again liquid. Like making a good lasagna.",
             "Water it till it feels like a wrung-out sponge. Not soup, not "
             "dust. Just damp and alive.",
             "{topic} asks for one more thing: a turning with the fork every "
             "few days, to let the air in."],
         "scene": "layering shredded leaves in a compost bin, watering can, "
                  "garden fork, step-by-step, cinematic photorealistic"},
        {"name": "patience",
         "lines": [
             "Then you wait \u2014 but not the months the books tell you. "
             "With the liquid working, days do what seasons used to do.",
             "Put your hand in the middle of the pile. Feel that warmth? That "
             "is the pile cooking, the tiny workers eating and multiplying.",
             "If it cools, turn it and wet it again. If it smells, add dry "
             "leaves. The pile tells you what it needs.",
             "{topic} rewards the watcher. A minute a day is all it asks."],
         "scene": "steam rising from a compost pile at dawn, hand testing "
                  "warmth, quiet garden, cinematic photorealistic"},
        {"name": "proof",
         "lines": [
             "And then one morning you dig in and find it: black, crumbly, "
             "sweet-smelling compost where leaves used to be.",
             "No sticks, no mats, no half-rotted mess. Just dark gold that "
             "falls through your fingers.",
             "Spread it two fingers thick over the beds. Watch what the "
             "garden does with it.",
             "{topic} ends the way all good garden work ends \u2014 with "
             "soil so alive you can smell the life in it."],
         "scene": "hands holding dark crumbly finished compost, rich garden "
                  "beds behind, golden light, cinematic photorealistic"},
        {"name": "closing",
         "lines": [
             "That is the whole of it. Leaves in, liquid on, patience, and "
             "black gold out.",
             "No money spent, nothing hauled away, nothing burned. Just the "
             "old way, working like it always did.",
             "Try {topic} this season, and come back and tell me how your "
             "pile cooked.",
             "Until next time \u2014 keep your soil covered and your heart "
             "thankful."],
         "scene": "a thriving vegetable garden at sunset, neat rows, "
                  "peaceful, cinematic photorealistic"},
    ],
    "rejoin_transitions": [
        "Now here is the part most folks get wrong.",
        "But the old-timers knew a secret about this.",
        "Stay with me \u2014 this next step is the important one.",
        "And when you see what came out of that pile, you will understand.",
        "One more thing before you try this yourself.",
    ],
    "cta_templates": [
        "If this helped your garden, subscribe so you don't miss the next "
        "old-time method. And tell me below: what do you do with your fall "
        "leaves? I read every comment.",
        "More plain garden wisdom every week \u2014 subscribe and ring the "
        "bell. Comment the word SOIL if you are trying this liquid this "
        "season.",
    ],
    "image_style": ("Photorealistic, cinematic 16:9 composition, warm natural "
                    "light, plain Amish garden, no people close-ups, no "
                    "text, no watermark, no logo."),
    "soft_promo_line": ("By the way, I have left links to the seeds and "
                        "supplies I use in the description below, take a "
                        "look if you like."),
    "style_notes": ("Plain old-fashioned words for seniors. Short sentences. "
                    "Practical how-to, zero hype. The presenter is a humble "
                    "Amish gardener. Typical rhythm: intro + 3 to 4 mid-video "
                    "rejoins with fresh lines; never repeat a sentence."),
}

BUILTIN_PATTERNS = {
    "kustorez-amish": ELIAS_GARDENER_PATTERN,
}


def fetch_video_info(url):
    """Best-effort YouTube oEmbed lookup: {title, author, description} or {}.
    Never raises.
    """
    try:
        import json
        import urllib.parse
        import urllib.request
        u = (url or "").strip()
        if "youtube.com" not in u and "youtu.be" not in u:
            return {}
        api = ("https://www.youtube.com/oembed?url="
               + urllib.parse.quote(u, safe="") + "&format=json")
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        result = {"title":  str(data.get("title", "")),
                  "author": str(data.get("author_name", ""))}
        # Try to get the video description via scraping the watch page
        try:
            watch_url = u if "watch" in u else (
                "https://www.youtube.com/watch?v=" +
                u.split("youtu.be/")[-1].split("?")[0])
            req2 = urllib.request.Request(
                watch_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=15) as r2:
                html = r2.read().decode("utf-8", "replace")
            # Extract description from structured data
            import re as _re
            m = _re.search(r'"shortDescription":"(.*?)"(?:,"isCrawlable")',
                           html, _re.DOTALL)
            if m:
                desc = m.group(1).replace("\\n", "\n").replace('\\"', '"')[:800]
                result["description"] = desc
        except Exception:  # noqa: BLE001
            pass
        return result
    except Exception:  # noqa: BLE001
        return {}


def fetch_competitor_pattern(url, api_key, model="gemini-2.0-flash",
                              base_url="", logger=None):
    """Decode a competitor YouTube video into a pattern dict using Gemini AI.

    Fetches video title + description, then asks the LLM to decode:
      - Hook style (question/shock/story/stat hook)
      - Story beats with names and template lines
      - Avatar re-entry transitions
      - CTA templates
      - Image style
      - Style notes (vocabulary, tone)

    Returns a partial pattern dict (same shape as default_pattern()).
    Never raises -- returns {} on any failure.
    """
    try:
        if logger:
            logger(f"Competitor analysis: fetching {url}...")

        info = fetch_video_info(url)
        if not info.get("title"):
            return {"error": "Could not fetch video info. Check the URL."}

        title  = info.get("title", "")
        author = info.get("author", "")
        desc   = info.get("description", "")[:600]

        if logger:
            logger(f'Competitor: "{title}" by {author}')

        prompt = f"""You are a YouTube content strategist analyzing a competitor video.

Video Title: {title}
Channel: {author}
Description snippet:
{desc}

Decode this video's content pattern. Return ONLY valid JSON with exactly these keys:

{{
  "name": "<short pattern name>",
  "hook_templates": ["<hook template 1 using {{topic}}>", "<hook template 2>"],
  "beats": [
    {{"name": "<beat name>", "lines": ["<template line using {{topic}}>"],
      "scene": "<image scene description>", "rejoin": false}},
    ...3-6 beats total...
  ],
  "rejoin_transitions": ["<avatar re-entry line 1>", "<line 2>", "<line 3>"],
  "cta_templates": ["<CTA template 1>", "<CTA template 2>"],
  "image_style": "<visual style for AI image generation>",
  "style_notes": "<writing tone, vocabulary, emotional style>",
  "reference_url": "{url}",
  "reference_title": "{title}"
}}

Rules:
- hook_templates: use the hook style from this video (question/shock/story/reveal)
- beats: infer the script arc from title+description (intro, problem, solution, proof, CTA)
- Use {{topic}} as placeholder for the video topic
- Keep everything concise and reusable
- Return ONLY the JSON, no markdown, no explanation"""

        try:
            import json as _json
            import urllib.request as _req2
            import urllib.parse as _up2

            if not api_key:
                return {"error": "No API key provided for competitor analysis."}

            api_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}")
            body = _json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500}
            }).encode("utf-8")
            req = _req2.Request(
                api_url, data=body,
                headers={"Content-Type": "application/json"})
            with _req2.urlopen(req, timeout=45) as r:
                resp = _json.loads(r.read().decode("utf-8", "replace"))

            text = (resp.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", ""))

            # Strip markdown fences if present
            import re as _re2
            text = _re2.sub(r"^```(?:json)?\s*", "", text.strip())
            text = _re2.sub(r"\s*```$", "", text.strip())

            pat = _json.loads(text)
            pat = normalize_pattern(pat)
            if logger:
                logger(f'Competitor pattern decoded: "{pat.get("name", "")}" '
                       f'({len(pat.get("beats", []))} beats)')
            return pat

        except Exception as e:  # noqa: BLE001
            if logger:
                logger(f"Competitor AI decode failed: {e}")
            # Return basic info even if AI decode fails
            return {
                "name": f"Pattern from: {title[:40]}",
                "reference_url": url,
                "reference_title": title,
                "error": str(e)[:200],
            }

    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"fetch_competitor_pattern error: {e}")
        return {}


def describe(pattern):
    """One-paragraph summary of a pattern for an LLM prompt. Never raises."""
    try:
        p = normalize_pattern(pattern) if pattern else default_pattern()
        beats = " → ".join(b.get("name", "") for b in p.get("beats", []))[:200]
        hooks = "; ".join(p.get("hook_templates", [])[:2])[:200]
        notes = str(p.get("style_notes", ""))[:200]
        img = str(p.get("image_style", ""))[:160]
        parts = [f"Pattern '{p.get('name', '')}'"]
        if beats:
            parts.append(f"beat arc: {beats}")
        if hooks:
            parts.append(f"hook style: {hooks}")
        if notes:
            parts.append(f"style notes: {notes}")
        if img:
            parts.append(f"image style: {img}")
        return ". ".join(parts) + "."
    except Exception:  # noqa: BLE001
        return ""
