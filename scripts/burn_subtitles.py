"""MoviePy 1.0.3 + ImageMagick hard-subtitle renderer; local media only."""
import argparse
import os
from pathlib import Path
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--subtitles',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from app.core import parse_srt
    from moviepy.editor import VideoFileClip,TextClip,CompositeVideoClip
    font=os.environ['SUBTITLE_FONT']
    if not Path(font).is_file():raise SystemExit('SUBTITLE_FONT must point to an installed Chinese font file.')
    clip=VideoFileClip(str(a.video));overlays=[]
    try:
        for cue in parse_srt(a.subtitles.read_text(),clip.duration):
            text=TextClip(cue.text,font=font,fontsize=max(18,int(clip.w*.036)),color='white',method='caption',size=(int(clip.w*.88),None),align='center')
            text=text.on_color(size=(text.w,text.h+12),color=(15,31,26),col_opacity=.72,pos=('center','center'))
            overlays.append(text.set_start(cue.start).set_duration(cue.end-cue.start).set_position(('center',int(clip.h*.84))))
        result=CompositeVideoClip([clip,*overlays])
        try:result.write_videofile(str(a.output),codec='libx264',audio_codec='aac',preset='veryfast',threads=2,logger=None)
        finally:result.close()
    finally:
        for overlay in overlays:overlay.close()
        clip.close()

if __name__=='__main__':main()
