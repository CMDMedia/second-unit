"""Recorded camera optics and explicit source provenance; never inferred camera pose."""
import json
import ntpath
import os
import re
from pathlib import Path

def path_key(value):
    value=str(value or '').strip()
    if not value:return ''
    if not (ntpath.isabs(value) or os.path.isabs(value)):return ''
    return ntpath.normcase(ntpath.normpath(value.replace('/','\\')))

ALIASES = {
    'focal_length_mm': ('Focal Point (mm)', 'Focal Length (mm)', 'Focal Length'),
    'lens': ('Lens', 'Lens Type'), 'camera': ('Camera Type', 'Camera Model', 'Camera'),
    'aperture': ('Camera Aperture', 'Aperture', 'F-Stop'), 'shutter_angle': ('Shutter Angle', 'Shutter'),
    'iso': ('ISO',), 'white_balance': ('White Point (Kelvin)', 'White Balance', 'White Balance (K)'),
}

def parse_metadata(metadata):
    data={re.sub(r'[^a-z0-9]','',str(k).lower()):v for k,v in (metadata or {}).items()}
    result={}
    for name, aliases in ALIASES.items():
        for alias in aliases:
            value=data.get(re.sub(r'[^a-z0-9]','',alias.lower()))
            if value not in (None,''):
                if name in ('focal_length_mm','aperture','shutter_angle','iso','white_balance'):
                    text=str(value).strip();m=re.fullmatch(r'(?:f/?)?([0-9]+(?:\.[0-9]+)?)(?:\s*(?:mm|K|deg|degrees|\u00b0))?',text,re.I)
                    if m and float(m.group(1))>0:result[name]=float(m.group(1))
                else:
                    clean=' '.join(str(value).split())[:120]
                    if not re.search(r'[<>{}\r\n]',clean):result[name]=clean
                break
    return result

def linked_original(target):
    """Known adjacent receipts only; exact absolute target, no filename similarity."""
    path=Path(target);folder=path if path.is_dir() else path.parent
    candidates=[]
    for name in ('resolve_plate_receipt.json','second-unit-source.json'):
        receipt=folder/name
        try:
            if receipt.stat().st_size>65536:continue
            data=json.loads(receipt.read_text(encoding='utf-8-sig'))
            source=data.get('source');recorded_target=data.get('target')
            if path_key(recorded_target)==path_key(target) and path_key(source) and path_key(source)!=path_key(target):
                candidates.append({'source':source,'receipt':str(receipt),'start_frame':data.get('start_frame'),'end_frame_exclusive':data.get('end_frame_exclusive')})
        except (OSError,ValueError,TypeError):pass
    keys={path_key(x['source']) for x in candidates}
    if len(keys)>1:return None,'ambiguous source receipts'
    return (candidates[0],'explicit source receipt') if candidates else (None,'no exact source receipt')

def choose_record(target, records, loader=linked_original):
    direct=[r for r in records if path_key(r.get('path'))==path_key(target) and path_key(target)]
    direct_data=[parse_metadata(r.get('metadata')) for r in direct]
    if len({json.dumps(d,sort_keys=True) for d in direct_data})>1:
        return {},{'status':'ambiguous','reason':'conflicting metadata for exact source path'}
    result=dict(direct_data[0]) if direct_data else {}
    fields={k:{'source':target,'basis':'selected media pool clip'} for k in result}
    link,reason=loader(target) if target else (None,'no reference source')
    if link:
        matches=[r for r in records if path_key(r.get('path'))==path_key(link['source'])]
        values=[parse_metadata(r.get('metadata')) for r in matches]
        if len({json.dumps(d,sort_keys=True) for d in values})>1:
            return result,{'status':'ambiguous','reason':'conflicting original-clip metadata','fields':fields}
        if values:
            for k,v in values[0].items():
                if k not in result:
                    result[k]=v;fields[k]=dict(link,basis='explicit derivative-to-original receipt and exact media path')
        else:reason='linked original clip metadata unavailable'
    status='recorded' if result else ('ambiguous' if reason.startswith('ambiguous') else 'unknown')
    return result,{'status':status,'reason':reason,'fields':fields,'scope':'clip metadata; zoom position per frame unverified'}

LENS_OVERRIDE = re.compile(r'\b(?:[0-9]+(?:\.[0-9]+)?\s*mm|(?:use|switch|change|shoot|shot|filmed|on|with)\s+(?:a\s+|an\s+|the\s+)?(?:different\s+)?(?:lens|telephoto|wide.angle|fisheye|anamorphic))\b',re.I)

def prompt_context(snapshot, request):
    if LENS_OVERRIDE.search(request or ''):return ''
    optics=(snapshot or {}).get('optics') or {}
    focal=optics.get('focal_length_mm')
    if not focal:return ''
    # Do not insert arbitrary lens names, paths or other untrusted metadata into prompts.
    return 'Use the recorded %g mm lens characteristics as an optics reference only. The requested camera position, framing and movement remain authoritative.' % focal

def add_context(request, context):
    if not context or context in (request or ''):return request
    return (request or '').rstrip()+'\n'+context
