"""Full Tk video workflow smoke test. Requires virtual display and FFmpeg."""
import sys,time,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import filedialog,messagebox
from proste_wideo import ProsteWideo

with tempfile.TemporaryDirectory() as d:
    source=Path(d)/'source.mp4';out=Path(d)/'out.mp4';project=Path(d)/'edit.protovid.json'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                    '-f','lavfi','-i','testsrc2=size=192x128:rate=10:duration=2',
                    '-f','lavfi','-i','sine=frequency=440:duration=2',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    root=tk.Tk();app=ProsteWideo(root);root.update()
    assert app.load_path(source)
    app.add_center_mask();app.seek(4);app.track(False)
    start=time.monotonic()
    while app.task is not None and time.monotonic()-start<15:
        root.update();time.sleep(.03)
    assert app.task is None
    assert len(app.masks[0].tracked)>=10
    app.seek(7);app.add_key()
    app.cut_here();app.partlist.selection_set('0');app.move_part(1)
    messagebox.showinfo=lambda *a,**k:None
    filedialog.asksaveasfilename=lambda *a,**k:str(project)
    app.save_project();assert project.exists()
    app.masks=[];app.segments=[]
    filedialog.askopenfilename=lambda *a,**k:str(project)
    app.open_project();assert len(app.masks)==1 and len(app.segments)==2
    assert 7 in app.masks[0].keys
    filedialog.asksaveasfilename=lambda *a,**k:str(out)
    app.export()
    start=time.monotonic()
    while app.task is not None and time.monotonic()-start<30:
        root.update();time.sleep(.04)
    assert app.task is None
    assert out.exists() and out.stat().st_size>6000
    info=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',str(out)],capture_output=True,text=True,check=True)
    assert 'audio' in info.stdout
    app.close()
print('FULL GUI TEST PASS: video loaded; track; key; split; reorder; project save & reopen; export with audio')
