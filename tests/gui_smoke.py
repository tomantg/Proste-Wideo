"""UI integration smoke test under Xvfb (for test environment)."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import tkinter as tk
import cv2
import numpy as np
from proste_wideo import ProsteWideo

root=tk.Tk();app=ProsteWideo(root)
root.update_idletasks();root.update()
assert app.root.winfo_exists()
with tempfile.TemporaryDirectory() as d:
    inp=Path(d)/'small.avi';vid=cv2.VideoWriter(str(inp),cv2.VideoWriter_fourcc(*'MJPG'),12,(192,128))
    for j in range(24):
        frame=np.random.default_rng(j).integers(0,255,(128,192,3),dtype=np.uint8)
        vid.write(frame)
    vid.release()
    assert app.load_path(str(inp))
    app.add_center_mask()
    assert len(app.masks)==1
    app.strength.set(75);app.property_changed()
    assert app.masks[0].strength==75
    app.seek(7);app.add_key();assert 7 in app.masks[0].keys
    app.cut_here();assert app.segments==[(0,7),(7,24)]
    app.partlist.selection_set('0');app.move_part(1)
    assert app.segments==[(7,24),(0,7)]
    app.seek(8);app.render()
    root.update_idletasks();root.update()
    assert app.photo.width()>0
app.close()
print('GUI SMOKE PASS: application boots, reads video, controls blur, keyframe, cuts, reorders, renders, closes')
