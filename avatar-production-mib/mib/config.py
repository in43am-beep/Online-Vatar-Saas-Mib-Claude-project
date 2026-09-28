"""mib/config.py — config.yaml + secrets.yaml load/save. Never crashes.

Frozen (PyInstaller exe) behaviour: the exe extracts to a throwaway temp dir,
so ALL writable state (config, secrets, avatars, output) lives in
%APPDATA%/AvatarProductionByMIB, seeded once from the bundled defaults.
Unfrozen (dev): everything lives next to the source tree, as before.

MIB_CONFIG_DIR: when set, config.yaml / secrets.yaml live directly inside
that dir instead. Test harnesses set it to a temp dir so automated UI tests
can never overwrite the user's real config (a polluted config once wiped
the presenter list and left the presenter page blank).
"""
import copy
import os
import shutil
import sys
from pathlib import Path

import yaml


def _bundle_dir():
    """Read-only bundled files: PyInstaller _MEIPASS, else the source tree."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def _app_dir():
    """Writable, persistent app dir (frozen) or source tree (dev)."""
    # Server/container override: MIB_DATA_DIR points at a persistent volume
    # (e.g. /data on Docker/Spaces hosts) so config + output survive restarts.
    _data = os.environ.get("MIB_DATA_DIR")
    if _data:
        d = Path(_data)
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / "AvatarProductionByMIB"
    else:
        d = Path(__file__).resolve().parent.parent
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


BUNDLE_DIR = _bundle_dir()
ROOT = _app_dir()
_config_dir = ROOT / "config"
_test_dir = os.environ.get("MIB_CONFIG_DIR")
if _test_dir:  # test harness isolation: never touch the real config
    _config_dir = Path(_test_dir)
    try:
        _config_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
CONFIG_PATH = _config_dir / "config.yaml"
SECRETS_PATH = _config_dir / "secrets.yaml"
SECRETS_EXAMPLE = _config_dir / "secrets.yaml.example"
SAMPLES_DIR = ROOT / "assets" / "voice_samples"


def store_voice_sample(src):
    """Copy a user-picked audio file into the app's own voice-samples
    folder so the clone sample survives even if the original PC file is
    moved or deleted. Returns the stored absolute path as str.
    Never raises — returns the original path on failure."""
    import time as _time

    p = Path(src)
    try:
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        stem = "".join(
            c if (c.isalnum() or c in " -_") else "_" for c in p.stem)[:40] \
            or "sample"
        suffix = p.suffix.lower() or ".wav"
        dest = SAMPLES_DIR / f"{stem}{suffix}"
        if dest.exists():
            dest = SAMPLES_DIR / \
                f"{stem}_{int(_time.time())}{suffix}"
        shutil.copy2(str(p), str(dest))
        return str(dest)
    except Exception:
        return str(p)

DEFAULT_CONFIG = {
    "channels": {
        "behind-the-hug": {
            "name": "Behind The Hug",
            "niche": "Emotional soldier-dog reunion stories for a 65+ audience.",
            "default_minutes": 30,
            "mode": "avatar",
            "presenter": "maria",
            "voice": {"provider": "edge", "voice_id": "en-US-AvaNeural"},
            "subtitles": False,
        },
        "kustorez-amish": {
            "name": "Kustorez Amish",
            "niche": "Amish gardening & self-reliant home wisdom for seniors.",
            "default_minutes": 15,
            "mode": "avatar",
            "presenter": "walter",
            "voice": {"provider": "edge", "voice_id": "en-US-AndrewNeural"},
            "subtitles": False,
        },
    },
    "presenters": [
        {"id": "maria", "name": "Maria", "image": "assets/avatars/maria.png",
         "gender": "f"},
        {"id": "walter", "name": "Walter", "image": "assets/avatars/walter.png",
         "gender": "m"},
        {"id": "priya", "name": "Priya", "image": "assets/avatars/priya.png",
         "gender": "f"},
    ],
    "providers": {
        "voice_order": ["channel", "edge"],
        "script_provider": "local",
        "ai33pro_llm_base_url": "",
        "ai33pro_llm_model": "",
        "gemini_llm_model": "gemini-2.5-flash",
        # claude_review: when True, Claude proofreads every script after
        # the writer and auto-applies fixes. Endpoint + model are set here
        # because the key comes from a custom (Antigravity) endpoint.
        "claude_review": False,
        "claude_base_url": "https://api.anthropic.com",
        "claude_model": "",
        "gdrive_auto_upload": False,
        "image_order": ["grok", "gemini", "local"],
        "gemini_model": "gemini-2.5-flash-image",
        "grok_model": "grok-imagine-image",
        "presenter_seconds": 6,
        "appearances": 1,
        # gold subscribe-bell watermark, bottom-right of every video
        # (reference mechanic — persistent, burnt into the frame)
        "presenter_watermark": True,
    },
}

DEFAULT_SECRETS = {
    "ai33pro_api_key": "",
    "gemini_api_key": "",
    "xai_api_key": "",
    "claude_api_key": "",
    # multi-key pools: one key per line (or a JSON-ish list). The pool tries
    # keys in order and auto-fails over when one hits a limit.
    "ai33pro_api_keys": [],
    "gemini_api_keys": [],
    "xai_api_keys": [],
    "claude_api_keys": [],
}


def _read_yaml(path):
    try:
        if Path(path).exists():
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _write_yaml(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                   encoding="utf-8")
    shutil.move(str(tmp), str(p))


def load_config():
    """Load config.yaml merged over defaults. Never raises.

    Merge rules (all defensive — a half-written or test-polluted file must
    never leave the app with zero presenters / zero channels, which blanks
    the presenter page and silently breaks the pipeline):
    - providers: deep-merged over defaults, so a partial stored dict keeps
      every default key (voice_order, presenter_seconds, ...).
    - channels: each stored channel deep-merged over its default twin when
      one exists; the stored set wins as a whole (user deletions respected),
      but an empty stored dict falls back to defaults.
    - presenters: an empty stored list never wipes the defaults.
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    user = _read_yaml(CONFIG_PATH)
    if not user:
        if not CONFIG_PATH.exists():
            try:
                _write_yaml(CONFIG_PATH, cfg)
            except Exception:
                pass
        return cfg
    provs = user.get("providers")
    if isinstance(provs, dict):
        merged = copy.deepcopy(DEFAULT_CONFIG["providers"])
        merged.update(provs)
        cfg["providers"] = merged
    chs = user.get("channels")
    if isinstance(chs, dict) and chs:
        defaults = DEFAULT_CONFIG["channels"]
        merged_chs = {}
        for ck, cv in chs.items():
            if isinstance(cv, dict) and ck in defaults:
                m = copy.deepcopy(defaults[ck])
                m.update(cv)
                merged_chs[ck] = m
            else:
                merged_chs[ck] = copy.deepcopy(cv)
        cfg["channels"] = merged_chs
    pres = user.get("presenters")
    if isinstance(pres, list) and pres:
        cfg["presenters"] = copy.deepcopy(pres)
    # any other top-level keys (patterns, etc.) pass through as stored
    for k, v in user.items():
        if k not in ("providers", "channels", "presenters"):
            cfg[k] = copy.deepcopy(v)
    return cfg


def save_config(cfg):
    """Persist config.yaml. Never raises (returns True/False)."""
    try:
        _write_yaml(CONFIG_PATH, cfg)
        return True
    except Exception:
        return False


def load_secrets():
    """Load secrets.yaml. Missing file -> defaults (all empty). Never raises."""
    sec = dict(DEFAULT_SECRETS)
    sec.update(_read_yaml(SECRETS_PATH))
    return sec


def save_secrets(sec):
    """Persist secrets.yaml. Never raises (returns True/False)."""
    try:
        merged = dict(DEFAULT_SECRETS)
        merged.update(sec or {})
        _write_yaml(SECRETS_PATH, merged)
        return True
    except Exception:
        return False


def ensure_secrets_file():
    """Create secrets.yaml from the example when missing. Never raises."""
    try:
        if not SECRETS_PATH.exists():
            for cand in (SECRETS_EXAMPLE, BUNDLE_DIR / "config" / "secrets.yaml.example"):
                if cand.exists():
                    shutil.copy(str(cand), str(SECRETS_PATH))
                    return
            _write_yaml(SECRETS_PATH, dict(DEFAULT_SECRETS))
    except Exception:
        pass


def seed_app_dir():
    """Frozen exe first-run: copy bundled defaults into the writable app dir.

    Seeds config.yaml (when absent), secrets.yaml.example, and the placeholder
    avatar PNGs. Dev mode: no-op. Never raises.
    """
    try:
        if not getattr(sys, "frozen", False):
            return
        bconf = BUNDLE_DIR / "config"
        if not CONFIG_PATH.exists() and (bconf / "config.yaml").exists():
            (ROOT / "config").mkdir(parents=True, exist_ok=True)
            shutil.copy(str(bconf / "config.yaml"), str(CONFIG_PATH))
        if not SECRETS_EXAMPLE.exists() and (bconf / "secrets.yaml.example").exists():
            (ROOT / "config").mkdir(parents=True, exist_ok=True)
            shutil.copy(str(bconf / "secrets.yaml.example"), str(SECRETS_EXAMPLE))
        bav = BUNDLE_DIR / "assets" / "avatars"
        tav = ROOT / "assets" / "avatars"
        if bav.is_dir():
            tav.mkdir(parents=True, exist_ok=True)
            for png in bav.glob("*.png"):
                dest = tav / png.name
                if not dest.exists():
                    shutil.copy(str(png), str(dest))
    except Exception:
        pass
