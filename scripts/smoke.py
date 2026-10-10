"""Exercise a running workspace with your own small video (real configured models)."""
import argparse
import json
import os
from pathlib import Path
import time
import httpx

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('video',type=Path)
p.add_argument('--srt',type=Path)
p.add_argument('--url',default='http://localhost:8000')
p.add_argument('--timeout',type=int,default=1800)
p.add_argument('--min-seconds',type=int,default=3)
a=p.parse_args()
headers={}
if os.getenv('WORKSPACE_TOKEN'): headers['Authorization']='Bearer '+os.environ['WORKSPACE_TOKEN']
with httpx.Client(base_url=a.url,headers=headers,timeout=120) as client:
    cards=client.get('/api/knowledge');cards.raise_for_status()
    if not cards.json(): raise SystemExit('Add knowledge through the studio before running a smoke test.')
    with a.video.open('rb') as video:
        files={'video':(a.video.name,video,'application/octet-stream')}
        subtitle=a.srt.open('rb') if a.srt else None
        if subtitle: files['subtitles']=(a.srt.name,subtitle,'text/plain')
        try:
            response=client.post('/api/jobs',files=files,data={'title':'Smoke test: '+a.video.stem,'config':json.dumps({'min_seconds':a.min_seconds,'max_seconds':90,'max_clips':3})})
            response.raise_for_status()
        finally:
            if subtitle: subtitle.close()
    job_id=response.json()['id']; print('Session:',job_id)
    deadline=time.monotonic()+a.timeout
    previous=None
    while time.monotonic()<deadline:
        response=client.get('/api/jobs/'+job_id);response.raise_for_status();job=response.json()
        if job['stage']!=previous:print(job['stage']);previous=job['stage']
        if job['status']=='failed':raise SystemExit('Failed: '+job['error'])
        if job['status']=='ready':
            print('Complete:',len(job['plan']),'clips. Review them in the studio.');break
        time.sleep(2)
    else:raise SystemExit('Timed out waiting. The backend job may still be processing.')
