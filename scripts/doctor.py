"""Read-only local preflight. Does not print secrets or download models."""
import importlib.util
import os
import shutil
import sys
import urllib.request
import json
print('Python:',sys.version.split()[0])
for binary in ['ffmpeg','ffprobe']:
    print(binary+':',shutil.which(binary) or 'NOT FOUND')
for package in ['fastapi','uvicorn','faster_whisper','obsws_python']:
    print(package+':','installed' if importlib.util.find_spec(package) else 'NOT INSTALLED')
endpoint=os.getenv('LLM_BASE_URL','http://127.0.0.1:11434/v1').rstrip('/')
print('Selection model:',os.getenv('LLM_MODEL','qwen3:8b'))
headers={}
if os.getenv('LLM_API_KEY'): headers['Authorization']='Bearer '+os.environ['LLM_API_KEY']
try:
    with urllib.request.urlopen(urllib.request.Request(endpoint+'/models',headers=headers),timeout=5) as r:
        obj=json.load(r)
    models=[item['id'] for item in obj.get('data',[])]
    print('Model service: reachable. Available:',', '.join(models) or '(none downloaded)')
except Exception:
    print('Model service: UNAVAILABLE. Start/configure Ollama or your provider.')
print('Remote workspace key:','configured' if os.getenv('WORKSPACE_TOKEN') else 'generated under data on first start')
print('OBS automation:','configured' if os.getenv('OBS_PASSWORD') else 'disabled')
