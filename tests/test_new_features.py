import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from proste_wideo_core import Mask,apply_masks

def test_ellipse_changes_only_inside_and_shape_sliders():
    rng=np.random.default_rng(170)
    frame=rng.integers(0,255,(180,250,3),dtype=np.uint8)
    ellipse=Mask('oval',(40,25,140,120),strength=75,shape='Ellipse')
    result=apply_masks(frame,[ellipse],3)
    assert np.array_equal(result[35,50],frame[35,50]), 'outside ellipse unchanged'
    assert not np.array_equal(result[90,110],frame[90,110]), 'center of ellipse affected'
    assert np.array_equal(result[:25],frame[:25]), 'outside bbox unchanged'
    ellipse.oval_width=45;ellipse.oval_height=60
    smaller=apply_masks(frame,[ellipse],3)
    assert np.array_equal(smaller[90,55],frame[90,55]), 'oval width narrows masking'
    assert np.array_equal(smaller[32,110],frame[32,110]), 'oval height narrows masking'
    assert not np.array_equal(smaller[90,110],frame[90,110]), 'oval center still masked'
    assert not np.array_equal(smaller,result), 'shape changes pixel output'

def test_oval_mosaic_changes_only_inside():
    arr=np.random.default_rng(10).integers(0,255,(128,128,3),dtype=np.uint8)
    mask=Mask('oval',(20,20,80,80),shape='Ellipse',mode='Mosaic',strength=99)
    processed=apply_masks(arr,[mask],3)
    assert np.array_equal(processed[25,25],arr[25,25])
    assert not np.array_equal(processed[60,60],arr[60,60])
