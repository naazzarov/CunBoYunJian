"""Timestamp validation, knowledge retrieval and reproducible edit plans."""
import json
import math
import re
from dataclasses import dataclass, asdict

@dataclass
class Cue:
    start: float
    end: float
    text: str

def seconds(value):
    h,m,s = value.replace(',', '.').split(':')
    return int(h)*3600 + int(m)*60 + float(s)

def stamp(value):
    ms=max(0,round(value*1000))
    h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def parse_srt(text, duration=None):
    cues=[]
    for block in re.split(r'\n\s*\n',text.replace('\r','').strip().lstrip('\ufeff')):
        lines=block.splitlines()
        idx=next((i for i,l in enumerate(lines) if '-->' in l),None)
        if idx is None: raise ValueError('Invalid SRT: missing timestamp line.')
        match=re.fullmatch(r'\s*(\d+:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d{3})\s*',lines[idx])
        if not match: raise ValueError('Invalid SRT timestamp.')
        a,b=map(seconds,match.groups()); content=' '.join(lines[idx+1:]).strip()
        if not content or not math.isfinite(a+b) or a<0 or b<=a: raise ValueError('Invalid subtitle interval.')
        if duration is not None and b>duration+0.5: raise ValueError('Subtitles extend beyond video duration.')
        if cues and a<cues[-1].start: raise ValueError('Subtitles must be in chronological order.')
        cues.append(Cue(a,b,content))
    if not cues: raise ValueError('No subtitles found.')
    return cues

def srt(cues, start=0, end=float('inf')):
    selected=[Cue(max(c.start,start)-start,min(c.end,end)-start,c.text) for c in cues if c.end>start and c.start<end]
    return '\n\n'.join(f'{i}\n{stamp(c.start)} --> {stamp(c.end)}\n{c.text}' for i,c in enumerate(selected,1))+'\n'

def tokens(text):
    low=text.lower()
    latin=re.findall(r'[a-z0-9]{2,}',low)
    chinese=re.findall(r'[\u4e00-\u9fff]+',low)
    return set(latin+[s[i:i+2] for s in chinese for i in range(len(s)-1)])

def retrieve(query, cards, limit=6):
    q=tokens(query)
    scored=[]
    for c in cards:
        terms=tokens(c['title']+' '+c['content'])
        score=len(q & terms)/math.sqrt(max(1,len(terms)))
        if c['kind']=='rule': score+=100
        scored.append((score,c))
    ranked=sorted(scored,key=lambda x:(-x[0],x[1]['id']))
    rules=[x for x in ranked if x[1]['kind']=='rule']
    evidence=[x for x in ranked if x[1]['kind']!='rule' and x[0]>0]
    selected=rules[:min(3,limit)]+evidence[:max(0,limit-min(3,len(rules)))]
    used={x[1]['id'] for x in selected}
    selected.extend(x for x in rules if x[1]['id'] not in used)
    return [dict(c,relevance=round(score,3)) for score,c in selected[:limit]]

def windows(cues, max_seconds=480, max_chars=16000, overlap_seconds=0):
    chunk=[]; chars=0
    for c in cues:
        if len(c.text)>max_chars:raise ValueError('A subtitle cue is too long. Split it into shorter timed cues.')
        if chunk and (c.end-chunk[0].start>max_seconds or chars+len(c.text)>max_chars):
            yield chunk
            tail=[x for x in chunk if overlap_seconds and x.end>chunk[-1].end-overlap_seconds]
            # Always leave room for the next cue; the window must make forward progress.
            while tail and (c.end-tail[0].start>max_seconds or sum(len(x.text) for x in tail)+len(c.text)>max_chars):tail.pop(0)
            chunk=tail; chars=sum(len(x.text) for x in tail)
        chunk.append(c); chars+=len(c.text)
    if chunk: yield chunk

def validate_plan(raw, cues, duration, min_seconds, max_seconds, max_clips):
    if not isinstance(raw,dict) or not isinstance(raw.get('clips'),list): raise ValueError('Model must return an object containing clips.')
    clean=[]
    for item in raw['clips']:
        if not isinstance(item,dict): raise ValueError('Invalid clip object.')
        a=item.get('start'); b=item.get('end')
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,(int,float)) or not isinstance(b,(int,float)) or not math.isfinite(a+b): raise ValueError('Clip times must be finite seconds.')
        if not 0<=a<b<=duration+0.05: raise ValueError('Model selected an interval outside the video.')
        if not cues[0].start-0.1<=a<b<=cues[-1].end+0.1: raise ValueError('Model selected an interval outside its transcript window.')
        # Snap to nearby spoken boundaries, never invent arbitrary cuts.
        snapped_a=min((c.start for c in cues),key=lambda v:abs(v-a))
        snapped_b=min((c.end for c in cues),key=lambda v:abs(v-b))
        if abs(snapped_a-a)>0.75 or abs(snapped_b-b)>0.75: raise ValueError('Clip boundaries must align to supplied subtitle times.')
        a,b=snapped_a,snapped_b
        if not min_seconds<=b-a<=max_seconds: continue
        if any(a<x['end'] and b>x['start'] for x in clean): continue
        title=str(item.get('title','')).strip()[:160]; reason=str(item.get('reason','')).strip()[:1200]
        if not title or not reason: raise ValueError('Clip title and reason are required.')
        score=item.get('score',0)
        if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=100: raise ValueError('Score must be 0–100.')
        ids=item.get('knowledge_ids',[])
        if not isinstance(ids,list) or any(not isinstance(x,int) or isinstance(x,bool) for x in ids): raise ValueError('Knowledge references must be IDs.')
        clean.append({'start':round(a,3),'end':round(b,3),'title':title,'reason':reason,'category':str(item.get('category','Highlight'))[:80],'score':score,'knowledge_ids':ids})
        if len(clean)>=max_clips: break
    return clean


def duration_ranges(cues,min_seconds,max_seconds):
    """Offer short, medium and long subtitle-aligned choices per starting cue.

    Eligibility checks timing only. The model must still judge meaning and can
    select nothing. Keeping the menu bounded avoids a quadratic prompt size.
    """
    result={}
    for a,cue in enumerate(cues,1):
        ends=[b for b in range(a,len(cues)+1) if min_seconds<=cues[b-1].end-cue.start<=max_seconds]
        if not ends:continue
        for b in sorted({ends[0],ends[len(ends)//2],ends[-1]}):
            result[f'{a}:{b}']=(a,b)
    return result


def resolve_cue_plan(raw,cues,ranges=None):
    if not isinstance(raw,dict) or not isinstance(raw.get('clips'),list): raise ValueError('Model must return an object containing clips.')
    result=[]
    for item in raw['clips']:
        if not isinstance(item,dict): raise ValueError('Invalid clip object.')
        if 'range_id' in item:
            key=item['range_id']
            if not isinstance(key,str) or ranges is None or key not in ranges:
                raise ValueError('Choose a range_id from the supplied duration-valid menu.')
            a,b=ranges[key]
        else:a,b=item.get('start_cue'),item.get('end_cue')
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,int) or not isinstance(b,int) or not 1<=a<=b<=len(cues):
            raise ValueError('Choose valid start_cue and end_cue IDs from the supplied transcript.')
        result.append(dict(item,start=cues[a-1].start,end=cues[b-1].end))
    return {'clips':result}
