"""Smoke test of hotkeys, timeline tiles, oval mask, and project reloading."""
import sys,tempfile,subprocess, time, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import filedialog,messagebox
from proste_wideo import ProsteWideo

with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder); source=folder/'source.mp4';project=folder/'saved.prostewideo.json';out=folder/'oval.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
       '-f','lavfi','-i','testsrc2=size=256x144:rate=12:duration=3',
       '-f','lavfi','-i','sine=frequency=550:duration=3',
       '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    root=tk.Tk(); app=ProsteWideo(root);root.update()
    assert root.title()=='PROSTE WIDEO'
    assert app.load_path(source)
    app.add_center_mask();app.select_mask(0)
    app.shape.set('Ellipse');app.oval_width.set(48);app.oval_height.set(62);app.property_changed()
    assert app.masks[0].shape=='Ellipse' and app.masks[0].oval_width==48
    assert app.masks[0].oval_height==62
    app.seek(12)
    root.focus_force();root.update()
    root.event_generate('<KeyPress-b>');root.update()
    assert len(app.segments)==2, app.segments
    assert len(app.tile_rects)==2
    root.event_generate('<KeyPress-space>');root.update()
    assert app.playing
    root.event_generate('<KeyPress-space>');root.update()
    assert not app.playing
    # Drag tile 1 onto tile 2 to rearrange in output order.
    a1,x1,y1=app.tile_rects[0];a2,x2,y2=app.tile_rects[1]
    app.tiles.event_generate('<ButtonPress-1>',x=int((x1+y1)/2),y=50)
    app.tiles.event_generate('<B1-Motion>',x=int((x2+y2)/2),y=50)
    app.tiles.event_generate('<ButtonRelease-1>',x=int((x2+y2)/2),y=50)
    root.update()
    assert app.segments==[(12,36),(0,12)],app.segments
    messagebox.showinfo=lambda *args:None
    filedialog.asksaveasfilename=lambda *args,**kwargs:str(project)
    app.save_project(); assert project.exists()
    payload=json.loads(project.read_text())
    assert payload['format']=='PROSTE-WIDEO-1'
    assert payload['masks'][0]['shape']=='Ellipse'
    filedialog.askopenfilename=lambda *args,**kwargs:str(project)
    app.open_project()
    assert app.masks[0].oval_width==48 and app.masks[0].oval_height==62
    assert app.segments==[(12,36),(0,12)]
    filedialog.asksaveasfilename=lambda *args,**kwargs:str(out)
    app.export()
    deadline=time.monotonic()+35
    while app.task and time.monotonic()<deadline:
        root.update();time.sleep(.03)
    assert app.task is None
    assert out.exists() and out.stat().st_size>10000
    stream=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','csv=p=0',str(out)],capture_output=True,text=True,check=True)
    assert 'audio' in stream.stdout
    app.close()
print('GUI NEW FEATURES PASS: ellipse sliders, B split, Space playback, tile drag reorder, project persistence, MP4 with audio')
