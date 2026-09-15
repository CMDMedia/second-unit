import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def run(module=None, namespace=None):
    root = Path(__file__).resolve().parents[1]
    if namespace is None:
        spec = importlib.util.spec_from_file_location('second_unit_preview_check', root / 'resolve-panel/SecondUnit.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        namespace = vars(module)
    su = type('Panel', (), {})()
    su.__dict__.update(namespace)
    results = []

    def check(label, condition):
        results.append(bool(condition))
        print(('PASS ' if condition else 'FAIL ') + label)

    info = {'CLIPLoader': {'input': {'required': {'clip_name': [['ltx-2.5-test.safetensors']]}}}}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = info if self.path == '/object_info' else {'system': {'comfyui_version': 'test'}}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:%s' % server.server_port
    old_log = namespace.get('_LOG_PATH')
    try:
        with tempfile.TemporaryDirectory(prefix='second-unit-package-check-') as tmp:
            namespace['_LOG_PATH'] = os.path.join(tmp, 'check.log')
            repo = Path(tmp) / 'repo'
            workflows = repo / 'workflows'
            (repo / 'tools').mkdir(parents=True)
            import shutil
            shutil.copyfile(root / 'tools/verify_graph.py', repo / 'tools/verify_graph.py')
            graph = {'1': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'ltx-2.5-test.safetensors'}}}
            source = Path(tmp) / 'ltx25_t2v_custom.json'
            source.write_text(json.dumps(graph), encoding='utf-8')
            name, summary = su.load_workflow_file(str(source), str(workflows), url, python=sys.executable)
            check('Custom import runs the verifier', summary.startswith('PASS'))
            entries, problems = su.discover_graphs(str(workflows))
            check('Imported workflow is discovered', len(entries) == 1 and not problems)
            entry = entries[0]
            check('Custom workflow is not falsely certified', entry.user_workflow and not entry.proven)
            check('Custom label is visible', entry.evidence_word() == 'custom')
            picked, reason = su.select_graph(entries, entry.mode, su.LANES[0], False, name, entry.family, show_unproven=False)
            check('Custom workflow selectable with unproven filter off', picked is entry)
            entry.local = False
            check('Cloud workflow requires explicit opt-in', not su.candidates_for(entries, entry.mode, su.LANES[0], False, entry.family, False))
            entry.local = True
            entry.production_ready = False
            check('Quarantine still prevents selection', not su.candidates_for(entries, entry.mode, su.LANES[0], False, entry.family, False))
            dest = workflows / su.LOADED_WORKFLOWS_SUBDIR / name
            dest.write_text(json.dumps({'1': {'class_type': 'CLIPLoader', 'inputs': {'clip_name':'changed.safetensors'}}}), encoding='utf-8')
            check('Edited graph invalidates compatibility stamp', su.read_stamp(str(dest)) is None)
            for label, payload, expected in [
                ('UI-format JSON rejected', {'nodes': [], 'links': []}, 'API'),
                ('Unknown node rejected', {'1': {'class_type':'MissingNode', 'inputs': {'model':'ltx-2.5-test.safetensors'}}}, 'MissingNode'),
                ('Missing model rejected', {'1': {'class_type':'CLIPLoader', 'inputs': {'clip_name':'ltx-2.5-missing.safetensors'}}}, 'ltx-2.5-missing.safetensors'),
                ('Unknown model family rejected', {'1': {'class_type':'CLIPLoader', 'inputs': {'clip_name':'unknown.safetensors'}}}, 'family'),
            ]:
                bad = Path(tmp) / 'input.json'
                bad.write_text(json.dumps(payload), encoding='utf-8')
                try:
                    su.load_workflow_file(str(bad), str(workflows), url, python=sys.executable)
                    check(label, False)
                except su.SecondUnitError as exc:
                    check(label, expected.lower() in str(exc).lower())
            check('Runtime files parse', all(compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in root.rglob('*.py')))
    finally:
        namespace['_LOG_PATH'] = old_log
        server.shutdown()
        server.server_close()
    print('%d/%d checks passed' % (sum(results), len(results)))
    print('No generation was submitted. These checks do not replace a Resolve render test.')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(run())
