"""Show first-use download progress, then hand port 6006 to ComfyUI."""
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

from model_store import DATA, PROJECT, STATUS, prepare, status

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MiniMax-H3-30s</title>
<style>body{background:#10151e;color:#edf0f6;font:17px system-ui;margin:10vh auto;max-width:680px;padding:24px;line-height:1.8}h1{font-size:30px}p{color:#abb9cb}progress{width:100%;height:20px}#error{color:#ffb6b6}</style>
<h1>MiniMax-H3-30s</h1><p>独立30秒有声视频工作流</p><div id="message">正在准备模型与运行环境…</div><progress id="progress"></progress><p id="file"></p><p>首次使用需要准备约42.47GB模型，保存在免费数据盘。再次启动可复用已下载模型。准备完成后自动打开工作流。</p><p id="error"></p>
<script>async function tick(){try{const r=await fetch('/status.json',{cache:'no-store'});if(!r.ok){location.reload();return}const s=await r.json();const labels={downloading:'正在下载模型',verifying:'正在校验模型',models_ready:'正在启动工作流',starting:'正在启动工作流',error:'准备未完成'};document.getElementById('message').textContent=labels[s.stage]||'正在准备';const p=document.getElementById('progress');if(s.stage==='downloading'){p.max=s.overall_total||s.total;p.value=s.overall_completed||s.completed;document.getElementById('file').textContent='总进度 '+(p.value/p.max*100).toFixed(1)+'% · 当前文件 '+(s.file||'')}else{p.removeAttribute('value')}document.getElementById('error').textContent=s.stage==='error'?(s.message||''):''}catch(e){location.reload()}}setInterval(tick,4000);tick();</script></html>'''


class Progress(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?')[0] == '/status.json':
            content = STATUS.read_bytes() if STATUS.exists() else b'{}'
            kind = 'application/json; charset=utf-8'
        else:
            content, kind = PAGE.encode('utf-8'), 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    DATA.mkdir(parents=True, exist_ok=True)
    service_lock = (DATA / '.service.lock').open('a')
    try:
        fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('MiniMax-H3-30s is already running')
    os.set_inheritable(service_lock.fileno(), True)
    comfy = Path('/root/H3-30s/ComfyUI')
    port = int(os.environ.get('PORT', '6006'))
    server = ThreadingHTTPServer(('0.0.0.0', port), Progress)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        prepare(comfy)
        for name in ('output', 'input', 'temp'):
            (DATA/name).mkdir(exist_ok=True)
        status(stage='starting', message='模型准备完成，正在启动30秒工作流。')
    except Exception as error:
        status(stage='error', message=str(error))
        print('PREPARATION_ERROR', str(error), flush=True)
        threading.Event().wait()
    server.shutdown()
    server.server_close()
    os.chdir(comfy)
    args = [sys.executable, 'main.py', '--listen', '0.0.0.0', '--port', str(port),
            '--disable-auto-launch', '--preview-method', 'none', '--cache-none',
            '--disable-pinned-memory', '--output-directory', str(DATA/'output'),
            '--input-directory', str(DATA/'input'), '--temp-directory', str(DATA/'temp'),
            '--enable-compress-response-body', '--front-end-root', '/root/H3-30s/frontend']
    args += sys.argv[1:]
    os.execv(sys.executable, args)
