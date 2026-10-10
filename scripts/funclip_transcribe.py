"""Isolated adapter for the official, pinned FunClip VideoClipper and FunASR.

Process exit releases the ASR models before the local LLM/editing stages.
No customer media is sent to a hosted speech service.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audio',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--hotwords',default='')
    p.add_argument('--speakers',action='store_true')
    a=p.parse_args()
    source=Path(os.environ['FUNCLIP_PATH']).resolve()
    if not (source/'funclip/videoclipper.py').is_file():raise SystemExit('FUNCLIP_PATH must point to the official FunClip v2.1.0 checkout.')
    sys.path.insert(0,str(source/'funclip'))
    from funasr import AutoModel
    from videoclipper import VideoClipper
    from utils.subtitle_utils import Text2SRT
    import soundfile
    started=time.monotonic()
    options=dict(model=os.getenv('FUNASR_MODEL','iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch'),
                 model_revision=os.getenv('FUNASR_MODEL_REVISION','v2.0.4'),
                 vad_model='damo/speech_fsmn_vad_zh-cn-16k-common-pytorch',vad_model_revision='v2.0.4',
                 punc_model='damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch',punc_model_revision='v2.0.4',
                 device='cpu',ncpu=int(os.getenv('ASR_CPU_THREADS','4')),disable_update=True)
    if a.speakers:options.update(spk_model='damo/speech_campplus_sv_zh-cn_16k-common',spk_model_revision='v2.0.2')
    model=AutoModel(**options)
    clipper=VideoClipper(model);clipper.lang='zh'
    samples,rate=soundfile.read(a.audio)
    text,raw_srt,state=clipper.recog((rate,samples),sd_switch='Yes' if a.speakers else 'no',hotwords=a.hotwords)
    cues=[];speakers=[]
    for sent in state['sentences']:
        if not sent.get('timestamp'):continue
        subtitle=Text2SRT(sent['text'],sent['timestamp']);start,end=subtitle.time()
        if end<=start or not subtitle.text().strip():continue
        cues.append({'start':start,'end':end,'text':subtitle.text()})
        if 'spk' in sent:speakers.append({'start':start,'end':end,'speaker':str(sent['spk']),'text':subtitle.text()})
    if not cues:raise RuntimeError('FunClip returned no timed speech segments.')
    result={'cues':cues,'text':text,'speakers':speakers,'raw_funclip_srt':raw_srt,'seconds':time.monotonic()-started,
            'model':options['model'],'model_revision':options['model_revision'],'speaker_labels':'anonymous within this recording'}
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
