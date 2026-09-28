"""mib/depth_pop.py — Depth Pop / Parallax 3D effect on images.

Frontier's "Depth pop" feature ($0.004/min):
    Person/car in a picture slowly lifts off while background pulls back.
    This creates a 3D parallax cinematic effect.

HOW IT WORKS:
    1. Run a depth estimation model on the image
    2. Get a depth map (bright = close, dark = far)
    3. Apply FFmpeg displacement filter:
       - Foreground (bright depth): moves forward/upward
       - Background (dark depth): zooms out slightly
    4. Render as short video clip

DEPTH MODEL:
    Uses 'LiheYoung/depth-anything-small-hf' — free, runs on CPU.
    Install: pip install transformers torch pillow

    For faster GPU inference: pip install transformers torch pillow accelerate

FALLBACK:
    If transformers not installed, falls back to a simple zoompan
    that mimics the effect without true depth separation.
    Cost: $0.00 either way.
"""
from pathlib import Path

from . import ffmpeg


def _has_depth_model():
    """Check if DepthAnything model is available."""
    try:
        from transformers import pipeline  # noqa: F401
        return True
    except ImportError:
        return False


def create_depth_map(image_path, out_depth_path, logger=None):
    """Generate depth map using DepthAnything model.

    Args:
        image_path:      Input image (PNG, JPG).
        out_depth_path:  Output depth map PNG (grayscale).

    Returns:
        str: depth map path, or '' on failure.
    Never raises.
    """
    try:
        from transformers import pipeline
        from PIL import Image

        pipe = pipeline(
            task="depth-estimation",
            model="LiheYoung/depth-anything-small-hf",
        )
        image = Image.open(image_path)
        depth = pipe(image)["depth"]
        depth.save(str(out_depth_path))
        if logger:
            logger.log(f"    depth_pop: depth map generated for "
                       f"{Path(image_path).name}")
        return str(out_depth_path)
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    depth_pop: depth model error: {e} — "
                       "install with: pip install transformers torch")
        return ""


def render_depth_pop_clip(image_path, audio_path, out_path, duration,
                           use_depth_map=True, logger=None):
    """Render a depth pop video clip from an image.

    Args:
        image_path:    Source image (1920x1080 PNG).
        audio_path:    Audio file to attach.
        out_path:      Output MP4 clip.
        duration:      Clip duration in seconds.
        use_depth_map: If True, attempt real depth estimation.

    Returns:
        str: Output clip path, or '' on failure.
    Never raises.
    """
    try:
        duration = max(2.0, float(duration))
        job_dir = Path(out_path).parent

        if use_depth_map and _has_depth_model():
            # Real depth pop: generate depth map then apply displacement
            depth_path = job_dir / f"{Path(out_path).stem}_depth.png"
            depth = create_depth_map(image_path, depth_path, logger)

            if depth:
                # FFmpeg displacement filter with depth map
                rc, _so, se = ffmpeg.run([
                    "-y",
                    "-framerate", "30",
                    "-loop", "1", "-t", f"{duration:.2f}", "-i", image_path,
                    "-loop", "1", "-t", f"{duration:.2f}", "-i", depth,
                    "-i", audio_path,
                    "-filter_complex",
                    # Displacement: depth map drives foreground/background split
                    "[0:v]scale=1920:1080[base];"
                    "[1:v]scale=1920:1080[dmap];"
                    "[base][dmap]displace=edge=smear[displaced];"
                    "[displaced]zoompan="
                    "z='min(1+0.0005*on,1.08)':"
                    "x='iw/2-(iw/zoom/2)':"
                    "y='ih/2-(ih/zoom/2)':"
                    "d=1:s=1920x1080:fps=30[v]",
                    "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2",
                    "-t", f"{duration:.2f}",
                    str(out_path),
                ], timeout=600)

                if rc == 0 and Path(out_path).is_file():
                    if logger:
                        logger.log(f"    depth_pop: real depth pop rendered "
                                   f"({duration:.1f}s)")
                    return str(out_path)

        # Fallback: simulated depth pop via layered zoompan
        # Pushes the whole image slightly forward — simulates depth pop feel
        rc, _so, se = ffmpeg.run([
            "-y",
            "-framerate", "30",
            "-loop", "1", "-t", f"{duration:.2f}",
            "-i", image_path,
            "-i", audio_path,
            "-filter_complex",
            # Slight zoom + shift upward = simulated depth pop
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "zoompan="
            "z='if(lte(on,1),1.05,min(zoom+0.0006,1.12))':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih*0.45-(ih/zoom/2)':"
            "d=1:s=1920x1080:fps=30[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{duration:.2f}",
            str(out_path),
        ], timeout=600)

        if rc == 0 and Path(out_path).is_file():
            if logger:
                logger.log(f"    depth_pop: simulated depth pop "
                           f"({duration:.1f}s)")
            return str(out_path)

        if logger:
            logger.log(f"    depth_pop: render failed: {(se or '')[-150:]}")
        return ""

    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    depth_pop: error: {e}")
        return ""
