#!/usr/bin/env python3
"""
AI 工具箱 - 本地服务
启动后在浏览器中查看用量仪表盘，点击按钮实时操作
"""
import json, os, sqlite3, re, sys, time, webbrowser, threading, traceback
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from http.server import HTTPServer, SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer

PORT = 9876
BASE = Path(__file__).parent.parent

# ========== 配置（GitHub 版本用户可改这里）==========
# Reasonix 数据目录
REASONIX_DIR = Path(os.environ.get("APPDATA", "")) / "reasonix"
# opencode 数据库
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
# 导出目录
EXPORT_DIR = BASE / "聊天记录"

# ========== 工具函数 ==========
def safe_fn(name, mx=60):
    name = str(name)
    name = re.sub(r'[\r\n\t]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    for c in r'\<>:"/|?*':
        name = name.replace(c, '-')
    return (name[:mx] or "untitled").rstrip('. ')

# ========== 数据采集 ==========
def get_reasonix_stats():
    stats_dir = REASONIX_DIR / "stats"
    if not stats_dir.exists():
        return {"models":{},"daily":{},"totals":{"prompt":0,"completion":0,"cache_hit":0,"requests":0,"total":0,"cache_rate":0}}
    models = defaultdict(lambda: {"prompt":0,"completion":0,"cache_hit":0,"requests":0,"total":0})
    daily = defaultdict(lambda: {"tokens":0,"requests":0})
    for f in sorted(stats_dir.glob("*.jsonl")):
        try:
            with open(f,"r",encoding="utf-8") as fh:
                for line in fh:
                    try:
                        o=json.loads(line.strip()); m=o.get("model","unknown")
                        models[m]["prompt"]+=o.get("prompt",0); models[m]["completion"]+=o.get("completion",0)
                        models[m]["cache_hit"]+=o.get("cache_hit",0); models[m]["requests"]+=o.get("requests",0)
                        models[m]["total"]+=o.get("total",0)
                        daily[f.stem]["tokens"]+=o.get("total",0); daily[f.stem]["requests"]+=o.get("requests",0)
                    except: continue
        except: continue
    tp=sum(v["prompt"] for v in models.values()); tc=sum(v["cache_hit"] for v in models.values())
    return {"models":{k:dict(v) for k,v in models.items()},"daily":dict(daily),
            "totals":{"prompt":tp,"completion":sum(v["completion"] for v in models.values()),"cache_hit":tc,
                      "requests":sum(v["requests"] for v in models.values()),"total":sum(v["total"] for v in models.values()),
                      "cache_rate":round(tc/max(tp,1)*100,1)}}

def get_opencode_stats():
    if not OPENCODE_DB.exists(): return {"models":[],"daily":[],"totals":{}}
    try:
        conn=sqlite3.connect(str(OPENCODE_DB), timeout=5); conn.row_factory=sqlite3.Row; cur=conn.cursor()
        cur.execute("""SELECT json_extract(model,'$.id') as mid,json_extract(model,'$.providerID') as prov,
            COUNT(*) as sessions,SUM(tokens_input) as inp,SUM(tokens_output) as out,
            SUM(tokens_reasoning) as reason,SUM(tokens_cache_read) as cache,ROUND(SUM(cost),4) as cost
            FROM session GROUP BY mid,prov ORDER BY (tokens_input+tokens_cache_read) DESC""")
        models=[dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT date(time_created/1000,'unixepoch','localtime') as date,COUNT(*) as sessions,
            SUM(tokens_input) as inp,SUM(tokens_output) as out,SUM(tokens_reasoning) as reason,
            SUM(tokens_cache_read) as cache,ROUND(SUM(cost),4) as cost
            FROM session GROUP BY date ORDER BY date""")
        daily=[dict(r) for r in cur.fetchall()]
        cur.execute("""SELECT COUNT(*) as sessions,SUM(tokens_input) as inp,SUM(tokens_output) as out,
            SUM(tokens_reasoning) as reason,SUM(tokens_cache_read) as cache,ROUND(SUM(cost),4) as cost FROM session""")
        totals=dict(cur.fetchone()); conn.close()
        return {"models":models,"daily":daily,"totals":totals}
    except Exception as e:
        print(f"[警告] opencode 读取失败: {e}")
        return {"models":[],"daily":[],"totals":{}}

def get_chats_stats():
    chats_dir = EXPORT_DIR
    if not chats_dir.exists(): return {"reasonix":{"sessions":0,"messages":0},"opencode":{"sessions":0,"messages":0}}
    def count_dir(d):
        if not d.exists(): return 0
        return len(list(d.rglob("*.md")))
    r = count_dir(chats_dir / "Reasonix")
    o = count_dir(chats_dir / "opencode")
    return {"reasonix":{"sessions":r,"messages":0},"opencode":{"sessions":o,"messages":0}}

def collect_all():
    R = get_reasonix_stats(); O = get_opencode_stats()
    return {"reasonix":R,"opencode":O,"chats":get_chats_stats(),"time":datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# ========== 导出聊天记录 ==========
def export_chats():
    print("[导出] 开始...")
    chats_dir = EXPORT_DIR; chats_dir.mkdir(parents=True, exist_ok=True)

    def parse_jl(fp):
        msgs=[]
        try:
            with open(fp,'r',encoding='utf-8') as f:
                for line in f:
                    line=line.strip()
                    if not line: continue
                    try:
                        o=json.loads(line)
                        if isinstance(o,dict) and 'role' in o and 'content' in o: msgs.append(o)
                    except: continue
        except: pass
        return msgs

    def clean_user(c):
        c=re.sub(r'<reasoning-language>.*?</reasoning-language>','',c,flags=re.DOTALL)
        c=re.sub(r'<response-language>.*?</response-language>','',c,flags=re.DOTALL)
        c=re.sub(r'<memory-recall>.*?</memory-recall>','',c,flags=re.DOTALL)
        return c.strip()

    def extract_dlg(msgs):
        d=[]
        for m in msgs:
            role,content=m.get('role',''),m.get('content','')
            if role=='user': content=clean_user(content)
            if not content or not content.strip(): continue
            if role not in ('user','assistant'): continue
            if role=='assistant' and content.strip().startswith('You are Reasonix'): continue
            d.append((role,content.strip()))
        return d

    def write_md(path,title,src,dlg,extra=""):
        md=f"# {title}\n\n"
        if extra: md+=f"{extra}\n"
        md+=f"**来源:** `{src}`\n\n**消息数:** {len(dlg)}\n\n---\n\n"
        for role,content in dlg:
            md+=f"## {'👤 用户' if role=='user' else '🤖 AI 助手'}\n\n{content}\n\n---\n\n"
        path.write_text(md,encoding='utf-8')

    def get_title(fp,tm=None):
        if tm and fp.name in tm:
            v=tm[fp.name]
            if isinstance(v,str): t=v
            elif isinstance(v,dict): tv=list(v.values()); t=tv[0] if tv else ""
            else: t=str(v)
            if t: return t[:80]+"..." if len(t)>80 else t
        parts=fp.stem.split('-')
        if len(parts)>=3:
            try:
                dt=datetime.strptime(parts[1][:8],"%Y%m%d"); return dt.strftime("%Y-%m-%d %H:%M")
            except: pass
        return fp.stem[:50]

    total_s=0; total_m=0

    # Reasonix sessions
    sess_dir=REASONIX_DIR/"sessions"
    if sess_dir.exists():
        tm=None; tf=sess_dir/".titles.json"
        if tf.exists():
            try: tm=json.loads(tf.read_text('utf-8'))
            except: pass
        files=[f for f in sess_dir.glob("*.jsonl") if not f.name.endswith('.events.jsonl') and not f.name.endswith('.lock')]
        out=chats_dir/"Reasonix"/"桌面端会话"; out.mkdir(parents=True,exist_ok=True)
        for fp in sorted(files):
            dlg=extract_dlg(parse_jl(fp))
            if not dlg: continue
            title=get_title(fp,tm); fn=safe_fn(title)+".md"; p=out/fn; c=1
            while p.exists(): p=out/f"{safe_fn(title)}_{c}.md"; c+=1
            write_md(p,title,fp,dlg); total_s+=1; total_m+=len(dlg)

    # Reasonix archive
    arc_dir=REASONIX_DIR/"archive"
    if arc_dir.exists():
        out=chats_dir/"Reasonix"/"归档会话"; out.mkdir(parents=True,exist_ok=True)
        for fp in sorted(arc_dir.glob("*.jsonl")):
            dlg=extract_dlg(parse_jl(fp))
            if not dlg: continue
            title=get_title(fp); fn=safe_fn(title)+".md"; p=out/fn; c=1
            while p.exists(): p=out/f"{safe_fn(title)}_{c}.md"; c+=1
            write_md(p,title,fp,dlg); total_s+=1; total_m+=len(dlg)

    # Reasonix projects
    proj_dir=REASONIX_DIR/"projects"
    if proj_dir.exists():
        for pd in sorted(proj_dir.iterdir()):
            if not pd.is_dir(): continue
            sd=pd/"sessions"
            if not sd.exists(): continue
            pname=pd.name
            # 通用路径还原：c--users-xxx-desktop-项目名 -> 项目名
            import re as _re
            m = _re.match(r'^c--users-[^-]+-(?:desktop|appdata)-(.+)$', pname)
            if m: pname = m.group(1)
            pname = pname.replace("global-workspace","global-workspace").replace("worktrees","worktrees")
            tm=None; df=sd/".display.json"
            if df.exists():
                try: tm=json.loads(df.read_text('utf-8'))
                except: pass
            files=[f for f in sd.glob("*.jsonl") if not f.name.endswith('.events.jsonl') and not f.name.endswith('.lock')]
            out=chats_dir/"Reasonix"/"项目对话"/pname; out.mkdir(parents=True,exist_ok=True)
            for fp in sorted(files):
                dlg=extract_dlg(parse_jl(fp))
                if not dlg: continue
                title=get_title(fp,tm); fn=safe_fn(title)+".md"; p=out/fn; c=1
                while p.exists(): p=out/f"{safe_fn(title)}_{c}.md"; c+=1
                write_md(p,title,fp,dlg,f"**项目:** {pname}\n"); total_s+=1; total_m+=len(dlg)

    # opencode
    if OPENCODE_DB.exists():
        try:
            conn=sqlite3.connect(str(OPENCODE_DB), timeout=5); conn.row_factory=sqlite3.Row; cur=conn.cursor()
            cur.execute("SELECT id,title,directory,time_created,agent,model FROM session ORDER BY time_created DESC")
            for sess in cur.fetchall():
                sid=sess['id']; title=sess['title'] or "无标题"; directory=sess['directory'] or ""
                cur.execute("SELECT id,data FROM message WHERE session_id=? ORDER BY time_created",(sid,))
                dialogue=[]
                for msg in cur.fetchall():
                    try:
                        md=json.loads(msg['data']); role=md.get('role','')
                        if role not in ('user','assistant'): continue
                        cur.execute("SELECT data FROM part WHERE message_id=? AND session_id=? ORDER BY time_created",(msg['id'],sid))
                        texts=[]
                        for p in cur.fetchall():
                            try:
                                pd=json.loads(p['data'])
                                if pd.get('type')=='text' and pd.get('text','').strip():
                                    texts.append(pd['text'].strip())
                            except: continue
                        if texts: dialogue.append((role,'\n\n'.join(texts)))
                    except: continue
                if not dialogue: continue
                subdir=Path(directory).parts[-1] if directory and Path(directory).parts else "其他"
                out=chats_dir/"opencode"/safe_fn(subdir); out.mkdir(parents=True,exist_ok=True)
                fn=safe_fn(title)+".md"; p=out/fn; c=1
                while p.exists(): p=out/f"{safe_fn(title)}_{c}.md"; c+=1
                md_text=f"# {title}\n\n**项目路径:** `{directory}`\n\n**消息数:** {len(dialogue)}\n\n---\n\n"
                for role,content in dialogue:
                    md_text+=f"## {'👤 用户' if role=='user' else '🤖 AI 助手'}\n\n{content}\n\n---\n\n"
                p.write_text(md_text,encoding='utf-8'); total_s+=1; total_m+=len(dialogue)
            conn.close()
        except Exception as e:
            print(f"[警告] opencode 导出失败: {e}")

    print(f"[导出] 完成: {total_s} 会话, {total_m} 条")
    return total_s, total_m

# ========== HTTP Handler ==========
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/api/data':
                data = collect_all()
                self._json_response(200, data)
            elif self.path == '/api/export':
                count, msgs = export_chats()
                self._json_response(200, {"ok":True,"sessions":count,"messages":msgs,"time":datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            elif self.path == '/favicon.ico':
                self.send_response(204); self.end_headers()
            elif self.path == '/' or self.path == '/index.html':
                self.path = '/dashboard.html'
                super().do_GET()
            else:
                super().do_GET()
        except Exception as e:
            print(f"[ERROR] {self.path}: {e}")
            traceback.print_exc()
            try:
                self._json_response(500, {"error": str(e)})
            except:
                pass

    def _json_response(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if '/api/' not in str(args[0]):
            super().log_message(format, *args)

def open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT}')

def main():
    os.chdir(str(BASE))
    print(f"\n  AI 工具箱已启动: http://localhost:{PORT}\n")
    print(f"  - 用量仪表盘: http://localhost:{PORT}/")
    print(f"  - 导出聊天:   http://localhost:{PORT}/api/export")
    print(f"\n  按 Ctrl+C 停止服务\n")
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        ThreadingHTTPServer(('', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")

if __name__ == "__main__":
    main()
