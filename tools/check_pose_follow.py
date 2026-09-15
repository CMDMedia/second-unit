"""Preview integration: fresh source binding, dynamic trim and no finish stage."""
import importlib.util,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("panel",root/"resolve-panel/SecondUnit.py")
su=importlib.util.module_from_spec(spec);spec.loader.exec_module(su)
g=json.loads((root/"workflows/h3/h3_envswap_fast_pose-follow-preview.json").read_text())
a,info=su.patch_graph(g,"ENVSWAP","Continuous follow, no cuts.",83/24,seed=42,source_name="fresh.mp4",source_name_last="set.png",identity_name="front.png",wardrobe_name="three.png",prop1_name="profile.png",prop2_name="body.png",resolution="4K")
roles={n.get("_meta",{}).get("second_unit_role"):n for n in a.values()}
assert "fresh.mp4" in roles["pose_source"]["inputs"].values()
assert isinstance(roles["pose_h3"]["inputs"]["length"],list)
assert info["frames"]==83 and info["final_output_size"]==(1536,864)
assert not any("upscale" in n["class_type"].lower() for n in a.values())
assert a["13"]["inputs"]["steps"]==4
entries,problems=su.discover_graphs(str(root/"workflows"))
assert not problems and sum(e.production_ready for e in entries)==2
entry=next(e for e in entries if e.stamp.get("pipeline")=="h3_pose_follow")
assert not entry.production_ready
assert su.select_graph(entries,entry.mode,entry.lane,False,entry.name,entry.family,show_unproven=False)[0] is entry
try:
 su.patch_graph(g,"ENVSWAP","Follow",3,source_name="new.mp4")
except su.SecondUnitError:pass
else:raise AssertionError("Missing cards must refuse")
print("PASS dynamic source/cards, linked padding/trim, native delivery/no upscale, selectable preview and two proven presets")
