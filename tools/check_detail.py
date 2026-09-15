"""Shared LTX photographic finish contract; no GPU or network calls."""
import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("detail_panel", ROOT / "resolve-panel/SecondUnit.py")
su = importlib.util.module_from_spec(spec); spec.loader.exec_module(su)
GRAPH = json.loads((ROOT / "workflows/ltx-2.5/finish/ltx25_pixel-spatial-x2_finish_api.json").read_text())

def run():
    for frames in (1, 81, 83, 124):
        for resolution, size in su.OUTPUT_SIZES.items():
            graph, info = su.patch_graph(GRAPH, "V2V", "Do not change the source.", frames/24,
                negative="", seed=7, source_name="source.mp4", resolution=resolution,
                finish_source_size=(1536, 866))
            su.force_graph_timing(graph, 24, frames)
            padded = 1 + ((frames-1+7)//8)*8
            assert graph['10']['inputs']['length'] == graph['12']['inputs']['frames_number'] == padded
            assert graph['6']['inputs']['frame_load_cap'] == graph['33']['inputs']['length'] == frames
            assert graph['30']['inputs']['batch_index'] == frames-1
            assert graph['31']['inputs']['amount'] == max(1,padded-frames)
            assert graph['15']['inputs']['cfg'] == graph['11']['inputs']['strength'] == graph['2']['inputs']['strength_model'] == 1
            assert graph['17']['inputs']['sigmas'] == su.DETAIL_UPSCALE_SIGMAS
            assert graph['7']['inputs']['text'] == su.DETAIL_UPSCALE_PROMPT
            assert graph['8']['inputs']['text'] == ''
            scales = [n for n in graph.values() if (n.get('_meta') or {}).get('second_unit_role') == 'delivery_scale']
            assert len(scales)==1 and (scales[0]['inputs']['width'],scales[0]['inputs']['height'])==size
            assert graph['22']['inputs']['audio']==['6',2]
            snap = graph[str(graph['11']['inputs']['image'][0])]
            assert snap['inputs']['height']==864
            assert snap['inputs']['image']==(['32',0] if padded>frames else ['6',0])
    old=copy.deepcopy(GRAPH);old['2']['inputs']['lora_name']='LTX2.3/ltx-2.3-22b-ic-lora-pixel-spatial-upscaler-x2-0.9.safetensors'
    try: su.apply_detail_realism_settings(old)
    except su.SecondUnitError: pass
    else: raise AssertionError('incompatible adapter accepted')
    captured=[]
    class Nested:
        def __init__(self,client,params,relay,stop):captured.append(params);self.relay=relay
        def _run(self):self.relay.done={'paths':['finished.mov']}
    original=su.GenerateJob
    for family in ('MINIMAXH3','LTX25','LTX23','WAN22'):
        job=original.__new__(original);job.params={'seed':10,'resolution':'4K','family':family}
        job.client=type('Client',(),{'base':su.COMFY_URL_FINISH})();job.outbox=None;job.stop_event=None
        with patch.object(su,'GenerateJob',Nested),patch.object(su,'detail_upscale_entry',lambda:'finish'),patch.object(su,'probe_frame_count',lambda p:83),patch.object(su,'probe_duration',lambda p:83/24),patch.object(su,'probe_dimensions',lambda p:(1536,864)):
            result=job.run_detail_upscale(['source.mov'],{'frames':83,'fps':24})
        assert result['paths']==['finished.mov']
    assert len(captured)==4
    for p in captured:
        assert p['resolution']=='4K' and p['detail_upscale'] is False
        assert p['prompt']==su.DETAIL_UPSCALE_PROMPT and p['negative']==''
        assert (p['exact_frames'],p['exact_fps'])==(83,24)
    print('PASS shared families; genuine2.5 adapter; CFG/guide/LoRA/sigmas; pad/trim/audio;720/1080/4K; no recursive detail')

if __name__=='__main__':run()
