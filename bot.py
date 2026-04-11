"""Intent Engine Telegram Bot - Minimal version"""
import json, os, re, subprocess, sys, time
from pathlib import Path
import requests

TOKEN = "8166304435:AAHobDNu6MFbLcQCZrcfdq_12bFfSwco2gA"
URL = f"https://api.telegram.org/bot{TOKEN}"
MY_ID = 1643185451
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")

pid = None  # pipeline process
log_path = None
offset = 0

def call(method, **kw):
    try:
        r = requests.post(f"{URL}/{method}", json=kw, timeout=15)
        return r.json()
    except Exception as e:
        print(f"API error: {e}")
        return None

def msg(text):
    for i in range(0, len(text), 4000):
        call("sendMessage", chat_id=MY_ID, text=text[i:i+4000], parse_mode="Markdown")

def running(p):
    if not p: return False
    try:
        r = subprocess.run(["tasklist","/FI",f"PID eq {p}"], capture_output=True, text=True)
        return str(p) in r.stdout
    except: return False

def last_session():
    try:
        sessions = list(Path(OUT).glob("*/session.json"))
        return max(sessions, key=os.path.getmtime) if sessions else None
    except: return None

def do_run(prompt):
    global pid, log_path
    if pid and running(pid):
        msg(f"⚠️ Already running (PID {pid}). /stop first.")
        return
    safe = re.sub(r"[^\w\s-]", "", prompt.lower()).replace(" ","-")[:50]
    op = os.path.join(OUT, safe)
    lp = os.path.join(OUT, f"{safe}.log")
    import shutil
    if os.path.exists(op): shutil.rmtree(op, ignore_errors=True)
    if os.path.exists(lp):
        try: os.remove(lp)
        except: pass
    log_path = lp
    msg(f"🚀 Launching:\n`{prompt}`")
    # Redirect to log file directly (not PIPE — prevents buffer deadlock)
    logf = open(lp, "w", encoding="utf-8")
    p = subprocess.Popen(
        [sys.executable, "-u", os.path.join(ROOT, "main.py"),
         prompt, "--max_cycles", "8", "--output", op],
        stdout=logf, stderr=logf,
        cwd=ROOT
    )
    pid = p.pid
    msg(f"✅ Started PID {pid}")

def do_status():
    lines = []
    if pid and running(pid):
        lines.append(f"🔄 *Running* PID {pid}")
        if log_path and os.path.exists(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as f:
                al = f.readlines()
            for l in reversed(al):
                if any(k in l for k in ["PHASE","Cycle","ALL_COMPLETE","VISUAL","TESTS"]):
                    lines.append(l.strip())
                    if len(lines) >= 4: break
    else:
        lines.append("⏸️ Idle")
    s = last_session()
    if s:
        try:
            d = json.loads(s.read_text(encoding="utf-8"))
            lines.append(f"Last: {os.path.basename(s.parent)} | {d.get('cycles_run',0)} cycles | {d.get('completed',False)}")
        except: pass
    msg("\n".join(lines))

def do_stop():
    global pid
    if pid and running(pid):
        subprocess.run(["taskkill","/F","/T","/PID",str(pid)], capture_output=True)
        msg(f"🛑 Stopped PID {pid}")
        pid = None
    else:
        msg("⏸️ Nothing running")

def do_log():
    lp = log_path
    if not lp or not os.path.exists(lp):
        logs = list(Path(OUT).glob("*.log"))
        if logs: lp = str(max(logs, key=os.path.getmtime))
        else: msg("❌ No log"); return
    with open(lp, encoding="utf-8", errors="replace") as f:
        tail = f.readlines()[-30:]
    msg(f"📝 Last 30 lines:\n```\n{''.join(tail)}\n```")

def do_metrics():
    s = last_session()
    if not s: msg("❌ No data"); return
    d = json.loads(s.read_text(encoding="utf-8"))
    od = d.get("output_dir","")
    sz = sum(os.path.getsize(os.path.join(od,f)) for f in d.get("file_list",[]) if os.path.exists(os.path.join(od,f)))
    seed = len(d.get("prompt","").encode())+30
    lines = [f"📊 *Metrics*", f"Cycles: {d.get('cycles_run',0)}", f"Done: {d.get('completed',False)}",
             f"Files: {len(d.get('file_list',[]))}", f"Size: {sz:,} B ({sz/1024:.1f} KB)",
             f"Seed: ~{seed} B"]
    if sz>0 and seed>0: lines.append(f"Ratio: 1:{sz//seed}")
    msg("\n".join(lines))

def do_sessions():
    if not os.path.exists(OUT): msg("None"); return
    ss = sorted([d for d in Path(OUT).iterdir() if d.is_dir()], key=lambda x:os.path.getmtime(str(x)), reverse=True)
    lines = ["📁 Sessions:"]
    for s in ss[:8]:
        sp = s/"session.json"
        info = ""
        if sp.exists():
            try:
                d = json.loads(sp.read_text(encoding="utf-8"))
                info = f" ({'✅' if d.get('completed') else '❌'} {d.get('cycles_run',0)})"
            except: pass
        lines.append(f"  • {s.name}{info}")
    msg("\n".join(lines))

CMDS = {"run":do_run, "status":do_status, "stop":do_stop, "log":do_log, "metrics":do_metrics, "sessions":do_sessions}

def main():
    global offset
    print("🤖 Bot starting...")
    # Consume old
    r = call("getUpdates", offset=0, limit=100)
    if r and r.get("result"):
        offset = r["result"][-1]["update_id"]+1
        print(f"Skipped {len(r['result'])} old updates")

    msg("🤖 *Intent Engine Bot online*\n\n/start /help /run /status /stop /metrics /log /sessions")

    while True:
        try:
            r = call("getUpdates", offset=offset, timeout=10)
            if not r or not r.get("result"):
                time.sleep(3)
                continue
            for u in r["result"]:
                offset = u["update_id"]+1
                m = u.get("message",{})
                if m.get("from",{}).get("id") != MY_ID: continue
                text = m.get("text","")
                print(f"[{m['from'].get('first_name','?')}] {text}")
                if text.startswith("/"):
                    parts = text.split(None,1)
                    cmd = parts[0][1:].lower()
                    arg = parts[1] if len(parts)>1 else ""
                    if cmd in ("start","help"):
                        msg("🤖 *Intent Engine Bot*\n\n"
                            "/run \"prompt\" — Launch pipeline\n"
                            "/status — Current status\n"
                            "/stop — Kill pipeline\n"
                            "/metrics — Session metrics\n"
                            "/log — Last 30 log lines\n"
                            "/sessions — List sessions")
                    elif cmd == "run":
                        if arg.strip(): do_run(arg.strip().strip('"').strip("'"))
                        else: msg("❌ /run \"create a tic-tac-toe game\"")
                    elif cmd in CMDS:
                        CMDS[cmd]()
                    else:
                        msg(f"❓ /{cmd}? Use /help")
                else:
                    msg("Use /help for commands")
        except KeyboardInterrupt:
            print("\n👋 Bye")
            break
        except Exception as e:
            print(f"❌ {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
