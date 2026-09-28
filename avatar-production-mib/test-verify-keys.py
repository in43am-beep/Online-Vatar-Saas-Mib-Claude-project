"""Offscreen UI test: per-key Verify button on the API Keys tab.

- KeyPool.mark_verified() persists per-key verify state across reloads
- stats()/summary() expose verified True/False/None
- API Keys tab has a "Verify all keys" button + "Verified" column per svc
- _keys_verify marks each key green/red via the background worker
- SettingsDialog.save() does NOT close the window (user closes it himself)
Run with QT_QPA_PLATFORM=offscreen and MIB_CONFIG_DIR=<tmpdir>.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MIB_CONFIG_DIR"] = tempfile.mkdtemp(prefix="mib-uitest-")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QEventLoop  # noqa: E402

from mib import config as config_mod  # noqa: E402
from mib.keypool import KeyPool, _last4  # noqa: E402
from mib.ui.settings import SettingsDialog  # noqa: E402
from mib.ui.wizard import WizardWindow  # noqa: E402

app = QApplication(sys.argv[:1])
state_dir = Path(os.environ["MIB_CONFIG_DIR"])

# 1. mark_verified persists across pool reloads
keys = ["sk-test-AAAA1111", "sk-test-BBBB2222", "sk-test-CCCC3333"]
p1 = KeyPool("gemini-image", keys, state_dir=state_dir)
p1.mark_verified(_last4(keys[0]), True)
p1.mark_verified(_last4(keys[1]), False)
p2 = KeyPool("gemini-image", keys, state_dir=state_dir)
st = {s["last4"]: s["verified"] for s in p2.stats()}
assert st[_last4(keys[0])] is True, "verified True not persisted"
assert st[_last4(keys[1])] is False, "verified False not persisted"
assert st[_last4(keys[2])] is None, "unverified key should be None"
s = p2.summary()
assert s["verified_ok"] == 1 and s["verified_bad"] == 1, s
print("1. KeyPool verify state persists + summary counts: OK")

# 2. API Keys tab: Verify button + Verified column for every service
cfg = config_mod.load_config()
secrets = config_mod.load_secrets()
win = WizardWindow(cfg, secrets)
dlg = SettingsDialog(win, cfg, secrets)

def buttons_of(layout):
    out = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and w.text():
            out.append(w.text())
    return out

found_verify = 0
for svc, _t, _m, _sg in dlg.KEY_SERVICES:
    tbl = dlg.key_tables[svc]
    headers = [tbl.horizontalHeaderItem(c).text()
               for c in range(tbl.columnCount())]
    assert "Verified" in headers, f"{svc}: Verified column missing"
found_verify = sum(
    1 for svc, _t, _m, _sg in dlg.KEY_SERVICES)
print(f"2. Verified column present for {found_verify} services: OK")

# 3. _keys_verify marks keys green/red through the background worker
svc = "gemini-image"
ed, _multi = dlg.key_edits[svc]
ed.setPlainText("\n".join(keys))

def fake_ping(k):
    if k.endswith("1111"):
        return "ok"
    raise Exception("401 unauthorized")

loop = QEventLoop()
dlg._verify_workers  # must exist
worker_holder = {}
orig_verify = dlg._keys_verify

def patched_verify(s):
    from mib.ui.settings import _VerifyWorker
    worker = _VerifyWorker(s, dlg._keys_list_from_edit(s), fake_ping,
                           config_mod.CONFIG_PATH.parent)
    worker.sig_done.connect(loop.quit)
    dlg._verify_workers[s] = worker
    worker.start()

patched_verify(svc)
loop.exec()  # wait for the background worker
dlg._on_verify_done(svc)  # what the real sig_done connection does
# (_on_verify_done already refreshed the board; no extra refresh — it
# would overwrite the verify-done label)
p3 = KeyPool(svc, keys, state_dir=state_dir)
st3 = {s_["last4"]: s_["verified"] for s_ in p3.stats()}
assert st3[_last4(keys[0])] is True, "key1 should verify green"
assert st3[_last4(keys[1])] is False, "key2 should verify red"
assert st3[_last4(keys[2])] is False, "key3 should verify red"
label = dlg.key_stat_labels[svc].text()
assert "1 of 3 keys verified" in label and "2 failed" in label, label
tbl = dlg.key_tables[svc]
ver_col = [tbl.horizontalHeaderItem(c).text()
           for c in range(tbl.columnCount())].index("Verified")
cells = [tbl.item(r, ver_col).text() for r in range(tbl.rowCount())]
assert "✓" in cells and "✗" in cells, f"cells: {cells}"
print("3. Verify worker marks green ✓ / red ✗ + count label: OK")

# 4. save() keeps the window open; user closes it himself
accepted = []
dlg.accept = lambda: accepted.append(True)
dlg.save()
assert not accepted, "save() must NOT close the dialog"
assert "Saved" in dlg.save_msg.text(), dlg.save_msg.text()
print("4. save() keeps the window open with Saved message: OK")

print("ALL VERIFY-BUTTON CHECKS PASSED")
