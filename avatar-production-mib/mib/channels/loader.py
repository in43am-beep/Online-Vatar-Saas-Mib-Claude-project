"""mib/channels/loader.py — Load channel configs from YAML files.

Provides channel style, voice, script tone, and visual settings
for all 18 Frontier-matched channel types.
"""
from pathlib import Path

import yaml

_CHANNELS_DIR = Path(__file__).parent


def load_channel(channel_id):
    """Load a channel config by ID. Returns dict or {} if not found."""
    path = _CHANNELS_DIR / f"{channel_id}.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_channels():
    """Return list of all channel configs, sorted by name."""
    channels = []
    for yaml_file in sorted(_CHANNELS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_id"] = yaml_file.stem
                channels.append(data)
        except Exception:
            continue
    return channels


def get_image_style(channel_id):
    """Get the image_style string for a channel. Returns '' if not configured."""
    ch = load_channel(channel_id)
    return (ch.get("visuals") or {}).get("image_style") or ""


def get_voice_config(channel_id):
    """Get voice provider and voice ID for a channel."""
    ch = load_channel(channel_id)
    audio = ch.get("audio") or {}
    return {
        "provider": audio.get("voice_provider", "gemini_tts"),
        "voice": audio.get("voice", "Charon"),
        "speed": audio.get("speed", 1.0),
    }


def get_script_config(channel_id):
    """Get script tone and hook style for a channel."""
    ch = load_channel(channel_id)
    script = ch.get("script") or {}
    return {
        "tone": script.get("tone", ""),
        "hook_style": script.get("hook_style", ""),
        "target_wpm": script.get("target_wpm", 140),
    }


def channel_cost_per_min(channel_id):
    """Return estimated cost per minute on Gemini free tier."""
    ch = load_channel(channel_id)
    return ch.get("cost_per_min_free", 0.05)
