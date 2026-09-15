"""LTX delivery selection, graph wiring and saved preference checks."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def run():
    spec = importlib.util.spec_from_file_location('delivery_check', ROOT/'resolve-panel/SecondUnit.py')
    su = importlib.util.module_from_spec(spec); spec.loader.exec_module(su)
    old = {'family': 'LTX25', 'resolution': '720P'}
    migrated = su.migrate_delivery_state(old)
    assert migrated['resolution'] == migrated['ltx_resolution'] == '1080P'
    for choice in su.RESOLUTIONS:
        saved = dict(migrated, resolution=choice, ltx_resolution=choice)
        assert su.migrate_delivery_state(saved) == saved
    print('PASS LTX1080 default migration once; later720/1080/4K preferences persist')
    graph = {
      '1': {'class_type':'UNETLoader','inputs':{'unet_name':'ltx-2.5-test.safetensors'}},
      '2': {'class_type':'ImageScale','_meta':{'second_unit_role':'delivery_scale'},'inputs':{'image':['3',0],'width':1920,'height':1080,'crop':'center','upscale_method':'lanczos'}},
      '3': {'class_type':'VAEDecodeTiled','inputs':{}},
      '4': {'class_type':'CreateVideo','inputs':{'images':['2',0],'audio':['5',0],'fps':24}},
      '5': {'class_type':'LTXVAudioVAEDecode','inputs':{}},
      '6': {'class_type':'SaveVideo','inputs':{'video':['4',0]}},
      '7': {'class_type':'EmptyLTXVLatentVideo','inputs':{'width':1216,'height':832,'length':81}},
    }
    import copy
    for resolution, size in su.OUTPUT_SIZES.items():
        patched = copy.deepcopy(graph)
        su.enforce_comfy_prores_hq(patched, 24, resolution)
        assert len([n for n in patched.values() if n['class_type']=='ImageScale']) == 1
        assert (patched['2']['inputs']['width'],patched['2']['inputs']['height']) == size
        assert patched['2']['inputs']['crop']=='center' and patched['2']['inputs']['image']==['3',0]
        assert patched['7']==graph['7']
        assert patched['6']['class_type']=='VHS_VideoCombine'
        assert patched['6']['inputs']['images']==['2',0] and patched['6']['inputs']['audio']==['5',0]
        assert patched['6']['inputs']['format']=='video/ProRes' and patched['6']['inputs']['profile']=='hq'
    print('PASS every export size reuses actual delivery node, center crop, native canvas preserved, ProRes HQ+audio wired')
    try:
        su.patch_graph({'1':{'class_type':'UNETLoader','inputs':{'unet_name':'Minimax-h3-test.safetensors'}}},'I2V','test',5,resolution='4K')
    except su.SecondUnitError as exc:
        assert '4K export is available for LTX' in str(exc)
    else: raise AssertionError('H3 accepted unvalidated4K path')
    h3=copy.deepcopy(graph)
    su.enforce_comfy_prores_hq(h3,24,'1080P',vsr=True)
    assert any(n['class_type']=='RTXVideoSuperResolution' for n in h3.values())
    print('PASS H3 rejects4K and retains1080 RTX VSR requirement')
if __name__=='__main__':run()
