"""Interpret auto-editor v3 timelines without losing subtitle-covered speech."""
from fractions import Fraction
import math
from .core import Cue

def retained_ranges(timeline,cues,duration):
    if timeline.get('version')!='3':raise ValueError('Expected auto-editor v3 timeline.')
    fps=float(Fraction(timeline['timebase']))
    if not math.isfinite(fps) or fps<=0:raise ValueError('Invalid timeline timebase.')
    tracks=timeline.get('v',[])
    if len(tracks)!=1:raise ValueError('Expected a single video track.')
    spans=[]
    for clip in tracks[0]:
        if clip.get('effects'):raise ValueError('Speed changes are not supported for subtitle mapping.')
        a=clip['offset']/fps;b=a+clip['dur']/fps
        if not math.isfinite(a+b) or a<0 or b<=a or b>duration+1/fps:raise ValueError('Invalid retained interval.')
        spans.append((a,min(b,duration)))
    # Never remove a period that the transcript says contains speech.
    spans.extend((max(0,c.start),min(duration,c.end)) for c in cues)
    merged=[]
    for a,b in sorted(spans):
        if b<=a:continue
        if merged and a<=merged[-1][1]+1/fps:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged

def rebase(cues,ranges):
    result=[];elapsed=0
    for a,b in ranges:
        for cue in cues:
            left=max(a,cue.start);right=min(b,cue.end)
            if right>left:result.append(Cue(round(elapsed+left-a,3),round(elapsed+right-a,3),cue.text))
        elapsed+=b-a
    return result

def concat_filter(ranges):
    parts=[];inputs=[]
    for i,(a,b) in enumerate(ranges):
        parts.append(f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]')
        parts.append(f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,afade=t=in:d=0.005,afade=t=out:st={max(0,b-a-.005)}:d=0.005[a{i}]')
        inputs.append(f'[v{i}][a{i}]')
    parts.append(''.join(inputs)+f'concat=n={len(ranges)}:v=1:a=1[v][a]')
    return ';'.join(parts)
