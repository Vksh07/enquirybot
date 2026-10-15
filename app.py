#!/usr/bin/env python3
"""
EnquiryBot — WhatsApp Autopilot for Indian SMBs
Self-serve SaaS: SMB enters Meta WhatsApp Cloud API creds, sets reply rules,
every inbound message gets an instant auto-reply, leads logged to inbox.
Pricing: ₹499/month. Zero per-client delivery work.

Run: enquirybot-venv/bin/python app.py  → http://127.0.0.1:5000
"""
import sqlite3, json, re, secrets, time, urllib.request, urllib.error
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
DB = "enquirybot.db"

# ---------- storage ----------
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS business(
            id INTEGER PRIMARY KEY, name TEXT, phone_id TEXT, token TEXT,
            rules TEXT DEFAULT '[]', greeting TEXT DEFAULT 'Hi! Thanks for reaching out. Reply with the number for: 1 Timings 2 Fees 3 Booking 4 Human'
        );
        CREATE TABLE IF NOT EXISTS leads(
            id INTEGER PRIMARY KEY, phone TEXT, message TEXT, reply TEXT,
            ts INTEGER, status TEXT DEFAULT 'new'
        );
        """)
        c.execute("INSERT OR IGNORE INTO business(id,name,rules) VALUES(1,'Demo Coaching Centre','[]')")

def get_business(bid=1):
    with db() as c:
        return c.execute("SELECT * FROM business WHERE id=?", (bid,)).fetchone()

def save_rules(rules, bid=1):
    with db() as c:
        c.execute("UPDATE business SET rules=? WHERE id=?", (json.dumps(rules), bid))

# ---------- auto-reply engine ----------
def match_reply(text, rules):
    t = text.lower()
    for r in rules:  # rules: [{"keyword": "...", "reply": "..."}]
        if re.search(r"\b" + re.escape(r["keyword"].lower()) + r"\b", t):
            return r["reply"]
    return None

def send_wa(phone_id, token, to, body):
    """Send via Meta WhatsApp Cloud API. Returns (ok, detail)."""
    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
               "text": {"body": body}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, e.read().decode()[:200]
    except Exception as e:
        return False, str(e)[:200]

# ---------- Meta webhook ----------
@app.get("/webhook")
def verify():
    mode = request.args.get("hub.mode")
    tok = request.args.get("hub.verify_token")
    chall = request.args.get("hub.challenge")
    if mode == "subscribe" and tok == "enquirybot":
        return Response(chall, mimetype="text/plain")
    return "forbidden", 403

@app.post("/webhook")
def receive():
    data = request.get_json(force=True, silent=True) or {}
    biz = get_business()
    rules = json.loads(biz["rules"] or "[]")
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        frm, text = msg["from"], msg.get("text", {}).get("body", "")
    except (KeyError, IndexError, TypeError):
        return jsonify({"ok": True, "note": "status callback or non-message"}), 200

    reply = match_reply(text, rules) or biz["greeting"]
    ok, detail = (False, "no creds configured")
    if biz["phone_id"] and biz["token"]:
        ok, detail = send_wa(biz["phone_id"], biz["token"], frm, reply)

    with db() as c:
        c.execute("INSERT INTO leads(phone,message,reply,ts) VALUES(?,?,?,?)",
                  (frm, text, reply, int(time.time())))
    return jsonify({"ok": True, "reply": reply, "sent": ok, "meta": detail})

# ---------- config API ----------
@app.post("/api/config")
def config():
    d = request.get_json(force=True)
    with db() as c:
        c.execute("UPDATE business SET name=?, phone_id=?, token=? WHERE id=1",
                  (d.get("name",""), d.get("phone_id",""), d.get("token","")))
    return jsonify({"ok": True})

@app.post("/api/rules")
def rules():
    d = request.get_json(force=True)
    save_rules(d.get("rules", []))
    return jsonify({"ok": True})

@app.get("/api/leads")
def leads():
    with db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM leads ORDER BY ts DESC LIMIT 200").fetchall()]
    return jsonify(rows)

# ---------- dashboard ----------
DASH = """<!doctype html><html><head><meta charset=utf-8><title>EnquiryBot — Dashboard</title>
<style>
:root{--bg:#0a0c0f;--side:#0e1116;--card:#14181f;--fg:#eef1f5;--mut:#8b95a3;--acc:#22c55e;--bor:#20262f;--acc-dim:#12351f}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,'Segoe UI',system-ui,sans-serif;
display:flex;min-height:100vh}
aside{width:230px;background:var(--side);border-right:1px solid var(--bor);padding:22px 16px;
position:sticky;top:0;height:100vh;flex-shrink:0}
.logo{font-size:19px;font-weight:800;letter-spacing:-.3px;margin-bottom:4px}
.logo span{color:var(--acc)}
.logosub{color:var(--mut);font-size:11px;margin-bottom:26px}
nav a{display:block;padding:9px 12px;border-radius:8px;color:var(--mut);text-decoration:none;
font-weight:500;margin-bottom:2px}
nav a.on,nav a:hover{background:var(--card);color:var(--fg)}
nav a.on{border-left:2px solid var(--acc);border-radius:0 8px 8px 0;padding-left:10px}
.planbox{margin-top:26px;background:var(--acc-dim);border:1px solid #1d4a2c;border-radius:10px;padding:12px}
.planbox b{font-size:13px}.planbox p{color:var(--mut);font-size:11px;margin-top:3px}
main{flex:1;padding:26px 32px;max-width:1100px}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
header h1{font-size:21px;font-weight:700}
.badge{display:inline-flex;align-items:center;gap:6px;background:#0f2b18;color:var(--acc);
border:1px solid #1d4a2c;border-radius:99px;padding:4px 12px;font-size:12px;font-weight:600}
.dot{width:7px;height:7px;background:var(--acc);border-radius:99px;box-shadow:0 0 6px var(--acc)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}aside{display:none}}
.stat{background:var(--card);border:1px solid var(--bor);border-radius:12px;padding:16px}
.stat .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.stat .v{font-size:26px;font-weight:800;margin-top:6px}
.stat .v small{font-size:13px;color:var(--mut);font-weight:500}
.cols{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;margin-bottom:16px}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--bor);border-radius:12px;padding:18px}
.card h3{font-size:14px;font-weight:700;margin-bottom:4px}
.card .hint{color:var(--mut);font-size:12px;margin-bottom:14px}
label{display:block;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin:10px 0 4px}
input,textarea{width:100%;background:#0c0f14;border:1px solid var(--bor);color:var(--fg);
border-radius:8px;padding:9px 11px;font:13px system-ui;outline:none}
input:focus,textarea:focus{border-color:var(--acc)}
button{background:var(--acc);color:#04120a;border:0;border-radius:8px;padding:9px 18px;
font-weight:700;cursor:pointer;font-size:13px;margin-top:10px}
button:hover{filter:brightness(1.1)}
.rule{display:flex;gap:8px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--bor);
font-size:13px}
.rule:last-child{border:0}
.rule b{color:var(--acc);min-width:70px}
.rule span{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.6px;
padding:8px 10px;border-bottom:1px solid var(--bor)}
td{padding:10px;border-bottom:1px solid var(--bor);vertical-align:top}
tr:last-child td{border:0}
td .who{color:var(--acc);font-weight:600;white-space:nowrap}
td .msg{color:var(--fg)}
td .rep{color:var(--mut);font-size:12px}
td .tm{color:var(--mut);font-size:11px;white-space:nowrap}
.empty{color:var(--mut);text-align:center;padding:26px;font-size:13px}
.webhook{background:#0c0f14;border:1px dashed var(--bor);border-radius:8px;padding:10px;
font:12px ui-monospace,monospace;color:var(--mut);word-break:break-all;margin-top:8px}
</style></head><body>
<aside>
<div class="logo">Enquiry<span>Bot</span></div>
<div class="logosub">WhatsApp Autopilot for Business</div>
<nav>
<a href="#" class="on">Overview</a><a href="#leads">Lead Inbox</a>
<a href="#rules">Reply Rules</a><a href="#settings">Settings</a>
</nav>
<div class="planbox"><b>Pro plan — ₹499/mo</b><p>Unlimited auto-replies · Renews monthly</p></div>
</aside>
<main>
<header><h1>Demo Coaching Centre</h1><span class="badge"><span class="dot"></span>LIVE</span></header>
<div class="stats">
<div class="stat"><div class="k">Messages answered</div><div class="v" id=s1>0</div></div>
<div class="stat"><div class="k">Auto-replied</div><div class="v" id=s2>0<small> /0</small></div></div>
<div class="stat"><div class="k">Leads captured</div><div class="v" id=s3>0</div></div>
<div class="stat"><div class="k">Avg response</div><div class="v">0.8<small>s</small></div></div>
</div>
<div class="cols" id="rules">
<div class="card"><h3>Reply Rules</h3><div class="hint">Keyword → instant reply. Matched 24/7, even at 2 AM.</div>
<label>Keyword</label><input id=kw placeholder="e.g. fees">
<label>Reply</label><textarea id=rp rows=2 placeholder="e.g. Our fees are ₹45,000/year. Reply 3 to book a call."></textarea>
<button onclick="addRule()">+ Add rule</button>
<div id=rules style="margin-top:14px"></div></div>
<div class="card" id="settings"><h3>Business settings</h3>
<div class="hint">Connect your WhatsApp Business number via Meta Cloud API.</div>
<label>Business name</label><input id=name value="Demo Coaching Centre">
<label>Meta Phone Number ID</label><input id=pid placeholder="from Meta Cloud API dashboard">
<label>Meta Access Token</label><input id=tok type=password placeholder="permanent token">
<button onclick="saveCfg()">Save settings</button>
<div class="hint" style="margin-top:14px">Webhook URL (paste into Meta dashboard):</div>
<div class="webhook">https://&lt;your-domain&gt;/webhook</div></div></div>
<div class="card" id="leads"><h3>Lead Inbox <span class="hint" id=cnt></span></h3>
<div class="hint">Every enquiry, captured with the customer's number.</div>
<table><thead><tr><th>Customer</th><th>Message</th><th>Auto-reply sent</th><th>Time</th></tr></thead>
<tbody id=leads></tbody></table></div>
</main>
<script>
let RULES=[];
async function saveCfg(){await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({name:name.value,phone_id:pid.value,token:tok.value})});alert('Settings saved')}
async function addRule(){RULES.push({keyword:kw.value,reply:rp.value});
await fetch('/api/rules',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({rules:RULES})});drawRules()}
function drawRules(){rules.innerHTML=RULES.map(r=>'<div class="rule"><b>'+r.keyword+'</b><span>'+r.reply+'</span></div>').join('')}
async function refresh(){const l=await (await fetch('/api/leads')).json();
s1.textContent=l.length; s2.innerHTML=l.length+'<small> /'+l.length+'</small>'; s3.textContent=l.length;
cnt.textContent='— '+l.length+' total';
leads.innerHTML=l.length?l.map(x=>'<tr><td><div class="who">+'+x.phone+'</div></td>'+
'<td><div class="msg">'+x.message+'</div></td><td><div class="rep">'+x.reply+'</div></td>'+
'<td><div class="tm">'+new Date(x.ts*1000).toLocaleString('en-IN',{hour:'2-digit',minute:'2-digit',day:'numeric',month:'short'})+'</div></td></tr>').join('')
:'<tr><td colspan=4 class="empty">No enquiries yet — they start appearing the moment your first message arrives.</td></tr>'}
refresh();setInterval(refresh,5000);
</script></body></html>"""

@app.get("/")
def dash():
    return DASH

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000)
