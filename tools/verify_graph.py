
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

CLOUD_NODES = {
    "GemmaAPITextEncode": "Lightricks api.ltx.video (paid) - use a local CLIPLoader/DualCLIPLoader chain",
    "MinimaxHailuo03TextToVideoNode": "MiniMax Hailuo cloud (paid) - use the local MiniMaxH3ImageToVideo stack",
    "GeminiNode": "Google Gemini (paid)",
    "GeminiInputFiles": "Google Gemini (paid)",
}
CLOUD_NAME_HINTS = ("hailuo", "kling", "runwayml", "lumaai", "pikaapi", "veoapi", "openaiapi", "recraft", "stabilityai")

NONDETERMINISTIC_NODES = {"TextGenerateLTX2Prompt"}

MODEL_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".sft", ".onnx", ".bin")

class Server:

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.base = f"http://{host}:{port}"
        self._info: dict | None = None

    def object_info(self) -> dict:
        if self._info is None:
            url = f"{self.base}/object_info"
            with urllib.request.urlopen(url, timeout=120) as resp:
                self._info = json.loads(resp.read())
        return self._info

    def version(self) -> str:
        try:
            with urllib.request.urlopen(f"{self.base}/system_stats", timeout=15) as resp:
                stats = json.loads(resp.read())
            return str(stats.get("system", {}).get("comfyui_version", "unknown"))
        except Exception:
            return "unknown"

def load_graph(path: Path) -> dict:

    return json.loads(path.read_text(encoding="utf-8-sig"))

def is_api_format(graph: dict) -> bool:
    if not isinstance(graph, dict) or not graph:
        return False
    if isinstance(graph.get("nodes"), list):
        return False
    return any(isinstance(v, dict) and "class_type" in v for v in graph.values())

def combo_options(spec) -> list | None:
    if not isinstance(spec, (list, tuple)) or not spec:
        return None
    if isinstance(spec[0], (list, tuple)):
        return list(spec[0])
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        options = spec[1].get("options")
        if isinstance(options, (list, tuple)):
            return list(options)
    return None

def autogrow_groups(required: dict, optional: dict) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for group, spec in list(required.items()) + list(optional.items()):
        if not (isinstance(spec, list) and spec and spec[0] == "COMFY_AUTOGROW_V3"):
            continue
        cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        tpl = cfg.get("template") if isinstance(cfg.get("template"), dict) else {}
        prefix = cfg.get("prefix") or tpl.get("prefix")
        maxn = cfg.get("max") or tpl.get("max") or 99
        if prefix:
            out[group] = (str(prefix), int(maxn))
    return out

def adapter_version_errors(graph: dict) -> list[str]:
    errors = []
    def version(value):
        match = re.search(r"ltx[-_ ]?(2\.[0-9]+)", str(value), re.I)
        return match.group(1) if match else None
    for nid, node in graph.items():
        inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
        adapter = inputs.get("lora_name", "")
        if "pixel-spatial" not in str(adapter).lower():
            continue
        av = version(adapter)
        if not av:
            continue
        link = inputs.get("model")
        seen = set()
        while isinstance(link, list) and len(link) == 2 and str(link[0]) not in seen:
            seen.add(str(link[0]))
            parent = graph.get(str(link[0]), {}).get("inputs", {})
            base = parent.get("unet_name") or parent.get("ckpt_name")
            bv = version(base)
            if bv and av != bv:
                errors.append(f"node {nid}: LTX {av} adapter '{adapter}' is wired to LTX {bv} base '{base}'")
                break
            link = parent.get("model")
    return errors

def check(graph: dict, info: dict) -> tuple[list[str], list[str], bool]:
    errors: list[str] = []
    warnings: list[str] = []
    is_local = True

    if not is_api_format(graph):
        return (["not API format (UI/subgraph JSON) - capture the flattened graph from /history"], [], True)

    for nid, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node:
            continue
        ct = str(node.get("class_type") or "")
        inputs = node.get("inputs") or {}

        if GUID_RE.match(ct):
            errors.append(f"node {nid}: class_type is a GUID ({ct[:8]}...) - unexpanded subgraph reference")
            continue

        if ct in CLOUD_NODES:
            is_local = False
            warnings.append(f"node {nid}: {ct} -> {CLOUD_NODES[ct]}")
        elif any(h in ct.lower() for h in CLOUD_NAME_HINTS):
            is_local = False
            warnings.append(f"node {nid}: {ct} looks like an external-service node")

        if ct in NONDETERMINISTIC_NODES:
            errors.append(f"node {nid}: {ct} rewrites the prompt at runtime - renders will not reproduce")

        schema = info.get(ct)
        if schema is None:
            errors.append(f"node {nid}: class_type '{ct}' is not registered on this server")
            continue

        spec = (schema.get("input") or {})
        required = spec.get("required") or {}
        optional = spec.get("optional") or {}
        known = set(required) | set(optional)

        dynamic_required: set[str] = set()
        format_spec = required.get("format")
        if isinstance(format_spec, list) and len(format_spec) > 1 \
                and isinstance(format_spec[1], dict):
            formats = format_spec[1].get("formats") or {}
            for extra in formats.get(inputs.get("format"), []) or []:
                if isinstance(extra, list) and extra and isinstance(extra[0], str):
                    dynamic_required.add(extra[0])
        known |= dynamic_required

        groups = autogrow_groups(required, optional)

        for key in required:
            if key in groups:
                continue
            if key not in inputs:
                errors.append(f"node {nid} ({ct}): missing required input '{key}'")
        for key in dynamic_required:
            if key not in inputs:
                errors.append(
                    f"node {nid} ({ct}): format '{inputs.get('format')}' needs input '{key}'")

        for key, val in inputs.items():
            base = key.split(".", 1)[0]
            if key in groups:
                errors.append(
                    f"node {nid} ({ct}): autogrow input '{key}' is nested; API format "
                    f"needs dotted live-socket keys such as '{key}.{groups[key][0]}0' or "
                    f"Comfy silently replaces the group with an empty dict"
                )
                continue
            autogrow_owner = None
            autogrow_valid = False
            for group, (prefix, maxn) in groups.items():
                marker = f"{group}.{prefix}"
                if key.startswith(marker):
                    autogrow_owner = group
                    tail = key[len(marker):]
                    autogrow_valid = tail.isdigit() and 0 <= int(tail) < maxn
                    break
            if autogrow_owner:
                if not autogrow_valid:
                    prefix, maxn = groups[autogrow_owner]
                    errors.append(
                        f"node {nid} ({ct}): '{key}' is not a valid autogrow socket; "
                        f"expected '{autogrow_owner}.{prefix}0'.."
                        f"'{autogrow_owner}.{prefix}{maxn - 1}'"
                    )
                continue
            if key not in known and base not in known:

                owner = next((g for g, (p, m) in groups.items()
                              if key.startswith(p) and key[len(p):].isdigit()), None)
                if owner:
                    errors.append(
                        f"node {nid} ({ct}): '{key}' is an undotted autogrow member; "
                        f"API format needs '{owner}.{key}'"
                    )
                else:
                    errors.append(f"node {nid} ({ct}): unknown input '{key}' (server does not expect it)")

        for key, val in inputs.items():
            if "." in key:
                base = key.split(".", 1)[0]
                if base not in groups and base not in inputs:
                    errors.append(
                        f"node {nid} ({ct}): dotted key '{key}' without its base key '{base}' "
                        f"(COMFY_DYNAMICCOMBO_V3 needs both)"
                    )
            if not isinstance(val, str):
                continue
            if not val.lower().endswith(MODEL_SUFFIXES):
                continue
            opts = combo_options(required.get(key) or optional.get(key))
            if opts is None:
                continue
            if val not in opts:
                errors.append(f"node {nid} ({ct}): '{val}' for '{key}' is not in the server's list")

    errors.extend(adapter_version_errors(graph))
    return errors, warnings, is_local

def verify(path: Path, server: Server, stamp: bool, skip_ui: bool = False) -> bool:
    try:
        graph = load_graph(path)
    except Exception as exc:
        print(f"FAIL {path.name}: unreadable ({exc})")
        return False

    if skip_ui and not is_api_format(graph):
        print(f"SKIP {path.name} (UI format - use verify_no_cloud_nodes.py)")
        return True

    try:
        info = server.object_info()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"ABORT: cannot reach {server.base}/object_info ({exc}).")
        print("       Start the target ComfyUI instance first - verification needs the live schema.")
        sys.exit(2)

    errors, warnings, is_local = check(graph, info)
    node_count = sum(1 for v in graph.values() if isinstance(v, dict) and "class_type" in v)

    if errors:
        print(f"FAIL {path.name} ({node_count} nodes, {len(errors)} problem(s)):")
        for e in errors[:20]:
            print(f"   - {e}")
        if len(errors) > 20:
            print(f"   ... and {len(errors) - 20} more")
        return False

    tag = "local" if is_local else "CLOUD"
    print(f"PASS {path.name} ({node_count} nodes) [{tag}]")
    for w in warnings:
        print(f"   ! {w}")

    if stamp:
        stamp_path = path.with_suffix(path.suffix + ".verified.json")
        release_metadata = {}
        if stamp_path.is_file():
            try:
                previous = json.loads(stamp_path.read_text(encoding="utf-8-sig"))
                for key in ("production_ready", "quarantine_reason", "provenance", "library",
                            "display_name", "category", "validation_status", "visual_review",
                            "render_evidence", "release_eligible", "experimental"):
                    if key in previous:
                        release_metadata[key] = previous[key]
                if previous.get("graph_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
                    release_metadata.pop("render_evidence", None)
                    release_metadata["visual_review"] = "unreviewed-after-edit"
                    release_metadata["validation_status"] = "schema-only"
                    release_metadata["release_eligible"] = False
                    release_metadata.pop("experimental", None)
            except (OSError, ValueError):
                pass

        graph_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = {
            "graph": path.name,
            "graph_sha256": graph_sha256,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "server": server.base,
            "comfyui_version": server.version(),
            "node_count": node_count,
            "local": is_local,
            "validation_scope": "schema-and-model-availability; not runtime or visual approval",
            "warnings": warnings,
            "checks": [
                "api_format", "no_subgraph_residue", "classes_registered",
                "required_inputs_present", "input_names_exact",
                "models_in_combo_list", "dynamic_combo_keys", "deterministic",
            ],
        }
        payload.update(release_metadata)
        stamp_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        print(f"   stamped -> {stamp_path.name}")
    return True

def main() -> int:
    ap = argparse.ArgumentParser(description="Verify ComfyUI API graphs are pristine.")
    ap.add_argument("graphs", nargs="*", help="graph JSON files")
    ap.add_argument("--all", action="store_true", help="verify every *.json under --dir, recursively")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "workflows"))
    ap.add_argument("--port", type=int, default=8188, help="ComfyUI port")
    ap.add_argument("--stamp", action="store_true", help="write .verified.json on pass")
    args = ap.parse_args()

    explicit = [Path(g) for g in args.graphs]
    swept: list[Path] = []
    if args.all:
        swept = sorted(p for p in Path(args.dir).rglob("*.json") if not p.name.endswith(".verified.json"))
    if not explicit and not swept:
        ap.error("no graphs given (pass files or --all)")

    server = Server(args.port)
    results = [verify(p, server, args.stamp) for p in explicit]
    results += [verify(p, server, args.stamp, skip_ui=True) for p in swept]
    ok, total = sum(results), len(results)
    print(f"\n{ok}/{total} structurally valid (not a render or visual-quality certification)")
    return 0 if ok == total else 1

if __name__ == "__main__":
    sys.exit(main())
