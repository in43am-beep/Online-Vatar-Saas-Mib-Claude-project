"""mib/competitor.py -- Competitor channel scraper + AI pattern decoder.

Workflow for each competitor channel:
  1. Fetch channel page -> extract recent video URLs + titles
  2. Pick top 6-9 "outlier" videos by view count (highest engagement)
  3. For each video: fetch_video_info() -> Gemini AI -> pattern dict
  4. Merge patterns into a channel-level master pattern
  5. Save to config/competitor_patterns.json

Entry points:
  scrape_channel(handle, url, api_key, ...)  -> channel_result dict
  run_full_scrape(api_key, progress_cb, ...)  -> summary dict
  load_patterns()                             -> all saved patterns
  best_pattern_for(topic_hint)               -> closest pattern dict

Never raises. All network errors logged and skipped.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

# ── paths ────────────────────────────────────────────────────────────────────
try:
    from .config import CONFIG_PATH
    _DATA_FILE = CONFIG_PATH.parent / "competitor_patterns.json"
except Exception:  # noqa: BLE001
    _DATA_FILE = Path(__file__).parent.parent / "config" / "competitor_patterns.json"

_COMPETITORS_FILE = _DATA_FILE.parent / "competitors.json"

# ── constants ─────────────────────────────────────────────────────────────────
VIDEOS_PER_CHANNEL = 7          # outlier videos to decode per channel
MIN_VIDEOS = 3                  # minimum acceptable
REQUEST_DELAY = 1.2             # seconds between HTTP requests (be polite)
GEMINI_MODEL  = "gemini-2.0-flash"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(url, timeout=20):
    """HTTP GET -> text. Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _oembed(video_url):
    """YouTube oEmbed -> {title, author, thumbnail_url} or {}."""
    try:
        api = ("https://www.youtube.com/oembed?url="
               + urllib.parse.quote(video_url, safe="") + "&format=json")
        data = json.loads(_get(api, timeout=15))
        return {"title":   str(data.get("title", "")),
                "author":  str(data.get("author_name", "")),
                "thumb":   str(data.get("thumbnail_url", ""))}
    except Exception:  # noqa: BLE001
        return {}


def _channel_videos_ytdlp(channel_url, max_videos=12, logger=None):
    """Fetch channel top videos using yt-dlp.

    Uses the channel's 'popular' sort tab to get highest-view videos first.
    Falls back to /videos tab. Returns list of dicts, never raises.
    """
    try:
        import yt_dlp

        base = channel_url.rstrip("/").rstrip("/videos")

        # Try popular sort first (gives real view counts sorted by popularity)
        urls_to_try = [
            base + "/videos?view=0&sort=p",   # sorted by popularity (most viewed)
            base + "/featured",
            base + "/videos",
        ]

        ydl_opts = {
            "quiet":        True,
            "no_warnings":  True,
            "extract_flat": "in_playlist",
            "playlistend":  max_videos + 5,
            "ignoreerrors": True,
            "skip_download": True,
        }

        entries = []
        for url_try in urls_to_try:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url_try, download=False)
                if info and info.get("entries"):
                    entries = info["entries"]
                    break
            except Exception:  # noqa: BLE001
                continue

        if not entries:
            return []

        videos = []
        for e in entries:
            if not e:
                continue
            vid_id = e.get("id", "")
            title  = e.get("title", "")
            views  = int(e.get("view_count") or 0)
            dur    = int(e.get("duration") or 0)
            # Skip Shorts (< 61s) and very long (> 90 min)
            if dur and (dur < 61 or dur > 5400):
                continue
            if not vid_id or not title:
                continue
            if title in ("[Deleted video]", "[Private video]"):
                continue
            videos.append({
                "video_id": vid_id,
                "url":      f"https://www.youtube.com/watch?v={vid_id}",
                "title":    title,
                "views":    views,
                "duration": dur,
            })

        # Sort by views if we got them, else keep playlist order
        if any(v["views"] > 0 for v in videos):
            videos.sort(key=lambda v: v.get("views", 0), reverse=True)

        return videos[:max_videos]

    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"    yt-dlp error: {e}")
        return []


def _channel_videos(channel_url, max_videos=12, logger=None):
    """Scrape a YouTube channel page -> list of {url, title, views} dicts.

    Tries yt-dlp first (most reliable), falls back to HTML scraping.
    Returns [] on failure. Never raises.
    """
    # Try yt-dlp first
    try:
        import yt_dlp as _  # noqa: F401
        vids = _channel_videos_ytdlp(channel_url, max_videos, logger)
        if vids:
            return vids
    except ImportError:
        pass

    # Fallback: HTML scraping
    try:
        base = channel_url.rstrip("/")
        if not base.endswith("/videos"):
            base = base + "/videos"

        html = _get(base, timeout=25)
        if not html:
            return []

        m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>",
                      html, re.DOTALL)
        if not m:
            m = re.search(r"ytInitialData\s*=\s*(\{.{200,}?\});", html, re.DOTALL)
        if not m:
            return []

        try:
            data = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            return []

        videos = []
        _extract_videos(data, videos)

        seen   = set()
        unique = []
        for v in videos:
            vid = v.get("video_id", "")
            if vid and vid not in seen:
                seen.add(vid)
                unique.append(v)

        return unique[:max_videos]

    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"    channel_videos fallback error: {e}")
        return []


def _extract_videos(obj, out, depth=0):
    """Recursively find videoRenderer objects in ytInitialData."""
    if depth > 25 or len(out) >= 20:
        return
    if isinstance(obj, dict):
        if "videoRenderer" in obj:
            v = obj["videoRenderer"]
            try:
                vid_id = v.get("videoId", "")
                title  = ""
                views  = 0
                # title
                runs = (v.get("title") or {}).get("runs") or []
                if runs:
                    title = "".join(r.get("text", "") for r in runs)
                # view count
                vc = (v.get("viewCountText") or {})
                vc_txt = vc.get("simpleText", "") or "".join(
                    r.get("text", "") for r in vc.get("runs", []))
                nums = re.findall(r"[\d,]+", vc_txt.replace(",", ""))
                views = int(nums[0]) if nums else 0
                if vid_id and title:
                    out.append({
                        "video_id": vid_id,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "title": title,
                        "views": views,
                    })
            except Exception:  # noqa: BLE001
                pass
        for v in obj.values():
            _extract_videos(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _extract_videos(item, out, depth + 1)


def _pick_outliers(videos, n=VIDEOS_PER_CHANNEL):
    """Pick the n highest-view videos as 'outliers' to analyse."""
    if not videos:
        return []
    sorted_vids = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)
    return sorted_vids[:n]


def _gemini_decode(video_url, title, description, api_key,
                   model=GEMINI_MODEL, logger=None):
    """Ask Gemini to decode a video's content pattern. Returns pattern dict."""
    try:
        prompt = f"""You are a YouTube content strategist analysing a competitor video.

Video Title: {title}
Video URL: {video_url}
Description snippet: {description[:500] if description else 'not available'}

Decode this video's EXACT content formula. Return ONLY valid JSON:

{{
  "hook_type": "question|shock|story|reveal|stat",
  "hook_templates": [
    "hook template 1 using {{{{topic}}}}",
    "hook template 2 using {{{{topic}}}}"
  ],
  "beats": [
    {{"name": "beat name", "lines": ["template line with {{{{topic}}}}"], "scene": "image scene", "rejoin": false}},
    {{"name": "beat name", "lines": ["template line"], "scene": "image scene", "rejoin": true}}
  ],
  "rejoin_transitions": ["avatar re-entry line 1", "line 2", "line 3"],
  "cta_templates": ["CTA template 1", "CTA template 2"],
  "image_style": "visual style for AI image generation",
  "style_notes": "writing tone, vocabulary, pace, emotional style",
  "est_video_minutes": 5,
  "niche": "gardening|cooking|cleaning|farming|homestead|firearms|other"
}}

Rules:
- Use {{{{topic}}}} as placeholder where topic would go
- beats: 4-7 beats covering intro -> problem -> solution -> proof -> cta arc
- rejoin=true for beats where the avatar/presenter would re-appear
- Return ONLY the JSON object, no markdown fences, no explanation"""

        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1200,
                "responseMimeType": "application/json",
            }
        }).encode("utf-8")

        api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}")
        req = urllib.request.Request(
            api_url, data=body,
            headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=45) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))

        text = (resp.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", ""))

        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())

        pat = json.loads(text)
        pat["reference_url"]   = video_url
        pat["reference_title"] = title
        return pat

    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"    gemini_decode error: {e}")
        return {}


def _get_description(video_url):
    """Try to scrape video description from watch page. Returns '' on fail."""
    try:
        html = _get(video_url, timeout=20)
        m = re.search(r'"shortDescription":"(.*?)"(?:,"isCrawlable")',
                      html, re.DOTALL)
        if m:
            desc = m.group(1).replace("\\n", "\n").replace('\\"', '"')
            return desc[:800]
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _merge_patterns(patterns):
    """Merge multiple decoded patterns into one channel master pattern.

    - hook_templates: union of all, capped at 6
    - beats: most common beat count / take longest set
    - style_notes: concatenate unique notes
    - image_style: most common
    - rejoin_transitions: union capped at 6
    - cta_templates: union capped at 4
    """
    if not patterns:
        return {}
    if len(patterns) == 1:
        return patterns[0]

    all_hooks    = []
    all_ctas     = []
    all_rejoins  = []
    all_styles   = []
    all_notes    = []
    all_niches   = []
    best_beats   = []

    for p in patterns:
        all_hooks   += p.get("hook_templates", [])
        all_ctas    += p.get("cta_templates", [])
        all_rejoins += p.get("rejoin_transitions", [])
        s = p.get("image_style", "")
        if s:
            all_styles.append(s)
        n = p.get("style_notes", "")
        if n:
            all_notes.append(n)
        ni = p.get("niche", "")
        if ni:
            all_niches.append(ni)
        beats = p.get("beats", [])
        if len(beats) > len(best_beats):
            best_beats = beats

    # Niche: most common
    niche = max(set(all_niches), key=all_niches.count) if all_niches else "other"

    # Image style: most common
    image_style = max(set(all_styles), key=all_styles.count) if all_styles else ""

    # De-duplicate lists preserving order
    def dedup(lst, cap):
        seen, out = set(), []
        for x in lst:
            k = x[:60] if isinstance(x, str) else str(x)
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out[:cap]

    return {
        "hook_templates":     dedup(all_hooks, 6),
        "beats":              best_beats,
        "rejoin_transitions": dedup(all_rejoins, 6),
        "cta_templates":      dedup(all_ctas, 4),
        "image_style":        image_style,
        "style_notes":        " | ".join(dict.fromkeys(all_notes))[:400],
        "niche":              niche,
        "videos_analysed":    len(patterns),
    }


# ── public API ────────────────────────────────────────────────────────────────

def load_competitors():
    """Load the competitors.json list. Returns [] on any error."""
    try:
        data = json.loads(_COMPETITORS_FILE.read_text(encoding="utf-8"))
        return data.get("competitors", [])
    except Exception:  # noqa: BLE001
        return []


def load_patterns():
    """Load all saved competitor patterns. Returns {} on any error."""
    try:
        if _DATA_FILE.is_file():
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_patterns(data):
    """Save patterns dict to disk. Never raises."""
    try:
        _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DATA_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def scrape_channel(handle, channel_url, api_key, n_videos=VIDEOS_PER_CHANNEL,
                   model=GEMINI_MODEL, logger=None, existing=None):
    """Scrape one channel, decode top videos, return channel result dict.

    existing: previously saved channel data (for skip/resume logic).
    Never raises.
    """
    result = {
        "handle":        handle,
        "url":           channel_url,
        "scraped_at":    datetime.now().isoformat()[:19],
        "videos_found":  0,
        "videos_decoded": 0,
        "status":        "pending",
        "master_pattern": {},
        "videos":        [],
    }

    try:
        if logger:
            logger(f"\n[{handle}] fetching videos...")

        # 1. Get video list
        videos = _channel_videos(channel_url, max_videos=15, logger=logger)
        time.sleep(REQUEST_DELAY)

        if not videos:
            # Try oEmbed for at least the latest video URL from handle
            result["status"] = "no_videos"
            if logger:
                logger(f"  {handle}: no videos found (page blocked or empty channel)")
            return result

        result["videos_found"] = len(videos)
        if logger:
            logger(f"  {handle}: {len(videos)} videos found")

        # 2. Pick outliers
        outliers = _pick_outliers(videos, n=n_videos)

        # 3. Decode each
        decoded = []
        for i, v in enumerate(outliers):
            video_url = v["url"]
            title     = v["title"]
            views     = v.get("views", 0)

            if logger:
                logger(f"  [{i+1}/{len(outliers)}] decoding: {title[:60]}... "
                       f"({views:,} views)")

            # Get description
            desc = _get_description(video_url)
            time.sleep(REQUEST_DELAY * 0.5)

            # AI decode
            pat = _gemini_decode(video_url, title, desc, api_key,
                                 model=model, logger=logger)
            time.sleep(REQUEST_DELAY)

            if pat:
                pat["video_title"] = title
                pat["views"]       = views
                decoded.append(pat)
                result["videos"].append({
                    "url": video_url, "title": title,
                    "views": views, "decoded": True})
            else:
                result["videos"].append({
                    "url": video_url, "title": title,
                    "views": views, "decoded": False})

        result["videos_decoded"] = len(decoded)

        # 4. Merge into master pattern
        if decoded:
            master = _merge_patterns(decoded)
            master["name"]       = f"{handle} pattern"
            master["channel"]    = handle
            master["channel_url"] = channel_url
            result["master_pattern"] = master
            result["status"] = "done"
            if logger:
                logger(f"  {handle}: {len(decoded)} patterns merged -> "
                       f"niche={master.get('niche', '?')}")
        else:
            result["status"] = "decode_failed"
            if logger:
                logger(f"  {handle}: decode failed for all videos")

    except Exception as e:  # noqa: BLE001
        result["status"] = "error"
        result["error"]  = str(e)[:200]
        if logger:
            logger(f"  {handle}: ERROR: {e}")

    return result


def run_full_scrape(api_key, n_videos=VIDEOS_PER_CHANNEL,
                    model=GEMINI_MODEL, progress_cb=None, logger=None,
                    resume=True, max_channels=None):
    """Scrape all 93 competitor channels and save patterns.

    resume=True: skip channels already successfully scraped.
    Returns summary dict. Never raises.
    """
    competitors = load_competitors()
    if not competitors:
        if logger:
            logger("No competitors found in config/competitors.json")
        return {"ok": False, "error": "No competitors list"}

    if max_channels:
        competitors = competitors[:max_channels]

    # Load existing data for resume
    all_data = load_patterns() if resume else {}
    channels_done = {k: v for k, v in all_data.items()
                     if isinstance(v, dict) and v.get("status") == "done"}

    total   = len(competitors)
    done    = 0
    skipped = 0
    failed  = 0

    summary = {
        "started_at": datetime.now().isoformat()[:19],
        "total":      total,
        "done":       0,
        "skipped":    0,
        "failed":     0,
        "channels":   {},
    }

    for i, comp in enumerate(competitors):
        handle = comp.get("handle", f"ch{i}")
        url    = comp.get("url", "")

        if progress_cb:
            pct = int(i / total * 100)
            progress_cb(pct, f"[{i+1}/{total}] {handle}...")

        # Skip already done
        if resume and handle in channels_done:
            skipped += 1
            summary["channels"][handle] = channels_done[handle]
            if logger:
                logger(f"[{i+1}/{total}] {handle}: SKIP (already done)")
            continue

        result = scrape_channel(
            handle, url, api_key,
            n_videos=n_videos, model=model, logger=logger,
            existing=all_data.get(handle))

        all_data[handle] = result
        summary["channels"][handle] = result

        if result.get("status") == "done":
            done += 1
        else:
            failed += 1

        # Save progress after every channel (resume-safe)
        save_patterns(all_data)

        # Small pause between channels
        time.sleep(REQUEST_DELAY)

    summary["done"]        = done
    summary["skipped"]     = skipped
    summary["failed"]      = failed
    summary["finished_at"] = datetime.now().isoformat()[:19]
    summary["ok"]          = True

    if progress_cb:
        progress_cb(100, f"Done: {done} decoded, {skipped} skipped, {failed} failed")
    if logger:
        logger(f"\nScrape complete: {done} decoded, {skipped} skipped, {failed} failed")

    return summary


def best_pattern_for(topic_hint="", niche_hint=""):
    """Return the best matching pattern dict for a given topic/niche hint.

    Ranks patterns by niche match, then by videos_decoded count.
    Returns {} if no patterns available.
    """
    try:
        all_data = load_patterns()
        candidates = []
        for handle, data in all_data.items():
            if not isinstance(data, dict):
                continue
            mp = data.get("master_pattern", {})
            if not mp:
                continue
            niche   = str(mp.get("niche", "")).lower()
            decoded = int(data.get("videos_decoded", 0))
            score   = decoded

            # Boost if niche matches topic hint
            hint_words = (topic_hint + " " + niche_hint).lower().split()
            if any(w in niche for w in hint_words if len(w) > 3):
                score += 100
            if any(w in handle.lower() for w in hint_words if len(w) > 3):
                score += 50

            candidates.append((score, handle, mp))

        if not candidates:
            return {}

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][2]  # return best master_pattern dict

    except Exception:  # noqa: BLE001
        return {}


def get_all_master_patterns():
    """Return list of (handle, niche, videos_decoded, master_pattern) tuples."""
    try:
        all_data = load_patterns()
        result   = []
        for handle, data in all_data.items():
            if not isinstance(data, dict):
                continue
            mp      = data.get("master_pattern", {})
            niche   = mp.get("niche", "?")
            decoded = data.get("videos_decoded", 0)
            status  = data.get("status", "?")
            result.append({
                "handle":   handle,
                "niche":    niche,
                "decoded":  decoded,
                "status":   status,
                "pattern":  mp,
                "videos":   data.get("videos", []),
            })
        result.sort(key=lambda x: x["decoded"], reverse=True)
        return result
    except Exception:  # noqa: BLE001
        return []
