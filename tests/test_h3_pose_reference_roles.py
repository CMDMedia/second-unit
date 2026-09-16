"""The panel's named slots must survive editable node display titles."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("h3_roles", ROOT / "resolve-panel/h3_prompt_translator.py")
translator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translator)


class PoseReferenceRolesTests(unittest.TestCase):
    def test_panel_slots_override_missing_or_misleading_titles(self):
        graph = json.loads((ROOT / "workflows/h3/h3_envswap_fast_pose-follow-preview.json").read_text())
        for node in graph.values():
            if node["class_type"] == "LoadImage":
                node["_meta"]["title"] = "Replacement character"
        _, refs = translator.refs_from_graph(graph)
        self.assertEqual([p["role"] for p in refs["pictures"]],
                         ["identity", "identity", "identity", "wardrobe", "environment"])
        self.assertEqual(refs["videos"][0]["role"], "source_edit")

    def test_legacy_graph_keeps_title_fallback(self):
        graph = {
            "1": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"ref_images.ref_image_0": ["2", 0]}},
            "2": {"class_type": "LoadImage", "inputs": {"image": "set.png"}, "_meta": {"title": "Environment"}},
        }
        _, refs = translator.refs_from_graph(graph)
        self.assertEqual(refs["pictures"][0]["role"], "environment")

    def test_plain_panel_prompt_uses_identity_and_location_not_weak_composition(self):
        panel_spec = importlib.util.spec_from_file_location("pose_panel", ROOT / "resolve-panel/SecondUnit.py")
        panel = importlib.util.module_from_spec(panel_spec)
        panel_spec.loader.exec_module(panel)
        graph = json.loads((ROOT / "workflows/h3/h3_envswap_fast_pose-follow-preview.json").read_text())
        patched, info = panel.patch_graph(
            graph, "ENVSWAP", "Follow the performer through the cave in the environment reference.",
            83 / 24, seed=7, source_name="new-take.mp4", source_name_last="new-set.png",
            identity_name="new-front.png", wardrobe_name="new-threequarter.png",
            prop1_name="new-profile.png", prop2_name="new-body.png", resolution="720P")
        generation = next(n for n in patched.values() if n["class_type"] == "MiniMaxH3ReferenceToVideo")
        text = generation["inputs"]["prompt"]
        self.assertIn("same person shown in <Picture 1>, <Picture 2>, <Picture 3>", text)
        self.assertIn("costume shown in <Picture 4>", text)
        self.assertIn("location shown in <Picture 5>", text)
        self.assertNotIn("weak_reference - only its composition", text)
        self.assertEqual(generation["inputs"]["ref_image_size"], "max")
        self.assertEqual(info["frames"], 83)
        self.assertEqual(info["reference_tail_padding"], 7)
        original = graph["9"]["inputs"]["ref_videos.ref_video_0"]
        def evaluate(link):
            if link == original:
                return list(range(83))
            node = patched[link[0]]
            values = node["inputs"]
            if node["class_type"] == "ImageFromBatch":
                return evaluate(values["image"])[values["batch_index"]:values["batch_index"] + values["length"]]
            if node["class_type"] == "RepeatImageBatch":
                return evaluate(values["image"]) * values["amount"]
            if node["class_type"] == "ImageBatch":
                return evaluate(values["image1"]) + evaluate(values["image2"])
            self.fail("Unexpected reference node " + node["class_type"])
        reference_frames = evaluate(generation["inputs"]["ref_videos.ref_video_0"])
        self.assertEqual(reference_frames, list(range(83)) + [82] * 7)
        self.assertEqual(len(reference_frames), info["generated_frames"])


if __name__ == "__main__":
    unittest.main()
