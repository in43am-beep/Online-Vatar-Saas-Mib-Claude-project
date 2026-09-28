"""mib/log.py — per-job logger (file + in-memory tail + UI callback)."""
from pathlib import Path


class JobLogger:
    """Append-only logger for one pipeline job. Never raises."""

    def __init__(self, job_dir, callback=None, tail_size=400):
        self.job_dir = Path(job_dir)
        self.callback = callback
        self._tail = []
        self._tail_size = tail_size
        try:
            self.job_dir.mkdir(parents=True, exist_ok=True)
            self._file = self.job_dir / "run.log"
        except Exception:  # noqa: BLE001
            self._file = None

    def log(self, msg):
        line = str(msg)
        self._tail.append(line)
        if len(self._tail) > self._tail_size:
            self._tail = self._tail[-self._tail_size:]
        try:
            if self._file is not None:
                with open(self._file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass
        if self.callback is not None:
            try:
                self.callback(line)
            except Exception:  # noqa: BLE001
                pass

    def tail(self, n=60):
        return list(self._tail[-n:])
