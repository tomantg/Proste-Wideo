"""PROSTE WIDEO video processing core. No GUI dependency."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import math
import os
import re
import shutil
import subprocess
import tempfile
import cv2
import numpy as np


def clamp_box(box, width, height):
    x, y, w, h = [int(round(t)) for t in box]
    w = max(1, min(width, w)); h = max(1, min(height, h))
    x = max(0, min(width-w, x)); y = max(0, min(height-h, y))
    return x, y, w, h


def lerp_box(a, b, t):
    return tuple(round(x+(y-x)*t) for x,y in zip(a,b))


@dataclass
class Mask:
    name: str
    base: tuple[int,int,int,int]
    strength: int = 35
    mode: str = 'Blur'
    enabled: bool = True
    first: int = 0
    last: int = 2**31-1
    keys: dict[int,tuple[int,int,int,int]] = field(default_factory=dict)
    tracked: dict[int,tuple[int,int,int,int]] = field(default_factory=dict)
    shape: str = 'Rectangle'
    oval_width: int = 100
    oval_height: int = 100

    def box_at(self, frame: int):
        if frame in self.keys:
            return self.keys[frame]
        anchors = sorted(self.keys)
        lo = max((k for k in anchors if k < frame), default=None)
        hi = min((k for k in anchors if k > frame), default=None)
        if frame in self.tracked:
            tracked_box = self.tracked[frame]
            # Adjust the tracked path to manual correction keyframes on either side.
            def delta(key):
                expected = self.tracked.get(key)
                if expected is None:
                    return tuple(0 for _ in range(4))
                return tuple(self.keys[key][i]-expected[i] for i in range(4))
            if lo is not None and hi is not None:
                a,b=delta(lo),delta(hi); t=(frame-lo)/(hi-lo)
                shift=[round(a[i]*(1-t)+b[i]*t) for i in range(4)]
            elif lo is not None: shift=delta(lo)
            elif hi is not None: shift=delta(hi)
            else: shift=(0,0,0,0)
            return tuple(tracked_box[i]+shift[i] for i in range(4))
        if lo is not None and hi is not None:
            return lerp_box(self.keys[lo], self.keys[hi], (frame-lo)/(hi-lo))
        if lo is not None:return self.keys[lo]
        if hi is not None:return self.keys[hi]
        return self.base


def apply_masks(frame:np.ndarray, masks:list[Mask], idx:int)->np.ndarray:
    out=frame.copy(); H,W=out.shape[:2]
    for mask in masks:
        if not mask.enabled or idx<mask.first or idx>mask.last:
            continue
        x,y,w,h=clamp_box(mask.box_at(idx),W,H)
        roi=out[y:y+h,x:x+w]
        if mask.mode=='Mosaic':
            block=max(2,round(2+int(mask.strength)*0.85))
            sw=max(1,math.ceil(w/block)); sh=max(1,math.ceil(h/block))
            mini=cv2.resize(roi,(sw,sh),interpolation=cv2.INTER_AREA)
            result=cv2.resize(mini,(w,h),interpolation=cv2.INTER_NEAREST)
        else:
            sigma=max(0.5, int(mask.strength)*0.9)
            result=cv2.GaussianBlur(roi,(0,0),sigmaX=sigma,sigmaY=sigma)
        if mask.shape=='Ellipse':
            # Adjustable horizontal/vertical ellipse, feathered by ~1.5 px at the boundary.
            xx=(np.arange(w,dtype=np.float32)+0.5-w/2)/(max(1,w*min(100,max(20,mask.oval_width))/200))
            yy=(np.arange(h,dtype=np.float32)+0.5-h/2)/(max(1,h*min(100,max(20,mask.oval_height))/200))
            rr=yy[:,None]**2+xx[None,:]**2
            feather=max(0.001,3.0/min(w,h))
            alpha=np.clip((1.0-rr)/(2*feather)+0.5,0,1).astype(np.float32)
            roi[:]=np.clip(result.astype(np.float32)*alpha[:,:,None]+roi.astype(np.float32)*(1-alpha[:,:,None]),0,255).astype(np.uint8)
        else:roi[:]=result
    return out


def gradient(gray):
    if gray.ndim==3: gray=cv2.cvtColor(gray,cv2.COLOR_BGR2GRAY)
    dx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)
    dy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    v=cv2.magnitude(dx,dy)
    return cv2.normalize(v,None,0,255,cv2.NORM_MINMAX).astype('uint8')


def track_step(prev, next_frame, box, radius=None):
    """Estimate local motion by phase correlation, then refine with gradient template."""
    H,W=next_frame.shape[:2]; x,y,w,h=clamp_box(box,W,H)
    rad = int(radius if radius is not None else max(22,min(160,max(w,h)*0.65)))
    # Local context gives a more useful shift than global full-scene correlation.
    pad=rad+max(16,min(w,h)//5)
    x0=max(0,x-pad); y0=max(0,y-pad)
    x1=min(W,x+w+pad); y1=min(H,y+h+pad)
    ga=gradient(prev[y0:y1,x0:x1]); gb=gradient(next_frame[y0:y1,x0:x1])
    dx=dy=0
    if min(ga.shape)>=20:
        scale=min(1, 280/max(ga.shape))
        if scale<1:
            size=(max(12,int(ga.shape[1]*scale)),max(12,int(ga.shape[0]*scale)))
            ga2=cv2.resize(ga,size,interpolation=cv2.INTER_AREA)
            gb2=cv2.resize(gb,size,interpolation=cv2.INTER_AREA)
        else: ga2,gb2=ga,gb
        win=cv2.createHanningWindow((ga2.shape[1],ga2.shape[0]),cv2.CV_32F)
        shift, quality=cv2.phaseCorrelate(ga2.astype('float32'),gb2.astype('float32'),win)
        if quality>=0.08 and all(math.isfinite(v) for v in shift):
            dx=int(round(shift[0]/scale)); dy=int(round(shift[1]/scale))
            dx=max(-rad,min(rad,dx));dy=max(-rad,min(rad,dy))
    cx=max(0,min(W-w,x+dx)); cy=max(0,min(H-h,y+dy))
    sx=max(0,cx-rad); sy=max(0,cy-rad)
    ex=min(W,cx+w+rad); ey=min(H,cy+h+rad)
    ta=gradient(prev[y:y+h,x:x+w]); sb=gradient(next_frame[sy:ey,sx:ex])
    if sb.shape[0]>=h and sb.shape[1]>=w and np.std(ta)>2.0:
        result=cv2.matchTemplate(sb,ta,cv2.TM_CCOEFF_NORMED)
        _,score,_,pos=cv2.minMaxLoc(result)
        if score>=0.31:
            return clamp_box((sx+pos[0],sy+pos[1],w,h),W,H),float(score)
    return (cx,cy,w,h),0.0


def track_range(path, mask:Mask, start:int, end:int,
                callback:Callable[[int],None]|None=None, stop_event=None):
    """Sequential reading, honors manual anchor frames. Returns tracking results."""
    cap=cv2.VideoCapture(str(path))
    if not cap.isOpened(): raise RuntimeError('Nie można otworzyć filmu do śledzenia.')
    direction=1 if end>=start else -1
    total=abs(end-start)+1
    positions={}
    prev=None
    box=mask.box_at(start)
    try:
        for step,idx in enumerate(range(start,end+direction,direction)):
            if stop_event is not None and stop_event.is_set(): break
            cap.set(cv2.CAP_PROP_POS_FRAMES,idx)
            ok,frame=cap.read()
            if not ok:raise RuntimeError(f'Nie można odczytać klatki {idx+1}.')
            if idx in mask.keys:
                box=mask.keys[idx]
            elif prev is not None:
                box,_=track_step(prev,frame,box)
            box=clamp_box(box,frame.shape[1],frame.shape[0]);positions[idx]=box
            prev=frame
            if callback and (step%4==0 or step+1==total):callback(round((step+1)*100/total))
    finally:cap.release()
    return positions


def validate_segments(segments,frame_count):
    if not segments:raise ValueError('Lista fragmentów jest pusta.')
    for a,b in segments:
        if not 0<=a<b<=frame_count:raise ValueError(f'Niepoprawny fragment: {a}:{b}')


def split_segment(segments,idx):
    for j,(a,b) in enumerate(segments):
        if a<idx<b:
            return segments[:j]+[(a,idx),(idx,b)]+segments[j+1:]
    return list(segments)


def locate_ffmpeg():
    path=shutil.which('ffmpeg')
    if path:return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError('Brak FFmpeg. Zainstaluj zależności z requirements.txt.')


def has_audio(ffmpeg,path):
    p=subprocess.run([ffmpeg,'-hide_banner','-i',str(path)],capture_output=True,text=True,errors='replace')
    return bool(re.search(r'Stream #.*Audio:',p.stderr))


def export_video(source,dest,masks,segments,keep_audio=True,crf=20,
                 callback=None,stop_event=None,ffmpeg=None):
    """Output H.264 MP4 preserving/reordering audio for segments, including reordered cuts."""
    ffmpeg=ffmpeg or locate_ffmpeg()
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened():raise RuntimeError('Nie można odczytać filmu źródłowego.')
    n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps=cap.get(cv2.CAP_PROP_FPS)
    if fps<=0 or n<1:cap.release();raise RuntimeError('Film ma niepoprawne FPS lub liczbę klatek.')
    W=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    validate_segments(segments,n)
    dest=Path(dest); dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.resolve()==Path(source).resolve():cap.release();raise RuntimeError('Plik wyjściowy nie może nadpisać źródła.')
    if W%2 or H%2:outW=W+(W%2);outH=H+(H%2)
    else:outW=W;outH=H
    tmp_path=None
    total=sum(b-a for a,b in segments)
    try:
        with tempfile.NamedTemporaryFile(prefix='proste_wideo_',suffix='.mp4',dir=str(dest.parent),delete=False) as t:
            tmp_path=Path(t.name)
        cmd=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo',
             '-pix_fmt','bgr24','-s',f'{outW}x{outH}','-r',f'{fps:.8f}','-i','pipe:0',
             '-an','-c:v','libx264','-preset','veryfast','-crf',str(int(crf)),
             '-pix_fmt','yuv420p','-movflags','+faststart',str(tmp_path)]
        enc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        written=0
        try:
            for a,b in segments:
                cap.set(cv2.CAP_PROP_POS_FRAMES,a)
                for idx in range(a,b):
                    if stop_event and stop_event.is_set():raise RuntimeError('Eksport przerwany.')
                    ok,frame=cap.read()
                    if not ok: raise RuntimeError(f'Błąd odczytu klatki {idx}.')
                    processed=apply_masks(frame,masks,idx)
                    if outW!=W or outH!=H:
                        processed=cv2.copyMakeBorder(processed,0,outH-H,0,outW-W,cv2.BORDER_REPLICATE)
                    enc.stdin.write(processed.tobytes())
                    written+=1
                    if callback and (written%5==0 or written==total):callback(round(written*85/total))
            enc.stdin.close()
            err=enc.stderr.read().decode(errors='replace')
            code=enc.wait()
            if code:raise RuntimeError('FFmpeg nie może zakodować filmu: '+err[-1300:])
        except Exception:
            if enc.poll() is None:enc.kill()
            try:enc.stdin.close()
            except Exception:pass
            enc.wait();raise
        finally:cap.release()

        if keep_audio and has_audio(ffmpeg,source):
            filter_items=[];audio_inputs=[]
            for i,(a,b) in enumerate(segments):
                filter_items.append(f'[1:a:0]atrim=start={a/fps:.9f}:end={b/fps:.9f},asetpts=PTS-STARTPTS[a{i}]')
                audio_inputs.append(f'[a{i}]')
            if len(segments)>1:
                filter_items.append(''.join(audio_inputs)+f'concat=n={len(segments)}:v=0:a=1[aout]')
                audio_out='[aout]'
            else:audio_out='[a0]'
            muxcmd=[ffmpeg,'-hide_banner','-loglevel','error','-y',
                    '-i',str(tmp_path),'-i',str(source),'-filter_complex',';'.join(filter_items),
                    '-map','0:v:0','-map',audio_out,'-c:v','copy','-c:a','aac','-b:a','192k',
                    '-movflags','+faststart','-shortest',str(dest)]
            result=subprocess.run(muxcmd,capture_output=True,text=True,errors='replace')
            if result.returncode:
                raise RuntimeError('Błąd podczas zachowania dźwięku: '+result.stderr[-1400:])
        else:
            os.replace(tmp_path,dest);tmp_path=None
        if callback:callback(100)
        return {'path':str(dest),'frames':total,'fps':fps,'audio':bool(keep_audio and has_audio(ffmpeg,source))}
    finally:
        if tmp_path and tmp_path.exists():tmp_path.unlink()
