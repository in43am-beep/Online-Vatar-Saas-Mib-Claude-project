"""web_app.py — MIB Avatar Production v4 — Wizard UI (Competitor Style).

Main wizard flow (numbered sections on one scrollable page):
  Mode tabs: FRONTIER | AI AVATAR  (hover activates)
  1 Channel      — dropdown of channels for that mode
  2 Presenter    — avatar grid (video thumbnail cards) + big preview + 
                   gender filter + seconds slider + appearances picker
  3 Title        — big textarea "one per line makes several"
  4 Length       — 5/10/20/30/other + render time + cost estimate
  [CREATE VIDEO] — big gold button

Side pages:  Channel Setup | Queue | Competitors | Settings

Run: python web_app.py  →  http://localhost:7860
"""
import json, queue, threading, time, uuid, mimetypes, re, subprocess
from pathlib import Path
from flask import (Flask, Response, jsonify, render_template_string,
                   request, send_file)
import sys
sys.path.insert(0, str(Path(__file__).parent))

from mib.config import load_config, load_secrets, save_config, save_secrets
from mib.pipeline import run_pipeline

app = Flask(__name__)
app.secret_key = "mib-v4-2026"

JOBS            = {}
JOB_QUEUES      = {}
JOB_QUEUE_ORDER = []
_worker_running = [False]
_COMP_STOP      = [False]
_COMP_Q         = queue.Queue()
AVATAR_DIR      = Path("assets/avatars")
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# THUMBNAIL HELPER — extract frame from avatar clip
# ─────────────────────────────────────────────────────────────────────────────
def ensure_thumbnail(clip_path: Path) -> Path | None:
    """Auto-generate thumbnail.jpg beside each clip if not present."""
    thumb = clip_path.parent / (clip_path.stem + "_thumb.jpg")
    if thumb.exists():
        return thumb
    try:
        subprocess.run(
            ["ffmpeg", "-ss", "2", "-i", str(clip_path),
             "-vframes", "1", "-q:v", "2", str(thumb), "-y"],
            capture_output=True, timeout=15)
        return thumb if thumb.exists() else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MIB — Avatar Production</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root{
  --gold:#e8a020;--gold2:#f5c842;--bg:#0a0a0a;--bg2:#111;
  --card:#161616;--card2:#1e1e1e;--border:#252525;--text:#e0e0e0;
  --muted:#666;--muted2:#444;--blue:#4a9eff;--green:#3ecf7e;
  --red:#e05555;--purple:#a855f7;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
input,select,textarea,button{font-family:inherit}

/* TOP BAR */
.topbar{height:48px;display:flex;align-items:center;padding:0 28px;gap:14px;
  border-bottom:1px solid var(--border);background:rgba(10,10,10,.97);
  backdrop-filter:blur(10px);position:sticky;top:0;z-index:200}
.brand{font-size:16px;font-weight:900;letter-spacing:-0.5px}
.brand span{color:var(--gold)}
.tb-nav{display:flex;gap:2px;margin-left:auto}
.tn{background:none;border:none;color:var(--muted);cursor:pointer;
  padding:5px 12px;border-radius:6px;font-size:12px;font-weight:500;transition:.15s}
.tn:hover,.tn.on{color:var(--gold);background:#e8a02010}

/* ── WIZARD PAGE ── */
.wizard{max-width:860px;margin:0 auto;padding:36px 20px 100px}

/* Mode tabs */
.mode-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:28px}
.mode-tab{background:var(--card);border:2px solid var(--border);border-radius:12px;
  padding:20px 24px;cursor:pointer;transition:.15s;position:relative}
.mode-tab:hover,.mode-tab.on{border-color:var(--gold);background:#180e00}
.mode-tab .mt-lbl{font-size:13px;font-weight:800;text-transform:uppercase;
  letter-spacing:.7px;margin-bottom:6px;color:var(--muted)}
.mode-tab.on .mt-lbl{color:var(--gold)}
.mode-tab:hover .mt-lbl{color:var(--gold)}
.mode-tab .mt-desc{font-size:12px;color:var(--muted);line-height:1.5}
.mode-tab .mt-cnt{position:absolute;top:12px;right:14px;
  font-size:10px;color:var(--muted2);font-weight:600}

/* Wizard section */
.wsec{margin-bottom:28px}
.wsec-hd{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.wsec-num{width:26px;height:26px;border-radius:50%;background:var(--card2);
  border:1px solid var(--border);display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:700;color:var(--muted);flex-shrink:0}
.wsec-title{font-size:14px;font-weight:700}
.wsec-hint{font-size:12px;color:var(--muted);margin-left:auto}

/* Channel select row */
.ch-select-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ch-pill{background:var(--card);border:1px solid var(--border);border-radius:99px;
  padding:8px 18px;cursor:pointer;font-size:13px;transition:.15s;white-space:nowrap}
.ch-pill:hover{border-color:var(--muted)}
.ch-pill.on{border-color:var(--gold);background:#1a1200;color:var(--gold);font-weight:600}

/* PRESENTER SECTION */
.presenter-wrap{position:relative}

/* Big preview */
.av-preview{width:100%;height:320px;border-radius:12px;overflow:hidden;
  background:#0d0d0d;border:1px solid var(--border);position:relative;margin-bottom:14px}
.av-preview video,.av-preview img{width:100%;height:100%;object-fit:cover;display:block}
.av-preview-name{position:absolute;bottom:0;left:0;right:0;padding:12px 16px;
  background:linear-gradient(transparent,#000c);font-size:14px;font-weight:700}
.av-preview-desc{font-size:11px;color:#aaa;margin-top:3px;line-height:1.5}
.use-btn{position:absolute;bottom:14px;right:14px;
  background:var(--gold);color:#000;border:none;border-radius:99px;
  padding:8px 18px;font-size:12px;font-weight:700;cursor:pointer;transition:.15s}
.use-btn:hover{background:var(--gold2)}

/* Gender filter */
.gender-row{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.gf{background:none;border:1px solid var(--border);color:var(--muted);
  padding:5px 14px;border-radius:99px;font-size:11px;font-weight:600;cursor:pointer;transition:.15s}
.gf:hover{border-color:var(--muted)}
.gf.on{background:var(--gold);border-color:var(--gold);color:#000}

/* Presenter grid */
.av-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;
  margin-bottom:16px}
.av-card{background:var(--card2);border:2px solid var(--border);border-radius:10px;
  overflow:hidden;cursor:pointer;position:relative;transition:.15s}
.av-card:hover{border-color:#444;transform:translateY(-1px)}
.av-card.on{border-color:var(--gold)}
.av-card-thumb{width:100%;height:110px;object-fit:cover;display:block;background:#111}
.av-card-name{padding:7px 9px;font-size:12px;font-weight:600}
.av-card-icons{position:absolute;top:6px;left:6px;display:flex;gap:4px}
.av-icon-btn{width:24px;height:24px;border-radius:50%;background:#000a;border:none;
  cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:11px;
  color:#fff;backdrop-filter:blur(4px);transition:.15s}
.av-icon-btn:hover{background:#000d}
.av-star{position:absolute;top:6px;right:6px}

/* Seconds slider + appearances */
.slider-row{display:flex;align-items:center;gap:14px;margin-bottom:12px;flex-wrap:wrap}
.slider-lbl{font-size:13px;font-weight:600;white-space:nowrap;min-width:160px}
.slider-lbl span{color:var(--gold)}
.range-slider{flex:1;min-width:160px;accent-color:var(--gold)}
.slider-cost{font-size:11px;color:var(--muted);margin-left:auto;white-space:nowrap}

.appear-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.appear-lbl{font-size:13px;font-weight:600;min-width:100px}
.ap{background:none;border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:99px;font-size:12px;cursor:pointer;transition:.15s}
.ap:hover{border-color:var(--muted)}
.ap.on{background:var(--gold);border-color:var(--gold);color:#000;font-weight:700}

.appear-desc{font-size:12px;color:var(--muted);line-height:1.6;
  padding:10px 0 4px;border-top:1px solid var(--border)}

/* Channel description (shows selected presenter char description) */
.char-desc-box{font-size:12px;color:var(--muted);padding:10px 0;line-height:1.6}
.char-warn{font-size:11px;color:#f97316;margin-top:4px}

/* Title textarea */
.title-area{width:100%;background:var(--card);border:1px solid var(--border);
  border-radius:10px;padding:16px;font-size:14px;color:var(--text);
  line-height:1.7;resize:vertical;outline:none;min-height:100px;transition:.15s}
.title-area:focus{border-color:var(--gold);box-shadow:0 0 0 3px #e8a02010}
.title-area::placeholder{color:var(--muted2)}

/* Length pills */
.len-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.lp{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:8px 18px;border-radius:99px;font-size:13px;cursor:pointer;transition:.15s}
.lp:hover{border-color:var(--muted)}
.lp.on{border-color:var(--gold);background:#1a1200;color:var(--gold);font-weight:700}
.len-other-wrap{display:flex;align-items:center;gap:6px}
.len-other{width:60px;background:var(--card);border:1px solid var(--border);
  border-radius:99px;padding:7px 14px;font-size:13px;color:var(--text);
  outline:none;text-align:center}
.len-other:focus{border-color:var(--gold)}
.len-info{font-size:11px;color:var(--muted);margin-top:6px}

/* CREATE BUTTON */
.create-btn{width:100%;padding:16px;border-radius:12px;border:none;
  background:linear-gradient(135deg,var(--gold),#c07818);color:#000;
  font-size:16px;font-weight:800;cursor:pointer;transition:.15s;
  margin-top:16px;letter-spacing:.5px}
.create-btn:hover{transform:translateY(-2px);box-shadow:0 8px 30px #e8a02030}
.create-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}

/* Cloud render */
.cloud-row{display:flex;align-items:center;gap:10px;margin-top:12px;
  font-size:12px;color:var(--muted)}
.cloud-row input{accent-color:var(--gold)}
.cloud-row strong{color:var(--text)}

/* PROGRESS (inline) */
.prog-wrap{margin-top:14px;display:none}
.prog-wrap.on{display:block}
.pb-hd{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:5px}
.pb{height:5px;background:var(--border);border-radius:99px;overflow:hidden}
.pb-f{height:100%;background:linear-gradient(90deg,var(--gold),var(--gold2));
  border-radius:99px;transition:width .4s}
.log-box{background:#060606;border:1px solid var(--border);border-radius:8px;
  padding:10px 12px;font-family:'Courier New',monospace;font-size:11px;color:#777;
  height:150px;overflow-y:auto;line-height:1.65;margin-top:8px}
.lok{color:#3ecf7e}.lerr{color:#e05555}.linf{color:#4a9eff}

/* QUEUE PREVIEW */
.queue-prev{margin-top:14px}
.qp-item{display:flex;align-items:center;gap:10px;padding:8px 12px;
  background:var(--card);border:1px solid var(--border);border-radius:8px;
  margin-bottom:5px;font-size:12px}
.pill{padding:2px 8px;border-radius:99px;font-size:10px;font-weight:700}
.p-run{background:#4a9eff1a;color:#4a9eff}
.p-done{background:#3ecf7e1a;color:#3ecf7e}
.p-err{background:#e055551a;color:#e05555}
.p-q{background:#fff1;color:#666}

/* ── OTHER PAGES ── */
.page{display:none;max-width:1100px;margin:0 auto;padding:28px 20px}
.page.on{display:block}
.card{background:var(--card);border:1px solid var(--border);border-radius:13px;padding:18px}
.sh h2{font-size:20px;font-weight:700;margin-bottom:4px}
.sh p{font-size:12px;color:var(--muted);margin-bottom:18px}
.lbl{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.7px;margin-bottom:5px;display:block}
.inp{width:100%;background:#0a0a0a;border:1px solid var(--border);border-radius:8px;
  color:var(--text);font-size:13px;padding:9px 13px;outline:none;transition:.15s;resize:vertical}
.inp:focus{border-color:var(--gold);box-shadow:0 0 0 3px #e8a02012}
.sel{appearance:none;cursor:pointer;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23666'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center;padding-right:30px}
.btn{padding:9px 16px;border-radius:8px;border:none;font-size:12px;font-weight:600;cursor:pointer;transition:.15s}
.btn-gold{background:linear-gradient(135deg,var(--gold),#c07818);color:#000}
.btn-gold:hover{transform:translateY(-1px)}
.btn-o{background:none;border:1px solid var(--border);color:var(--text)}
.btn-o:hover{border-color:var(--gold);color:var(--gold)}
.btn-red{background:#e055551a;border:1px solid #e05555;color:#e05555}
.btn-green{background:#3ecf7e1a;border:1px solid #3ecf7e;color:#3ecf7e}
.btn-sm{padding:4px 9px;font-size:11px}
.row{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
.mrow{margin-bottom:12px}

/* Setup tabs */
.stabs{display:flex;gap:5px;margin-bottom:16px;flex-wrap:wrap}
.stab{background:none;border:1px solid var(--border);color:var(--muted);
  padding:6px 14px;border-radius:7px;font-size:12px;cursor:pointer;transition:.15s;position:relative}
.stab:hover{border-color:var(--muted)}
.stab.on{background:var(--card2);border-color:var(--gold);color:var(--gold);font-weight:600}
.stab .dot{width:6px;height:6px;border-radius:50%;position:absolute;top:5px;right:5px}
.dot-r{background:#e05555}.dot-g{background:#3ecf7e}
.sp{display:none}.sp.on{display:block}

/* Quick Paste Bar */
.qp-bar{background:#0d0d0d;border:1px solid var(--gold);border-radius:10px;
  padding:12px 14px;margin-bottom:14px}
.qp-label{font-size:11px;font-weight:700;color:var(--gold);margin-bottom:8px;
  letter-spacing:.3px}
.qp-row{display:flex;gap:8px;align-items:flex-start}
.qp-input{flex:1;background:#111;border:1px solid #2a2300;border-radius:7px;
  color:var(--text);font-size:12px;padding:8px 11px;outline:none;resize:none;
  line-height:1.5;transition:.15s}
.qp-input:focus{border-color:var(--gold);box-shadow:0 0 0 2px #e8a02015}
.qp-input::placeholder{color:#444}
.qp-btn{background:linear-gradient(135deg,var(--gold),#c07818);color:#000;
  border:none;border-radius:7px;padding:8px 16px;font-size:12px;font-weight:800;
  cursor:pointer;white-space:nowrap;transition:.15s;min-width:80px}
.qp-btn:hover{transform:translateY(-1px);box-shadow:0 4px 14px #e8a02030}
.qp-btn:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none}
.qp-hint{font-size:10px;color:#444;margin-top:6px;line-height:1.5}

/* Clip cards */
.upload-zone{border:2px dashed var(--border);border-radius:10px;padding:24px;text-align:center;
  cursor:pointer;transition:.2s;background:#0a0a0a}
.upload-zone:hover,.upload-zone.drag{border-color:var(--gold);background:#130e00}
.clips-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin-top:12px}
.clip-card{background:var(--card2);border:1px solid var(--border);border-radius:8px;overflow:hidden;position:relative}
.clip-card video{width:100%;height:100px;object-fit:cover;display:block}
.clip-info{padding:6px 8px}
.clip-name{font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clip-del{position:absolute;top:4px;right:4px;background:#000b;border:none;border-radius:50%;
  width:20px;height:20px;cursor:pointer;color:#e05555;font-size:11px;
  display:flex;align-items:center;justify-content:center}
.cs-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.cs-full{grid-column:1/-1}

/* Tables */
.tbl{width:100%;border-collapse:collapse}
.tbl th{text-align:left;font-size:10px;text-transform:uppercase;color:var(--muted);
  padding:6px 10px;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid #141414;font-size:12px}
.tbl tr:hover td{background:#ffffff02}

/* Settings */
.sg{display:grid;grid-template-columns:160px 1fr;gap:14px}
.snav{display:flex;flex-direction:column;gap:2px}
.snb{text-align:left;background:none;border:none;color:var(--muted);
  padding:7px 10px;border-radius:6px;cursor:pointer;font-size:12px;transition:.15s}
.snb:hover,.snb.on{background:#e8a02010;color:var(--gold)}
.sp2{display:none}.sp2.on{display:block}
.sr{display:flex;align-items:center;gap:12px;padding:11px 0;border-bottom:1px solid var(--border)}
.sr:last-child{border-bottom:none}
.sl{flex:1}.sl strong{display:block;font-size:12px;margin-bottom:2px}
.sl span{font-size:10px;color:var(--muted)}

/* Competitors */
.cstat-num{font-size:22px;font-weight:800}
.cstat-lbl{font-size:10px;color:var(--muted)}

/* Modal */
.modal-bg{display:none;position:fixed;inset:0;background:#000c;z-index:500;
  align-items:center;justify-content:center}
.modal-bg.on{display:flex}
.modal{background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:22px;width:540px;max-height:84vh;overflow-y:auto;box-shadow:0 20px 60px #000d}
.modal-title{font-size:15px;font-weight:700;color:var(--gold);margin-bottom:14px}
.vtabs{display:flex;gap:5px;margin-bottom:10px}
.vtab{background:none;border:1px solid var(--border);color:var(--muted);
  padding:4px 11px;border-radius:99px;font-size:11px;cursor:pointer;transition:.15s}
.vtab:hover{border-color:var(--muted)}
.vtab.on{background:var(--gold);border-color:var(--gold);color:#000;font-weight:700}
.vgrid{display:grid;grid-template-columns:1fr 1fr;gap:6px;max-height:250px;overflow-y:auto}
.vc{background:#0d0d0d;border:2px solid var(--border);border-radius:7px;
  padding:8px 10px;cursor:pointer;transition:.15s}
.vc:hover{border-color:#555}
.vc.on{border-color:var(--gold);background:#1a1500}
.vc .vn{font-size:11px;font-weight:600}
.vc .vd{font-size:10px;color:var(--muted)}

/* Toast */
.toast-wrap{position:fixed;top:58px;right:14px;z-index:999;display:flex;flex-direction:column;gap:4px}
.toast{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:9px 13px;font-size:12px;min-width:200px;animation:tin .2s;box-shadow:0 6px 20px #000a}
.toast.ok{border-color:#3ecf7e}.toast.er{border-color:#e05555}
@keyframes tin{from{transform:translateX(18px);opacity:0}to{transform:none;opacity:1}}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:#222;border-radius:99px}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="brand">MIB<span>.</span></div>
  <nav class="tb-nav">
    <button class="tn on" onclick="showPage('wizard',this)">Create</button>
    <button class="tn" onclick="showPage('setup',this)">Channel Setup</button>
    <button class="tn" onclick="showPage('jobs',this)">Queue</button>
    <button class="tn" onclick="showPage('competitors',this)">Competitors</button>
    <button class="tn" onclick="showPage('settings',this)">Settings</button>
  </nav>
</div>

<div class="toast-wrap" id="toasts"></div>

<!-- VOICE MODAL -->
<div class="modal-bg" id="voiceModal">
  <div class="modal">
    <div class="modal-title">Select Voice</div>
    <input type="hidden" id="voiceCid">
    <div class="vtabs" id="voiceTabs"></div>
    <div id="voiceListWrap"></div>
    <div style="display:flex;gap:7px;margin-top:12px">
      <button class="btn btn-gold" onclick="saveVoice()">Save</button>
      <button class="btn btn-o" onclick="closeModal('voiceModal')">Cancel</button>
    </div>
  </div>
</div>

<!-- ADD CHANNEL MODAL -->
<div class="modal-bg" id="chModal">
  <div class="modal">
    <div class="modal-title">New Channel</div>
    <div class="mrow"><label class="lbl">Channel ID (slug)</label>
      <input class="inp" id="newChId" placeholder="my-channel"></div>
    <div class="mrow"><label class="lbl">Display Name</label>
      <input class="inp" id="newChName" placeholder="My Channel"></div>
    <div class="mrow"><label class="lbl">Niche</label>
      <input class="inp" id="newChNiche" placeholder="What this channel is about"></div>
    <div class="mrow"><label class="lbl">Mode</label>
      <select class="inp sel" id="newChMode">
        <option value="avatar">AI Avatar</option>
        <option value="frontier">Frontier Production</option>
      </select></div>
    <div style="display:flex;gap:7px;margin-top:10px">
      <button class="btn btn-gold" onclick="createChannel()">Create</button>
      <button class="btn btn-o" onclick="closeModal('chModal')">Cancel</button>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<!-- WIZARD PAGE (main) -->
<!-- ══════════════════════════════════════════════════════════ -->
<div id="page-wizard" class="on" style="display:block">
<div class="wizard">

  <!-- MODE TABS -->
  <div class="mode-row">
    <div class="mode-tab on" id="tab-frontier"
      onmouseenter="hoverMode('frontier')" onclick="clickMode('frontier')">
      <span class="mt-cnt" id="cnt-frontier"></span>
      <div class="mt-lbl">Frontier Production</div>
      <div class="mt-desc">Documentaries and edited videos: real footage, maps, headlines, graphics.</div>
    </div>
    <div class="mode-tab" id="tab-avatar"
      onmouseenter="hoverMode('avatar')" onclick="clickMode('avatar')">
      <span class="mt-cnt" id="cnt-avatar"></span>
      <div class="mt-lbl">AI Avatar</div>
      <div class="mt-desc">A real-looking presenter opens every video, then the pictures take over.</div>
    </div>
  </div>

  <!-- HINT (small) -->
  <div id="mainHint" style="font-size:12px;color:var(--muted);margin-bottom:20px">
    The presenter speaks your first lines to camera, then it cuts to the pictures
    — the cut lands on a pause in the read, never mid-word.
  </div>

  <!-- ── SECTION 1: CHANNEL ── -->
  <div class="wsec" id="sec1">
    <div class="wsec-hd">
      <div class="wsec-num">1</div>
      <div class="wsec-title">Channel</div>
      <div class="wsec-hint" id="chCount"></div>
    </div>
    <div class="ch-select-row" id="chPills"></div>
  </div>

  <!-- ── SECTION 2: PRESENTER ── -->
  <div class="wsec" id="sec2" style="display:none">
    <div class="wsec-hd">
      <div class="wsec-num">2</div>
      <div class="wsec-title">Presenter</div>
      <div class="wsec-hint" id="avCount"></div>
    </div>

    <!-- Big preview -->
    <div class="av-preview" id="avPreview">
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);flex-direction:column;gap:8px">
        <div style="font-size:32px">🎭</div>
        <div style="font-size:13px">Select a presenter below</div>
      </div>
    </div>

    <!-- Gender filter -->
    <div class="gender-row" id="genderFilter">
      <button class="gf on" onclick="filterGender('all',this)">Everyone</button>
      <button class="gf" onclick="filterGender('men',this)">Men</button>
      <button class="gf" onclick="filterGender('women',this)">Women</button>
    </div>

    <!-- Grid of avatar cards -->
    <div class="av-grid" id="avGrid"></div>

    <!-- Seconds slider -->
    <div class="slider-row">
      <div class="slider-lbl">Seconds of presenter: <span id="secVal">8</span></div>
      <input type="range" class="range-slider" id="secSlider" min="5" max="15" value="8"
        oninput="updateSecs(this.value)">
      <div class="slider-cost" id="secCost">≈ $0.30 for the intro, once per video</div>
    </div>

    <!-- Appearances -->
    <div class="appear-row">
      <div class="appear-lbl">Appearances:</div>
      <button class="ap on" onclick="setAppear('intro',this)" data-v="1">Intro only</button>
      <button class="ap" onclick="setAppear('2x',this)" data-v="2">2×</button>
      <button class="ap" onclick="setAppear('3x',this)" data-v="3">3×</button>
      <button class="ap" onclick="setAppear('4x',this)" data-v="4">4×</button>
      <button class="ap" onclick="setAppear('5x',this)" data-v="5">5×</button>
      <button class="ap" onclick="setAppear('6x',this)" data-v="6">6×</button>
    </div>

    <div class="appear-desc" id="appearDesc">
      The presenter opens the video to camera.
    </div>

    <!-- Character description of selected channel -->
    <div class="char-desc-box" id="charDescBox"></div>
  </div>

  <!-- ── SECTION 3: TITLE ── -->
  <div class="wsec" id="sec3">
    <div class="wsec-hd">
      <div class="wsec-num" id="sec3num">2</div>
      <div class="wsec-title">Title</div>
      <div class="wsec-hint">one per line makes several</div>
    </div>
    <textarea class="title-area" id="titleArea" rows="4"
      placeholder="The Shadow You Keep Feeding Without Knowing It"></textarea>
  </div>

  <!-- ── SECTION 4: LENGTH ── -->
  <div class="wsec">
    <div class="wsec-hd">
      <div class="wsec-num" id="sec4num">3</div>
      <div class="wsec-title">Length</div>
      <div class="wsec-hint" id="lenInfo"></div>
    </div>
    <div class="len-row">
      <button class="lp" onclick="setLen(5,this)">5 min</button>
      <button class="lp" onclick="setLen(10,this)">10 min</button>
      <button class="lp" onclick="setLen(20,this)">20 min</button>
      <button class="lp on" onclick="setLen(30,this)">30 min</button>
      <div class="len-other-wrap">
        <span class="lp" style="cursor:default;background:none">other</span>
        <input class="len-other" id="lenOther" type="number" value="30" min="1" max="90"
          oninput="setLen(parseInt(this.value)||30,null)">
      </div>
    </div>
    <div class="len-info" id="lenDetail"></div>
  </div>

  <!-- CREATE BUTTON -->
  <button class="create-btn" id="createBtn" onclick="createVideos()">Create video</button>

  <!-- Cloud render -->
  <div class="cloud-row">
    <input type="checkbox" id="cloudRender">
    <strong>CLOUD RENDER</strong>
    <span>close the laptop — a rented machine makes the video instead</span>
  </div>

  <!-- PROGRESS -->
  <div class="prog-wrap" id="progWrap">
    <div class="pb-hd"><span id="pMsg">Starting...</span><span id="pPct">0%</span></div>
    <div class="pb"><div class="pb-f" id="pFill" style="width:0"></div></div>
    <div class="log-box" id="logBox"></div>
    <div style="margin-top:8px;display:flex;gap:6px" id="resRow"></div>
  </div>

  <!-- QUEUE PREVIEW -->
  <div class="queue-prev" id="qPrev"></div>

</div>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<!-- CHANNEL SETUP PAGE -->
<!-- ══════════════════════════════════════════════════════════ -->
<div id="page-setup" class="page">
  <div class="sh"><h2>Channel Setup</h2>
    <p>Configure avatar clips, character sheet and AI prompt — once per channel.</p>
  </div>
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;flex-wrap:wrap">
    <div style="flex:1;max-width:280px">
      <label class="lbl">Channel</label>
      <select id="chSetupSel" class="inp sel" onchange="loadSetup()"></select>
    </div>
    <div style="margin-top:14px;display:flex;gap:6px">
      <button class="btn btn-o" onclick="openModal('chModal')">+ New Channel</button>
    </div>
    <div id="setupStatus" style="margin-left:auto;font-size:12px;color:var(--muted)"></div>
  </div>
  <div class="stabs">
    <button class="stab on" onclick="showSP('clips',this)">🎭 Avatar Clips<span class="dot dot-r" id="dot-clips"></span></button>
    <button class="stab" onclick="showSP('charsheet',this)">🪪 Character Sheet<span class="dot dot-r" id="dot-charsheet"></span></button>
    <button class="stab" onclick="showSP('prompt',this)">🤖 AI Prompt<span class="dot dot-r" id="dot-prompt"></span></button>
    <button class="stab" onclick="showSP('voice',this)">🎙️ Voice</button>
    <button class="stab" onclick="showSP('chinfo',this)">⚙️ Info</button>
  </div>

  <div id="panel-clips" class="sp on card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
      <div><div style="font-size:13px;font-weight:700">Avatar Clips</div>
        <div style="font-size:11px;color:var(--muted)">Upload 5-15s natural talking MP4 clips</div></div>
      <label class="btn btn-gold" style="cursor:pointer;margin-left:auto">Upload MP4
        <input type="file" id="clipUpload" accept="video/mp4,video/*" multiple style="display:none"
          onchange="uploadClips(this)"></label>
    </div>
    <div class="upload-zone" id="dropZone"
      ondrop="dropClips(event)" ondragover="event.preventDefault();this.classList.add('drag')"
      ondragleave="this.classList.remove('drag')"
      onclick="document.getElementById('clipUpload').click()">
      <div style="font-size:24px">🎬</div>
      <div style="font-size:12px;color:var(--muted);margin-top:6px">Drop MP4 here or click to browse</div>
    </div>
    <div class="clips-grid" id="clipsGrid"></div>
  </div>

  <div id="panel-charsheet" class="sp card">
    <!-- QUICK PASTE BAR -->
    <div style="font-size:13px;font-weight:700;margin-bottom:6px">Character Sheet
      <span style="font-size:10px;color:var(--muted);font-weight:400;margin-left:8px">Identity card — AI uses this to keep character consistent</span>
    </div>
    <div class="qp-bar" id="qpBar">
      <div class="qp-label">⚡ Quick Paste: paste any character description to auto-fill all fields</div>
      <div class="qp-row">
        <textarea class="qp-input" id="qpText" rows="2"
          placeholder="e.g. 68-year-old Amish farmer named Elias Yoder, slim, Caucasian male, traditional hat and suspenders, weathered hands, calm wise personality, earth tones, rustic barn setting..."></textarea>
        <button class="qp-btn" id="qpBtn" onclick="autoFillCharSheet()">Auto-Fill</button>
      </div>
      <div class="qp-hint">Works with any format: competitor description, ChatGPT output, handwritten notes — Gemini extracts all fields automatically</div>
    </div>
    <div class="cs-grid">
      <div><label class="lbl">Full Name</label><input class="inp" id="csName" placeholder="Elias Yoder"></div>
      <div><label class="lbl">Age</label><input class="inp" id="csAge" placeholder="68 years old"></div>
      <div><label class="lbl">Gender</label>
        <select class="inp sel" id="csGender"><option>Male</option><option>Female</option><option>Other</option></select></div>
      <div><label class="lbl">Ethnicity</label><input class="inp" id="csEthnicity" placeholder="Caucasian"></div>
      <div><label class="lbl">Build</label><input class="inp" id="csBuild" placeholder="Slim, 5'10''"></div>
      <div><label class="lbl">Occupation</label><input class="inp" id="csOcc" placeholder="Amish Farmer"></div>
      <div class="cs-full"><label class="lbl">Personality</label>
        <textarea class="inp" id="csPersonality" rows="2" placeholder="Calm, wise..."></textarea></div>
      <div class="cs-full"><label class="lbl">Outfit</label>
        <textarea class="inp" id="csOutfit" rows="2" placeholder="Traditional hat, plain shirt..."></textarea></div>
      <div class="cs-full"><label class="lbl">Key Traits</label>
        <input class="inp" id="csTraits" placeholder="Weathered hands, kind eyes, silver beard"></div>
      <div><label class="lbl">Color Palette</label><input class="inp" id="csColors" placeholder="Earth tones"></div>
      <div><label class="lbl">Setting</label><input class="inp" id="csBg" placeholder="Rustic barn"></div>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
      <button class="btn btn-gold" onclick="saveCharSheet()">Save Character Sheet</button>
      <div id="csAutoMsg" style="font-size:11px;color:var(--muted)"></div>
    </div>
  </div>

  <div id="panel-prompt" class="sp card">
    <div style="font-size:13px;font-weight:700;margin-bottom:10px">AI Consistency Prompt</div>
    <div class="mrow"><label class="lbl">Master Prompt (every scene)</label>
      <textarea class="inp" id="masterPrompt" rows="6" placeholder="Photorealistic 68-year-old Amish farmer..."></textarea></div>
    <div class="mrow"><label class="lbl">Short / 9:16 Clip Prompt</label>
      <textarea class="inp" id="shortPrompt" rows="3" placeholder="Close-up portrait, same character, vertical..."></textarea></div>
    <div class="mrow"><label class="lbl">Negative Prompt</label>
      <input class="inp" id="negPrompt" placeholder="cartoon, plastic skin, neon, young..."></div>
    <button class="btn btn-gold" onclick="savePrompt()">Save</button>
  </div>

  <div id="panel-voice" class="sp card">
    <div style="font-size:13px;font-weight:700;margin-bottom:12px">Voice</div>
    <div id="voiceCurrentInfo" style="padding:10px;background:#111;border-radius:7px;font-size:12px;margin-bottom:12px"></div>
    <button class="btn btn-gold" onclick="openVoiceModal(document.getElementById('chSetupSel').value)">Change Voice</button>
  </div>

  <div id="panel-chinfo" class="sp card">
    <div style="font-size:13px;font-weight:700;margin-bottom:12px">Channel Settings</div>
    <div id="chInfoFields"></div>
    <div style="margin-top:12px;display:flex;gap:7px">
      <button class="btn btn-gold" onclick="saveChInfo()">Save</button>
      <button class="btn btn-red" onclick="deleteChannel()">Delete</button>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<!-- JOBS PAGE -->
<!-- ══════════════════════════════════════════════════════════ -->
<div id="page-jobs" class="page">
  <div class="sh"><h2>Job Queue</h2><p>All video generation jobs</p></div>
  <div style="display:flex;gap:7px;margin-bottom:14px">
    <button class="btn btn-o btn-sm" onclick="loadJobs()">Refresh</button>
    <button class="btn btn-red btn-sm" onclick="clearDone()">Clear done</button>
  </div>
  <table class="tbl">
    <thead><tr><th>Title</th><th>Channel</th><th>Min</th><th>Ratio</th><th>Status</th><th></th></tr></thead>
    <tbody id="jobsTbl"></tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<!-- COMPETITORS PAGE -->
<!-- ══════════════════════════════════════════════════════════ -->
<div id="page-competitors" class="page">
  <div class="sh"><h2>Competitor Intelligence</h2><p>Decode channels with Gemini AI</p></div>
  <div class="card" style="margin-bottom:16px">
    <div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
      <div><div class="cstat-num" style="color:var(--gold)" id="cTotal">92</div><div class="cstat-lbl">Channels</div></div>
      <div><div class="cstat-num" style="color:#3ecf7e" id="cDone">0</div><div class="cstat-lbl">Decoded</div></div>
      <div><div class="cstat-num" style="color:#e05555" id="cFail">0</div><div class="cstat-lbl">Failed</div></div>
      <div style="margin-left:auto;display:flex;gap:6px">
        <button class="btn btn-gold" id="scrapeBtn" onclick="startScrape()">Start</button>
        <button class="btn btn-red" onclick="stopScrape()">Stop</button>
        <button class="btn btn-o" onclick="loadComp()">Refresh</button>
      </div>
    </div>
    <div class="pb"><div class="pb-f" id="cProg" style="width:0"></div></div>
    <div id="cStatus" style="font-size:11px;color:var(--muted);margin-top:5px">Requires Gemini API key.</div>
  </div>
  <table class="tbl">
    <thead><tr><th>Channel</th><th>Niche</th><th>Videos</th><th>Status</th></tr></thead>
    <tbody id="compTbl"></tbody>
  </table>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<!-- SETTINGS PAGE -->
<!-- ══════════════════════════════════════════════════════════ -->
<div id="page-settings" class="page">
  <div class="sh"><h2>Settings</h2><p>API keys and providers</p></div>
  <div class="sg">
    <div class="snav">
      <button class="snb on" onclick="sp2('api',this)">API Keys</button>
      <button class="snb" onclick="sp2('voice',this)">Voiceover</button>
      <button class="snb" onclick="sp2('images',this)">Images</button>
    </div>
    <div>
      <div id="sp2-api" class="sp2 on card">
        <div class="sr"><div class="sl"><strong>Gemini API Key</strong><span>Script, images, TTS, competitors</span></div>
          <input id="kGem" type="password" class="inp" style="width:200px" placeholder="AIza..."></div>
        <div class="sr"><div class="sl"><strong>AI33 Pro</strong><span>Premium TTS</span></div>
          <input id="kAi33" type="password" class="inp" style="width:200px" placeholder="ai33-..."></div>
        <div class="sr"><div class="sl"><strong>xAI / Grok</strong><span>Image generation</span></div>
          <input id="kXai" type="password" class="inp" style="width:200px" placeholder="xai-..."></div>
        <div class="sr"><div class="sl"><strong>Anthropic Claude</strong><span>Script review</span></div>
          <input id="kClaude" type="password" class="inp" style="width:200px" placeholder="sk-ant-..."></div>
        <div style="margin-top:12px"><button class="btn btn-gold" onclick="saveKeys()">Save</button></div>
      </div>
      <div id="sp2-voice" class="sp2 card">
        <div class="sr"><div class="sl"><strong>Edge TTS (Free)</strong><span>47 voices</span></div>
          <span class="pill p-done">Ready</span></div>
        <div class="sr"><div class="sl"><strong>Gemini TTS</strong><span>7 voices</span></div>
          <span class="pill" id="gemTTSpill">—</span></div>
        <div class="sr"><div class="sl"><strong>AI33 Pro TTS</strong></div>
          <span class="pill" id="ai33TTSpill">—</span></div>
        <div class="sr"><div class="sl"><strong>Provider Order</strong></div>
          <select class="inp sel" id="voiceOrder" style="width:230px"
            onchange="saveProv('voice_order',this.value.split(','))">
            <option value="channel,gemini-tts,edge">Channel → Gemini → Edge</option>
            <option value="channel,ai33,gemini-tts,edge">Channel → AI33 → Gemini → Edge</option>
            <option value="channel,edge">Channel → Edge only</option>
          </select></div>
      </div>
      <div id="sp2-images" class="sp2 card">
        <div class="sr"><div class="sl"><strong>Image Order</strong></div>
          <select class="inp sel" id="imgOrder" style="width:210px"
            onchange="saveProv('image_order',this.value.split(','))">
            <option value="grok,gemini,local">Grok → Gemini → Local</option>
            <option value="gemini,grok,local">Gemini → Grok → Local</option>
            <option value="gemini,local">Gemini → Local</option>
          </select></div>
      </div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════ -->
<script>
// ═══════ STATE ═══════
let cfg = {};
let activeMode = 'frontier';
let selCh = null;
let selAv = null;        // {cid, name, thumb, desc}
let secSliderV = 8;
let appearV = 1;         // 1 = intro only
let lenV = 30;
let genderFilter = 'all';
let activeJobId = null;
let activeSSE = null;
let scrapeSSE = null;
let selVoice = null, selVProvider = 'gemini-tts';
let allVoices = {};
let currentSetupCh = null;

// ═══════ PAGE NAV ═══════
function showPage(name, btn) {
  document.getElementById('page-wizard').style.display = 'none';
  document.querySelectorAll('.page').forEach(p => p.classList.remove('on'));
  document.querySelectorAll('.tn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  if (name === 'wizard') {
    document.getElementById('page-wizard').style.display = 'block';
  } else {
    const p = document.getElementById('page-' + name);
    if (p) p.classList.add('on');
    if (name === 'jobs') loadJobs();
    if (name === 'competitors') loadComp();
    if (name === 'settings') loadSettings();
    if (name === 'setup') initSetup();
  }
}
function openModal(id) { document.getElementById(id).classList.add('on'); }
function closeModal(id) { document.getElementById(id).classList.remove('on'); }
function sp2(n, btn) {
  document.querySelectorAll('.sp2').forEach(p => p.classList.remove('on'));
  document.querySelectorAll('.snb').forEach(b => b.classList.remove('on'));
  document.getElementById('sp2-' + n).classList.add('on'); btn.classList.add('on');
}

// ═══════ INIT ═══════
async function init() {
  const r = await fetch('/api/config');
  cfg = await r.json();
  updateModeCounts();
  renderChPills();
  updateLenInfo();
}

// ═══════ MODE TABS ═══════
function hoverMode(mode) {
  document.getElementById('tab-frontier').classList.toggle('on', mode === 'frontier');
  document.getElementById('tab-avatar').classList.toggle('on', mode === 'avatar');
  activeMode = mode;
  selCh = null; selAv = null;
  renderChPills();
  updateSec2();
}
function clickMode(mode) {
  activeMode = mode;
  hoverMode(mode);
}
function updateModeCounts() {
  const ch = cfg.channels || {};
  const fc = Object.values(ch).filter(c => c.mode === 'frontier').length;
  const ac = Object.values(ch).filter(c => c.mode === 'avatar').length;
  document.getElementById('cnt-frontier').textContent = fc + ' channels';
  document.getElementById('cnt-avatar').textContent = ac + ' channels';
}

// ═══════ SECTION 1 — CHANNEL ═══════
function renderChPills() {
  const ch = cfg.channels || {};
  const filtered = Object.entries(ch).filter(([, c]) => c.mode === activeMode);
  const el = document.getElementById('chPills');
  document.getElementById('chCount').textContent = filtered.length + ' channels';
  el.innerHTML = filtered.map(([cid, c]) =>
    `<div class="ch-pill${cid === selCh ? ' on' : ''}" onclick="selectCh('${cid}')">${c.name || cid}</div>`
  ).join('') +
  `<button class="btn btn-o btn-sm" onclick="showPage('setup',document.querySelector('.tn:nth-child(2)'))">+ Add</button>`;
}
async function selectCh(cid) {
  selCh = cid; selAv = null;
  renderChPills();
  await loadAvGrid();
  updateSec2();
  updateSec3Num();
}

// ═══════ SECTION 2 — PRESENTER ═══════
function updateSec2() {
  const show = activeMode === 'avatar' && selCh;
  document.getElementById('sec2').style.display = show ? '' : 'none';
  document.getElementById('sec3num').textContent = show ? '3' : '2';
  document.getElementById('sec4num').textContent = show ? '4' : '3';
}
function updateSec3Num() { updateSec2(); }

async function loadAvGrid() {
  if (!selCh) return;
  const r = await fetch('/api/avatars-rich/' + selCh);
  const avs = await r.json();

  document.getElementById('avCount').textContent = avs.length + ' presenters';

  // Show char description of channel
  const ch = (cfg.channels || {})[selCh] || {};
  const cs = ch.character || {};
  const desc = cs.name ? `${cs.name} — ${cs.age_desc || ''} ${cs.gender || ''}, ${cs.occupation || ''}. ${cs.outfit || ''}`
    : '';
  const voice = (ch.voice || {});
  document.getElementById('charDescBox').innerHTML = desc
    ? `<span>${desc.trim()}</span>`
    : '<span style="color:var(--muted2)">No character sheet yet — set in Channel Setup</span>';

  // Build grid
  const grid = document.getElementById('avGrid');
  grid.innerHTML = avs.map((a, i) => `
    <div class="av-card${selAv && selAv.name === a.name ? ' on' : ''}"
      id="avc-${i}" onclick="selectAv(${JSON.stringify(JSON.stringify(a))},${i})">
      ${a.thumb
        ? `<img class="av-card-thumb" src="/api/avatar-thumb/${selCh}/${encodeURIComponent(a.thumb_name)}" loading="lazy">`
        : `<div class="av-card-thumb" style="display:flex;align-items:center;justify-content:center;font-size:28px">🎭</div>`
      }
      <div class="av-card-name">${a.label}</div>
    </div>`).join('') +
    `<div class="av-card av-new" onclick="showPage('setup',document.querySelector('.tn:nth-child(2)'))"
      style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;min-height:130px;border-style:dashed">
      <div style="font-size:24px;color:var(--gold)">+</div>
      <div style="font-size:11px;color:var(--muted)">Upload clip</div>
    </div>`;

  // Auto-select first
  if (avs.length && !selAv) selectAv(JSON.stringify(avs[0]), 0);
}

function selectAv(jsonStr, idx) {
  const a = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr;
  selAv = a;
  document.querySelectorAll('.av-card').forEach(c => c.classList.remove('on'));
  const card = document.getElementById('avc-' + idx);
  if (card) card.classList.add('on');
  updatePreview(a);
}

function updatePreview(a) {
  const prev = document.getElementById('avPreview');
  if (a.thumb) {
    prev.innerHTML = `
      <img src="/api/avatar-thumb/${selCh}/${encodeURIComponent(a.thumb_name)}"
        style="width:100%;height:100%;object-fit:cover;display:block">
      <div class="av-preview-name">${a.label}
        <div class="av-preview-desc">${a.desc || ''}</div>
      </div>
      <button class="use-btn" onclick="this.textContent='Selected ✓';this.style.background='#3ecf7e'">Use this presenter</button>`;
  } else {
    prev.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;flex-direction:column;gap:8px">
        <div style="font-size:48px">🎭</div>
        <div style="font-size:14px;font-weight:700">${a.label}</div>
        <div style="font-size:11px;color:var(--muted)">${a.desc || 'No description yet'}</div>
      </div>`;
  }
}

function filterGender(g, btn) {
  genderFilter = g;
  document.querySelectorAll('.gf').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
}

function updateSecs(v) {
  secSliderV = parseInt(v);
  document.getElementById('secVal').textContent = v;
  const cost = (secSliderV * 0.038).toFixed(2);
  document.getElementById('secCost').textContent = `≈ $${cost} for the intro, once per video`;
  updateLenInfo();
}

function setAppear(key, btn) {
  const map = {intro:1,'2x':2,'3x':3,'4x':4,'5x':5,'6x':6};
  appearV = map[key] || 1;
  document.querySelectorAll('.ap').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  const desc = appearV === 1
    ? 'The presenter opens the video to camera.'
    : `Beyond the intro the presenter comes back ${appearV - 1} more time${appearV > 2 ? 's' : ''} during the video, on a pause in the read; while the presenter is on screen nothing else is shown.`;
  document.getElementById('appearDesc').textContent = desc;
  updateLenInfo();
}

// ═══════ LENGTH ═══════
function setLen(v, btn) {
  lenV = v;
  if (btn) {
    document.querySelectorAll('.lp').forEach(b => b.classList.remove('on'));
    btn.classList.add('on');
  }
  document.getElementById('lenOther').value = v;
  updateLenInfo();
}
function updateLenInfo() {
  const renderMins = Math.round(lenV * 2.2);
  const cost = (lenV * 0.148 + appearV * secSliderV * 0.038).toFixed(2);
  document.getElementById('lenInfo').textContent =
    `about ${renderMins} min to render · about $${cost} in API costs`;
  document.getElementById('lenDetail').textContent =
    `${lenV} minute video · ${Math.round(lenV * 140)} words of script · ~${Math.round(lenV * 60 / 45)} images`;
  // AR info
  const ar = lenV <= 3 ? '9:16 Short' : lenV <= 10 ? '1:1' : '16:9';
  document.getElementById('lenDetail').textContent +=
    ` · ${ar} aspect ratio`;
}

// ═══════ CREATE ═══════
async function createVideos() {
  const raw = document.getElementById('titleArea').value;
  const titles = raw.split('\n').map(t => t.trim()).filter(Boolean);
  if (!titles.length) { toast('Enter at least one title', 'er'); return; }
  if (!selCh) { toast('Select a channel', 'er'); return; }

  const btn = document.getElementById('createBtn');
  btn.disabled = true; btn.textContent = 'Queuing...';

  for (const t of titles) {
    await addJob({ title: t, channel_id: selCh,
                   avatar: selAv?.name || '',
                   minutes: lenV,
                   presenter_seconds: secSliderV,
                   appearances: appearV });
  }
  btn.disabled = false;
  btn.textContent = titles.length > 1 ? `${titles.length} videos queued!` : 'Create video';
  setTimeout(() => { btn.textContent = 'Create video'; }, 3000);
}

async function addJob(params) {
  const r = await fetch('/api/generate', { method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(params) });
  const d = await r.json();
  if (!d.job_id) { toast('Failed: ' + (d.error||''), 'er'); return; }
  refreshQPrev();
  if (!activeJobId) listenNextJob();
}

function listenNextJob() {
  fetch('/api/jobs').then(r => r.json()).then(jobs => {
    const next = jobs.find(j => j.status === 'running') || jobs.find(j => j.status === 'queued');
    if (!next) return;
    activeJobId = next.job_id;
    const pw = document.getElementById('progWrap');
    pw.classList.add('on');
    document.getElementById('logBox').innerHTML = '';
    document.getElementById('resRow').innerHTML = '';
    setProg(0, 'Starting...');
    if (activeSSE) activeSSE.close();
    activeSSE = new EventSource('/api/job/' + activeJobId + '/stream');
    activeSSE.onmessage = e => {
      const d = JSON.parse(e.data);
      if (d.type === 'progress') setProg(d.pct, d.msg);
      else if (d.type === 'log') appendLog(d.msg);
      else if (d.type === 'done') {
        activeSSE.close(); activeJobId = null;
        refreshQPrev();
        if (d.ok) {
          setProg(100, 'Done!'); toast('Video ready!', 'ok');
          if (d.final_mp4)
            document.getElementById('resRow').innerHTML =
              `<a href="/api/job/${activeJobId}/download" class="btn btn-green">Download MP4</a>`;
        } else { setProg(0, 'Failed: ' + (d.error||'')); toast('Failed', 'er'); }
        setTimeout(listenNextJob, 2000);
      }
    };
  });
}
function setProg(pct, msg) {
  document.getElementById('pFill').style.width = pct + '%';
  document.getElementById('pPct').textContent = pct + '%';
  document.getElementById('pMsg').textContent = msg;
}
function appendLog(msg) {
  const b = document.getElementById('logBox');
  const d = document.createElement('div');
  d.className = msg.includes('ERROR') || msg.includes('fail') ? 'lerr'
    : msg.includes('OK') || msg.includes('done') ? 'lok' : '';
  d.textContent = msg; b.appendChild(d); b.scrollTop = b.scrollHeight;
}

async function refreshQPrev() {
  const jobs = await fetch('/api/jobs').then(r => r.json());
  const pending = jobs.filter(j => j.status !== 'done' && j.status !== 'error');
  const el = document.getElementById('qPrev');
  if (!pending.length) { el.innerHTML = ''; return; }
  el.innerHTML = `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">Queue (${pending.length} pending)</div>` +
    pending.map(j => {
      const pc = j.status === 'running' ? 'p-run' : 'p-q';
      return `<div class="qp-item"><span class="pill ${pc}">${j.status}</span>
        <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${j.title}</span>
        <span style="color:var(--muted)">${j.channel_id} · ${j.minutes}min</span></div>`;
    }).join('');
}

// ═══════ JOBS ═══════
async function loadJobs() {
  const jobs = await fetch('/api/jobs').then(r => r.json());
  const tb = document.getElementById('jobsTbl');
  if (!tb) return;
  tb.innerHTML = '';
  for (const j of [...jobs].reverse()) {
    const pc = j.status === 'done' ? 'p-done' : j.status === 'running' ? 'p-run'
      : j.status === 'error' ? 'p-err' : 'p-q';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600">${j.title}</td>
      <td style="color:var(--muted)">${j.channel_id}</td>
      <td>${j.minutes}</td><td>${j.ratio||'16:9'}</td>
      <td><span class="pill ${pc}">${j.status}</span></td>
      <td>${j.status==='done'&&j.final_mp4?`<a href="/api/job/${j.job_id}/download" class="btn btn-green btn-sm">Download</a>`:''}</td>`;
    tb.appendChild(tr);
  }
}
async function clearDone() {
  await fetch('/api/jobs/clear', {method:'POST'});
  loadJobs(); toast('Cleared', 'ok');
}

// ═══════ CHANNEL SETUP ═══════
function initSetup() {
  const sel = document.getElementById('chSetupSel');
  const ch = cfg.channels || {};
  sel.innerHTML = Object.entries(ch).map(([cid, c]) =>
    `<option value="${cid}">${c.name||cid}</option>`).join('');
  if (!currentSetupCh && sel.options.length) currentSetupCh = sel.value;
  else if (currentSetupCh) sel.value = currentSetupCh;
  loadSetup();
}
async function loadSetup() {
  currentSetupCh = document.getElementById('chSetupSel').value;
  if (!currentSetupCh) return;
  const ch = (cfg.channels||{})[currentSetupCh]||{};
  const cs = ch.character||{}; const p = ch.prompts||{};
  document.getElementById('csName').value = cs.name||'';
  document.getElementById('csAge').value = cs.age_desc||'';
  document.getElementById('csGender').value = cs.gender||'Male';
  document.getElementById('csEthnicity').value = cs.ethnicity||'';
  document.getElementById('csBuild').value = cs.build||'';
  document.getElementById('csOcc').value = cs.occupation||'';
  document.getElementById('csPersonality').value = cs.personality||'';
  document.getElementById('csOutfit').value = cs.outfit||'';
  document.getElementById('csTraits').value = cs.traits||'';
  document.getElementById('csColors').value = cs.colors||'';
  document.getElementById('csBg').value = cs.background||'';
  document.getElementById('masterPrompt').value = p.master||'';
  document.getElementById('shortPrompt').value = p.short||'';
  document.getElementById('negPrompt').value = p.negative||'';
  const clips = await fetch('/api/avatars/'+currentSetupCh).then(r=>r.json());
  document.getElementById('dot-clips').className = 'dot '+(clips.length?'dot-g':'dot-r');
  document.getElementById('dot-charsheet').className = 'dot '+(cs.name?'dot-g':'dot-r');
  document.getElementById('dot-prompt').className = 'dot '+(p.master?'dot-g':'dot-r');
  const done=(clips.length?1:0)+(cs.name?1:0)+(p.master?1:0);
  document.getElementById('setupStatus').textContent = done+'/3 configured';
  document.getElementById('setupStatus').style.color = done===3?'#3ecf7e':'var(--muted)';
  loadClips(); loadVoiceTab(); loadChInfo();
}
function showSP(n, btn) {
  document.querySelectorAll('.sp').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.stab').forEach(b=>b.classList.remove('on'));
  document.getElementById('panel-'+n).classList.add('on'); btn.classList.add('on');
  if(n==='clips') loadClips(); if(n==='voice') loadVoiceTab(); if(n==='chinfo') loadChInfo();
}
async function loadClips() {
  if (!currentSetupCh) return;
  const clips = await fetch('/api/avatars/'+currentSetupCh).then(r=>r.json());
  const grid = document.getElementById('clipsGrid'); if (!grid) return;
  grid.innerHTML = '';
  for (const c of clips) {
    const card = document.createElement('div'); card.className='clip-card';
    card.innerHTML = `<video src="/api/avatar-clip/${currentSetupCh}/${encodeURIComponent(c.name)}"
      muted loop preload="metadata"
      onmouseover="this.play()" onmouseout="this.pause();this.currentTime=0"></video>
      <div class="clip-info"><div class="clip-name">${c.name.replace(/\.[^.]+$/,'')}</div>
      <div class="clip-dur" style="font-size:10px;color:var(--muted)">${c.size||''}</div></div>
      <button class="clip-del" onclick="deleteClip('${c.name}')">✕</button>`;
    grid.appendChild(card);
  }
}
async function uploadClips(input) {
  if(!currentSetupCh){toast('Select channel','er');return;}
  for(const f of input.files){
    const fd=new FormData(); fd.append('file',f); fd.append('channel_id',currentSetupCh);
    const r=await fetch('/api/avatar-clip/upload',{method:'POST',body:fd});
    const d=await r.json(); if(!d.ok) toast('Upload failed: '+d.error,'er');
  }
  toast(input.files.length+' uploaded!','ok'); input.value=''; loadClips();
  document.getElementById('dot-clips').className='dot dot-g';
}
async function dropClips(e) {
  e.preventDefault(); document.getElementById('dropZone').classList.remove('drag');
  const input=document.getElementById('clipUpload');
  const dt=new DataTransfer();
  for(const f of e.dataTransfer.files) dt.items.add(f);
  input.files=dt.files; await uploadClips(input);
}
async function deleteClip(name) {
  if(!confirm('Delete?')) return;
  await fetch('/api/avatar-clip/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:currentSetupCh,name})});
  loadClips(); toast('Deleted','ok');
}
async function autoFillCharSheet() {
  const raw = document.getElementById('qpText').value.trim();
  if (!raw) { toast('Paste a character description first', 'er'); return; }
  const btn = document.getElementById('qpBtn');
  btn.disabled = true; btn.textContent = 'Parsing...';
  document.getElementById('csAutoMsg').textContent = 'Gemini is reading your text...';
  try {
    const r = await fetch('/api/character-sheet/parse', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: raw})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Parse failed');
    const c = d.character;
    if (c.name)        document.getElementById('csName').value = c.name;
    if (c.age_desc)    document.getElementById('csAge').value = c.age_desc;
    if (c.gender)      document.getElementById('csGender').value = c.gender;
    if (c.ethnicity)   document.getElementById('csEthnicity').value = c.ethnicity;
    if (c.build)       document.getElementById('csBuild').value = c.build;
    if (c.occupation)  document.getElementById('csOcc').value = c.occupation;
    if (c.personality) document.getElementById('csPersonality').value = c.personality;
    if (c.outfit)      document.getElementById('csOutfit').value = c.outfit;
    if (c.traits)      document.getElementById('csTraits').value = c.traits;
    if (c.colors)      document.getElementById('csColors').value = c.colors;
    if (c.background)  document.getElementById('csBg').value = c.background;
    // Flash fields gold
    document.querySelectorAll('.cs-grid .inp').forEach(el => {
      el.style.borderColor = 'var(--gold)';
      setTimeout(() => el.style.borderColor = '', 2000);
    });
    document.getElementById('csAutoMsg').textContent = '\u2713 All fields filled! Review and save.';
    document.getElementById('csAutoMsg').style.color = '#3ecf7e';
    document.getElementById('qpText').value = '';
    toast('Auto-filled from your text!', 'ok');
  } catch(e) {
    document.getElementById('csAutoMsg').textContent = 'Error: ' + e.message;
    document.getElementById('csAutoMsg').style.color = '#e05555';
    toast('Auto-fill failed: ' + e.message, 'er');
  }
  btn.disabled = false; btn.textContent = 'Auto-Fill';
}
async function saveCharSheet() {

  if(!currentSetupCh) return;
  const char={name:document.getElementById('csName').value.trim(),age_desc:document.getElementById('csAge').value.trim(),
    gender:document.getElementById('csGender').value,ethnicity:document.getElementById('csEthnicity').value.trim(),
    build:document.getElementById('csBuild').value.trim(),occupation:document.getElementById('csOcc').value.trim(),
    personality:document.getElementById('csPersonality').value.trim(),outfit:document.getElementById('csOutfit').value.trim(),
    traits:document.getElementById('csTraits').value.trim(),colors:document.getElementById('csColors').value.trim(),
    background:document.getElementById('csBg').value.trim()};
  const r=await fetch('/api/channel/character',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:currentSetupCh,character:char})});
  const d=await r.json();
  if(d.ok){toast('Saved!','ok');document.getElementById('dot-charsheet').className='dot '+(char.name?'dot-g':'dot-r');cfg=await fetch('/api/config').then(r=>r.json());}
  else toast('Error: '+d.error,'er');
}
async function savePrompt() {
  if(!currentSetupCh) return;
  const prompts={master:document.getElementById('masterPrompt').value.trim(),short:document.getElementById('shortPrompt').value.trim(),negative:document.getElementById('negPrompt').value.trim()};
  const r=await fetch('/api/channel/prompts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:currentSetupCh,prompts})});
  const d=await r.json();
  if(d.ok){toast('Saved!','ok');document.getElementById('dot-prompt').className='dot '+(prompts.master?'dot-g':'dot-r');cfg=await fetch('/api/config').then(r=>r.json());}
  else toast('Error: '+d.error,'er');
}
function loadVoiceTab() {
  if(!currentSetupCh) return;
  const ch=(cfg.channels||{})[currentSetupCh]||{};
  const v=ch.voice||{};
  document.getElementById('voiceCurrentInfo').innerHTML = v.provider
    ? `<strong>${v.provider}</strong> — ${v.voice_id}`
    : '<span style="color:var(--muted)">No voice set — default Gemini TTS</span>';
}
function loadChInfo() {
  if(!currentSetupCh) return;
  const ch=(cfg.channels||{})[currentSetupCh]||{};
  document.getElementById('chInfoFields').innerHTML = `
    <div class="mrow"><label class="lbl">Display Name</label><input class="inp" id="ciName" value="${ch.name||''}"></div>
    <div class="mrow"><label class="lbl">Niche</label><input class="inp" id="ciNiche" value="${ch.niche||''}"></div>
    <div class="mrow"><label class="lbl">Mode</label>
      <select class="inp sel" id="ciMode">
        <option value="avatar" ${ch.mode==='avatar'?'selected':''}>AI Avatar</option>
        <option value="frontier" ${ch.mode==='frontier'?'selected':''}>Frontier</option>
      </select></div>
    <div class="mrow"><label class="lbl">Default Minutes</label>
      <input class="inp" type="number" id="ciMins" value="${ch.default_minutes||30}" style="width:80px"></div>`;
}
async function saveChInfo() {
  const body={channel_id:currentSetupCh,name:document.getElementById('ciName').value.trim(),
    niche:document.getElementById('ciNiche').value.trim(),mode:document.getElementById('ciMode').value,
    default_minutes:parseInt(document.getElementById('ciMins').value)||30};
  const r=await fetch('/api/channel/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.ok){toast('Saved!','ok');cfg=await fetch('/api/config').then(r=>r.json());updateModeCounts();renderChPills();}
  else toast('Error: '+d.error,'er');
}
async function deleteChannel() {
  if(!confirm('Delete?')) return;
  await fetch('/api/channel/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:currentSetupCh})});
  toast('Deleted','ok'); cfg=await fetch('/api/config').then(r=>r.json()); initSetup(); renderChPills(); updateModeCounts();
}
async function createChannel() {
  const cid=document.getElementById('newChId').value.trim().toLowerCase().replace(/\s+/g,'-').replace(/[^a-z0-9-]/g,'');
  if(!cid){toast('ID required','er');return;}
  const body={channel_id:cid,name:document.getElementById('newChName').value.trim()||cid,
    niche:document.getElementById('newChNiche').value.trim(),mode:document.getElementById('newChMode').value,
    avatar_clip_mode:'static',default_minutes:30};
  const r=await fetch('/api/channel/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.ok){toast('Created!','ok');closeModal('chModal');await fetch('/api/avatar-dir/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:cid})});
    cfg=await fetch('/api/config').then(r=>r.json());renderChPills();updateModeCounts();initSetup();document.getElementById('chSetupSel').value=cid;currentSetupCh=cid;loadSetup();}
  else toast('Error: '+d.error,'er');
}

// ═══════ VOICE MODAL ═══════
async function openVoiceModal(cid) {
  document.getElementById('voiceCid').value=cid;
  const ch=(cfg.channels||{})[cid]||{}; const v=ch.voice||{};
  selVProvider=v.provider||'gemini-tts'; selVoice=v.voice_id||'';
  openModal('voiceModal');
  document.getElementById('voiceListWrap').innerHTML='<div style="color:var(--muted);padding:10px">Loading...</div>';
  allVoices=await fetch('/api/voices').then(r=>r.json());
  renderVTabs();
}
function renderVTabs() {
  const ps=[{id:'gemini-tts',lbl:`Gemini (${(allVoices.gemini||[]).length})`},{id:'edge',lbl:`Edge (${(allVoices.edge||[]).length})`},{id:'ai33',lbl:`AI33 (${(allVoices.ai33||[]).length})`}];
  document.getElementById('voiceTabs').innerHTML=ps.map(p=>`<button class="vtab${p.id===selVProvider?' on':''}" onclick="switchVTab('${p.id}',this)">${p.lbl}</button>`).join('');
  renderVList();
}
function switchVTab(pid,btn){selVProvider=pid;document.querySelectorAll('.vtab').forEach(b=>b.classList.remove('on'));btn.classList.add('on');renderVList();}
function renderVList(){
  const vs=(allVoices[selVProvider==='gemini-tts'?'gemini':selVProvider]||[]);
  if(!vs.length){document.getElementById('voiceListWrap').innerHTML='<div style="color:var(--muted);padding:10px">No voices</div>';return;}
  document.getElementById('voiceListWrap').innerHTML='<div class="vgrid">'+vs.slice(0,100).map(v=>`<div class="vc${v.id===selVoice?' on':''}" onclick="pickV('${v.id}',this)"><div class="vn">${v.name||v.id}</div><div class="vd">${v.gender||''}</div></div>`).join('')+'</div>';
}
function pickV(vid,el){selVoice=vid;document.querySelectorAll('.vc').forEach(c=>c.classList.remove('on'));el.classList.add('on');}
async function saveVoice(){
  if(!selVoice){toast('Select voice','er');return;}
  const cid=document.getElementById('voiceCid').value;
  const r=await fetch('/api/channel/voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel_id:cid,provider:selVProvider,voice_id:selVoice})});
  const d=await r.json();
  if(d.ok){toast('Saved!','ok');closeModal('voiceModal');cfg=await fetch('/api/config').then(r=>r.json());loadVoiceTab();}
  else toast('Error: '+d.error,'er');
}

// ═══════ COMPETITORS ═══════
async function loadComp(){
  const d=await fetch('/api/competitors').then(r=>r.json());
  document.getElementById('cTotal').textContent=d.total||92;
  document.getElementById('cDone').textContent=d.done||0;
  document.getElementById('cFail').textContent=d.failed||0;
  document.getElementById('cProg').style.width=(d.total?Math.round(d.done/d.total*100):0)+'%';
  const tb=document.getElementById('compTbl');tb.innerHTML='';
  for(const c of (d.channels||[])){
    const pc=c.status==='done'?'p-done':c.status==='error'?'p-err':'p-q';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td style="font-weight:600">${c.handle}</td><td style="color:var(--muted)">${c.niche||'?'}</td><td>${c.decoded||0}</td><td><span class="pill ${pc}">${c.status||'pending'}</span></td>`;
    tb.appendChild(tr);
  }
}
async function startScrape(){
  const r=await fetch('/api/competitors/scrape',{method:'POST'});const d=await r.json();
  if(!d.ok){toast(d.error||'Set Gemini key','er');return;}
  document.getElementById('scrapeBtn').disabled=true;
  if(scrapeSSE)scrapeSSE.close();
  scrapeSSE=new EventSource('/api/competitors/stream');
  scrapeSSE.onmessage=e=>{const d=JSON.parse(e.data);
    if(d.type==='progress'){document.getElementById('cProg').style.width=d.pct+'%';document.getElementById('cStatus').textContent=d.msg;}
    else if(d.type==='done'){scrapeSSE.close();document.getElementById('scrapeBtn').disabled=false;loadComp();toast('Done!','ok');}};
}
async function stopScrape(){await fetch('/api/competitors/stop',{method:'POST'});if(scrapeSSE)scrapeSSE.close();document.getElementById('scrapeBtn').disabled=false;}

// ═══════ SETTINGS ═══════
async function loadSettings(){
  const d=await fetch('/api/settings').then(r=>r.json());
  if(d.has_gemini)document.getElementById('kGem').placeholder='●●●● saved ●●●●';
  if(d.has_ai33)document.getElementById('kAi33').placeholder='●●●● saved ●●●●';
  if(d.has_xai)document.getElementById('kXai').placeholder='●●●● saved ●●●●';
  if(d.has_claude)document.getElementById('kClaude').placeholder='●●●● saved ●●●●';
  const gp=document.getElementById('gemTTSpill');const ap=document.getElementById('ai33TTSpill');
  gp.textContent=d.has_gemini?'Ready':'No key';gp.className='pill '+(d.has_gemini?'p-done':'p-err');
  ap.textContent=d.has_ai33?'Ready':'—';ap.className='pill '+(d.has_ai33?'p-done':'p-q');
}
async function saveKeys(){
  const body={};const gem=document.getElementById('kGem').value.trim();const ai33=document.getElementById('kAi33').value.trim();
  const xai=document.getElementById('kXai').value.trim();const claude=document.getElementById('kClaude').value.trim();
  if(gem)body.gemini_api_key=gem;if(ai33)body.ai33pro_api_key=ai33;if(xai)body.xai_api_key=xai;if(claude)body.anthropic_api_key=claude;
  const r=await fetch('/api/settings/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();toast(d.ok?'Saved!':'Error: '+d.error,d.ok?'ok':'er');
}
async function saveProv(k,v){await fetch('/api/settings/provider',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k,value:v})});toast('Saved','ok');}

// ═══════ TOAST ═══════
function toast(msg,type=''){
  const w=document.getElementById('toasts');const el=document.createElement('div');
  el.className='toast '+(type==='ok'?'ok':type==='er'?'er':'');
  el.textContent=(type==='ok'?'✅ ':type==='er'?'❌ ':'ℹ️ ')+msg;
  w.appendChild(el);setTimeout(()=>el.remove(),4000);
}

// BOOT
init();
</script>
</body></html>"""

# ─────────────────────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/config")
def api_config():
    return jsonify({"channels": load_config().get("channels", {}),
                    "providers": load_config().get("providers", {})})

@app.route("/api/settings")
def api_settings():
    c = load_config(); sec = load_secrets(); p = c.get("providers", {})
    return jsonify({"has_gemini": bool(sec.get("gemini_api_key")),
                    "has_ai33": bool(sec.get("ai33pro_api_key")),
                    "has_xai": bool(sec.get("xai_api_key")),
                    "has_claude": bool(sec.get("anthropic_api_key")),
                    "voice_order": p.get("voice_order", ["channel","gemini-tts","edge"]),
                    "image_order": p.get("image_order", ["grok","gemini","local"]),
                    "claude_review": p.get("claude_review", False)})

@app.route("/api/settings/keys", methods=["POST"])
def api_save_keys():
    try:
        sec = load_secrets(); data = request.json or {}
        for k in ["gemini_api_key","ai33pro_api_key","xai_api_key","anthropic_api_key"]:
            if data.get(k): sec[k] = data[k]
        save_secrets(sec); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/settings/provider", methods=["POST"])
def api_save_prov():
    try:
        c = load_config(); data = request.json or {}
        c.setdefault("providers", {})[data["key"]] = data["value"]
        save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/voices")
def api_voices():
    try:
        from mib.providers import edgevoice, geminitts
        ev = edgevoice.list_voices(); gv = geminitts.VOICES
        ai33_v = []
        try:
            sec = load_secrets(); key = (sec.get("ai33pro_api_key") or "").strip()
            if key:
                from mib.providers import ai33voice
                ai33_v = ai33voice.list_voices(key, page_size=60)
        except: pass
        return jsonify({"edge": ev, "gemini": gv, "ai33": ai33_v})
    except Exception as e:
        return jsonify({"edge": [], "gemini": [], "ai33": [], "error": str(e)})

# ── AVATARS ───────────────────────────────────────────────────────────────────
def _av_dir(cid): return AVATAR_DIR / cid

@app.route("/api/avatars/<cid>")
def api_avatars_ch(cid):
    d = _av_dir(cid); d.mkdir(parents=True, exist_ok=True)
    clips = []
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in (".mp4", ".mov", ".webm", ".avi"):
            try:
                sz = f.stat().st_size
                clips.append({"name": f.name,
                               "size": f"{sz//1024}KB" if sz < 1024*1024 else f"{sz//1024//1024}MB"})
            except: pass
    return jsonify(clips)

@app.route("/api/avatars-rich/<cid>")
def api_avatars_rich(cid):
    """Return avatar clips with thumbnail info and character description."""
    d = _av_dir(cid); d.mkdir(parents=True, exist_ok=True)
    ch = (load_config().get("channels") or {}).get(cid, {})
    cs = ch.get("character") or {}
    base_desc = ""
    if cs.get("name"):
        parts = [cs.get("age_desc",""), cs.get("ethnicity",""), cs.get("occupation","")]
        base_desc = ", ".join(p for p in parts if p)
        if cs.get("outfit"): base_desc += ". " + cs["outfit"]

    clips = []
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in (".mp4", ".mov", ".webm", ".avi"):
            try:
                # Ensure thumbnail exists
                thumb = ensure_thumbnail(f)
                thumb_name = thumb.name if thumb else None
                clips.append({
                    "name": f.name,
                    "label": f.stem.replace("_", " ").replace("-", " ").title()[:20],
                    "thumb": bool(thumb),
                    "thumb_name": thumb_name or "",
                    "desc": base_desc,
                    "gender": cs.get("gender", ""),
                })
            except: pass
    return jsonify(clips)

@app.route("/api/avatar-thumb/<cid>/<path:name>")
def api_avatar_thumb(cid, name):
    f = _av_dir(cid) / name
    if not f.is_file(): return "Not found", 404
    return send_file(str(f), mimetype="image/jpeg")

@app.route("/api/avatar-clip/<cid>/<path:name>")
def api_avatar_clip(cid, name):
    f = _av_dir(cid) / name
    if not f.is_file(): return "Not found", 404
    mt, _ = mimetypes.guess_type(str(f))
    return send_file(str(f), mimetype=mt or "video/mp4")

@app.route("/api/avatar-clip/upload", methods=["POST"])
def api_clip_upload():
    try:
        cid = request.form.get("channel_id", "").strip()
        f   = request.files.get("file")
        if not cid or not f: return jsonify({"ok": False, "error": "channel_id and file required"})
        d = _av_dir(cid); d.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", f.filename)
        dest = d / safe
        f.save(str(dest))
        # Generate thumbnail in background
        threading.Thread(target=ensure_thumbnail, args=(dest,), daemon=True).start()
        return jsonify({"ok": True, "name": safe})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/avatar-clip/delete", methods=["POST"])
def api_clip_delete():
    try:
        data = request.json or {}
        clip = _av_dir(data.get("channel_id", "")) / data.get("name", "")
        thumb = clip.parent / (clip.stem + "_thumb.jpg")
        if clip.is_file(): clip.unlink()
        if thumb.is_file(): thumb.unlink()
        return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/avatar-dir/create", methods=["POST"])
def api_avdir_create():
    cid = (request.json or {}).get("channel_id", "")
    if cid: _av_dir(cid).mkdir(parents=True, exist_ok=True)
    return jsonify({"ok": True})

# ── CHANNELS ──────────────────────────────────────────────────────────────────
@app.route("/api/channel/save", methods=["POST"])
def api_ch_save():
    try:
        c = load_config(); data = request.json or {}
        cid = data.get("channel_id", "").strip()
        if not cid: return jsonify({"ok": False, "error": "channel_id required"})
        ch = c.setdefault("channels", {}).setdefault(cid, {})
        for k in ["name","niche","mode","avatar_clip_mode"]:
            if k in data: ch[k] = data[k]
        if "default_minutes" in data: ch["default_minutes"] = int(data["default_minutes"])
        save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/channel/character", methods=["POST"])
def api_ch_char():
    try:
        c = load_config(); data = request.json or {}
        cid = data.get("channel_id", "")
        if cid not in c.get("channels", {}): return jsonify({"ok": False, "error": "Not found"})
        c["channels"][cid]["character"] = data.get("character", {})
        save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/channel/prompts", methods=["POST"])
def api_ch_prompts():
    try:
        c = load_config(); data = request.json or {}
        cid = data.get("channel_id", "")
        if cid not in c.get("channels", {}): return jsonify({"ok": False, "error": "Not found"})
        c["channels"][cid]["prompts"] = data.get("prompts", {})
        save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/channel/voice", methods=["POST"])
def api_ch_voice():
    try:
        c = load_config(); data = request.json or {}
        cid = data.get("channel_id", "")
        if cid not in c.get("channels", {}): return jsonify({"ok": False, "error": "Not found"})
        c["channels"][cid]["voice"] = {"provider": data.get("provider","gemini-tts"),
                                        "voice_id": data.get("voice_id","")}
        save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

@app.route("/api/character-sheet/parse", methods=["POST"])
def api_parse_character():
    """Parse free-text character description into structured fields using Gemini."""
    try:
        text = (request.json or {}).get("text", "").strip()
        if not text:
            return jsonify({"ok": False, "error": "No text provided"})

        sec = load_secrets()
        api_key = (sec.get("gemini_api_key") or "").strip()

        if api_key:
            # Use Gemini to parse
            import google.generativeai as genai, json as _json
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            prompt = f"""Extract character information from the text below.
Return ONLY a JSON object with these exact keys (leave empty string if not found):
name, age_desc, gender (Male/Female/Other), ethnicity, build, occupation,
personality, outfit, traits, colors, background

Text:
{text}

JSON output only, no markdown:"""
            resp = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.2, max_output_tokens=1024)
            )
            raw = resp.text.strip()
            # Strip markdown fences if any
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"): raw = raw[4:]
            raw = raw.strip()
            char = _json.loads(raw)
        else:
            # Fallback: basic keyword extraction without Gemini
            import re
            char = {"name":"","age_desc":"","gender":"Male","ethnicity":"",
                    "build":"","occupation":"","personality":"","outfit":"",
                    "traits":"","colors":"","background":""}
            # Try to extract name (word after "named")
            m = re.search(r'named\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', text)
            if m: char["name"] = m.group(1)
            # Age
            m = re.search(r'(\d+)[- ]year[- ]old', text, re.I)
            if m: char["age_desc"] = m.group(1) + " years old"
            # Gender
            if re.search(r'\bwom[ae]n\b|\bfem[ae]le\b|\bher\b', text, re.I):
                char["gender"] = "Female"
            # Use full text as personality fallback
            char["personality"] = text[:200]

        # Ensure all keys present
        for k in ["name","age_desc","gender","ethnicity","build","occupation",
                   "personality","outfit","traits","colors","background"]:
            char.setdefault(k, "")

        return jsonify({"ok": True, "character": char})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/channel/delete", methods=["POST"])
def api_ch_delete():
    try:
        c = load_config(); cid = (request.json or {}).get("channel_id","")
        c.get("channels",{}).pop(cid,None); save_config(c); return jsonify({"ok": True})
    except Exception as e: return jsonify({"ok": False, "error": str(e)})

# ── GENERATE ─────────────────────────────────────────────────────────────────
def _ratio(mins):
    if mins <= 3:  return "9:16"
    if mins <= 10: return "1:1"
    return "16:9"

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data  = request.json or {}
        title = data.get("title","").strip()
        cid   = data.get("channel_id","").strip()
        mins  = int(data.get("minutes", 30))
        av    = data.get("avatar","")
        if not title or not cid: return jsonify({"error":"title and channel_id required"}), 400
        ratio  = _ratio(mins)
        job_id = str(uuid.uuid4())[:8]
        q = queue.Queue()
        JOB_QUEUES[job_id] = q
        JOBS[job_id] = {"job_id": job_id, "title": title, "channel_id": cid,
                        "avatar": av, "minutes": mins, "ratio": ratio,
                        "status": "queued", "started_at": time.strftime("%H:%M:%S"),
                        "final_mp4": None, "error": None}
        JOB_QUEUE_ORDER.append(job_id)
        _maybe_start_worker()
        return jsonify({"job_id": job_id})
    except Exception as e: return jsonify({"error": str(e)}), 500

def _maybe_start_worker():
    if _worker_running[0]: return
    queued = [j for j in JOB_QUEUE_ORDER if JOBS.get(j,{}).get("status")=="queued"]
    if not queued: return
    threading.Thread(target=_run_job, args=(queued[0],), daemon=True).start()

def _run_job(job_id):
    _worker_running[0] = True
    try:
        JOBS[job_id]["status"] = "running"
        c = load_config(); sec = load_secrets()
        j = JOBS[job_id]; cid = j["channel_id"]
        ch = (c.get("channels") or {}).get(cid, {})
        opts = {"minutes_override": j["minutes"], "mode": ch.get("mode","avatar"),
                "aspect_ratio": j["ratio"], "avatar_clip": j.get("avatar","")}
        q = JOB_QUEUES[job_id]
        result = run_pipeline(j["title"], cid, c, sec, opts=opts,
                              progress_cb=lambda pct,msg: q.put({"type":"progress","pct":pct,"msg":msg}),
                              log_cb=lambda msg: q.put({"type":"log","msg":str(msg)}))
        JOBS[job_id]["status"] = "done" if result.get("ok") else "error"
        JOBS[job_id]["final_mp4"] = result.get("final_mp4","")
        JOBS[job_id]["error"] = result.get("error","")
        q.put({"type":"done","ok":result.get("ok"),"final_mp4":result.get("final_mp4",""),
               "error":result.get("error","")})
    except Exception as e:
        JOBS[job_id]["status"] = "error"; JOBS[job_id]["error"] = str(e)
        JOB_QUEUES[job_id].put({"type":"done","ok":False,"error":str(e)})
    finally:
        _worker_running[0] = False
        time.sleep(5); _maybe_start_worker()

@app.route("/api/job/<job_id>/stream")
def api_job_stream(job_id):
    def _gen():
        q = JOB_QUEUES.get(job_id)
        if not q:
            yield f'data: {json.dumps({"type":"done","ok":False,"error":"Not found"})}\n\n'; return
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "done": break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(_gen(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/api/job/<job_id>/download")
def api_job_download(job_id):
    mp4 = JOBS.get(job_id,{}).get("final_mp4","")
    if mp4 and Path(mp4).is_file():
        return send_file(mp4, as_attachment=True, download_name=Path(mp4).name)
    return "Not found", 404

@app.route("/api/jobs")
def api_jobs(): return jsonify(list(JOBS.values()))

@app.route("/api/jobs/clear", methods=["POST"])
def api_jobs_clear():
    for jid in list(JOBS.keys()):
        if JOBS[jid]["status"] in ("done","error"):
            JOBS.pop(jid,None); JOB_QUEUES.pop(jid,None)
            if jid in JOB_QUEUE_ORDER: JOB_QUEUE_ORDER.remove(jid)
    return jsonify({"ok": True})

# ── COMPETITORS ───────────────────────────────────────────────────────────────
@app.route("/api/competitors")
def api_competitors():
    try:
        from mib.competitor import get_all_master_patterns, load_competitors
        all_p = get_all_master_patterns(); total = len(load_competitors())
        done = sum(1 for p in all_p if p.get("status")=="done")
        failed = sum(1 for p in all_p if p.get("status") in ("error","decode_failed"))
        return jsonify({"total":total,"done":done,"failed":failed,"channels":all_p})
    except Exception as e:
        return jsonify({"total":92,"done":0,"failed":0,"channels":[],"error":str(e)})

@app.route("/api/competitors/scrape", methods=["POST"])
def api_comp_scrape():
    sec = load_secrets(); key = (sec.get("gemini_api_key") or "").strip()
    if not key: return jsonify({"ok":False,"error":"No Gemini key"})
    _COMP_STOP[0] = False
    def _run():
        from mib.competitor import run_full_scrape
        def _prog(pct,msg):
            if _COMP_STOP[0]: raise InterruptedError
            _COMP_Q.put({"type":"progress","pct":pct,"msg":msg})
        try: run_full_scrape(key, progress_cb=_prog, resume=True)
        except InterruptedError: pass
        _COMP_Q.put({"type":"done"})
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/competitors/stream")
def api_comp_stream():
    def _gen():
        while True:
            try:
                msg = _COMP_Q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type")=="done": break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'
    return Response(_gen(), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/api/competitors/stop", methods=["POST"])
def api_comp_stop():
    _COMP_STOP[0] = True; return jsonify({"ok":True})

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = 7860
    # Pre-generate thumbnails for all existing clips at startup
    def _pregenthumbs():
        for clip in AVATAR_DIR.rglob("*.mp4"):
            try: ensure_thumbnail(clip)
            except: pass
    threading.Thread(target=_pregenthumbs, daemon=True).start()

    print(f"\n{'='*50}")
    print(f"  MIB Avatar Production v4 — Wizard UI")
    print(f"  Open: http://localhost:{port}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
