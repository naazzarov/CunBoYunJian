import asyncio
import json
import sqlite3
from fastapi.testclient import TestClient
import pytest
from app import access,store,pipeline
from app.main import app,TOKEN
from app.limits import BodyLimit

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    store.init()
    return tmp_path


def sample_job():
    with store.db() as c:
        c.execute('INSERT INTO jobs(id,title,status,stage,config,snapshot,plan) VALUES(?,?,?,?,?,?,?)',('group','Group test','ready','Ready for manual review','{}','{}',json.dumps([{'title':'A complete point'}])))


def test_two_reviewers_do_not_overwrite_each_other(workspace):
    sample_job()
    with TestClient(app) as first,TestClient(app) as second:
        a=first.post('/api/login',json={'key':TOKEN,'name':'小明'}).json()['viewer']
        b=second.post('/api/login',json={'key':TOKEN,'name':'小红'}).json()['viewer']
        assert a['id']!=b['id']
        first.put('/api/jobs/group/clips/0/feedback',json={'decision':'approved','note':'完整清晰'})
        second.put('/api/jobs/group/clips/0/feedback',json={'decision':'needs_changes','note':'需要补充背景'})
        first.put('/api/jobs/group/clips/0/feedback',json={'decision':'rejected','note':'更新我的判断'})
        reviews=first.get('/api/jobs/group').json()['feedback']
        assert len(reviews)==2
        assert {r['reviewer_name']:r['note'] for r in reviews}=={'小明':'更新我的判断','小红':'需要补充背景'}
        assert second.get('/api/me').json()==b


def test_logout_revokes_a_copied_cookie_and_expiry_is_server_enforced(workspace):
    client=TestClient(app)
    client.post('/api/login',json={'key':TOKEN,'name':'Friend'})
    copied=client.cookies.get('session')
    assert client.get('/api/me').status_code==200
    assert client.post('/api/logout').status_code==200
    client.cookies.set('session',copied)
    assert client.get('/api/me').status_code==401
    expired,_=access.issue('Expired',TOKEN,ttl=-1)
    client.cookies.set('session',expired)
    assert client.get('/api/me').status_code==401


def test_queue_claim_is_atomic_and_cancelled_jobs_are_skipped(workspace):
    with store.db() as c:
        for name in ['queued','cancelled','ready']:
            c.execute('INSERT INTO jobs(id,title,status,stage,config,snapshot) VALUES(?,?,?,?,?,?)',(name,name,name,'Test','{}','{}'))
    assert pipeline.claim('queued')=='queued'
    assert pipeline.claim('queued') is None
    assert pipeline.claim('ready') is None
    assert pipeline.claim('cancelled') is None
    assert pipeline.claim() is None


def test_cancelled_queue_message_cannot_restart_job(workspace):
    with store.db() as c:c.execute('INSERT INTO jobs(id,title,status,stage,config,snapshot) VALUES(?,?,?,?,?,?)',('cancel','x','queued','Waiting','{}','{}'))
    client=TestClient(app);headers={'Authorization':'Bearer '+TOKEN}
    assert client.post('/api/jobs/cancel/cancel',headers=headers).status_code==200
    assert pipeline.claim('cancel') is None
    assert client.delete('/api/jobs/cancel',headers=headers).status_code==200


def test_old_feedback_migrates_without_losing_data(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    with sqlite3.connect(tmp_path/'workspace.sqlite3') as c:
        c.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,title TEXT,status TEXT,stage TEXT,config TEXT,snapshot TEXT,plan TEXT,progress INTEGER,duration REAL,created_at TEXT,error TEXT)")
        c.execute("INSERT INTO jobs(id,title,status) VALUES('old','Old recording','ready')")
        c.execute("CREATE TABLE feedback(id INTEGER PRIMARY KEY,job_id TEXT REFERENCES jobs(id),clip_index INTEGER,decision TEXT,note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(job_id,clip_index))")
        c.execute("INSERT INTO feedback(job_id,clip_index,decision,note) VALUES('old',0,'approved','Keep this exact note')")
    store.init();store.init()
    with store.db() as c:
        row=dict(c.execute('SELECT * FROM feedback').fetchone())
    assert row['note']=='Keep this exact note' and row['reviewer_id']=='legacy'


def test_oversized_body_is_rejected_before_app_consumes_it():
    consumed=[];sent=[]
    async def endpoint(scope,receive,send):consumed.append(True)
    async def receive():raise AssertionError('Body should not be read')
    async def send(message):sent.append(message)
    scope={'type':'http','method':'POST','path':'/api/knowledge','headers':[(b'content-length',b'3000000')]}
    asyncio.run(BodyLimit(endpoint,max_upload=1)(scope,receive,send))
    assert not consumed and sent[0]['status']==413


def test_chunked_body_limit_is_enforced_without_content_length():
    sent=[];messages=iter([{'type':'http.request','body':b'x'*(1024*1024),'more_body':True}]*3)
    async def endpoint(scope,receive,send):
        while True:
            message=await receive()
            if message['type']=='http.disconnect':raise RuntimeError('Client disconnected')
    async def receive():return next(messages)
    async def send(message):sent.append(message)
    asyncio.run(BodyLimit(endpoint,max_upload=1)({'type':'http','method':'POST','path':'/api/knowledge','headers':[]},receive,send))
    assert sent[0]['status']==413


def test_full_queue_rejects_new_job_and_preserves_existing_rows(workspace,monkeypatch):
    from app.main import create_job
    from fastapi import HTTPException
    monkeypatch.setattr('app.main.MAX_PENDING',1)
    with store.db() as c:
        c.execute("INSERT INTO knowledge(title,content,kind,category) VALUES('Rule','Complete points','rule','General')")
        c.execute("INSERT INTO jobs(id,title,status,stage,config,snapshot) VALUES('busy','Busy','processing','Test','{}','{}')")
    with pytest.raises(HTTPException) as error:create_job('new','New',{})
    assert error.value.status_code==429 and store.job('new') is None


def test_retrieval_leaves_room_for_relevant_facts():
    from app.core import retrieve
    cards=[{'id':i,'title':'Rule','content':'Choose complete statements','kind':'rule'} for i in range(1,10)]
    cards.append({'id':10,'title':'保质期','content':'产品保质期为三个月','kind':'fact'})
    assert 10 in [card['id'] for card in retrieve('产品保质期',cards)]


def test_overlapping_windows_keep_cross_boundary_context():
    from app.core import Cue,windows
    cues=[Cue(i*10,i*10+10,str(i)) for i in range(10)]
    chunks=list(windows(cues,max_seconds=40,overlap_seconds=20))
    assert any(cues[3] in chunk and cues[4] in chunk for chunk in chunks)
    assert {c.text for chunk in chunks for c in chunk}=={c.text for c in cues}
    assert all(chunk[-1].end-chunk[0].start<=40 for chunk in chunks)


def test_unicode_invalid_key_is_a_login_error(workspace):
    assert TestClient(app).post('/api/login',json={'key':'错误的密钥','name':'朋友'}).status_code==401


def test_unbounded_subtitle_cue_cannot_overflow_model_context():
    from app.core import Cue,windows
    with pytest.raises(ValueError):list(windows([Cue(0,10,'长'*4000)],max_chars=3000))


def test_job_keeps_only_selected_and_general_knowledge(workspace,monkeypatch):
    from app.main import create_job
    with store.db() as c:
        for category in ['直播产品','Other category','General']:
            c.execute('INSERT INTO knowledge(title,content,kind,category) VALUES(?,?,?,?)',(category,'Keep a complete statement','rule',category))
    result=create_job('scoped','Scoped',{'knowledge_category':'直播产品'})
    snapshot=store.job(result['id'])['snapshot']['cards']
    assert {card['category'] for card in snapshot}=={'直播产品','General'}
