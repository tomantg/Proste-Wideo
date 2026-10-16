import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import math
import subprocess
import shutil
import cv2
import numpy as np
import pytest
from proste_wideo_core import Mask, apply_masks, split_segment, track_step, track_range, export_video


def test_blur_strength_and_outside_untouched():
    rng=np.random.default_rng(15); frame=rng.integers(0,255,(110,180,3),dtype=np.uint8)
    a=Mask('A',(20,20,95,70),strength=2)
    b=Mask('B',(20,20,95,70),strength=95)
    low=apply_masks(frame,[a],0);high=apply_masks(frame,[b],0)
    assert not np.array_equal(low[20:90,20:115],high[20:90,20:115])
    assert np.array_equal(low[:20],frame[:20])
    assert np.var(high[30:80,30:105])<np.var(low[30:80,30:105])
    a.mode='Mosaic';b.mode='Mosaic'
    assert not np.array_equal(apply_masks(frame,[a],0),apply_masks(frame,[b],0))


def test_mask_keyframe_and_tracking_offsets():
    m=Mask('M',(0,0,20,20),keys={0:(5,5,20,20),10:(25,15,20,20)})
    assert m.box_at(5)==(15,10,20,20)
    m.tracked={i:(5+i,5+i,20,20) for i in range(11)}
    assert m.box_at(0)==(5,5,20,20)
    assert m.box_at(10)==(25,15,20,20)
    assert m.box_at(5)==(15,10,20,20)


def test_local_phase_plus_template():
    r=np.random.default_rng(13)
    image=r.integers(0,250,(250,350,3),dtype=np.uint8)
    M=np.float32([[1,0,12],[0,1,9]])
    shifted=cv2.warpAffine(image,M,(350,250),borderMode=cv2.BORDER_REFLECT)
    box,quality=track_step(image,shifted,(110,100,85,60))
    assert abs(box[0]-122)<=2,(box,quality)
    assert abs(box[1]-109)<=2,(box,quality)


def test_split_reorder_and_ranges():
    a=split_segment([(0,120)],45)
    assert a==[(0,45),(45,120)]
    assert split_segment(a,45)==a
    a[0],a[1]=a[1],a[0]
    assert a==[(45,120),(0,45)]


def create_av_sample(path):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg missing')
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y',
         '-f','lavfi','-i','testsrc2=size=160x120:rate=12:duration=2',
         '-f','lavfi','-i','sine=frequency=540:duration=2',
         '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)]
    subprocess.run(cmd,check=True)


def test_export_video_edits_and_audio(tmp_path):
    inp=tmp_path/'source.mp4';out=tmp_path/'edited.mp4'
    create_av_sample(inp)
    mask=Mask('blur',(10,10,40,40),strength=65,keys={0:(10,10,40,40)})
    result=export_video(inp,out,[mask],[(12,24),(0,12)],keep_audio=True)
    assert result['frames']==24
    assert result['audio'] is True
    assert out.stat().st_size>5000
    info=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',str(out)],capture_output=True,text=True,check=True)
    assert 'video' in info.stdout
    assert 'audio' in info.stdout
    capture=cv2.VideoCapture(str(out))
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT))==24
    ok,frame=capture.read();capture.release();assert ok and frame.shape[:2]==(120,160)


def test_tracking_range_honors_manual_keyframes(tmp_path):
    outfile=tmp_path/'moving.avi'
    w=cv2.VideoWriter(str(outfile),cv2.VideoWriter_fourcc(*'MJPG'),12,(160,120))
    bg=np.random.default_rng(5).integers(0,255,(120,160,3),dtype=np.uint8)
    for i in range(9):
        moved=cv2.warpAffine(bg,np.float32([[1,0,i*2],[0,1,0]]),(160,120),borderMode=cv2.BORDER_REFLECT)
        w.write(moved)
    w.release()
    m=Mask('m',(38,35,54,48),keys={0:(38,35,54,48),5:(48,35,54,48)})
    results=track_range(outfile,m,0,8)
    assert len(results)==9
    assert results[5]==(48,35,54,48)
    assert abs(results[8][0]-54)<=3,results
