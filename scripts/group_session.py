"""Start a protected Mac-hosted group test. Private runtime configuration stays under data/."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--config',type=Path,default=ROOT/'data/group-config.json')
a=p.parse_args()
if not a.config.exists():raise SystemExit('Missing private group configuration. See GROUP-TEST.zh-CN.md.')
config=json.loads(a.config.read_text())
os.chdir(ROOT)
data=Path(config.get('data',ROOT/'data')).resolve();data.mkdir(parents=True,exist_ok=True)
# Refuse a second launcher; never kill an unrelated process to reclaim a port.
lock=(data/'group.lock').open('a+')
if os.name=='nt':
    import msvcrt
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit('A group-test launcher is already running.')
else:
    import fcntl
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:raise SystemExit('A group-test launcher is already running.')
children=[];logs=[]
stop_file=data/'group.stop'
stop_file.unlink(missing_ok=True)
env=dict(os.environ,CLIPFORGE_DATA=str(data),LOCAL_TRUST='0',COOKIE_SECURE='1',MAX_UPLOAD_MB='90',MAX_PENDING_JOBS='6',MIN_FREE_DISK_MB='2048',TRANSCRIPT_WINDOW_CHARS='3000')
for key in ['LLM_BASE_URL','LLM_MODEL','LLM_JSON_SCHEMA','ASR_MODEL','ASR_MODEL_LABEL','ASR_CPU_THREADS','ASR_BACKEND','FUNCLIP_PYTHON','FUNCLIP_PATH','FUNASR_MODEL','FUNASR_MODEL_REVISION','MODELSCOPE_CACHE','MODELSCOPE_HOME','HF_HOME','LLM_TIMEOUT_SECONDS','EDITOR_PYTHON','AUTO_EDITOR_BINARY','IMAGEMAGICK_BINARY','SUBTITLE_FONT']:
    if key in config:env[key]=str(config[key])
port=int(config.get('port',8766))

def reachable(url):
    try:
        with urllib.request.urlopen(url,timeout=2) as response:return response.status==200
    except Exception:return False

def start(command,name):
    stream=(data/(name+'.log')).open('w');logs.append(stream)
    process=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT)
    children.append(process);return process

def await_service(process,url,timeout=180):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError('A service exited; inspect its log in data/.')
        if reachable(url):return
        time.sleep(1)
    raise RuntimeError('Service startup timed out; inspect its log in data/.')

try:
    if reachable(f'http://127.0.0.1:{port}/api/health'):raise RuntimeError('The studio port is already in use. Stop the previous studio before launching this version.')
    database=data/'workspace.sqlite3'
    if database.exists():
        backup=data/'backups';backup.mkdir(exist_ok=True)
        with sqlite3.connect(database) as source,sqlite3.connect(backup/('workspace-'+time.strftime('%Y%m%d-%H%M%S')+'.sqlite3')) as destination:source.backup(destination)
    command=config.get('llm_command')
    if command:
        if reachable(env['LLM_BASE_URL']+'/models'):raise RuntimeError('The configured model port is already in use. Stop the previous model process.')
        print('Starting selection model…',flush=True)
        await_service(start(command,'group-model'),env['LLM_BASE_URL']+'/models')
    elif not reachable(env.get('LLM_BASE_URL','http://127.0.0.1:11434/v1')+'/models'):
        raise RuntimeError('Start the configured model service before launching the studio.')
    print('Starting studio…',flush=True)
    studio=start([config.get('python',sys.executable),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--workers','1','--no-proxy-headers','--log-level','warning'],'group-studio')
    await_service(studio,f'http://127.0.0.1:{port}/api/health',30)
    tunnel=start([config.get('cloudflared','cloudflared'),'tunnel','--url',f'http://127.0.0.1:{port}','--protocol','http2','--no-autoupdate'],'group-tunnel')
    deadline=time.monotonic()+60;url=None
    while time.monotonic()<deadline:
        if tunnel.poll() is not None:raise RuntimeError('The phone tunnel exited; inspect data/group-tunnel.log.')
        match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',(data/'group-tunnel.log').read_text(errors='replace'))
        if match:url=match.group(0);break
        time.sleep(1)
    if not url:raise RuntimeError('No phone link was created; inspect data/group-tunnel.log.')
    (data/'group-access.json').write_text(json.dumps({'url':url,'version':'1.0.0-beta.2','started_at':time.strftime('%Y-%m-%d %H:%M:%S')},indent=2))
    key=env.get('WORKSPACE_TOKEN') or (data/'workspace-token').read_text().strip()
    print('\nOpen on phones / 手机访问：'+url,flush=True)
    print('Workspace key / 工作区密钥：'+key,flush=True)
    print('Each friend enters their own nickname. Keep this window open. Ctrl+C stops sharing.\n每位朋友填写自己的昵称。保持窗口打开，按 Ctrl+C 停止共享。',flush=True)
    if sys.platform=='darwin':children.append(subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())]))
    while True:
        if stop_file.exists():
            print('Stopping group test… / 正在停止好友测试…',flush=True)
            break
        for process in children:
            if process.poll() is not None:raise RuntimeError('A service stopped. Inspect the logs and restart the launcher.')
        time.sleep(2)
except KeyboardInterrupt:print('\nStopping group test…',flush=True)
except Exception as error:print(str(error),file=sys.stderr);sys.exitcode=1
finally:
    for process in reversed(children):
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=12)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    for stream in logs:stream.close()
    lock.close()
    stop_file.unlink(missing_ok=True)
if getattr(sys,'exitcode',0):raise SystemExit(1)
