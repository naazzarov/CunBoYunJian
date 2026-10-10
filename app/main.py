import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
from collections import deque
from urllib.parse import urlsplit
import uuid
import zipfile
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import store, pipeline, access
from .limits import BodyLimit

ROOT=Path(__file__).resolve().parent.parent
MAX_BYTES=int(os.getenv('MAX_UPLOAD_MB','2048'))*1024*1024
TOKEN=os.getenv('WORKSPACE_TOKEN')
if not TOKEN:
    token_file=store.DATA/'workspace-token'
    if token_file.exists(): TOKEN=token_file.read_text().strip()
    else:
        TOKEN=secrets.token_urlsafe(32)
        fd=os.open(token_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f: f.write(TOKEN)
LOGIN_ATTEMPTS=deque()
LOGIN_LOCK=threading.Lock()
MAX_PENDING=int(os.getenv('MAX_PENDING_JOBS','6'))
MIN_FREE_BYTES=int(os.getenv('MIN_FREE_DISK_MB','2048'))*1024*1024
OBS_LOCK=threading.Lock()
OBS_ACTIVE=False

@asynccontextmanager
async def lifespan(app):
    store.init(); app.state.worker=pipeline.start()
    async def supervise():
        while True:
            await asyncio.sleep(15)
            if not app.state.worker.is_alive():
                app.state.worker.join(timeout=0)
                app.state.worker=pipeline.start()
    supervisor=asyncio.create_task(supervise())
    try:yield
    finally:
        supervisor.cancel()
        pipeline.STOP.set()
        process=app.state.worker
        process.join(timeout=3)
        if process.is_alive():
            process.terminate(); process.join(timeout=3)

app=FastAPI(title='CunBo YunJian · 村播云剪',version='1.0.0-beta.2',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

def local(request):
    return os.getenv('LOCAL_TRUST','1')=='1' and request.client and request.client.host in ['127.0.0.1','::1'] and request.url.hostname in ['localhost','127.0.0.1','::1']

@app.middleware('http')
async def guard(request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc!=request.headers.get('host'): return JSONResponse({'detail':'Cross-origin requests are blocked.'},403)
    request.state.viewer={'id':'owner','name':'Workspace owner'}
    if request.url.path.startswith('/api/') and request.url.path not in ['/api/login','/api/health']:
        bearer=request.headers.get('authorization','').removeprefix('Bearer ')
        if not local(request) and not hmac.compare_digest(bearer,TOKEN):
            viewer=access.resolve(request.cookies.get('session',''),TOKEN)
            if not viewer:return JSONResponse({'detail':'Sign in with your workspace access key.'},401)
            request.state.viewer=viewer
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    return response

class Login(BaseModel):
    key:str=Field(max_length=200)
    name:str=Field(default='Reviewer',min_length=1,max_length=40)

@app.post('/api/login')
def login(value:Login,request:Request):
    with LOGIN_LOCK:
        now=time.monotonic()
        while LOGIN_ATTEMPTS and LOGIN_ATTEMPTS[0]<now-60:LOGIN_ATTEMPTS.popleft()
        if len(LOGIN_ATTEMPTS)>=30:raise HTTPException(429,'Too many login attempts. Wait one minute and try again.')
        if not hmac.compare_digest(value.key.encode(),TOKEN.encode()):
            LOGIN_ATTEMPTS.append(now)
            raise HTTPException(401,'Incorrect workspace access key.')
    name=value.name.strip()
    if not name:raise HTTPException(422,'Enter your reviewer name.')
    token,viewer=access.issue(name,TOKEN)
    result=JSONResponse({'ok':True,'viewer':viewer})
    result.set_cookie('session',token,httponly=True,secure=os.getenv('COOKIE_SECURE','0')=='1' or request.url.scheme=='https',samesite='strict',max_age=86400)
    return result

@app.post('/api/logout')
def logout(request:Request):
    access.revoke(request.cookies.get('session',''),TOKEN)
    result=JSONResponse({'ok':True}); result.delete_cookie('session'); return result

@app.get('/api/health')
def health(): return {'ok':True}

@app.get('/api/me')
def me(request:Request):return request.state.viewer

@app.get('/api/settings')
def settings():
    import importlib.util
    backend=os.getenv('ASR_BACKEND','whisper')
    funclip_ready=bool(os.getenv('FUNCLIP_PATH') and (Path(os.environ['FUNCLIP_PATH'])/'funclip/videoclipper.py').is_file() and Path(os.getenv('FUNCLIP_PYTHON','')).is_file())
    return {'asr_backend':backend,'auto_editor_ready':bool(shutil.which(os.getenv('AUTO_EDITOR_BINARY','auto-editor'))),'subtitle_renderer_ready':bool(importlib.util.find_spec('moviepy') and shutil.which(os.getenv('IMAGEMAGICK_BINARY','magick')) and Path(os.getenv('SUBTITLE_FONT','')).is_file()),'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'asr_installed':funclip_ready if backend=='funclip' else bool(importlib.util.find_spec('faster_whisper')),'llm_model':os.getenv('LLM_MODEL','qwen3:8b'),'obs_enabled':bool(os.getenv('OBS_PASSWORD')),'max_upload_mb':MAX_BYTES//1024//1024,'version':'1.0.0-beta.2','max_pending_jobs':MAX_PENDING,'free_disk_mb':shutil.disk_usage(store.DATA).free//1024//1024,'asr_model':os.getenv('ASR_MODEL_LABEL',Path(os.getenv('ASR_MODEL','small')).name)}

@app.get('/api/readiness')
async def readiness():
    headers={}
    if os.getenv('LLM_API_KEY'):headers['Authorization']='Bearer '+os.environ['LLM_API_KEY']
    reachable=False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response=await client.get(os.getenv('LLM_BASE_URL','http://127.0.0.1:11434/v1').rstrip('/')+'/models',headers=headers)
            reachable=response.is_success
    except httpx.HTTPError:pass
    worker=getattr(app.state,'worker',None)
    with store.db() as c:pending=c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]
    return {'llm_reachable':reachable,'worker_running':bool(worker and worker.is_alive()),'pending_jobs':pending,'free_disk_mb':shutil.disk_usage(store.DATA).free//1024//1024}

class Card(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    content:str=Field(min_length=1,max_length=12000)
    kind:str='fact'
    category:str=Field(default='General',max_length=80)

@app.get('/api/knowledge')
def knowledge(): return store.cards()

def check_card(value):
    if not value.title.strip() or not value.content.strip():raise HTTPException(422,'Knowledge title and content cannot be blank.')
    if value.kind not in ['fact','rule','example']: raise HTTPException(422,'Card type must be fact, rule, or example.')

@app.post('/api/knowledge')
def add_card(value:Card):
    check_card(value)
    with store.db() as c:
        cursor=c.execute('INSERT INTO knowledge(title,content,kind,category) VALUES(?,?,?,?)',(value.title,value.content,value.kind,value.category))
        return {'id':cursor.lastrowid}

class KnowledgeImport(BaseModel):
    cards:list[Card]=Field(max_length=100)

@app.post('/api/knowledge/import')
def import_knowledge(value:KnowledgeImport):
    for card in value.cards: check_card(card)
    with store.db() as c:
        for card in value.cards:
            c.execute('INSERT INTO knowledge(title,content,kind,category) VALUES(?,?,?,?)',(card.title,card.content,card.kind,card.category))
    return {'imported':len(value.cards)}

@app.put('/api/knowledge/{card_id}')
def edit_card(card_id:int,value:Card):
    check_card(value)
    with store.db() as c:
        cursor=c.execute('UPDATE knowledge SET title=?,content=?,kind=?,category=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(value.title,value.content,value.kind,value.category,card_id))
        if not cursor.rowcount: raise HTTPException(404,'Knowledge card not found.')
    return {'ok':True}

@app.delete('/api/knowledge/{card_id}')
def delete_card(card_id:int):
    with store.db() as c: c.execute('DELETE FROM knowledge WHERE id=?',(card_id,))
    return {'ok':True}

class Config(BaseModel):
    min_seconds:int=Field(default=15,ge=3,le=300)
    max_seconds:int=Field(default=90,ge=3,le=600)
    max_clips:int=Field(default=6,ge=1,le=30)
    portrait:bool=False
    hotwords:str=Field(default='',max_length=2000)
    output_language:Literal['zh','en','source']='zh'
    knowledge_category:str=Field(default='',max_length=80)
    segmentation_mode:Literal['general','seven']='general'
    keyword_analysis:bool=False
    speaker_diarization:bool=False
    remove_silence:bool=False
    burn_subtitles:bool=False

def config_value(text):
    try: value=Config.model_validate_json(text)
    except ValueError: raise HTTPException(422,'Invalid clip settings.')
    if value.min_seconds>value.max_seconds: raise HTTPException(422,'Minimum duration must be no greater than maximum.')
    return value.model_dump()

def job_cards(config):
    cards=store.cards()
    category=config.get('knowledge_category','')
    if category:cards=[card for card in cards if card['category'] in [category,'General','通用']]
    return cards

def create_job(job_id,title,config):
    cards=job_cards(config)
    if not cards: raise HTTPException(422,'Add a knowledge card or editorial rule first.')
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        pending=c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]
        if pending>=MAX_PENDING:raise HTTPException(429,'The processing queue is full. Try again after a session finishes.')
        c.execute('INSERT INTO jobs(id,title,status,stage,config,snapshot) VALUES(?,?,?,?,?,?)',(job_id,title[:160],'queued','Waiting to process',json.dumps(config),json.dumps({'cards':cards},ensure_ascii=False)))
    pipeline.TASKS.put(job_id)
    return {'id':job_id}

async def save_upload(upload,path,limit):
    total=0
    with path.open('wb') as out:
        while chunk:=await upload.read(1024*1024):
            total+=len(chunk)
            if total>limit: raise HTTPException(413,'File exceeds the configured upload limit.')
            out.write(chunk)
    if total==0: raise HTTPException(422,'Uploaded file is empty.')
    await upload.close()

@app.post('/api/jobs')
async def upload(video:UploadFile=File(...),subtitles:UploadFile|None=File(None),title:str=Form('Untitled livestream'),config:str=Form('{}')):
    cfg=config_value(config)
    if shutil.disk_usage(store.DATA).free<MIN_FREE_BYTES:raise HTTPException(507,'Not enough free storage. Delete exported sessions or ask the workspace owner.')
    if not job_cards(cfg): raise HTTPException(422,'Add knowledge for the selected category first.')
    job_id=uuid.uuid4().hex
    folder=store.DATA/'jobs'/job_id; folder.mkdir(parents=True)
    try:
        await save_upload(video,folder/'source',MAX_BYTES)
        if subtitles:
            await save_upload(subtitles,folder/'input.srt',5*1024*1024)
            try: pipeline.parse_srt((folder/'input.srt').read_text(encoding='utf-8-sig'))
            except (ValueError,UnicodeError) as e: raise HTTPException(422,str(e))
        return create_job(job_id,title,cfg)
    except BaseException:
        shutil.rmtree(folder,ignore_errors=True); raise

@app.get('/api/jobs')
def jobs():
    with store.db() as c:
        rows=[dict(r) for r in c.execute('SELECT id,title,status,stage,progress,duration,created_at,error,plan FROM jobs ORDER BY created_at DESC,id DESC')]
        for r in rows: r['clip_count']=len(json.loads(r.pop('plan')))
    return rows

@app.get('/api/jobs/{job_id}')
def get_job(job_id:str):
    value=store.job(job_id)
    if not value: raise HTTPException(404,'Job not found.')
    with store.db() as c: value['feedback']=[dict(r) for r in c.execute('SELECT * FROM feedback WHERE job_id=?',(job_id,))]
    diagnostic=store.DATA/'jobs'/job_id/'selection-diagnostics.json'
    try:value['diagnostics']=json.loads(diagnostic.read_text()) if diagnostic.is_file() else None
    except (OSError,ValueError):value['diagnostics']=None
    return value

class Reprocess(BaseModel):
    config:Config
    subtitles:str=Field(min_length=1,max_length=1000000)

@app.post('/api/jobs/{job_id}/reprocess')
def reprocess(job_id:str,value:Reprocess):
    previous=store.job(job_id)
    if not previous:raise HTTPException(404,'Job not found.')
    if previous['status'] not in ['ready','failed']:raise HTTPException(409,'Wait for processing to finish before starting a new version.')
    config=config_value(value.config.model_dump_json())
    try:pipeline.parse_srt(value.subtitles,previous['duration'] or None)
    except ValueError as error:raise HTTPException(422,str(error))
    source=store.DATA/'jobs'/job_id/'source'
    if not source.is_file():raise HTTPException(404,'Original recording is unavailable.')
    if shutil.disk_usage(store.DATA).free-source.stat().st_size<MIN_FREE_BYTES:raise HTTPException(507,'Not enough free storage. Delete exported sessions or ask the workspace owner.')
    new_id=uuid.uuid4().hex;folder=store.DATA/'jobs'/new_id
    folder.mkdir(parents=True)
    try:
        shutil.copyfile(source,folder/'source')
        (folder/'input.srt').write_text(value.subtitles,encoding='utf-8')
        (folder/'revision-origin.json').write_text(json.dumps({'source_job':job_id,'subtitles':'manually_confirmed'}),encoding='utf-8')
        return create_job(new_id,previous['title']+' · v2',config)
    except BaseException:
        shutil.rmtree(folder,ignore_errors=True);raise

@app.post('/api/jobs/{job_id}/retry')
def retry(job_id:str):
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]>=MAX_PENDING:raise HTTPException(429,'The processing queue is full. Try again after a session finishes.')
        result=c.execute("UPDATE jobs SET status='queued',stage='Waiting to retry',error=NULL,progress=0 WHERE id=? AND status='failed'",(job_id,))
        if not result.rowcount: raise HTTPException(409,'Only failed jobs can be retried.')
    pipeline.TASKS.put(job_id); return {'ok':True}

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id:str):
    with store.db() as c:
        result=c.execute("UPDATE jobs SET status='cancelled',stage='Cancelled before processing',progress=0 WHERE id=? AND status='queued'",(job_id,))
        if not result.rowcount:raise HTTPException(409,'Only queued sessions can be cancelled.')
    return {'ok':True}

@app.delete('/api/jobs/{job_id}')
def delete_job(job_id:str):
    with store.db() as c:
        row=c.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row: raise HTTPException(404,'Job not found.')
        if row['status'] not in ['ready','failed','cancelled']: raise HTTPException(409,'Wait for processing to finish before deleting.')
        c.execute('DELETE FROM feedback WHERE job_id=?',(job_id,)); c.execute('DELETE FROM jobs WHERE id=?',(job_id,))
    shutil.rmtree(store.DATA/'jobs'/job_id,ignore_errors=True); return {'ok':True}

@app.get('/api/jobs/{job_id}/files/{filename}')
def artifact(job_id:str,filename:str):
    job=store.job(job_id)
    if not job: raise HTTPException(404,'Job not found.')
    allowed={'transcript.srt','transcript.json','transcript.txt','plan.json','keywords.json','speakers.json','七段标签.json','selection-diagnostics.json','source.mp4'}
    if job['status']=='ready':
        for i in range(len(job['plan'])): allowed.update({f'clip-{i+1:03}.mp4',f'clip-{i+1:03}.srt'})
    if filename not in allowed: raise HTTPException(404,'Artifact not found.')
    path=store.DATA/'jobs'/job_id/('source' if filename=='source.mp4' else filename)
    if not path.exists(): raise HTTPException(404,'Artifact is not ready.')
    media='video/mp4' if filename.endswith('.mp4') else 'application/json' if filename.endswith('.json') else 'text/plain; charset=utf-8'
    return FileResponse(path,media_type=media,filename=None if filename.endswith('.mp4') else filename)

@app.get('/api/jobs/{job_id}/bundle')
def bundle(job_id:str):
    job=store.job(job_id)
    if not job or job['status']!='ready': raise HTTPException(409,'Clips are not ready.')
    folder=store.DATA/'jobs'/job_id
    # Rebuilt per request with a unique filename to avoid races between downloads.
    bundle_path=folder/('export-'+uuid.uuid4().hex+'.zip')
    names=['transcript.srt','transcript.json','plan.json']
    names.extend(name for name in ['transcript.txt','keywords.json','speakers.json','七段标签.json','selection-diagnostics.json'] if (folder/name).is_file())
    for i in range(len(job['plan'])): names.extend([f'clip-{i+1:03}.mp4',f'clip-{i+1:03}.srt'])
    with zipfile.ZipFile(bundle_path,'w',compression=zipfile.ZIP_STORED) as z:
        for name in names: z.write(folder/name,name)
        z.writestr('review-feedback.json',json.dumps(get_job(job_id)['feedback'],ensure_ascii=False,indent=2))
    from starlette.background import BackgroundTask
    return FileResponse(bundle_path,filename='cunbo-yunjian-'+job_id[:8]+'.zip',background=BackgroundTask(bundle_path.unlink))

class Feedback(BaseModel):
    decision:str
    note:str=Field(default='',max_length=3000)

@app.put('/api/jobs/{job_id}/clips/{clip_index}/feedback')
def feedback(job_id:str,clip_index:int,value:Feedback,request:Request):
    job=store.job(job_id)
    if not job or job['status']!='ready' or not 0<=clip_index<len(job['plan']): raise HTTPException(404,'Clip not found.')
    if value.decision not in ['approved','rejected','needs_changes']: raise HTTPException(422,'Invalid review decision.')
    with store.db() as c:
        viewer=request.state.viewer
        c.execute('INSERT INTO feedback(job_id,clip_index,decision,note,reviewer_id,reviewer_name) VALUES(?,?,?,?,?,?) ON CONFLICT(job_id,clip_index,reviewer_id) DO UPDATE SET decision=excluded.decision,note=excluded.note,reviewer_name=excluded.reviewer_name,created_at=CURRENT_TIMESTAMP',(job_id,clip_index,value.decision,value.note,viewer['id'],viewer['name']))
    return {'ok':True}

@app.get('/api/feedback')
def feedback_list():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT f.*,j.title,j.plan FROM feedback f JOIN jobs j ON f.job_id=j.id ORDER BY f.created_at DESC')]

def obs_client():
    if not os.getenv('OBS_PASSWORD'): raise HTTPException(503,'Configure OBS_PASSWORD and OBS_RECORDING_DIR on the backend first.')
    try:
        from obsws_python import ReqClient
        return ReqClient(host=os.getenv('OBS_HOST','127.0.0.1'),port=int(os.getenv('OBS_PORT','4455')),password=os.environ['OBS_PASSWORD'],timeout=10)
    except Exception: raise HTTPException(503,'OBS is unavailable. Enable authenticated WebSocket access in OBS.')

@app.post('/api/recording/start')
def recording_start():
    global OBS_ACTIVE
    with OBS_LOCK:
        if OBS_ACTIVE: raise HTTPException(409,'A recording is already active.')
        client=obs_client()
        try:
            if client.get_record_status().output_active: raise HTTPException(409,'OBS is already recording; finish that session first.')
            client.start_record(); OBS_ACTIVE=True
        except HTTPException: raise
        except Exception: raise HTTPException(503,'OBS could not start recording. Check the scene and recording settings.')
        finally: client.disconnect()
    return {'ok':True}

@app.get('/api/recording')
def recording_status(): return {'active':OBS_ACTIVE}

@app.post('/api/recording/stop')
def recording_stop(title:str=Form('Livestream recording'),config:str=Form('{}')):
    global OBS_ACTIVE
    cfg=config_value(config)
    if not store.cards(): raise HTTPException(422,'Add knowledge before processing the recording.')
    with OBS_LOCK:
        if not OBS_ACTIVE: raise HTTPException(409,'No recording was started by this workspace.')
        client=obs_client()
        try: result=client.stop_record(); OBS_ACTIVE=False
        except Exception: raise HTTPException(503,'OBS could not stop recording. Check OBS directly.')
        finally: client.disconnect()
    root=os.getenv('OBS_RECORDING_DIR')
    if not root: raise HTTPException(503,'Recording is saved in OBS. Set OBS_RECORDING_DIR, then upload the saved recording.')
    path=Path(result.output_path).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file(): raise HTTPException(422,'OBS recording path is outside the allowed directory. Upload it manually.')
    if path.stat().st_size>MAX_BYTES: raise HTTPException(413,'Recording exceeds the configured limit. It is saved in OBS.')
    job_id=uuid.uuid4().hex; folder=store.DATA/'jobs'/job_id; folder.mkdir(parents=True)
    try:
        shutil.copyfile(path,folder/'source'); return create_job(job_id,title,cfg)
    except BaseException:
        shutil.rmtree(folder,ignore_errors=True); raise

app.add_middleware(BodyLimit,max_upload=MAX_BYTES,directory=lambda:store.DATA,min_free=MIN_FREE_BYTES)

app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
