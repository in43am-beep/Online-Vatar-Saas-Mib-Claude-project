"""mib/keypool.py — multi-API-key rotation with automatic failover.

One service (e.g. "gemini-image", "ai33-voice") can hold UNLIMITED API keys.
The pool tries keys in order; when a key hits a rate limit / quota
(KeyExhausted) it is cooled down and the next key takes over instantly.
A dead/invalid key (KeyRejected, e.g. HTTP 401/403) is parked for 24h.

Every failover emits a backend message (via the job logger AND an optional
event callback) so the user always sees WHICH key stopped working and WHY.

Per-key usage is tracked by operation ("image", "voice", "script",
"avatar", ...) so the Settings → API Keys tab can show a live status
board (green/amber/red dots) and a per-key report: how much work each key
did, what it did, and when it hit its limit.

Cooldown state is persisted as METADATA ONLY (key id = last 4 chars,
cooldown timestamps, use/fail counters, per-op counters). Raw key values
are never written to disk by this module — they live in secrets
(Secure Vault / secrets.yaml) and are passed in at runtime.

Any future provider (image, video, LLM — including a Claude/Anthropic
endpoint later) gets rotation for free by constructing a KeyPool.
"""
import json
import time
from pathlib import Path

DEFAULT_COOLDOWN_SEC = 3600        # 1h after a 429 / quota hit
REJECT_COOLDOWN_SEC = 24 * 3600    # 24h after a 401/403 (dead key)


class KeyExhausted(Exception):
    """A key hit its rate limit / quota. Pool should try the next key."""


class KeyRejected(Exception):
    """A key was refused (401/403 — invalid or revoked). Pool parks it."""


# Module-level event sink: the desktop app registers a handler here
# (e.g. to flash a toast) — providers stay UI-free.
_global_handler = None


def set_event_handler(fn):
    """Register fn(event, service, last4, detail). Never raises the caller."""
    global _global_handler
    _global_handler = fn


def _last4(key):
    k = str(key or "").strip()
    return ("…" + k[-4:]) if k else "…?"


def _now_str(ts=None):
    return time.strftime("%d-%b %H:%M", time.localtime(ts or time.time()))


class KeyPool:
    """Unlimited-key pool with cooldown failover. Never raises on init."""

    def __init__(self, service, keys, state_dir=None,
                 cooldown_sec=DEFAULT_COOLDOWN_SEC, on_event=None):
        self.service = str(service or "default")
        self.cooldown_sec = max(60, int(cooldown_sec or DEFAULT_COOLDOWN_SEC))
        seen, self.keys = set(), []
        for k in keys or []:
            k = str(k or "").strip()
            if k and k not in seen:
                seen.add(k)
                self.keys.append(k)
        self.state_dir = Path(state_dir) if state_dir else None
        self.on_event = on_event
        # per-slot metadata, aligned to current key order by last4
        self.meta = [{"last4": _last4(k), "cool_until": 0, "uses": 0,
                      "fails": 0, "by_op": {}, "last_used": 0,
                      "last_event": "", "parked": False,
                      "verified": None, "verified_at": 0}
                     for k in self.keys]
        self._load()

    # ---------------------------------------------------------- events
    def _emit(self, event, last4, detail=""):
        for fn in (self.on_event, _global_handler):
            if not fn:
                continue
            try:
                fn(event, self.service, last4, detail)
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------- persistence
    def _state_path(self):
        if not self.state_dir:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in self.service) or "default"
        return self.state_dir / f"keypool_{safe}.json"

    def _load(self):
        try:
            p = self._state_path()
            if not p or not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            saved = data.get("keys") if isinstance(data, dict) else None
            if not isinstance(saved, list):
                return
            by_last4 = {}
            for s in saved:
                if isinstance(s, dict) and s.get("last4"):
                    by_last4.setdefault(s["last4"], s)
            for m in self.meta:
                s = by_last4.get(m["last4"])
                if s:
                    m["cool_until"] = float(s.get("cool_until") or 0)
                    m["uses"] = int(s.get("uses") or 0)
                    m["fails"] = int(s.get("fails") or 0)
                    by_op = s.get("by_op")
                    m["by_op"] = {str(k): int(v) for k, v in by_op.items()} \
                        if isinstance(by_op, dict) else {}
                    m["last_used"] = float(s.get("last_used") or 0)
                    m["last_event"] = str(s.get("last_event") or "")
                    m["parked"] = bool(s.get("parked"))
                    v = s.get("verified")
                    m["verified"] = bool(v) if v is not None else None
                    m["verified_at"] = float(s.get("verified_at") or 0)
        except Exception:  # noqa: BLE001
            pass

    def _save(self):
        """Write state, merging with the file first so two pools sharing
        one service (e.g. ai33 voice + script LLM) don't clobber each
        other's counters."""
        try:
            p = self._state_path()
            if not p:
                return
            p.parent.mkdir(parents=True, exist_ok=True)
            old = {}
            try:
                if p.exists():
                    data = json.loads(p.read_text(encoding="utf-8"))
                    for s in (data.get("keys") or []):
                        if isinstance(s, dict) and s.get("last4"):
                            old.setdefault(s["last4"], s)
            except Exception:  # noqa: BLE001
                pass
            merged = []
            for m in self.meta:
                s = old.get(m["last4"]) or {}
                by_op = dict(m.get("by_op") or {})
                for k, v in (s.get("by_op") or {}).items():
                    if isinstance(v, (int, float)):
                        by_op[k] = max(by_op.get(k, 0), int(v))
                s_last_used = float(s.get("last_used") or 0)
                last_used = max(float(m.get("last_used") or 0), s_last_used)
                merged.append({
                    "last4": m["last4"],
                    "cool_until": max(float(m.get("cool_until") or 0),
                                      float(s.get("cool_until") or 0)),
                    "uses": max(int(m.get("uses") or 0),
                                int(s.get("uses") or 0)),
                    "fails": max(int(m.get("fails") or 0),
                                 int(s.get("fails") or 0)),
                    "by_op": by_op,
                    "last_used": last_used,
                    "last_event": (m.get("last_event") or ""
                                   if float(m.get("last_used") or 0)
                                   >= s_last_used
                                   else s.get("last_event") or ""),
                    "parked": bool(m.get("parked")) or bool(s.get("parked")),
                    "verified": (m.get("verified")
                                 if m.get("verified") is not None
                                 else s.get("verified")),
                    "verified_at": max(float(m.get("verified_at") or 0),
                                       float(s.get("verified_at") or 0)),
                })
            p.write_text(json.dumps({"service": self.service,
                                     "keys": merged},
                                    ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------------- runtime
    def usable(self):
        """Indices of keys not currently cooling down."""
        now = time.time()
        return [i for i, m in enumerate(self.meta)
                if m["cool_until"] <= now]

    def run(self, fn, logger=None, op=None):
        """Call fn(key) -> result, failing over across keys. Never silent.

        fn must raise KeyExhausted on 429/quota and KeyRejected on 401/403.
        Any other exception is a real error and propagates after state save.
        op is a short tag ("image", "voice", "script", "avatar") recorded
        in the per-key usage report.
        """
        if not self.keys:
            raise KeyExhausted(f"No API keys configured for {self.service}.")
        order = self.usable()
        if not order:
            soonest = min(m["cool_until"] for m in self.meta)
            wait = max(1, int(soonest - time.time()))
            raise KeyExhausted(
                f"All {len(self.keys)} {self.service} keys are cooling down "
                f"— next retry in ~{wait // 60 + 1} min.")
        last_err = None
        failed = 0
        for i in order:
            m = self.meta[i]
            try:
                result = fn(self.keys[i])
                m["uses"] += 1
                m["last_used"] = time.time()
                if op:
                    by_op = m.setdefault("by_op", {})
                    by_op[str(op)] = int(by_op.get(str(op), 0)) + 1
                if m.get("parked") or m.get("cool_until"):
                    # a previously-rested key is back in service
                    m["parked"] = False
                    m["cool_until"] = 0
                    m["last_event"] = f"back live {_now_str()}"
                    self._emit("revived", m["last4"], self.service)
                self._save()
                if failed and logger:
                    logger.log(f"    ✓ BACKEND [{self.service}]: now live "
                               f"on key {m['last4']}")
                return result
            except KeyExhausted as e:
                m["fails"] += 1
                m["cool_until"] = time.time() + self.cooldown_sec
                m["last_event"] = f"limit hit {_now_str()}"
                last_err = e
                failed += 1
                msg = (f"    ⚠ BACKEND [{self.service}]: key {m['last4']} "
                       f"hit its limit/quota ({e}) — resting 1h, "
                       f"switching to next key")
                if logger:
                    logger.log(msg[:300])
                self._emit("exhausted", m["last4"], str(e)[:200])
            except KeyRejected as e:
                m["fails"] += 1
                m["cool_until"] = time.time() + REJECT_COOLDOWN_SEC
                m["parked"] = True
                m["last_event"] = f"rejected {_now_str()}"
                last_err = e
                failed += 1
                msg = (f"    ⛔ BACKEND [{self.service}]: key {m['last4']} "
                       f"REJECTED ({e}) — invalid/revoked? parked 24h, "
                       f"switching to next key")
                if logger:
                    logger.log(msg[:300])
                self._emit("rejected", m["last4"], str(e)[:200])
        self._save()
        # Every usable key failed with exhaustion/rejection: summarize.
        if failed and failed == len(order):
            soonest = min(m["cool_until"] for m in self.meta)
            wait = max(1, int(soonest - time.time()))
            err = KeyExhausted(
                f"All {len(self.keys)} {self.service} keys hit limits and "
                f"are cooling down — next retry in ~{wait // 60 + 1} min. "
                f"(last error: {last_err})")
            if logger:
                logger.log(f"    ⛔ BACKEND [{self.service}]: {err}")
            self._emit("all_down", "", str(err)[:200])
            raise err
        if last_err:
            raise last_err
        raise KeyExhausted(f"All {self.service} keys failed.")

    def mark_verified(self, last4, ok):
        """Record a manual 'Verify' result for one key (True/False)."""
        for m in self.meta:
            if m["last4"] == last4:
                m["verified"] = bool(ok)
                m["verified_at"] = time.time()
        self._save()

    def stats(self):
        """UI-safe per-key stats (no raw key values)."""
        now = time.time()
        out = []
        for m in self.meta:
            cooling = m["cool_until"] > now
            if m.get("parked") and cooling:
                status = "parked"
            elif cooling:
                status = "cooling"
            else:
                status = "ready"
            out.append({
                "last4": m["last4"],
                "uses": m["uses"],
                "fails": m["fails"],
                "status": status,
                "cool_min": (max(1, int((m["cool_until"] - now) // 60))
                             if cooling else 0),
                "by_op": dict(m.get("by_op") or {}),
                "last_used": m.get("last_used") or 0,
                "last_event": m.get("last_event") or "",
                "verified": m.get("verified"),
                "verified_at": m.get("verified_at") or 0,
            })
        return out

    def summary(self):
        """One-line service summary for the UI header."""
        st = self.stats()
        live = sum(1 for s in st if s["status"] == "ready")
        cool = sum(1 for s in st if s["status"] == "cooling")
        parked = sum(1 for s in st if s["status"] == "parked")
        uses = sum(s["uses"] for s in st)
        ver_ok = sum(1 for s in st if s["verified"] is True)
        ver_bad = sum(1 for s in st if s["verified"] is False)
        return {"total": len(st), "live": live, "cooling": cool,
                "parked": parked, "uses": uses,
                "verified_ok": ver_ok, "verified_bad": ver_bad}


def pool_from_secrets(service, secrets, single_name, multi_name,
                      state_dir=None, cooldown_sec=DEFAULT_COOLDOWN_SEC,
                      on_event=None):
    """Build a KeyPool from secrets: multi-key list wins, else single key.

    No limit on the number of keys. Never raises; returns None when no
    keys are configured.
    """
    try:
        secrets = secrets or {}
        keys = []
        multi = secrets.get(multi_name)
        if isinstance(multi, (list, tuple)):
            keys.extend(multi)
        elif isinstance(multi, str) and multi.strip():
            # tolerate newline/comma separated pastes
            keys.extend(x for x in
                        multi.replace(",", "\n").splitlines() if x.strip())
        single = secrets.get(single_name)
        if single and str(single).strip():
            keys.append(single)
        pool = KeyPool(service, keys, state_dir=state_dir,
                       cooldown_sec=cooldown_sec, on_event=on_event)
        return pool if pool.keys else None
    except Exception:  # noqa: BLE001
        return None
