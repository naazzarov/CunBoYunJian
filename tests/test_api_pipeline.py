import io
import json
import shutil
import subprocess
import zipfile
import httpx
import pytest
from fastapi.testclient import TestClient
from app import store,pipeline
from app.main import app,TOKEN

@pytest.fixture
def client(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(total=20*1024**3,used=10*1024**3,free=10*1024**3))
    monkeypatch.setattr(store,'DATA',tmp_path)
    store.init()
    return TestClient(app)

def auth():return {'Authorization':'Bearer '+TOKEN}

def test_workspace_security(client):
    assert client.get('/api/knowledge').status_code==401
    assert client.get('/api/health').status_code==200
    assert client.post('/api/login',json={'key':'wrong'}).status_code==401
    r=client.post('/api/login',json={'key':TOKEN})
    assert r.status_code==200 and 'HttpOnly' in r.headers['set-cookie']
    assert client.get('/api/knowledge').status_code==200
    assert client.post('/api/knowledge',json={'title':'x','content':'x'},headers={'origin':'https://attacker.example'}).status_code==403
    assert client.get('/data/workspace-token').status_code==404

def test_card_revisions_and_validation(client):
    r=client.post('/api/knowledge',headers=auth(),json={'title':'Audience','content':'Teach beginners','kind':'rule'})
    card_id=r.json()['id']
    client.put('/api/knowledge/'+str(card_id),headers=auth(),json={'title':'Audience','content':'Teach beginners with concrete examples','kind':'rule'})
    assert client.get('/api/knowledge',headers=auth()).json()[0]['revision']==2
    assert client.post('/api/knowledge',headers=auth(),json={'title':'','content':'x'}).status_code==422
    assert client.post('/api/knowledge',headers=auth(),json={'title':'x','content':'x','kind':'unknown'}).status_code==422

def test_llm_invalid_response_is_retried(monkeypatch):
    from app.core import Cue
    actual_client=httpx.Client
    calls=[]
    def respond(request):
        calls.append(json.loads(request.content))
        text='not json' if len(calls)==1 else json.dumps({'clips':[{'start_cue':1,'end_cue':1,'title':'Answer','reason':'Complete statement','score':80,'knowledge_ids':[1]}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':text}}]})
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:actual_client(transport=httpx.MockTransport(respond),**kw))
    clips,cards=pipeline.select([Cue(0,4,'Useful statement')],[{'id':1,'title':'Rule','content':'Useful statement','kind':'rule'}],{'min_seconds':3,'max_seconds':10,'max_clips':2})
    assert len(calls)==2 and len(clips)==1
    assert len(calls[1]['messages'])==4 and calls[1]['messages'][-2]['role']=='assistant'

def test_llm_unknown_knowledge_is_rejected(monkeypatch):
    from app.core import Cue
    actual_client=httpx.Client
    raw={'clips':[{'start_cue':1,'end_cue':1,'title':'Answer','reason':'Statement','score':80,'knowledge_ids':[999]}]}
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}]}))
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:actual_client(transport=transport,**kw))
    with pytest.raises(ValueError): pipeline.select([Cue(0,4,'Useful statement')],[{'id':1,'title':'Rule','content':'Useful','kind':'rule'}],{'min_seconds':3,'max_seconds':10,'max_clips':2})

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg is required for media integration')
def test_real_media_pipeline_export_feedback_and_snapshot(client,tmp_path,monkeypatch):
    source=tmp_path/'test.mp4'
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=8','-f','lavfi','-i','sine=frequency=440:duration=8','-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True)
    client.post('/api/knowledge',headers=auth(),json={'title':'Rule','content':'Choose complete explanations','kind':'rule'})
    subtitles='1\n00:00:01,000 --> 00:00:04,000\nHere is the explanation.\n\n2\n00:00:04,000 --> 00:00:07,000\nThis is the complete answer.\n'
    config={'min_seconds':3,'max_seconds':10,'max_clips':2,'portrait':True}
    with source.open('rb') as f:
        r=client.post('/api/jobs',headers=auth(),files={'video':('test.mp4',f,'video/mp4'),'subtitles':('test.srt',subtitles,'text/plain')},data={'title':'Integration sample','config':json.dumps(config)})
    assert r.status_code==200
    job_id=r.json()['id']
    # Mutating live knowledge must not alter the queued job's evidence.
    client.put('/api/knowledge/1',headers=auth(),json={'title':'Changed rule','content':'A different lesson','kind':'rule'})
    monkeypatch.setattr(pipeline,'select',lambda cues,cards,cfg:([{'start':1,'end':7,'title':'Complete answer','reason':'Explanation and conclusion','category':'Q&A','score':90,'knowledge_ids':[1]}],cards))
    pipeline.run(job_id)
    job=client.get('/api/jobs/'+job_id,headers=auth()).json()
    assert job['status']=='ready' and job['snapshot']['cards'][0]['title']=='Rule'
    out=store.DATA/'jobs'/job_id/'clip-001.mp4'
    media=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out)]))
    assert abs(float(media['format']['duration'])-6)<.2
    video=next(s for s in media['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(720,1280)
    audio=next(s for s in media['streams'] if s['codec_type']=='audio')
    assert abs(float(video['duration'])-float(audio['duration']))<.2
    srt_response=client.get('/api/jobs/'+job_id+'/files/clip-001.srt',headers=auth())
    assert '00:00:00,000 --> 00:00:03,000' in srt_response.text
    assert client.get('/api/jobs/'+job_id+'/files/source',headers=auth()).status_code==404
    assert client.put('/api/jobs/'+job_id+'/clips/0/feedback',headers=auth(),json={'decision':'approved','note':'Clear complete answer'}).status_code==200
    assert len(client.get('/api/feedback',headers=auth()).json())==1
    bundle=client.get('/api/jobs/'+job_id+'/bundle',headers=auth())
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
        assert 'clip-001.mp4' in z.namelist()
        assert json.loads(z.read('review-feedback.json'))[0]['decision']=='approved'
        manifest=json.loads(z.read('plan.json'))
        assert manifest['limits']['output_language']=='zh'
        assert 'Simplified Chinese' in manifest['prompt']
    assert client.delete('/api/jobs/'+job_id,headers=auth()).status_code==200
    assert not out.exists()

@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg is required')
def test_audio_extraction_preserves_leading_track_offset(tmp_path):
    import array
    import wave
    source=tmp_path/'offset.mp4'; audio=tmp_path/'audio.wav'
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24:duration=5','-itsoffset','1.5','-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-c:a','aac',str(source)],check=True)
    pipeline.extract_audio(source,audio)
    with wave.open(str(audio)) as wav:
        data=array.array('h',wav.readframes(wav.getnframes()))
        rate=wav.getframerate()
    assert max(abs(x) for x in data[:rate])<5
    assert max(abs(x) for x in data[2*rate:3*rate])>1000

def test_knowledge_import_is_atomic(client):
    payload={'cards':[{'title':'Valid','content':'Fact','kind':'fact'},{'title':'Invalid','content':'Rule','kind':'unrecognized'}]}
    assert client.post('/api/knowledge/import',headers=auth(),json=payload).status_code==422
    assert client.get('/api/knowledge',headers=auth()).json()==[]
    payload['cards'][1]['kind']='rule'
    assert client.post('/api/knowledge/import',headers=auth(),json=payload).json()['imported']==2
    assert len(client.get('/api/knowledge',headers=auth()).json())==2

@pytest.mark.skipif(not shutil.which('ffprobe'),reason='ffprobe required')
def test_uploaded_playlist_cannot_fetch_network_or_local_files(tmp_path):
    fake=tmp_path/'source.m3u8'
    fake.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:1/private\n#EXT-X-ENDLIST\n')
    with pytest.raises(RuntimeError) as error: pipeline.probe(fake)
    assert 'whitelist' in str(error.value)

def test_rule_heading_is_replaced_by_actual_transcript_title(monkeypatch):
    from app.core import Cue
    actual_client=httpx.Client
    count=0
    def respond(request):
        nonlocal count
        count+=1
        raw={'clips':[{'start_cue':1,'end_cue':1,'title':'Editorial brief' if count==1 else 'A complete explanation','reason':'Speaker explains a complete point','score':80,'knowledge_ids':[1]}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}]})
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:actual_client(transport=httpx.MockTransport(respond),**kw))
    clips,_=pipeline.select([Cue(0,4,'A complete explanation')],[{'id':1,'title':'Editorial brief','content':'Choose complete points','kind':'rule'}],{'min_seconds':3,'max_seconds':10,'max_clips':2})
    assert count==1 and clips[0]['title']=='A complete explanation' and clips[0]['title_source']=='transcript'


def test_output_language_validation():
    from app.main import config_value
    from fastapi import HTTPException
    assert config_value('{}')['output_language']=='zh'
    for language in ['zh','en','source']:
        assert config_value(json.dumps({'output_language':language}))['output_language']==language
    with pytest.raises(HTTPException) as error:
        config_value(json.dumps({'output_language':'unknown'}))
    assert error.value.status_code==422


def test_chinese_knowledge_and_language_reach_model(monkeypatch):
    from app.core import Cue
    actual_client=httpx.Client
    captured=[]
    def respond(request):
        captured.append(json.loads(request.content))
        clip={'start_cue':1,'end_cue':2,'title':'如何选择合适的产品','category':'产品讲解','reason':'先说明用途，再解释选择方法，内容完整。','score':85,'knowledge_ids':[7]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'clips':[clip]},ensure_ascii=False)}}]})
    monkeypatch.setattr(pipeline.httpx,'Client',lambda **kw:actual_client(transport=httpx.MockTransport(respond),**kw))
    transcript=[Cue(0,3,'今天介绍产品选择。'),Cue(3,7,'根据实际用途选择适合的产品。')]
    cards=[{'id':7,'title':'产品选择规则','content':'选择完整说明产品用途与选择方法的片段。','kind':'rule','category':'产品'}]
    for language,label in [('zh','Simplified Chinese'),('en','English'),('source','the transcript language')]:
        clips,selected=pipeline.select(transcript,cards,{'min_seconds':3,'max_seconds':10,'max_clips':2,'output_language':language})
        request=captured[-1]
        payload=json.loads(request['messages'][1]['content'])
        assert label in request['messages'][0]['content']
        assert payload['transcript'][0]['text']=='今天介绍产品选择。'
        assert payload['knowledge'][0]['content']==cards[0]['content']
        assert clips[0]['title']=='如何选择合适的产品'
        assert clips[0]['start']==0 and clips[0]['end']==7


def test_corrected_subtitles_create_new_job_and_preserve_original(client,tmp_path):
    client.post('/api/knowledge',headers=auth(),json={'title':'Rule','content':'Complete speech','kind':'rule'})
    original='a'*32
    folder=tmp_path/'jobs'/original;folder.mkdir(parents=True)
    (folder/'source').write_bytes(b'original recording')
    with store.db() as c:
        c.execute("INSERT INTO jobs(id,title,status,stage,config,duration) VALUES(?,?,?,?,?,?)",(original,'Original','ready','No qualifying clips found','{}',30))
    subtitles='1\n00:00:01,000 --> 00:00:20,000\n校对后的文字\n'
    result=client.post('/api/jobs/'+original+'/reprocess',headers=auth(),json={'config':{'min_seconds':15,'max_seconds':30},'subtitles':subtitles})
    assert result.status_code==200
    new_id=result.json()['id']
    assert new_id!=original and store.job(original)['status']=='ready'
    assert (tmp_path/'jobs'/new_id/'source').read_bytes()==b'original recording'
    assert (tmp_path/'jobs'/new_id/'input.srt').read_text()==subtitles
    assert client.get('/api/jobs/'+original+'/files/source.mp4').status_code==401
    assert client.get('/api/jobs/'+original+'/files/source.mp4',headers=auth()).status_code==200
    bad=client.post('/api/jobs/'+original+'/reprocess',headers=auth(),json={'config':{},'subtitles':'invalid'})
    assert bad.status_code==422
