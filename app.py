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
DASH = """<!doctype html><html><head><meta charset=utf-8><title>EnquiryBot</title>
<style>
:root{--bg:#0b0d10;--card:#15181d;--fg:#e8eaed;--mut:#8a919c;--acc:#22c55e;--bor:#252a31}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui;padding:24px;max-width:980px;margin:auto}
h1{font-size:22px;margin-bottom:4px}
.sub{color:var(--mut);margin-bottom:20px;font-size:13px}
.card{background:var(--card);border:1px solid var(--bor);border-radius:12px;padding:16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.grid{grid-template-columns:1fr}}
input,textarea{width:100%;background:#0e1116;border:1px solid var(--bor);color:var(--fg);
border-radius:8px;padding:8px 10px;font:14px system-ui;margin:4px 0 10px}
label{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
button{background:var(--acc);color:#04120a;border:0;border-radius:8px;padding:9px 16px;
font-weight:600;cursor:pointer}
.lead{border-bottom:1px solid var(--bor);padding:10px 0}
.lead:last-child{border:0}
.ph{color:var(--acc);font-weight:600}
.mut{color:var(--mut);font-size:12px}
.reply{background:#0e1116;border-left:2px solid var(--acc);padding:6px 10px;margin-top:6px;
border-radius:0 6px 6px 0;font-size:13px}
.badge{display:inline-block;background:#17351f;color:var(--acc);border-radius:99px;
padding:2px 10px;font-size:11px;font-weight:600}
</style></head><body>
<h1>EnquiryBot <span class="badge">LIVE</span></h1>
<div class="sub">WhatsApp Autopilot for Indian SMBs — every message answered in seconds, 24/7</div>
<div class="grid">
<div class="card"><h3 style="margin-bottom:10px">Business setup</h3>
<label>Business name</label><input id=name value="Demo Coaching Centre">
<label>Meta Phone Number ID</label><input id=pid placeholder="from Meta Cloud API dashboard">
<label>Meta Access Token</label><input id=tok type=password placeholder="permanent token">
<button onclick="saveCfg()">Save config</button></div>
<div class="card"><h3 style="margin-bottom:10px">Reply rules (keyword → reply)</h3>
<label>Keyword</label><input id=kw placeholder="fees"><label>Reply</label>
<textarea id=rp rows=2 placeholder="Our fees are ₹X. Reply 3 to book a call."></textarea>
<button onclick="addRule()">Add rule</button>
<div id=rules class="mut" style="margin-top:8px"></div></div></div>
<div class="card"><h3 style="margin-bottom:10px">Lead inbox <span class="mut" id=cnt></span></h3>
<div id=leads></div></div>
<script>
let RULES=[];
async function saveCfg(){await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({name:name.value,phone_id:pid.value,token:tok.value})});alert('saved')}
async function addRule(){RULES.push({keyword:kw.value,reply:rp.value});
await fetch('/api/rules',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({rules:RULES})});drawRules()}
function drawRules(){rules.innerHTML=RULES.map(r=>'• <b>'+r.keyword+'</b> → '+r.reply).join('<br>')}
async function refresh(){const l=await (await fetch('/api/leads')).json();
cnt.textContent='('+l.length+')';
leads.innerHTML=l.map(x=>'<div class="lead"><div class="ph">+'+x.phone+'</div>'+
'<div>'+x.message+'</div><div class="reply">→ '+x.reply+'</div>'+
'<div class="mut">'+new Date(x.ts*1000).toLocaleString()+'</div></div>').join('')}
refresh();setInterval(refresh,5000);
</script></body></html>"""

@app.get("/")
def dash():
    return DASH

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000)
