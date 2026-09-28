"""tests/test_avatar_thumbnail.py — 1 title = 1 avatar thumbnail.

Covers:
  1. build_avatar_prompt() with NO character sheet -> falls back to the
     legacy locked prompt (default behaviour unchanged).
  2. build_avatar_prompt() WITH a character sheet -> prompt carries the
     identity-lock block (user's details.txt), NOT the hardcoded Amish
     spec; overlay text stays <=3 words; exactly one prompt string.
  3. package.run() with channel id -> thumbnail-prompt.txt written.
  4. render_thumbnail() with no image keys -> prompt-file-only (""),
     thumbnail-prompt.txt still written. Never raises.

Run: MIB_CONFIG_DIR=<tmpdir> python tests/test_avatar_thumbnail.py
Also pytest-collectable (plain assert test_* functions).
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["MIB_CONFIG_DIR"] = tempfile.mkdtemp(prefix="mib-avthumb-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mib.prompts import thumbnail as th  # noqa: E402
from mib import character as charmod  # noqa: E402
from mib.stages import package as st_package  # noqa: E402


def _make_sheet(channel_id):
    """Write a fake character sheet + details for the channel."""
    d = charmod.character_dir(channel_id)
    assert d is not None
    # minimal valid PNG (1x1) so ref_images() picks it up
    from PIL import Image
    Image.new("RGB", (8, 8), (200, 100, 50)).save(d / "sheet.png", "PNG")
    charmod.save_details(
        channel_id,
        "NAME: TestAvatar\nAGE RANGE: 60s\nOUTFIT (locked): red plaid "
        "shirt, denim overalls\nKEY TRAITS: round face, grey beard")
    assert charmod.has_character(channel_id)


# ------------------------------------------------------------ 1. fallback

def test_avatar_prompt_falls_back_without_sheet():
    p = th.build_avatar_prompt("Save $500 With This Trick", "no-such-channel")
    assert isinstance(p, str) and p.strip()
    # legacy default spec kept when the channel has no character sheet
    assert "Amish man" in p


# ------------------------------------------------------------ 2. avatar lock

def test_avatar_prompt_uses_character_sheet():
    _make_sheet("thumbchan")
    title = "The $200 Pantry Mistake Nobody Talks About"
    p = th.build_avatar_prompt(title, "thumbchan",
                               topic_visual="empty pantry shelves")
    assert isinstance(p, str) and p.strip()
    # identity lock from details.txt is in the prompt...
    assert "TestAvatar" in p
    assert "CHARACTER CONSISTENCY" in p
    # ...and the hardcoded default character is NOT
    assert "Amish man" not in p
    # overlay text rule still holds (<=3 words, uppercase)
    overlay = th.derive_overlay_text(title)
    assert overlay in p
    assert len(overlay.split()) <= 3
    # expression + staging present
    assert "AVATAR STAGING" in p


# ------------------------------------------------------------ 3. package txt

def test_package_writes_avatar_prompt_txt():
    _make_sheet("thumbchan2")
    job = Path(tempfile.mkdtemp(prefix="mib-avthumb-job-"))
    script = {"title": "Save $300 Fast", "topic": "budget",
              "hook": "h", "beats": [], "cta": "c",
              "words": 100, "est_minutes": 1.0}
    st_package.run(str(job), script,
                   {"id": "thumbchan2", "name": "Thumb Chan"},
                   "", 60.0, {}, logger=None)
    tp = job / "thumbnail-prompt.txt"
    assert tp.is_file()
    txt = tp.read_text(encoding="utf-8")
    assert "TestAvatar" in txt  # avatar-locked, not the default spec


# ------------------------------------------------------------ 4. no-key mode

def test_render_thumbnail_prompt_file_only_without_keys():
    _make_sheet("thumbchan3")
    job = Path(tempfile.mkdtemp(prefix="mib-avthumb-job-"))
    out = st_package.render_thumbnail(
        str(job), "Save $300 Fast", "budget", "thumbchan3",
        {"providers": {"image_order": ["gemini", "local"]}},
        {},  # no secrets -> no keys
        logger=None)
    assert out == ""
    tp = job / "thumbnail-prompt.txt"
    assert tp.is_file()
    assert "TestAvatar" in tp.read_text(encoding="utf-8")


if __name__ == "__main__":
    for name, fn in sorted(
            [(k, v) for k, v in globals().items()
             if k.startswith("test_")]):
        fn()
        print(f"PASS {name}")
    print("all avatar-thumbnail tests passed")
