"""Selected-model prompt routing and asynchronous panel regression checks."""
import importlib.util
import json
from pathlib import Path
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path(__file__).resolve().parents[1]
def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    tr = load('prompt_translator_check', 'resolve-panel/h3_prompt_translator.py')
    su = load('prompt_panel_check', 'resolve-panel/SecondUnit.py')
    graph = {'1': {'class_type': 'LoadImage', 'inputs': {'image': 'environment.png'}}}
    requests = []
    reply = ['Existing mineral surfaces retain their fine detail. Reflections remain consistent with the existing illumination.']
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            data = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': reply[0]}}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(data)
        def log_message(self, *args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = {'configured': True, 'provider': 'openai', 'url': 'http://127.0.0.1:%d/v1' % server.server_port,
           'model': 'test-provider-model', 'key': '', 'timeout': 3}
    try:
        for request in ('Keep the camera stationary in this cave.', 'Pan left slowly.', 'Push forward through this cave.',
                        'Okay, give me this cave with the camera held still and water dripping.'):
            text, info = tr.expand_for_family('LTX25', graph, request, cfg=cfg)
            assert text.startswith(request) and info['source'] == 'llm'
            assert 'subject_definitions:' not in text and '[Shot 1]' not in text
            assert 'LTX 2.5' in requests[-1]['messages'][0]['content']
            assert requests[-1]['model'] == 'test-provider-model'
        print('PASS real HTTP adapter: LTX instructions selected independently of LLM provider; dictated camera words retained')
        reply[0] = 'Wet limestone contains fine mineral strata and believable irregular surface detail. Puddles have physically plausible reflections.'
        still_request = 'Wet limestone cave, distant mountains and fog, blue night lighting, eye-level camera, no people.'
        text, info = tr.expand_for_family('JUGGERNAUT', graph, still_request, cfg=cfg)
        assert text.startswith(still_request) and info['source'] == 'llm' and info['family'] == 'JUGGERNAUT'
        assert 'SDXL still-image' in requests[-1]['messages'][0]['content']
        assert len(text.split()) < 100 and 'detailed_description:' not in text
        for bad in ('A man stands near the entrance.', 'Then the camera pans left for five seconds.',
                    'Golden sunlight fills the cave.', 'subject_definitions: <Subject 1>'):
            reply[0] = bad
            text, info = tr.expand_for_family('JUGGERNAUT', graph, still_request, cfg=cfg)
            assert info['fallback'] and text.startswith(still_request) and bad not in text
        text, info = tr.expand_for_family('JUGGERNAUT', graph, still_request, cfg={'configured': False})
        assert info['source'] == 'template' and not info['fallback']
        print('PASS Juggernaut concise SDXL still route preserves scene/camera/light/exclusions; rejects actor, video and lighting overrides')
        reply[0] = 'The camera moves right as a man enters.'
        text, info = tr.expand_for_family('LTX25', graph, 'Keep the camera stationary.', cfg=cfg)
        assert info['fallback'] and text.startswith('Keep the camera stationary.') and 'moves right' not in text and 'man enters' not in text
        reply[0] = 'subject_definitions: <Subject 1>'
        assert tr.expand_for_family('LTX25', graph, 'Pan left.', cfg=cfg)[1]['fallback']
        print('PASS conflicting camera, invented actor and H3-format replies cannot replace operator instructions')
        h3 = {'1': {'class_type': 'LoadImage', 'inputs': {'image': 'reference.png'}},
              '2': {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': {'ref_images.ref_image_0': ['1', 0], 'length': 124}}}
        mode, refs = tr.refs_from_graph(h3)
        before = tr.expand(mode, refs, 'The camera pans left.', tr.duration_seconds(h3), {}, cfg={'configured': False})
        after = tr.expand_for_family('MINIMAXH3', h3, 'The camera pans left.', cfg={'configured': False})
        assert before == after and 'detailed_description:' in after[0]
        print('PASS H3 router preserves existing translator output and section format')
        class PanelHarness:
            expander_inflight = True
            expander_original = 'original'
            def __init__(self): self.attrs = {}; self.text = 'original'; self.family = 'LTX25'; self.preset = 'current'
            def current_family(self): return self.family
            def current_mode(self): return 'I2V'
            def current_preset(self): return self.preset
            def get_text(self, widget): return self.text
            def set_attr(self, widget, prop, value): self.attrs[(widget, prop)] = value
            def status(self, *a, **kw): pass
        harness = PanelHarness()
        su.SecondUnitPanel.on_expanded(harness, {'selection_key': ('MINIMAXH3', 'I2V', 'old'), 'original_request': 'original', 'prompt': 'stale H3'})
        assert ('prompt', 'PlainText') not in harness.attrs and not harness.expander_inflight
        harness = PanelHarness(); harness.text = 'new dictation'
        su.SecondUnitPanel.on_expanded(harness, {'selection_key': ('LTX25', 'I2V', 'current'), 'original_request': 'original', 'prompt': 'stale text'})
        assert ('prompt', 'PlainText') not in harness.attrs
        harness = PanelHarness()
        su.SecondUnitPanel.on_expanded(harness, {'selection_key': ('LTX25', 'I2V', 'current'), 'original_request': 'original', 'prompt': 'expanded', 'info': {'source': 'llm'}})
        assert harness.attrs[('prompt', 'PlainText')] == 'expanded'
        su.SecondUnitPanel.on_revert_prompt(harness, None)
        assert harness.attrs[('prompt', 'PlainText')] == 'original'
        print('PASS model/preset switches and newer dictation protected; accepted expansion and REVERT work')
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'Juggernaut-Environment-Stills-API.json'
            path.write_text(json.dumps(graph))
            entry = su.GraphEntry(str(path), 'STILLS', 'Quality',
                {'local': True, 'production_ready': True, 'validation_status': 'render-proven', 'release_eligible': True}, 'JUGGERNAUT')
            class StillHarness(PanelHarness):
                def __init__(self):
                    super().__init__(); self.family = 'JUGGERNAUT'; self.preset = entry.name
                    self.entries = [entry]; self.outbox = queue.Queue(); self.expander_inflight = False
                    self.text = still_request
                def camera_source_key(self): return ''
                def current_mode(self): return 'STILLS'
                def current_lane(self): return 'Quality'
                def get_checked(self, widget): return False
                def show_unproven(self): return False
            su.h3_translator = lambda: tr
            su.h3_expander_config = lambda translator: {'configured': False}
            harness = StillHarness()
            su.SecondUnitPanel.on_expand_prompt(harness, None)
            harness.expander_thread.join(timeout=3)
            message = harness.outbox.get(timeout=1)
            assert message['info']['family'] == 'JUGGERNAUT' and message['selection_key'][0] == 'JUGGERNAUT'
            assert message['prompt'].startswith(still_request)
            su.SecondUnitPanel.on_expanded(harness, message)
            assert harness.attrs[('expand_prompt', 'Enabled')] is True
            assert harness.attrs[('prompt', 'PlainText')].startswith(still_request)
        print('PASS Juggernaut panel button dispatches asynchronously, accepts returned still prose and re-enables')

    finally:
        server.shutdown(); server.server_close()

if __name__ == '__main__':
    run()
