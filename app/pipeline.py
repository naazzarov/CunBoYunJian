import json
import logging
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import multiprocessing
import sys
import time
from dataclasses import asdict
import httpx
from . import store
from . import editorial
from . import roughcut
from .core import Cue, parse_srt, srt, retrieve, windows, validate_plan, resolve_cue_plan, duration_ranges

log=logging.getLogger('cunbo_yunjian')
MP=multiprocessing.get_context('spawn')
TASKS=MP.Queue()
STOP=MP.Event()
MODEL=None
TOKEN_USAGE=[]
SELECTION_TRACE=[]
ROOT=Path(__file__).resolve().parent.parent
MEDIA_FLAGS=['-protocol_whitelist','file,pipe','-format_whitelist','mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpegts,flv']

def command(args,timeout=7200):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if result.returncode: raise RuntimeError('Media processing failed: '+result.stderr[-1800:])
    return result.stdout

def probe(path):
    obj=json.loads(command(['ffprobe','-v','error',*MEDIA_FLAGS,'-show_format','-show_streams','-of','json',str(path)],120))
    if not any(s.get('codec_type')=='video' for s in obj['streams']): raise ValueError('File has no video track.')
    duration=float(obj['format'].get('duration',0))
    if not 0<duration<=float(os.getenv('MAX_DURATION_SECONDS','14400')): raise ValueError('Video must be between 0 and 4 hours (configurable).')
    return duration,any(s.get('codec_type')=='audio' for s in obj['streams'])

def extract_audio(source, output):
    # Preserve leading audio silence/offset against the recording presentation timeline.
    command(['ffmpeg','-nostdin','-y','-v','error',*MEDIA_FLAGS,'-i',str(source),'-vn','-af','aresample=async=1:first_pts=0','-ac','1','-ar','16000','-c:a','pcm_s16le',str(output)])

def transcribe(path, hotwords):
    global MODEL
    try: from faster_whisper import WhisperModel
    except ImportError: raise RuntimeError('Speech engine is not installed. Install requirements-asr.txt, or attach an existing SRT from FunClip.')
    if MODEL is None:
        options={'device':os.getenv('ASR_DEVICE','cpu'),'compute_type':os.getenv('ASR_COMPUTE_TYPE','int8'),'download_root':str(store.DATA/'models'),'cpu_threads':int(os.getenv('ASR_CPU_THREADS','4'))}
        try: MODEL=WhisperModel(os.getenv('ASR_MODEL','small'),local_files_only=True,**options)
        except Exception: MODEL=WhisperModel(os.getenv('ASR_MODEL','small'),**options)
    segments,_=MODEL.transcribe(str(path),vad_filter=True,initial_prompt=hotwords or None,language=os.getenv('ASR_LANGUAGE') or None)
    cues=[Cue(s.start,s.end,s.text.strip()) for s in segments if s.text.strip() and s.end>s.start]
    if not cues: raise ValueError('No speech detected. Check the recorded audio.')
    return cues

def selection_prompt(config):
    prompt=(ROOT/'prompts/select.md').read_text()
    if config.get('segmentation_mode')=='seven':
        prompt+='\n'+(ROOT/'prompts/01_七段选段.md').read_text()+'\nAllowed category labels: '+json.dumps(editorial.categories(config),ensure_ascii=False)
    language=config.get('output_language','source')
    prompt+='\nOutput language for title, category and reason: '+{'zh':'Simplified Chinese (简体中文).','en':'English.','source':'the transcript language.'}[language]+' Preserve proper names and exact quoted words where needed. Do not translate or alter subtitle text.'
    return prompt

def select(chunk, cards, config):
    endpoint=os.getenv('LLM_BASE_URL','http://127.0.0.1:11434/v1').rstrip('/')
    selected=retrieve(' '.join(c.text for c in chunk),cards)
    # Keep the context bounded; the immutable snapshot retains the complete cards.
    selected=[dict(card,content=card['content'][:1200],excerpted=len(card['content'])>1200) for card in selected]
    ranges=duration_ranges(chunk,config['min_seconds'],config['max_seconds'])
    if not ranges:return [],selected
    payload={'duration_valid_ranges':{key:round(chunk[b-1].end-chunk[a-1].start,3) for key,(a,b) in ranges.items()},'limits':config,'knowledge':selected,'transcript':[dict(asdict(c),cue_id=i) for i,c in enumerate(chunk,1)]}
    prompt=selection_prompt(config)
    headers={}
    if os.getenv('LLM_API_KEY'): headers['Authorization']='Bearer '+os.environ['LLM_API_KEY']
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    response_format={'type':'json_object'}
    if os.getenv('LLM_JSON_SCHEMA','0')=='1':
        allowed_ids=[c['id'] for c in selected]
        schema={'type':'object','additionalProperties':False,'required':['clips'],'properties':{'clips':{'type':'array','maxItems':config['max_clips'],'items':{'type':'object','additionalProperties':False,'required':['range_id','title','category','reason','score','knowledge_ids'],'properties':{'range_id':{'type':'string','enum':list(ranges)},'title':{'type':'string','minLength':1},'category':{'type':'string','minLength':1},'reason':{'type':'string','minLength':1},'score':{'type':'integer','minimum':0,'maximum':100},'knowledge_ids':{'type':'array','items':{'type':'integer','enum':allowed_ids} if allowed_ids else {'type':'integer'},'maxItems':len(allowed_ids)}}}}}}
        response_format={'type':'json_schema','json_schema':{'name':'clip_plan','strict':True,'schema':schema}}
        if config.get('segmentation_mode')=='seven':schema['properties']['clips']['items']['properties']['category']['enum']=editorial.categories(config)
    failure=None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=float(os.getenv('LLM_TIMEOUT_SECONDS','480'))) as client:
                response=client.post(endpoint+'/chat/completions',headers=headers,json={'model':os.getenv('LLM_MODEL','qwen3:8b'),'messages':messages,'temperature':0.2,'max_tokens':4096,'response_format':response_format})
                response.raise_for_status()
            response_data=response.json()
            TOKEN_USAGE.append(response_data.get('usage'))
            content=response_data['choices'][0]['message']['content']
            content=re.sub(r'<think>.*?</think>','',content,flags=re.S).strip()
            content=re.sub(r'^```(?:json)?\s*|\s*```$','',content)
            trace={'attempt':attempt+1,'raw_content':content,'proposed_count':0,'accepted_count':0,'duration_rejections':[]}
            SELECTION_TRACE.append(trace)
            raw=resolve_cue_plan(json.loads(content),chunk,ranges)
            valid=validate_plan(raw,chunk,chunk[-1].end,config['min_seconds'],config['max_seconds'],config['max_clips'])
            rejected=[{'start':c['start'],'end':c['end'],'seconds':round(c['end']-c['start'],3),'reason':'duration_out_of_range'} for c in raw['clips'] if not config['min_seconds']<=c['end']-c['start']<=config['max_seconds']]
            trace.update(proposed_count=len(raw['clips']),accepted_count=len(valid),duration_rejections=rejected)
            if rejected and not valid:
                raise ValueError('Selected durations '+str([c['seconds'] for c in rejected])+' do not meet '+str(config['min_seconds'])+'–'+str(config['max_seconds'])+' seconds. Select coherent ranges spanning multiple cues. Check end time minus start time. Do not pad with unrelated speech; return an empty clips array if no range qualifies.')
            allowed={c['id'] for c in selected}
            if any(set(c['knowledge_ids'])-allowed for c in valid): raise ValueError('Model cited unknown knowledge.')
            if config.get('segmentation_mode')=='seven' and any(c['category'] not in editorial.categories(config) for c in valid):raise ValueError('Choose one of the seven supplied category labels.')
            headings={c['title'].strip().lower() for c in selected if c['kind'] in ['rule','example']}
            for clip in valid:
                if clip['title'].lower() in headings:
                    clip['title']=next(c.text for c in chunk if c.start==clip['start'])[:120]
                    clip['title_source']='transcript'
                else: clip['title_source']='model'
            return valid,selected
        except (ValueError,KeyError,TypeError) as e:
            failure=e
            if 'trace' in locals():trace['validation_error']=str(e)
            if 'content' in locals() and isinstance(content,str): messages.append({'role':'assistant','content':content[:4000]})
            messages.append({'role':'user','content':'Your last response failed validation: '+str(e)+'. Return corrected JSON using the supplied data.'})
        except httpx.HTTPError:
            raise RuntimeError('Cannot reach the configured LLM. Start Ollama and pull the configured model, or check your cloud endpoint and API key.')
    raise ValueError('Model returned an invalid edit plan after retry: '+str(failure))

def cut(source,out,start,end,portrait=False):
    args=['ffmpeg','-nostdin','-y','-v','error',*MEDIA_FLAGS,'-i',str(source),'-ss',str(start),'-t',str(end-start),'-map','0:v:0','-map','0:a:0?']
    if portrait: args+=['-vf','scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1']
    else: args+=['-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1']
    args+=['-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-movflags','+faststart',str(out)]
    command(args)

def run(job_id):
    job=store.job(job_id); folder=store.DATA/'jobs'/job_id; config=job['config']
    started=time.monotonic();metrics={};TOKEN_USAGE.clear();SELECTION_TRACE.clear()
    source=folder/'source'; cues=[]
    store.update(job_id,status='processing',stage='Inspecting recording',progress=5,error=None)
    duration,audio=probe(source)
    store.update(job_id,duration=duration)
    if (folder/'input.srt').exists():
        cues=parse_srt((folder/'input.srt').read_text(encoding='utf-8-sig'),duration)
    else:
        if not audio: raise ValueError('Recording has no audio. Include livestream audio or attach an SRT.')
        store.update(job_id,stage='Transcribing speech',progress=15)
        wav=folder/'audio.wav'
        extract_audio(source,wav)
        speech_started=time.monotonic()
        if os.getenv('ASR_BACKEND','whisper')=='funclip':
            adapter=folder/'speech-result.json'
            args=[os.getenv('FUNCLIP_PYTHON',sys.executable),str(ROOT/'scripts/funclip_transcribe.py'),'--audio',str(wav),'--out',str(adapter),'--hotwords',config.get('hotwords','')]
            if config.get('speaker_diarization'):args.append('--speakers')
            command(args)
            result=json.loads(adapter.read_text());cues=[Cue(**item) for item in result['cues']]
            (folder/'speakers.json').write_text(json.dumps(result['speakers'],ensure_ascii=False,indent=2),encoding='utf-8')
        else:cues=transcribe(wav,config.get('hotwords',''))
        metrics['speech_seconds']=round(time.monotonic()-speech_started,3)
        # Validate generated timestamps through the same path as uploaded subtitles.
        cues=parse_srt(srt(cues),duration)
    (folder/'transcript.srt').write_text(srt(cues),encoding='utf-8')
    (folder/'transcript.json').write_text(json.dumps([asdict(c) for c in cues],ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'transcript.txt').write_text('\n'.join(c.text for c in cues),encoding='utf-8')
    if config.get('keyword_analysis'):
        analysis_started=time.monotonic()
        (folder/'keywords.json').write_text(json.dumps(editorial.keyword_analysis(cues),ensure_ascii=False,indent=2),encoding='utf-8')
        metrics['jieba_seconds']=round(time.monotonic()-analysis_started,3)
    cards=job['snapshot'].get('cards',[])
    if not cards: raise ValueError('Add at least one knowledge card or editorial rule before processing.')
    chunks=list(windows(cues,max_chars=int(os.getenv('TRANSCRIPT_WINDOW_CHARS','3000')),overlap_seconds=min(config['max_seconds'],120))); plan=[]; retrieved={}
    selection_started=time.monotonic()
    for i,chunk in enumerate(chunks):
        store.update(job_id,stage=f'Selecting moments {i+1}/{len(chunks)}',progress=30+int(30*i/len(chunks)))
        try:clips,knowledge=select(chunk,cards,config)
        finally:(folder/'selection-diagnostics.json').write_text(json.dumps({'attempts':SELECTION_TRACE,'limits':config},ensure_ascii=False,indent=2),encoding='utf-8')
        plan.extend(clips)
        retrieved.update({c['id']:c for c in knowledge})
    metrics['selection_seconds']=round(time.monotonic()-selection_started,3)
    final=[]
    for c in sorted(plan,key=lambda x:-x['score']):
        if not any(c['start']<x['end'] and c['end']>x['start'] for x in final): final.append(c)
        if len(final)>=config['max_clips']: break
    final.sort(key=lambda x:x['start'])
    if config.get('segmentation_mode')=='seven':
        tags=[{'segment':c['category'],'start':c['start'],'end':c['end'],'key_sentence':next((cue.text for cue in cues if cue.start==c['start']),''),'reason':c['reason'],'knowledge_ids':c['knowledge_ids']} for c in final]
        (folder/'七段标签.json').write_text(json.dumps(tags,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'clips':final,'knowledge':list(retrieved.values()),'model':os.getenv('LLM_MODEL','qwen3:8b'),'prompt':selection_prompt(config),'limits':config,'source_duration':duration,'knowledge_snapshot':cards,'speech_model':os.getenv('ASR_MODEL_LABEL',Path(os.getenv('ASR_MODEL','small')).name),'supplied_subtitles':(folder/'input.srt').exists(),'selection_model':os.getenv('LLM_MODEL','qwen3:8b')}
    if manifest['supplied_subtitles']:manifest['speech_model']=None
    elif os.getenv('ASR_BACKEND','whisper')=='funclip':
        manifest['speech_model']=result['model']
        manifest['speech_model_revision']=result['model_revision']
    (folder/'plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    store.update(job_id,plan=json.dumps(final,ensure_ascii=False),stage='Rendering clips',progress=65)
    rendering_started=time.monotonic()
    for i,c in enumerate(final):
        stem=f'clip-{i+1:03}'
        cut(source,folder/(stem+'.mp4'),c['start'],c['end'],config['portrait'])
        clip_cues=parse_srt(srt(cues,c['start'],c['end']))
        if config.get('remove_silence'):
            editor=os.environ.get('AUTO_EDITOR_BINARY')
            if not editor:raise RuntimeError('Configure AUTO_EDITOR_BINARY before enabling silence removal.')
            timeline=folder/(stem+'.timeline.v3')
            command([editor,str(folder/(stem+'.mp4')),'--margin','0.25sec','--export','v3','--output',str(timeline),'--no-open'])
            clip_duration,has_audio=probe(folder/(stem+'.mp4'))
            if not has_audio:raise RuntimeError('Silence removal requires a recording with audio.')
            ranges=roughcut.retained_ranges(json.loads(timeline.read_text()),clip_cues,clip_duration)
            new_duration=sum(b-a for a,b in ranges)
            c['silence_removal']={'retained_ranges':ranges,'removed_seconds':round(clip_duration-new_duration,3)}
            if ranges and new_duration>=config['min_seconds'] and new_duration<clip_duration-.1:
                clean=folder/(stem+'.clean.mp4')
                command(['ffmpeg','-nostdin','-y','-v','error','-i',str(folder/(stem+'.mp4')),'-filter_complex',roughcut.concat_filter(ranges),'-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-movflags','+faststart',str(clean)])
                clean.replace(folder/(stem+'.mp4'));clip_cues=roughcut.rebase(clip_cues,ranges)
            elif new_duration<config['min_seconds']:c['silence_removal']['skipped']='would_violate_minimum_duration'
        (folder/(stem+'.srt')).write_text(srt(clip_cues),encoding='utf-8')
        if config.get('burn_subtitles'):
            rendered=folder/(stem+'.captioned.mp4')
            command([os.getenv('EDITOR_PYTHON',sys.executable),str(ROOT/'scripts/burn_subtitles.py'),'--video',str(folder/(stem+'.mp4')),'--subtitles',str(folder/(stem+'.srt')),'--output',str(rendered)])
            rendered.replace(folder/(stem+'.mp4'));c['hard_subtitles']=True
        c['output_duration']=round(probe(folder/(stem+'.mp4'))[0],3)
        store.update(job_id,progress=65+int(30*(i+1)/len(final)))
    metrics['rendering_seconds']=round(time.monotonic()-rendering_started,3)
    metrics['total_seconds']=round(time.monotonic()-started,3)
    manifest.update(metrics=metrics,token_usage=TOKEN_USAGE.copy(),speech_backend='supplied_subtitles' if manifest['supplied_subtitles'] else os.getenv('ASR_BACKEND','whisper'),prompt_sha256=editorial.fingerprint(ROOT/'prompts/select.md'))
    manifest['selection_diagnostics']={'attempts':len(SELECTION_TRACE),'proposed_count':sum(t['proposed_count'] for t in SELECTION_TRACE),'duration_rejections':[c for t in SELECTION_TRACE for c in t['duration_rejections']],'empty_reason':'model_selected_no_qualifying_moment' if not final else None}
    if config.get('segmentation_mode')=='seven':manifest['seven_prompt_sha256']=editorial.fingerprint(ROOT/'prompts/01_七段选段.md')
    (folder/'plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    store.update(job_id,status='ready',stage='Ready for manual review' if final else 'No qualifying clips found',progress=100,plan=json.dumps(final,ensure_ascii=False))
    wav=folder/'audio.wav'
    if wav.exists(): wav.unlink()

def claim(job_id=None):
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if job_id is None:
            row=c.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:return None
            job_id=row['id']
        changed=c.execute("UPDATE jobs SET status='processing',stage='Inspecting recording',progress=1 WHERE id=? AND status='queued'",(job_id,)).rowcount
        return job_id if changed else None

class WorkerInterrupted(BaseException):pass

def worker(tasks, stop):
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    def terminate(signum,frame):raise WorkerInterrupted()
    signal.signal(signal.SIGTERM,terminate)
    while not stop.is_set():
        try:hint=tasks.get(timeout=1)
        except queue.Empty:hint=None
        job_id=claim(hint)
        if not job_id:continue
        try: run(job_id)
        except Exception as e:
            log.exception('Job failed: %s',job_id)
            store.update(job_id,status='failed',stage='Needs attention',error=str(e)[:2000])
        except WorkerInterrupted:break


def start():
    STOP.clear()
    # The single worker restarts interrupted jobs from their immutable source.
    with store.db() as c:
        ids=[r['id'] for r in c.execute("SELECT id FROM jobs WHERE status IN ('processing','queued')")]
        c.execute("UPDATE jobs SET status='queued',stage='Recovered after restart' WHERE status='processing'")
    for job_id in ids: TASKS.put(job_id)
    t=MP.Process(target=worker,args=(TASKS,STOP),daemon=True); t.start()
    return t
