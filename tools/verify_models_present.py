

from __future__ import annotations

import argparse
import glob
import json
import ntpath
import os
import sys
import urllib.error
import urllib.request

MODEL_EXT = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".sft", ".bin")

def combo_options(spec):
    if not isinstance(spec, (list, tuple)) or not spec:
        return None
    if isinstance(spec[0], (list, tuple)):
        return list(spec[0])
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        options = spec[1].get("options")
        if isinstance(options, (list, tuple)):
            return list(options)
    return None

def get_object_info(base: str) -> dict:
    url = base.rstrip("/") + "/object_info"
    with urllib.request.urlopen(url, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))

def published_values(object_info: dict):
    exact = set()
    by_base = {}
    for spec in object_info.values():
        section = spec.get("input") or {}
        for group in ("required", "optional"):
            for ispec in (section.get(group) or {}).values():
                opts = combo_options(ispec)
                if opts is None:
                    continue
                for opt in opts:
                    if isinstance(opt, str) and opt.lower().endswith(MODEL_EXT):
                        exact.add(opt)
                        by_base.setdefault(ntpath.basename(opt), opt)
    return exact, by_base

def refs_in_graph(path: str):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except (ValueError, OSError):
        return []

    out = []
    if isinstance(d, dict) and "nodes" in d:
        for n in d.get("nodes") or []:
            cls = n.get("type", "?")
            for w in (n.get("widgets_values") or []):
                if isinstance(w, str) and w.lower().endswith(MODEL_EXT):
                    out.append((w, cls))
    elif isinstance(d, dict):
        for n in d.values():
            if not isinstance(n, dict):
                continue
            cls = n.get("class_type", "?")
            for v in (n.get("inputs") or {}).values():
                if isinstance(v, str) and v.lower().endswith(MODEL_EXT):
                    out.append((v, cls))
    return out

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check every workflow model reference against a live ComfyUI.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8188)
    ap.add_argument("--dir", action="append", required=True,
                    help="directory of workflows (repeatable, searched recursively)")
    ap.add_argument("--quiet", action="store_true", help="only print failures")
    args = ap.parse_args()

    base = "http://%s:%d" % (args.host, args.port)
    try:
        info = get_object_info(base)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print("ABORT: cannot reach %s/object_info (%s)" % (base, exc))
        return 1

    exact, by_base = published_values(info)
    if not args.quiet:
        print("server %s publishes %d distinct model strings\n" % (base, len(exact)))

    files = []
    for d in args.dir:
        files += [f for f in glob.glob(os.path.join(d, "**", "*.json"), recursive=True)
                  if not f.endswith(".verified.json")]

    missing, checked, seen = [], 0, set()
    for f in sorted(files):
        for ref, cls in refs_in_graph(f):
            if ref.startswith("http"):
                continue
            key = (ref, cls)
            if key in seen:
                continue
            seen.add(key)
            checked += 1
            if ref in exact:
                continue
            hint = by_base.get(ntpath.basename(ref))
            missing.append((os.path.basename(f), cls, ref, hint))

    for wf, cls, ref, hint in missing:
        print("MISSING  %s" % ref)
        print("         in %s, node %s" % (wf, cls))
        if hint:
            print("         server publishes it as: %s   <- graph string is wrong, file IS there" % hint)
        else:
            print("         no file of that name is published by this server at all")

    print("\n%d references checked, %d would show MISSING" % (checked, len(missing)))
    return 1 if missing else 0

if __name__ == "__main__":
    sys.exit(main())
