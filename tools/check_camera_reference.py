"""Recorded optics provenance and camera-policy regression tests; no render."""
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('camera_ref','resolve-panel/camera_reference.py')
su=load('camera_panel','resolve-panel/SecondUnit.py')
tr=load('camera_translator','resolve-panel/h3_prompt_translator.py')
def run():
    parsed=c.parse_metadata({'Focal Point (mm)':'24','Lens':'RF24-105mm F4-7.1 IS STM','Camera Aperture':'4.6','White Point (Kelvin)':'5260','Shutter':'180'})
    assert parsed['focal_length_mm']==24 and parsed['aperture']==4.6 and parsed['white_balance']==5260
    assert 'focal_length_mm' not in c.parse_metadata({'Lens':'24-105mm','Focal Length':'24-105 mm'})
    with tempfile.TemporaryDirectory() as td:
        target=str(Path(td)/'graded.mov');original=str(Path(td)/'camera.mxf');receipt=Path(td)/'resolve_plate_receipt.json'
        receipt.write_text(json.dumps({'target':target,'source':original}))
        records=[{'path':target,'metadata':{'Camera Type':'Recorded camera'}},{'path':original,'metadata':{'Focal Point (mm)':'24'}}]
        optics,provenance=c.choose_record(target,records)
        assert optics=={'camera':'Recorded camera','focal_length_mm':24} and provenance['fields']['focal_length_mm']['receipt']==str(receipt)
        receipt.write_text(json.dumps({'target':str(Path(td)/'another.mov'),'source':original}))
        optics,provenance=c.choose_record(target,records);assert 'focal_length_mm' not in optics
        receipt.write_text(json.dumps({'target':target,'source':original}))
        (Path(td)/'second-unit-source.json').write_text(json.dumps({'target':target,'source':str(Path(td)/'other.mxf')}))
        optics,provenance=c.choose_record(target,records);assert 'focal_length_mm' not in optics
    optics,provenance=c.choose_record('',[]);assert optics=={} and provenance['status']=='unknown'
    records=[{'path':'C:/same.mov','metadata':{'Focal Point (mm)':'24'}},{'path':'C:/same.mov','metadata':{'Focal Point (mm)':'50'}}]
    assert c.choose_record('C:/same.mov',records)[1]['status']=='ambiguous'
    snapshot={'optics':{'focal_length_mm':24,'lens':'private path C:/never-print'}}
    request='Follow him over the shoulder with hard cuts.'
    context=c.prompt_context(snapshot,request);assert '24 mm' in context and 'private' not in context
    assert c.prompt_context(snapshot,'Use an 85mm lens.')==''
    assert c.prompt_context(snapshot,'Use 85 mm.')==''
    assert c.prompt_context({},request)==''
    assert su.h3_compose_opts({},request)['reframe'] is True and su.h3_compose_opts({},request)['continuous_take'] is False
    follow=su.h3_compose_opts({},'The camera follows his cautious walk continuously.')
    assert follow['reframe'] is True and follow['continuous_take'] is True
    assert su.h3_compose_opts({},'A person walks through the set.')['reframe'] is True
    assert su.h3_compose_opts({},'Keep the source camera position.')['reframe'] is False
    with patch.object(tr,'expand_juggernaut',lambda request,**k:(request,{})),patch.object(tr,'expand_ltx25',lambda request,graph,**k:(request,{})),patch.object(tr,'refs_from_graph',lambda g:('ref2va',{})),patch.object(tr,'duration_seconds',lambda g:4),patch.object(tr,'expand',lambda mode,refs,request,*a,**k:(request,{})):
        for family in ('JUGGERNAUT','LTX25','MINIMAXH3'):
            text,_=tr.expand_for_family(family,{},request,opts={'camera_context':context})
            assert text.startswith(request) and text.count('24 mm')==1
    refs={'pictures':[],'videos':[{'index':1,'role':'source_edit'}],'audios':[]}
    opts=su.h3_compose_opts({},request);report=tr.classify_request(c.add_context(request,context),'ref2va',refs,opts)
    assert not report['camera_locked'] and not report['held_back'],report
    graph=json.loads((ROOT/'workflows/juggernaut/SecondUnit-Juggernaut-Environment-Stills-API.json').read_text())
    patched=su.prepare_environment_still(graph,c.add_context('Wet limestone cave at blue night.',context),4)
    positive=next(n for n in patched.values() if (n.get('_meta') or {}).get('second_unit_role')=='environment_prompt')
    assert '24 mm' in positive['inputs']['text'] and 'Wet limestone' in positive['inputs']['text']
    assert c.add_context(positive['inputs']['text'],context)==positive['inputs']['text']
    class ChangedSource:
        def __init__(self):self.attrs={};self.expander_inflight=True
        def current_family(self):return 'JUGGERNAUT'
        def camera_source_key(self):return 'new-source'
        def get_text(self,key):return 'original'
        def set_attr(self,key,attr,value):self.attrs[(key,attr)]=value
    panel=ChangedSource()
    su.SecondUnitPanel.on_expanded(panel,{'source_key':'old-source','original_request':'original','prompt':'stale24mm'})
    assert ('prompt','PlainText') not in panel.attrs
    assert 'Reference source changed' in panel.attrs[('expander_status','Text')]
    print('PASS exact provenance, missing/ambiguous metadata, partial focal fallback, lens overrides, all expander families, source camera unlocked and requested cuts preserved')
if __name__=='__main__':run()
