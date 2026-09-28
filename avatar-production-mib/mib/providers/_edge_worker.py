"""mib/providers/_edge_worker.py — runs edge-tts in its own subprocess.

Called by edgevoice.synthesize() to avoid asyncio clashing with the
PySide6 Qt event loop. This module is the child process: it runs
asyncio.run() safely in isolation and exits with code 0 on success,
1 on failure (stderr carries the error message).
"""
import asyncio
import sys


async def _speak(text, voice, rate, out_path):
    try:
        import edge_tts
    except ImportError as e:
        raise RuntimeError("edge-tts not installed") from e
    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(out_path)


def main():
    if len(sys.argv) != 4:
        sys.stderr.write("usage: _edge_worker <text> <voice> <out_path>\n")
        sys.exit(1)
    text, voice, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        asyncio.run(asyncio.wait_for(_speak(text, voice, "-15%", out_path), timeout=300))
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"edge-tts error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
