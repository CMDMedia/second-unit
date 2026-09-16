import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('selection_panel', ROOT / 'resolve-panel/SecondUnit.py')
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


class ModelSelectionTests(unittest.TestCase):
    def test_switch_from_stills_to_h3_to_ltx_and_back(self):
        obj = panel.SecondUnitPanel.__new__(panel.SecondUnitPanel)
        obj.entries, problems = panel.discover_graphs(str(ROOT / 'workflows'))
        self.assertFalse(problems)
        state = dict(family='JUGGERNAUT', mode='STILLS', lane='Quality')
        obj.current_family = lambda: state['family']
        obj.current_mode = lambda: state['mode']
        obj.current_lane = lambda: state['lane']
        obj.get_checked = lambda key: False
        obj.show_unproven = lambda: False
        def set_attr(widget, attribute, index):
            pairs = {'mode': panel.MODE_LABELS, 'lane': panel.LANE_LABELS,
                     'family': panel.FAMILY_LABELS}
            state[widget] = pairs[widget][index][0]
        obj.set_attr = set_attr
        obj.repopulate_presets = lambda: None
        obj.on_selection_changed = lambda event: None
        for family in ('MINIMAXH3', 'LTX25', 'JUGGERNAUT', 'MINIMAXH3'):
            state['family'] = family
            obj.on_family_changed()
            # Resolve also queues change events after updating other dropdowns.
            obj.on_mode_changed()
            self.assertEqual(state['family'], family)
            entry, reason = panel.select_graph(obj.entries, state['mode'], state['lane'],
                                               False, family=family, show_unproven=False)
            self.assertIsNotNone(entry, reason)

    def test_h3_direct_workflow_and_panel_deliver_prores(self):
        graph = json.loads((ROOT / 'workflows/h3/h3_envswap_fast_pose-follow-preview.json').read_text())
        self.assertEqual(graph['16']['inputs']['format'], 'video/ProRes')
        self.assertEqual(graph['16']['inputs']['profile'], 'hq')
        patched, _ = panel.patch_graph(graph, 'ENVSWAP', 'Follow the performer',
                                      83 / 24, source_name='take.mp4', source_name_last='set.png',
                                      identity_name='front.png', wardrobe_name='threequarter.png',
                                      prop1_name='profile.png', prop2_name='body.png')
        savers = [n['inputs'] for n in patched.values() if n['class_type'] == 'VHS_VideoCombine']
        self.assertTrue(savers)
        for saver in savers:
            self.assertEqual(saver['format'], 'video/ProRes')
            self.assertEqual(saver['profile'], 'hq')


if __name__ == '__main__':
    unittest.main()
