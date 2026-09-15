

import argparse
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

class ReconcileError(Exception):
    pass

def read_json(path):
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise ReconcileError("Could not read %s: %s" % (path, exc))
    return value if isinstance(value, dict) else {}

def read_events(path):
    events = []
    if not path.is_file():
        return events
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                value["_line"] = number
                events.append(value)
    return events

def load_job(job_value):
    job_dir = pathlib.Path(job_value).expanduser().resolve()
    request = read_json(job_dir / "request.json")
    if not request.get("request_id"):
        raise ReconcileError("Not a Second Unit panel job: %s" % job_dir)
    events = read_events(job_dir / "events.jsonl")
    intent = read_json(job_dir / "submit-intent.json")
    exit_record = read_json(job_dir / "exit.json")
    consumed = read_json(job_dir / "consumed.json")
    prompt_ids = []
    for value in [intent.get("prompt_id"), exit_record.get("prompt_id")] + [
            event.get("prompt_id") for event in events]:
        if value and str(value) not in prompt_ids:
            prompt_ids.append(str(value))
    terminal = next(
        (event for event in reversed(events)
         if event.get("kind") in ("done", "error")), {})
    return {
        "job_dir": str(job_dir),
        "request": request,
        "request_id": str(request["request_id"]),
        "base": str(request.get("client_base") or "http://127.0.0.1:8190").rstrip("/"),
        "intent": intent,
        "exit": exit_record,
        "consumed": consumed,
        "events": events,
        "terminal": terminal,
        "prompt_ids": prompt_ids,
    }

def get_json(base, path, timeout=8):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(base + path, headers={"Accept": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode("utf-8", "replace")) if body else {}

def fetch_live(job):
    result = {"reachable": False, "prompts": {}, "recovered_prompt_ids": []}
    try:
        queue = get_json(job["base"], "/queue")
        result["reachable"] = True
    except Exception as exc:
        result["error"] = "%s: %s" % (exc.__class__.__name__, exc)
        return result
    running = {str(item[1]) for item in (queue.get("queue_running") or []) if len(item) > 1}
    pending = {str(item[1]) for item in (queue.get("queue_pending") or []) if len(item) > 1}
    effective_ids = list(job["prompt_ids"])
    client_id = str(job["intent"].get("client_id") or "")
    if client_id:
        for item in (queue.get("queue_running") or []) + (queue.get("queue_pending") or []):
            extra = item[3] if len(item) > 3 and isinstance(item[3], dict) else {}
            prompt_id = str(item[1]) if len(item) > 1 else ""
            if extra.get("client_id") == client_id and prompt_id and prompt_id not in effective_ids:
                effective_ids.append(prompt_id)
                result["recovered_prompt_ids"].append(prompt_id)
        try:
            recent_history = get_json(job["base"], "/history?max_items=64")
        except Exception as exc:
            recent_history = {}
            result["recent_history_error"] = str(exc)
        for prompt_id, entry in (recent_history or {}).items():
            prompt = (entry or {}).get("prompt") if isinstance(entry, dict) else None
            extra = prompt[3] if isinstance(prompt, list) and len(prompt) > 3 \
                and isinstance(prompt[3], dict) else {}
            prompt_id = str(prompt_id)
            if extra.get("client_id") == client_id and prompt_id not in effective_ids:
                effective_ids.append(prompt_id)
                result["recovered_prompt_ids"].append(prompt_id)
    result["effective_prompt_ids"] = effective_ids
    for prompt_id in effective_ids:
        try:
            history = get_json(
                job["base"], "/history/" + urllib.parse.quote(prompt_id)).get(prompt_id)
        except Exception as exc:
            history = None
            result.setdefault("history_errors", {})[prompt_id] = str(exc)
        state = "running" if prompt_id in running else "pending" if prompt_id in pending else (
            "history" if history else "absent")
        outputs = []
        if isinstance(history, dict):
            for node in (history.get("outputs") or {}).values():
                if not isinstance(node, dict):
                    continue
                for key in ("gifs", "videos", "images"):
                    for item in node.get(key) or []:
                        if isinstance(item, dict):
                            outputs.append(item.get("filename"))
        result["prompts"][prompt_id] = {
            "state": state,
            "history_terminal": bool(history),
            "history_status": ((history or {}).get("status") or {}).get("status_str"),
            "outputs": [value for value in outputs if value],
        }
    return result

def classify(job, live):
    terminal = job["terminal"] or {}
    if job["consumed"]:
        return True, "already-consumed"
    if terminal.get("kind") == "done":
        return False, "render is complete but its Resolve import is still unconsumed"
    if job["intent"].get("state") == "rejected":
        return True, "durable-http-rejection"
    if not live.get("reachable"):
        return False, "ComfyUI is not reachable, so terminal state cannot be proven"
    effective_ids = live.get("effective_prompt_ids") or job["prompt_ids"]
    if not effective_ids:
        return False, "submit intent has no prompt id; the POST-response gap cannot be reconciled"
    states = [live.get("prompts", {}).get(pid, {}).get("state") for pid in effective_ids]
    if any(state in ("running", "pending") for state in states):
        return False, "prompt is still running or queued"
    if all(state == "history" for state in states):
        return True, "all prompt ids have terminal Comfy history"
    return False, "at least one prompt is absent from both queue and history"

def inspect_job(job):
    live = fetch_live(job)
    safe, evidence = classify(job, live)
    return {
        "request_id": job["request_id"],
        "job_dir": job["job_dir"],
        "lane": job["base"],
        "intent_state": job["intent"].get("state"),
        "terminal_kind": job["terminal"].get("kind"),
        "terminal_uncertain": job["terminal"].get("uncertain"),
        "prompt_ids": live.get("effective_prompt_ids") or job["prompt_ids"],
        "consumed": bool(job["consumed"]),
        "live": live,
        "safe_to_resolve": safe,
        "evidence": evidence,
    }

def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8]))
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="GET-only status; writes nothing")
    inspect_parser.add_argument("job_dir")
    resolve_parser = commands.add_parser(
        "resolve", help="write consumed.json only after positive terminal evidence")
    resolve_parser.add_argument("job_dir")
    resolve_parser.add_argument("--confirm-job", required=True)
    args = parser.parse_args(argv)
    try:
        job = load_job(args.job_dir)
        report = inspect_job(job)
        if args.command == "resolve":
            if args.confirm_job != job["request_id"]:
                raise ReconcileError("--confirm-job must exactly equal %s" % job["request_id"])
            if not report["safe_to_resolve"]:
                raise ReconcileError("Refusing to resolve: %s" % report["evidence"])
            consumed_path = pathlib.Path(job["job_dir"]) / "consumed.json"
            if not consumed_path.exists():
                atomic_json(consumed_path, {
                    "request_id": job["request_id"],
                    "kind": "agent-reconciled",
                    "evidence": report["evidence"],
                    "prompt_ids": report["prompt_ids"],
                    "consumed_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                })
            report["resolved"] = True
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except ReconcileError as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
