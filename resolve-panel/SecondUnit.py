

import time


_T_IMPORT = time.perf_counter()
_T_WALL = time.time()

import base64
import copy
import ctypes
import hashlib
import json
import glob
import math
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from ctypes import wintypes




def _self_path():
    try:
        return os.path.abspath(__file__)
    except NameError:
        pass
    deployed = os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "Blackmagic Design", "DaVinci Resolve", "Support",
        "Workflow Integration Plugins", "Second Unit.py")
    if os.path.isfile(deployed):
        return deployed
    if sys.argv and sys.argv[0]:
        return os.path.abspath(sys.argv[0])
    return os.path.join(os.getcwd(), "SecondUnit.py")


_HERE = os.path.dirname(_self_path())
_REPO = os.path.dirname(_HERE)


def _capture_loaded_script_sha256():
    try:
        digest = hashlib.sha256()
        with open(_self_path(), "rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except Exception:
        return ""


_LOADED_SCRIPT_SHA256 = _capture_loaded_script_sha256()




_LOG_LOCK = threading.Lock()
_LOG_PATH = None


def log_path():
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    candidates = []

    override = os.environ.get("SECOND_UNIT_LOG")
    if override:
        candidates.append(override)
    try:
        candidates.append(os.path.join(os.path.dirname(_self_path()), "second-unit-panel.log"))
    except Exception:
        pass
    try:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.getcwd()
        candidates.append(os.path.join(base, "SecondUnit", "second-unit-panel.log"))
    except Exception:
        pass
    for path in candidates:
        try:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with open(path, "a", encoding="utf-8"):
                pass
            _LOG_PATH = path
            return _LOG_PATH
        except Exception:
            continue
    _LOG_PATH = ""
    return _LOG_PATH


def log(message):
    try:
        path = log_path()
        if not path:
            return
        now = time.time()

        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)) + ".%03d" % int((now % 1.0) * 1000)
        line = "%s  %s\n" % (stamp, message)
        with _LOG_LOCK:
            try:
                if os.path.getsize(path) > 5 * 1024 * 1024:
                    rotated = path + ".1"
                    if os.path.exists(rotated):
                        os.remove(rotated)
                    os.replace(path, rotated)
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        pass


def build_id():
    try:
        with open(_self_path(), "rb") as fh:
            data = fh.read()
        return "%s/%d" % (hashlib.sha256(data).hexdigest()[:12], len(data))
    except Exception:
        return "unknown"


USER_CONFIG_NAME = "second-unit.json"
USER_CONFIG_KEYS = ("comfy_url", "comfy_url_finish", "comfy_api_key", "comfy_auth_header", "comfy_headers",
                    "bin", "keyword",
                    "workflows_dir", "cache_dir", "python", "ffmpeg",
                    "output_copy_dir", "detail_graph", "h3_card_builder", "experimental_auto_cards",
                    "expander_provider", "expander_url", "expander_model", "expander_key_file",
                    "expander_timeout", "expander_effort", "expander_chain",
                    "sequence_dir", "own_loop", "own_loop_sleep_ms", "show_unproven", "h3_first_frame_anchor")

USER_CONFIG_PATH_KEYS = ("workflows_dir", "cache_dir", "python", "ffmpeg", "output_copy_dir",
                         "h3_card_builder", "expander_key_file", "sequence_dir")
_USER_CONFIG = {}
_USER_CONFIG_PATH = ""


def user_config_path():
    return os.path.join(os.path.dirname(_self_path()), USER_CONFIG_NAME)


def load_user_config(path=None):
    global _USER_CONFIG, _USER_CONFIG_PATH
    path = path or user_config_path()
    loaded = {}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                log("config: %s is not a JSON object (%s) - ignored, running on built-in defaults"
                    % (path, type(data).__name__))
                data = {}
            base = os.path.dirname(os.path.abspath(path))
            for key, value in data.items():
                key = str(key)
                if key.startswith("_") or value is None or value == "":
                    continue
                if not isinstance(value, (str, int, float, bool)):
                    log("config: %s.%s is not a scalar - ignored" % (os.path.basename(path), key))
                    continue
                value = str(value).strip()
                if not value:
                    continue
                if key in USER_CONFIG_PATH_KEYS:
                    value = os.path.expandvars(os.path.expanduser(value))
                    if not os.path.isabs(value):
                        value = os.path.normpath(os.path.join(base, value))
                loaded[key] = value
            unknown = sorted(k for k in loaded if k not in USER_CONFIG_KEYS)
            if unknown:
                log("config: %s carries keys this build does not read: %s"
                    % (os.path.basename(path), ", ".join(unknown)))
            if loaded:
                log("config: %s -> %s" % (path, ", ".join(sorted(k for k in loaded if k in USER_CONFIG_KEYS))))
    except Exception as exc:
        log("config: %s is unreadable (%s: %s) - ignored, running on built-in defaults"
            % (path, exc.__class__.__name__, exc))
        loaded = {}
    _USER_CONFIG = loaded
    _USER_CONFIG_PATH = path
    return loaded


def user_config_value(key):
    return _USER_CONFIG.get(key) or ""


def _cfg(key, env_name, default):
    value = os.environ.get(env_name) if env_name else None
    if value is not None and str(value).strip():
        return value
    configured = user_config_value(key)
    if configured:
        return configured
    return default


load_user_config()

if user_config_value("ffmpeg") and not (os.environ.get("SECOND_UNIT_FFMPEG") or "").strip():
    os.environ["SECOND_UNIT_FFMPEG"] = user_config_value("ffmpeg")


PRODUCTION_PORTS = (8188,)


def _with_scheme(url):
    url = str(url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = "http://" + url
    return url


COMFY_URL = _with_scheme(_cfg("comfy_url", "SECOND_UNIT_COMFY_URL", "http://127.0.0.1:8190"))

COMFY_URL_FINISH = _with_scheme(_cfg("comfy_url_finish", "SECOND_UNIT_COMFY_URL_FINISH", COMFY_URL))

SEQUENCE_DIR = _cfg("sequence_dir", "SECOND_UNIT_SEQUENCE_DIR", "")

OWN_LOOP = str(_cfg("own_loop", "SECOND_UNIT_OWN_LOOP", "0")).strip().lower() in ("1", "true", "yes", "on")
try:
    OWN_LOOP_SLEEP_S = max(0.005, min(0.05, float(_cfg("own_loop_sleep_ms", "SECOND_UNIT_OWN_LOOP_SLEEP_MS", "20")) / 1000.0))
except (TypeError, ValueError):
    OWN_LOOP_SLEEP_S = 0.02

SHOW_UNPROVEN = str(_cfg("show_unproven", "SECOND_UNIT_SHOW_UNPROVEN", "0")).strip().lower() in ("1", "true", "yes", "on")

H3_CARD_BUILDER = _cfg(
    "h3_card_builder", "SECOND_UNIT_H3_CARD_BUILDER",
    "")


def comfy_is_production(url=None):
    try:
        port = int((url or COMFY_URL).rsplit(":", 1)[-1].split("/")[0])
    except Exception:
        return False
    return port in PRODUCTION_PORTS


def comfy_target_label(url=None):
    u = url or COMFY_URL
    if comfy_is_production(u):
        return "%s  [PRODUCTION - opted in via SECOND_UNIT_COMFY_URL]" % u
    return u
HOME_STAMP = "second-unit-home.json"


def _stamped_home_data():
    return read_home_stamp_data(
        os.path.join(os.path.dirname(_self_path()), HOME_STAMP))


def _stamped_home():
    return (_stamped_home_data() or {}).get("repo")


def read_home_stamp_data(stamp):
    if not os.path.isfile(stamp):
        return {}
    try:
        with open(stamp, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle) or {}
    except Exception as exc:
        log("home stamp at %s is unreadable: %s: %s"
            % (stamp, exc.__class__.__name__, exc))
        return {}
    if not isinstance(data, dict):
        log("home stamp at %s is not an object: %r" % (stamp, data))
        return {}
    validated = dict(data)
    recorded = data.get("repo")
    if recorded and os.path.isdir(recorded):
        validated["repo"] = os.path.abspath(recorded)
    else:
        validated.pop("repo", None)
        if recorded:
            log("home stamp repo %s is not currently a directory" % recorded)
        else:
            log("home stamp at %s names no repo: %r" % (stamp, data))

    recorded_cache = data.get("cache")
    if recorded_cache and os.path.isdir(recorded_cache):
        validated["cache"] = os.path.abspath(recorded_cache)
    else:
        validated.pop("cache", None)
        if recorded_cache:
            log("home stamp cache %s is not currently a directory" % recorded_cache)

    recorded_python = data.get("python")
    if recorded_python and os.path.isfile(recorded_python):
        validated["python"] = os.path.abspath(recorded_python)
    else:
        validated.pop("python", None)
        if recorded_python:
            log("home stamp worker Python %s is not currently a file" % recorded_python)
    return validated


def read_home_stamp(stamp):
    return (read_home_stamp_data(stamp) or {}).get("repo")


def workflow_dir_candidates():
    candidates = []
    chosen = os.environ.get("SECOND_UNIT_WORKFLOWS")
    if chosen:
        candidates.append(("SECOND_UNIT_WORKFLOWS", chosen))
    configured = user_config_value("workflows_dir")
    if configured:
        candidates.append(("second-unit.json workflows_dir", configured))
    home = _stamped_home()
    if home:
        candidates.append(("the repo Deploy-Panel.ps1 installed from",
                           os.path.join(home, "workflows")))
    candidates.append(("beside this file", os.path.join(_REPO, "workflows")))
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    if profile:
        candidates.append(("your home folder", os.path.join(profile, "second-unit", "workflows")))
    return candidates


def find_workflow_dir():
    tried = []
    for why, path in workflow_dir_candidates():
        tried.append("%s: %s" % (why, path))
        if path and os.path.isdir(path):
            log("workflows: using %s (%s)" % (path, why))
            return path
    log("workflows: NOTHING FOUND. Looked in - %s" % "; ".join(tried))
    return workflow_dir_candidates()[0][1]


WORKFLOW_DIR = find_workflow_dir()


def cache_dir_candidates():
    candidates = []
    explicit = os.environ.get("SECOND_UNIT_CACHE")
    if explicit:
        candidates.append(("SECOND_UNIT_CACHE", explicit))
    configured = user_config_value("cache_dir")
    if configured:
        candidates.append(("second-unit.json cache_dir", configured))
    home = _stamped_home_data() or {}
    if home.get("cache"):
        candidates.append(("Deploy-Panel.ps1", home["cache"]))
    if home.get("repo"):
        candidates.append(("the installed repo", os.path.join(home["repo"], ".lab-cache")))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(("LOCALAPPDATA", os.path.join(local, "SecondUnit", "cache")))
    candidates.append(("beside this panel", os.path.join(_REPO, ".lab-cache")))
    return candidates


def find_cache_dir():
    candidates = cache_dir_candidates()
    for why, path in candidates:
        if path and os.path.isdir(path):
            resolved = os.path.abspath(path)
            log("cache: using %s (%s)" % (resolved, why))
            return resolved

    return os.path.abspath(candidates[0][1])


LAB_CACHE = find_cache_dir()
EXTERNAL_WORKER_SCHEMA = 1
EXTERNAL_JOB_FOLDER = "panel-worker-jobs"


BIN_NAME = str(_cfg("bin", "SECOND_UNIT_BIN", "Second Unit Media") or "Second Unit Media").strip()
CLIP_KEYWORD = str(_cfg("keyword", "SECOND_UNIT_KEYWORD", "Second Unit") or "Second Unit").strip()
GPU_TAG = "_render_"
OUTPUT_PREFIX_ROOT = "CMD/SecondUnit/"
DEFAULT_FPS = 24.0

MIN_SECONDS = 0.5
MAX_SECONDS = 30.0


WORLD_WINDOW_MAX_SECONDS = 10.0
STILL_SOURCE_MODES = ("I2V", "FLF2V", "STILLS", "STORYBOARD")
LOOP_DEGRADE_STREAK = 3
WORLD_WINDOW_OVERLAP_SECONDS = 1.0

try:
    H3_WINDOW_MAX_FRAMES = max(124, min(362, int(os.environ.get("SECOND_UNIT_H3_WINDOW_MAX_FRAMES") or 362)))
except ValueError:
    H3_WINDOW_MAX_FRAMES = 362
H3_WINDOW_OVERLAP_FRAMES = 22

WORLD_ASSEMBLY_BASE_ESTIMATE_S = 12.0
WORLD_ASSEMBLY_PER_WINDOW_ESTIMATE_S = 4.0
WORLD_DELIVERY_PER_SOURCE_SECOND_ESTIMATE_S = 1.0
WORLD_AUDIO_BASE_ESTIMATE_S = 8.0

PING_TIMEOUT = 4
SUBMIT_TIMEOUT = 60
VRAM_AUTO_FREE_GB = 4.0
POLL_TIMEOUT = 20
POLL_INTERVAL = 1.5

def _env_number(name, default, cast):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return cast(default)
    try:
        return cast(str(raw).strip())
    except (TypeError, ValueError):
        log("ignored %s=%r (not a number); using %r" % (name, raw, default))
        return cast(default)


def _env_int(name, default):
    return _env_number(name, default, lambda v: int(float(v)))


def _env_float(name, default):
    return _env_number(name, default, float)


WATCHER_MIN_SECONDS = max(
    4 * 60 * 60,
    _env_int("SECOND_UNIT_JOB_TIMEOUT", 14400),
    _env_int("SECOND_UNIT_WATCHER_MIN_SECONDS", 14400),
)
WATCHER_ESTIMATE_MULTIPLIER = max(
    1.0, _env_float("SECOND_UNIT_WATCHER_ESTIMATE_MULTIPLIER", 3.0))
WATCHER_GRACE_SECONDS = max(
    0, _env_int("SECOND_UNIT_WATCHER_GRACE_SECONDS", 1800))
WATCHER_MAX_SECONDS = max(
    WATCHER_MIN_SECONDS,
    _env_int("SECOND_UNIT_WATCHER_MAX_SECONDS", 72 * 60 * 60),
)
RUN_ESTIMATE_S = _env_float("SECOND_UNIT_RUN_ESTIMATE", 180)

MODES = ("T2V", "I2V", "FLF2V", "V2V", "ENVSWAP", "SWAP", "ANGLE", "SEGMENT", "STORYBOARD", "STILLS")
LANES = ("Distilled", "Quality")
FAMILIES = ("LTX25", "LTX23", "MINIMAXH3", "WAN22", "SAM31", "JUGGERNAUTQWEN", "JUGGERNAUT")
H3_ENVSWAP_MASTER_NAME = "SECONDUNIT - H3 - Environment Replacement Depth Locked Master.json"
H3_ENVSWAP_MASTER_LEGACY_NAME = "h3_environment-swap_lock_master_world-relocation.json"

DEFAULT_PRESETS = {
    ("JUGGERNAUT", "STILLS", "Quality"): "SecondUnit-Juggernaut-Environment-Stills-API.json",
    ("JUGGERNAUTQWEN", "STORYBOARD", "Quality"): "SecondUnit-Environment-Storyboard-Quality-API.json",
    ("MINIMAXH3", "ENVSWAP", "Distilled"): "SECONDUNIT - H3 - Environment Replacement Depth Locked Fast.json",
    ("MINIMAXH3", "ENVSWAP", "Quality"): "SECONDUNIT - H3 - Environment Replacement Depth Locked Quality.json",
    ("MINIMAXH3", "V2V", "Distilled"): "SECONDUNIT - H3 - Restyle Footage With Sound Fast.json",
    ("MINIMAXH3", "V2V", "Quality"): "SECONDUNIT - H3 - Restyle Footage With Sound Quality.json",
    ("MINIMAXH3", "SWAP", "Distilled"): "SECONDUNIT - H3 - Character Replacement Depth Locked Fast.json",
    ("MINIMAXH3", "SWAP", "Quality"): "SECONDUNIT - H3 - Character Replacement Depth Locked Quality.json",
    ("MINIMAXH3", "I2V", "Distilled"): "SECONDUNIT - H3 - Animate Still With Sound Fast.json",
    ("MINIMAXH3", "I2V", "Quality"): "SECONDUNIT - H3 - Animate Still With Sound Quality.json",
    ("MINIMAXH3", "FLF2V", "Distilled"): "SECONDUNIT - H3 - First Last Frame Fast.json",
    ("MINIMAXH3", "FLF2V", "Quality"): "SECONDUNIT - H3 - First Last Frame Quality.json",
    ("MINIMAXH3", "ANGLE", "Distilled"): "SECONDUNIT - H3 - Second Angle Fast.json",
    ("MINIMAXH3", "ANGLE", "Quality"): "SECONDUNIT - H3 - Second Angle Quality.json",
    ("MINIMAXH3", "T2V", "Distilled"): "SECONDUNIT - H3 - Text To Video With Sound Fast.json",
    ("LTX25", "I2V", "Distilled"): "SECONDUNIT - LTX 2.5 - Animate Still With Audio Fast.json",
    ("LTX25", "T2V", "Distilled"): "SECONDUNIT - LTX 2.5 - Text To Video With Audio.json",
    ("LTX25", "SWAP", "Distilled"): "SECONDUNIT - LTX 2.5 - Character Replacement.json",
    ("LTX25", "V2V", "Distilled"): "SECONDUNIT - LTX 2.5 - Restyle Footage.json",
}

LEGACY_NAME_MAP_FOR_SELFTEST = {
    "h3_angle_fast_second-angle-on-performance.json": "SECONDUNIT - H3 - Second Angle Fast.json",
    "h3_angle_quality_second-angle-on-performance.json": "SECONDUNIT - H3 - Second Angle Quality.json",
    "h3_environment-swap_depthlock_fast_world-relocation.json": "SECONDUNIT - H3 - Environment Replacement Depth Locked Fast.json",
    "h3_environment-swap_depthlock_quality_world-relocation.json": "SECONDUNIT - H3 - Environment Replacement Depth Locked Quality.json",
    "h3_environment-swap_lock_master_world-relocation.json": "SECONDUNIT - H3 - Environment Replacement Depth Locked Master.json",
    "h3_environment-swap_fast_world-generation.json": "SECONDUNIT - H3 - Environment Replacement Free Camera Fast.json",
    "h3_flf2v_fast_first-last-frame.json": "SECONDUNIT - H3 - First Last Frame Fast.json",
    "h3_flf2v_first-last-frame_quality.json": "SECONDUNIT - H3 - First Last Frame Quality.json",
    "h3_i2v_fast_image-to-video-with-sound.json": "SECONDUNIT - H3 - Animate Still With Sound Fast.json",
    "h3_i2v_quality_image-to-video-with-sound.json": "SECONDUNIT - H3 - Animate Still With Sound Quality.json",
    "h3_swap_lock_fast_character-replace-depth-locked.json": "SECONDUNIT - H3 - Character Replacement Depth Locked Fast.json",
    "h3_swap_lock_quality_character-replace-depth-locked.json": "SECONDUNIT - H3 - Character Replacement Depth Locked Quality.json",
    "h3_swap_quality_character-replace.json": "SECONDUNIT - H3 - Character Replacement Quality.json",
    "h3_t2v_fast_text-to-video-with-sound.json": "SECONDUNIT - H3 - Text To Video With Sound Fast.json",
    "h3_v2v_draft_turbo4step_reference-video-with-sound.json": "SECONDUNIT - H3 - Restyle Footage With Sound Draft.json",
    "h3_v2v_fast_reference-video-with-sound.json": "SECONDUNIT - H3 - Restyle Footage With Sound Fast.json",
    "h3_v2v_quality_reference-video-with-sound.json": "SECONDUNIT - H3 - Restyle Footage With Sound Quality.json",
    "ltx25_i2v_distilled_camera-arcshot.json": "SECONDUNIT - LTX 2.5 - Animate Still Camera Arc Shot Fast.json",
    "ltx25_i2v_distilled_image-to-video-with-audio.json": "SECONDUNIT - LTX 2.5 - Animate Still With Audio Fast.json",
    "ltx25_swap_character-replace.json": "SECONDUNIT - LTX 2.5 - Character Replacement.json",
    "ltx25_t2v_text-to-video-with-audio.json": "SECONDUNIT - LTX 2.5 - Text To Video With Audio.json",
    "ltx25_v2v_restyle.json": "SECONDUNIT - LTX 2.5 - Restyle Footage.json",
    "ltx25_pixel-spatial-x2_finish_api.json": "SECONDUNIT - LTX 2.5 - Detail Finish Pixel Spatial 2x.json",
    "sam31_segment_roto-matte.json": "SECONDUNIT - SAM 3.1 - Segment Roto Matte.json",
    "wan22_i2v_quality_5b.json": "SECONDUNIT - WAN 2.2 - Animate Still 5B Quality.json",
}
RESOLUTIONS = ("720P", "1080P", "4K")


MODE_LABELS = (
    ("T2V", "Text to video"),
    ("I2V", "Animate a still"),
    ("FLF2V", "First and last frame"),
    ("V2V", "Restyle footage"),
    ("ENVSWAP", "World Generation"),
    ("SWAP", "Replace the performer"),
    ("ANGLE", "Second angle"),
    ("SEGMENT", "Cut a matte"),
    ("STORYBOARD", "Environment storyboard"),
    ("STILLS", "Environment still"),
)
LANE_LABELS = (("Distilled", "Fast"), ("Quality", "Best quality"))
FAMILY_LABELS = (
    ("LTX25", "LTX 2.5"),
    ("LTX23", "LTX 2.3"),
    ("MINIMAXH3", "MiniMax H3"),
    ("WAN22", "WAN 2.2"),
    ("SAM31", "SAM 3.1"),
    ("JUGGERNAUTQWEN", "Juggernaut + Qwen"),
    ("JUGGERNAUT", "Juggernaut XL v9"),
)
RESOLUTION_LABELS = (("720P", "720p export"), ("1080P", "1080p export"), ("4K", "4K export (LTX only)"))
OUTPUT_SIZES = {"720P": (1280, 720), "1080P": (1920, 1080), "4K": (3840, 2160)}

DETAIL_UPSCALE_RELATIVE = _cfg(
    "detail_graph", "SECOND_UNIT_DETAIL_GRAPH",
    os.path.join("ltx-2.5", "finish", "ltx25_pixel-spatial-x2_finish_api.json")).replace("/", os.sep)
DETAIL_UPSCALE_PROMPT = (
    "A continuous photographic rendering of the supplied source video. Retain the same "
    "subjects, identity, facial and body proportions, pose, wardrobe, actions and timing. "
    "Keep the source camera, framing, perspective, geometry, lighting direction, exposure "
    "and colors. Refine only existing visible photographic materials and natural texture, "
    "without inventing pores, objects or unseen facial features. Preserve back-facing views "
    "and the source motion. No beauty smoothing, plastic skin, exaggerated texture, crunchy "
    "sharpening, relighting, camera changes or new cuts."
)
# Distilled CFG1 does not use negative conditioning; retain the tested empty negative.
DETAIL_UPSCALE_NEGATIVE = ""
DETAIL_UPSCALE_SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
DETAIL_UPSCALE_LORA = "ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors"
LTX_WORLD_REQUIRED_NEGATIVE = (
    "reference sheet, contact sheet, image grid, collage, split screen, tiled panels, "
    "multiple views, white catalog background, isolated clothing display, visible control "
    "image, duplicated performer"
)
V2V_RETENTION_LABELS = (
    ("LOCK_ALL", "Lock subject + motion + camera"),
    ("LOCK_PERFORMANCE", "Lock motion + camera"),
    ("MOTION_ONLY", "Motion timing only"),
)
V2V_INGREDIENT_LABELS = (
    ("SUBJECT", "Subject / identity"),
    ("WARDROBE", "Wardrobe"),
    ("PRODUCT", "Product / prop"),
    ("LOOK", "Look / style"),
    ("ENVIRONMENT", "Environment"),
)
LTX25_INGREDIENT_LORA = (
    "LTX2.3\\ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"
)
V2V_EDIT_LABELS = (
    ("BALANCED", "Balanced edit"),
    ("SUBTLE", "Subtle edit"),
    ("STRONG", "Strong edit"),
)

V2V_LOCK_TEXT = {
    "LOCK_ALL": "motion, timing, camera movement, framing, subject identity, background, and lighting continuity",
    "LOCK_PERFORMANCE": "motion, timing, camera movement, framing, pose sequence, and physical performance",
    "MOTION_ONLY": "motion timing, action beats, and camera trajectory",
}
V2V_INGREDIENT_TEXT = {
    "SUBJECT": "subject identity and facial appearance",
    "WARDROBE": "wardrobe and wearable details",
    "PRODUCT": "product or prop appearance",
    "LOOK": "visual look, material treatment, and color style",
    "ENVIRONMENT": "environment and production design",
}
V2V_EDIT_TEXT = {
    "SUBTLE": "Make the smallest visible change needed and keep the source dominant.",
    "BALANCED": "Make the requested change clearly while retaining the locked source traits.",
    "STRONG": "Prioritize the requested transformation while retaining only the locked source traits.",
}


def comfy_short_target(url=None):
    target = (url or COMFY_URL).rstrip("/")
    try:
        parsed = urllib.parse.urlparse(target)
        host = parsed.hostname or ""
        port = parsed.port
        if not port:
            return host or "?"
        if host in ("127.0.0.1", "localhost", "::1"):
            return str(port)
        return "%s:%d" % (host, port)
    except Exception:
        return "?"


def mmss(seconds):
    try:
        seconds = int(max(0, seconds))
    except Exception:
        return "-"
    return "%d:%02d" % (seconds // 60, seconds % 60)


def watcher_duration(seconds):
    try:
        seconds = int(max(0, seconds))
    except Exception:
        return "-"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return "%dh %02dm" % (hours, minutes)
    return "%dm" % minutes


def watcher_deadline_seconds(estimated_seconds):
    try:
        estimate = max(0.0, float(estimated_seconds or 0.0))
    except Exception:
        estimate = 0.0
    derived = estimate * WATCHER_ESTIMATE_MULTIPLIER + WATCHER_GRACE_SECONDS
    return int(math.ceil(min(WATCHER_MAX_SECONDS, max(WATCHER_MIN_SECONDS, derived))))


def watcher_timeout_message(prompt_id, target, deadline_seconds):
    return (
        "Watcher deadline %s reached for prompt %s on %s. ComfyUI may still be running; "
        "Second Unit did NOT cancel it and will NOT retry it automatically. The durable "
        "job remains uncertain and Generate stays locked until it is reconciled."
        % (watcher_duration(deadline_seconds), str(prompt_id or "?")[:8], target)
    )


ESTIMATE_SECONDS_121 = {
    "LTX23": 300.0,

    "LTX25": 150.0,
    "MINIMAXH3": 540.0,
    "WAN22": 600.0,
    "SAM31": 150.0,
}
MODE_ESTIMATE_FACTOR = {
    "T2V": 0.90, "I2V": 1.00, "FLF2V": 1.08,
    "V2V": 1.12, "ENVSWAP": 1.25, "SWAP": 1.18, "SEGMENT": 0.75,
}


H3_QUALITY_TEMPORAL_EXPONENT = 2.256126


def is_ltx_pixel_detail_graph(graph):
    for node in (graph or {}).values():
        inputs = (node or {}).get("inputs") or {}
        name = str(inputs.get("lora_name") or "").lower()
        if "pixel-spatial-upscaler" in name:
            return True
    return False


def apply_detail_realism_settings(graph):
    """Shared generative finish contract, independent of the upstream family."""
    if not is_ltx_pixel_detail_graph(graph):
        raise SecondUnitError("LTX detail requires the pixel-spatial x2 IC-LoRA graph.")
    adapters = [n for n in graph.values() if "pixel-spatial-upscaler" in str((n.get("inputs") or {}).get("lora_name", ""))]
    if len(adapters) != 1 or os.path.basename(adapters[0]["inputs"]["lora_name"].replace("\\", "/")) != DETAIL_UPSCALE_LORA:
        raise SecondUnitError("LTX detail requires the genuine LTX 2.5 pixel-spatial x2 adapter; older adapters are incompatible.")
    adapters[0]["inputs"]["strength_model"] = 1.0
    for node in graph.values():
        inputs = node.get("inputs") or {}
        kind = node.get("class_type")
        if kind == "LTXAddVideoICLoRAGuide": inputs["strength"] = 1.0
        elif kind == "CFGGuider": inputs["cfg"] = 1.0
        elif kind == "ManualSigmas": inputs["sigmas"] = DETAIL_UPSCALE_SIGMAS
    positive, negative = find_prompt_targets(graph)
    graph[positive[0]]["inputs"][positive[1]] = DETAIL_UPSCALE_PROMPT
    if negative: graph[negative[0]]["inputs"][negative[1]] = DETAIL_UPSCALE_NEGATIVE


def configure_detail_padding(graph, frames):
    """Pad only the last source image to8n+1; trim decoded output tooriginal count."""
    roles = {(n.get("_meta") or {}).get("second_unit_role"): str(i)
             for i,n in graph.items() if (n.get("_meta") or {}).get("second_unit_role")}
    needed = ("detail_source", "detail_tail", "detail_repeat", "detail_batch", "detail_guide", "detail_trim")
    if not all(role in roles for role in needed):
        raise SecondUnitError("LTX detail graph lacks exact source-frame padding/trim wiring.")
    padded = 1 + int(math.ceil(max(0, frames - 1) / 8.0)) * 8
    graph[roles["detail_source"]]["inputs"]["frame_load_cap"] = frames
    graph[roles["detail_tail"]]["inputs"].update(batch_index=frames - 1, length=1)
    graph[roles["detail_repeat"]]["inputs"]["amount"] = max(1, padded - frames)
    source = [roles["detail_batch"], 0] if padded != frames else [roles["detail_source"], 0]
    guide = graph[roles["detail_guide"]]["inputs"]
    link = guide.get("image")
    snap = graph.get(str(link[0]), {}) if is_link(link) else {}
    if (snap.get("_meta") or {}).get("title") == "SECOND UNIT LTX GUIDE 32-GRID SNAP":
        snap["inputs"]["image"] = source
    else:
        guide["image"] = source
    for node in graph.values():
        if node.get("class_type") == "LTXVEmptyLatentAudio": node["inputs"]["frames_number"] = padded
    graph[roles["detail_trim"]]["inputs"].update(batch_index=0, length=frames)
    return padded


def estimate_detail_upscale_seconds(frames, resolution="1080P", graph=None):
    if graph is not None and any(
            isinstance(node, dict) and "ltx-2.5" in str((node.get("inputs") or {}).get("unet_name") or "").lower()
            for node in graph.values()):

        dims = graph_dimensions(graph) or (2048, 1152)
        pixel_factor = float(dims[0] * dims[1]) / float(2048 * 1152)
        return max(90.0, 60.0 + 240.0 * max(1.0, float(frames or 73)) / 73.0 * pixel_factor)

    value = max(75.0, 291.9 * max(1.0, float(frames or 1)) / 56.0)
    return value if resolution == "1080P" else value * 0.97


def estimate_render_seconds(family, mode, resolution, frames, graph=None):
    if family in ("LTX23", "LTX25") and isinstance(graph, dict) and is_ltx_pixel_detail_graph(graph):
        return estimate_detail_upscale_seconds(frames, resolution, graph=graph)
    if family == "MINIMAXH3" and isinstance(graph, dict):
        steps = max([
            int((node.get("inputs") or {}).get("steps"))
            for node in graph.values()
            if isinstance(node, dict)
            and isinstance((node.get("inputs") or {}).get("steps"), (int, float))
        ] or [20])
        generation_dims = []
        for node in graph.values():
            if not isinstance(node, dict) or node.get("class_type") not in (
                    "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo",
                    "EmptyMiniMaxH3LatentAV"):
                continue
            inputs = node.get("inputs") or {}
            if isinstance(inputs.get("width"), (int, float)) \
                    and isinstance(inputs.get("height"), (int, float)):
                generation_dims.append((float(inputs["width"]), float(inputs["height"])))
        width, height = max(generation_dims, key=lambda pair: pair[0] * pair[1]) \
            if generation_dims else (864.0, 480.0)
        megapixels = width * height / 1000000.0


        has_lora = any(
            isinstance(node, dict)
            and str(node.get("class_type") or "").startswith(("MiniMaxH3TurboLoRA", "LoraLoader"))
            for node in graph.values())
        has_sage = any(
            isinstance(node, dict)
            and str(node.get("class_type") or "").startswith(
                ("PathchSageAttentionKJ", "MiniMaxH3MemoryEfficientSageAttentionPatch",
                 "MiniMaxH3SageAttention"))
            for node in graph.values())
        has_reference_video = any(
            isinstance(node, dict)
            and node.get("class_type") == "MiniMaxH3ReferenceToVideo"
            for node in graph.values())
        pixel_factor = megapixels / (1344 * 768 / 1000000.0)
        ref_video_count = 0
        has_fade = False
        for node in graph.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "MiniMaxH3ReferenceToVideo":
                ref_video_count = max(ref_video_count, sum(
                    1 for key, value in (node.get("inputs") or {}).items()
                    if key.startswith("ref_videos.") and is_link(value)))
            elif node.get("class_type") == "MiniMaxH3ReferenceVideoFadeModelPatch":
                has_fade = True
        if has_reference_video:

            if has_lora:
                base_step = 62.0
            elif ref_video_count >= 2:
                base_step = 67.0
            elif has_fade:
                base_step = 57.0
            else:
                base_step = 41.0 if has_sage else 51.7
            per_step = base_step * (max(5.0, float(frames or 141)) / 141.0) ** 1.5 * pixel_factor
            fixed = 60.0
        else:
            per_step = ((25.0 if has_lora else (14.5 if has_sage else 18.5))
                        * (max(5.0, float(frames or 124)) / 124.0) ** 1.5 * pixel_factor)
            fixed = 25.0
        delivery = 15.0 if resolution == "1080P" else 0.0
        return max(30.0, fixed + steps * per_step + delivery)
    base = ESTIMATE_SECONDS_121.get(family, RUN_ESTIMATE_S)
    frame_factor = max(0.2, float(frames or 121) / 121.0)
    output_factor = 1.08 if resolution == "1080P" else 1.0
    return max(15.0, base * frame_factor * MODE_ESTIMATE_FACTOR.get(mode, 1.0)
               * output_factor)



JOB_CHIPS = (
    ("READY",       "ST_CHIP_IDLE"),
    ("CHECKING",    "ST_CHIP_BUSY"),
    ("QUEUED",      "ST_CHIP_BUSY"),
    ("STAGING",     "ST_CHIP_BUSY"),
    ("UPLOADING",   "ST_CHIP_BUSY"),
    ("RENDERING",   "ST_CHIP_RUN"),
    ("FETCHING",    "ST_CHIP_BUSY"),
    ("DELIVERING",  "ST_CHIP_BUSY"),
    ("VERIFYING HQ", "ST_CHIP_BUSY"),
    ("CHECKING FILE", "ST_CHIP_BUSY"),
    ("VIDEO 1 AUDIO", "ST_CHIP_BUSY"),
    ("IMPORTING",   "ST_CHIP_BUSY"),
    ("ON TIMELINE", "ST_CHIP_OK"),
    ("IN BIN",      "ST_CHIP_WARN"),
    ("LIVE UPDATES OFF", "ST_CHIP_WARN"),
    ("STOPPED",     "ST_CHIP_WARN"),
    ("REFUSED",     "ST_CHIP_BAD"),
    ("FAILED",      "ST_CHIP_BAD"),
)


STICKY_STATES = ("REFUSED", "FAILED", "STOPPED")


def job_chip(key):
    for name, sheet in JOB_CHIPS:
        if name == key:
            return key, globals()[sheet]
    return key, ST_CHIP_IDLE


def server_chip(url=None, ok=None, version=None, error=None, probed=True):
    target = (url or COMFY_URL)
    short = comfy_short_target(target)
    production = comfy_is_production(target)
    if ok is None:
        return u"\u25cf %s  checking..." % short, ST_CHIP_WAIT
    if not ok:
        if production:
            return u"\u25cf %s  PRODUCTION - not running" % short, ST_CHIP_BAD
        return u"\u25cf %s  not running" % short, ST_CHIP_BAD
    if error:
        return u"\u25cf %s  %s" % (short, error), ST_CHIP_WARN
    if production:
        return u"\u25cf %s  PRODUCTION" % short, ST_CHIP_PROD
    if version:
        return u"\u25cf %s  live \u00b7 ComfyUI %s" % (short, version), ST_CHIP_OK
    return u"\u25cf %s  live" % short, ST_CHIP_OK


def _label_to_key(text, pairs, default):
    text = (text or "").strip()
    for key, label in pairs:
        if text in (label, key):
            return key
    return default


C_BG             = "#030304"
C_CARD           = "#09090C"
C_INPUT          = "#0A0A0D"
C_LINE           = "#2A2A2B"
C_TEXT           = "#E9E9E3"
C_DIM            = "#ADADA7"
C_META           = "#777A70"
C_ACCENT         = "#D9FF52"
C_ACCENT2        = "#EBFF9A"
C_RENEGADE_BLUE  = "#3047FF"
C_BLUE_TEXT      = "#909CFF"
C_RENEGADE_RED   = "#D83B2D"
C_EMBER          = "#FF7037"
C_OK             = C_ACCENT
C_WARN           = "#FFB18E"
C_BAD            = "#FF9A82"
C_BAD_BG         = "#3A1210"
C_INK            = "#080A04"


def wcag_contrast(fg, bg):
    def luminance(value):
        value = value.lstrip("#")
        channels = []
        for index in (0, 2, 4):
            part = int(value[index:index + 2], 16) / 255.0
            channels.append(part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)



PALETTE_CONTRACT = (
    (C_TEXT,   C_BG,     7.0, "body text"),
    (C_DIM,    C_BG,     4.5, "secondary text"),
    (C_META,   C_BG,     3.0, "tracked label"),
    (C_TEXT,   C_INPUT,  7.0, "typed value in a field"),
    (C_DIM,    C_INPUT,  4.5, "placeholder-weight text"),
    (C_BAD,       C_BG,            4.5, "failure text"),
    (C_WARN,      C_BG,            4.5, "warning text"),
    (C_OK,        C_CARD,          4.5, "success text"),
    (C_BLUE_TEXT, C_BG,            4.5, "active-state blue"),
    (C_INK,       C_ACCENT,        4.5, "Renegade acid action"),
    (C_BAD,       C_BAD_BG,        4.5, "failure chip"),
    (C_TEXT,      C_RENEGADE_BLUE, 4.5, "production chip"),
)

ST_WINDOW = "background-color: %s; color: %s;" % (C_BG, C_TEXT)


RADIUS_CTRL = 1
RADIUS_CHIP = 1

ST_CARD = ("background-color: %s; border: 1px solid %s; padding: 8px;"
           % (C_CARD, C_LINE))
ST_HEADER = ("background-color: %s; border: 1px solid %s; padding: 9px 11px;"
             % (C_CARD, C_LINE))
ST_ACCENT_BAR = "background-color: %s; border: none;" % C_ACCENT
ST_SECTION = ("background-color: transparent; border: none; border-top: 1px solid %s;"
              " padding-top: 5px;" % C_LINE)
ST_SECTION_NUMBER = ("color: %s; font-weight: 900; letter-spacing: 1.5px;"
                     " background: transparent; border: none;" % C_ACCENT)
ST_SECTION_TITLE = ("color: %s; font-family: 'Bahnschrift SemiCondensed', 'Arial Narrow';"
                    " font-size: 15px; font-weight: 900; font-style: italic;"
                    " letter-spacing: 1.5px; background: transparent; border: none;"
                    % C_TEXT)
ST_SECTION_META = ("color: %s; font-size: 10px; font-weight: 700; letter-spacing: 1.3px;"
                   " background: transparent; border: none;" % C_META)


ST_RULE = "background-color: %s; border: none;" % C_LINE


ST_ROWLABEL = ("color: %s; letter-spacing: 1.8px; font-weight: 800; background: transparent;"
               " border: none;" % C_META)
ST_EYEBROW = ST_ROWLABEL

ST_LABEL = "color: %s; background: transparent; border: none;" % C_DIM
ST_SUBTLE = "color: %s; background: transparent; border: none;" % C_TEXT
ST_META = "color: %s; background: transparent; border: none;" % C_META

ST_INPUT = (
    "QLineEdit, QTextEdit {"
    " background-color: %s; color: %s; border: 1px solid %s; border-radius: %dpx;"
    " padding: 5px 8px; selection-background-color: %s; selection-color: %s; }"
    "QLineEdit:focus, QTextEdit:focus { border: 1px solid %s; }"
    % (C_INPUT, C_TEXT, C_LINE, RADIUS_CTRL, C_ACCENT, C_INK, C_ACCENT)
)

ST_COMBO = (
    "QComboBox { background-color: %s; color: %s; border: 1px solid %s; border-radius: %dpx;"
    " padding: 5px 8px; }"
    "QComboBox:hover { border: 1px solid %s; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView { background-color: %s; color: %s;"
    " selection-background-color: %s; selection-color: %s; border: 1px solid %s; }"
    % (C_INPUT, C_TEXT, C_LINE, RADIUS_CTRL, C_ACCENT, C_INPUT, C_TEXT,
       C_ACCENT, C_INK, C_LINE)
)


ST_BTN_PRIMARY = (
    "QPushButton { background-color: %s; color: %s; border: none; border-radius: %dpx;"
    " font-weight: 700; letter-spacing: 2.4px; padding: 9px 18px; }"
    "QPushButton:hover { background-color: %s; }"
    "QPushButton:pressed { background-color: %s; }"
    "QPushButton:disabled { background-color: #2A2A2E; color: #8E8E95; }"
    % (C_ACCENT, C_INK, RADIUS_CTRL, C_ACCENT2, C_DIM)
)

ST_BTN_GHOST = (
    "QPushButton { background-color: transparent; color: %s; border: 1px solid %s;"
    " border-radius: %dpx; letter-spacing: 1.2px; padding: 7px 10px; }"
    "QPushButton:hover { color: %s; border: 1px solid %s; }"
    "QPushButton:pressed { background-color: %s; }"
    "QPushButton:disabled { color: %s; border: 1px solid #212125; }"
    % (C_DIM, C_LINE, RADIUS_CTRL, C_ACCENT, C_ACCENT, C_CARD, C_META)
)

ST_CHECK = (
    "QCheckBox { color: %s; background: transparent; border: none; spacing: 7px; }"
    "QCheckBox::indicator { width: 12px; height: 12px; border: 1px solid %s;"
    " border-radius: %dpx; background: %s; }"
    "QCheckBox::indicator:checked { background: %s; border: 1px solid %s; }"
    % (C_DIM, C_LINE, RADIUS_CHIP, C_INPUT, C_ACCENT, C_ACCENT)
)

ST_PROGRESS = (
    "QSlider::groove:horizontal { height: 2px; background: %s; border-radius: 1px; }"
    "QSlider::sub-page:horizontal { background: %s; border-radius: 1px; }"
    "QSlider::handle:horizontal { width: 0px; height: 0px; background: transparent; }"
    % (C_LINE, C_ACCENT)
)


def _status_sheet(colour, rule_colour=None):
    return ("color: %s; background-color: %s; border: none; border-left: 2px solid %s;"
            "padding: 7px 10px;" % (colour, C_CARD, rule_colour or colour))


ST_STATUS      = _status_sheet(C_DIM)
ST_STATUS_OK   = _status_sheet(C_OK)
ST_STATUS_WARN = _status_sheet(C_WARN, C_EMBER)
ST_STATUS_FAIL = _status_sheet(C_BAD, C_RENEGADE_RED)

STATUS_SHEETS = {"info": ST_STATUS, "ok": ST_STATUS_OK,
                 "warn": ST_STATUS_WARN, "fail": ST_STATUS_FAIL}


def _chip_sheet(colour, background="transparent", border=None):
    return ("color: %s; background-color: %s; border: 1px solid %s; border-radius: %dpx;"
            "padding: 2px 7px; font-weight: 700; letter-spacing: 1.5px;"
            % (colour, background, border or colour, RADIUS_CHIP))


ST_CHIP_WAIT = _chip_sheet(C_META, "transparent", C_LINE)
ST_CHIP_IDLE = _chip_sheet(C_META, "transparent", C_LINE)
ST_CHIP_BUSY = _chip_sheet(C_BLUE_TEXT, "transparent", C_RENEGADE_BLUE)

ST_CHIP_RUN  = _chip_sheet(C_ACCENT, "transparent", C_ACCENT)
ST_CHIP_OK   = _chip_sheet(C_ACCENT, "transparent", C_ACCENT)
ST_CHIP_WARN = _chip_sheet(C_WARN, "transparent", C_EMBER)
ST_CHIP_BAD  = _chip_sheet(C_BAD, C_BAD_BG, C_RENEGADE_RED)
ST_CHIP_PROD = _chip_sheet(C_TEXT, C_RENEGADE_BLUE, C_RENEGADE_BLUE)


MODE_TOKENS = {
    "T2V": ("t2v", "t2va", "text2video", "txt2vid", "texttovideo"),
    "I2V": ("i2v", "i2va", "img2video", "image2video", "imagetovideo"),

    "FLF2V": ("fl2v", "fl2va", "flf2v", "firstlast", "firsttolast", "keyframe2keyframe"),
    "V2V": ("v2v", "v2va", "vid2vid", "video2video", "videotovideo"),
    "ENVSWAP": ("envswap", "environmentswap", "environmentreplace", "replaceenvironment",
                "setswap", "backgroundswap"),
    "SWAP": ("ref2va", "ref2v", "r2v", "swap", "charreplace", "characterreplace",
             "outfitswap", "reference2video"),

    "ANGLE": ("angle", "secondangle", "newangle", "reangle", "coverage"),
    "SEGMENT": ("segment", "segmentation", "seg", "matte", "rotoscope"),
}

MODE_MATCH_ORDER = ("SEGMENT", "ENVSWAP", "ANGLE", "SWAP", "FLF2V", "V2V", "I2V", "T2V")
LANE_TOKENS = {

    "Distilled": ("distilled", "distill", "fast", "turbo",
                  "turbo4step", "4step", "turbo4",
                  "turbo6step", "6step", "turbo6",
                  "turbo8step", "8step", "turbo8", "draft", "previz"),
    "Quality": ("quality", "hq", "full", "dev", "master"),
}

NON_FRAME_LENGTH_CLASSES = ("ImageFromBatch", "LatentFromBatch")


FRAME_INPUTS = ("length", "frames_number", "frame_load_cap", "image_load_cap", "num_frames", "video_frames", "frame_count")

FPS_INPUTS = ("fps", "frame_rate", "force_rate")
SEED_INPUTS = ("noise_seed", "seed")

VIDEO_SOURCE_INPUTS = (("VHS_LoadVideo", "video"), ("VHS_LoadVideoPath", "video"), ("LoadVideo", "file"))
IMAGE_SOURCE_INPUTS = (("LoadImage", "image"), ("LoadImageOutput", "image"))

SOURCE_FORMAT_LABELS = (
    ("PNGSEQ", "PNG sequence (lossless frames)"),
    ("VIDEO", "Video proxy (H.264)"),
)

FRAME_SEQUENCE_MODES = ("V2V", "ENVSWAP", "SWAP", "ANGLE", "SEGMENT")
FRAMES_CACHE_VERSION = 1
SEQUENCE_FRAME_EXTENSIONS = (".png", ".tif", ".tiff", ".exr", ".dpx", ".jpg", ".jpeg", ".bmp", ".webp")
SEQUENCE_AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac", ".m4a", ".mp3")

SOURCE_REQUIRED_MODES = ("I2V", "FLF2V", "V2V", "ENVSWAP", "SWAP", "ANGLE", "SEGMENT")

IMAGE_SOURCE_MODES = ("I2V", "FLF2V")


FORBIDDEN_NODES = (
    "GemmaAPITextEncode",
    "MinimaxHailuo03TextToVideoNode",
    "GeminiNode",
    "GeminiInputFiles",
    "TextGenerateLTX2Prompt",
)

UNREACHABLE_MSG = (
    "ComfyUI is NOT reachable at {base}. Start your ComfyUI server (or set "
    "SECOND_UNIT_COMFY_URL to the right address) and press Reload. Nothing was submitted."
)


class SecondUnitError(Exception):
    pass


class ComfyTimeout(SecondUnitError):
    pass


class ComfyUnreachable(SecondUnitError):
    pass


class ComfySubmitRejected(SecondUnitError):
    pass





def derive_frames(fps, seconds):
    fps = float(fps)
    seconds = float(seconds)
    if fps <= 0:
        raise SecondUnitError("fps must be positive (graph reported %r)" % (fps,))
    if seconds <= 0:
        raise SecondUnitError("duration must be positive (got %r)" % (seconds,))
    return 1 + int(math.floor(fps * seconds / 8.0)) * 8


def derive_frames_h3(fps, seconds):
    fps = float(fps)
    seconds = float(seconds)
    if fps <= 0:
        raise SecondUnitError("fps must be positive (graph reported %r)" % (fps,))
    if seconds <= 0:
        raise SecondUnitError("duration must be positive (got %r)" % (seconds,))
    wanted = int(math.floor(fps * seconds + 1e-6))
    if wanted <= 5:
        return 5
    return 5 + ((wanted - 5) // 17) * 17


def parse_seconds(text):
    raw = (text or "").strip()
    if not raw:
        raise SecondUnitError("Duration is empty. Enter seconds, e.g. 5")
    try:
        value = float(raw)
    except ValueError:
        raise SecondUnitError("Duration %r is not a number. Enter seconds, e.g. 5" % (raw,))
    if value < MIN_SECONDS or value > MAX_SECONDS:
        raise SecondUnitError(
            "Duration %g s is out of range (%g - %g s)." % (value, MIN_SECONDS, MAX_SECONDS)
        )
    return value


def duration_guidance(family, seconds):
    try:
        seconds = float(seconds)
    except Exception:
        return ""
    if family == "MINIMAXH3" and seconds < 4.0:
        return "H3 prefers 4-15s"
    if family == "MINIMAXH3" and seconds > 15.0:
        return "H3 prefers 4-15s; long clips are heavier"
    return ""


def parse_seed(text):
    raw = (text or "").strip()
    if not raw or raw == "-1":
        return None
    if raw.lower() in ("r", "rand", "random"):
        value = random_seed()
        log("seed: %s requested -> random seed %d" % (raw, value))
        return value
    try:
        value = int(raw)
    except ValueError:
        raise SecondUnitError("Seed %r is not an integer. Leave it blank (or -1) to keep the graph's seed, "
                              "type a whole number to pin it, or 'random' for a fresh seed." % (raw,))
    if value < 0:
        value = random_seed()
        log("seed: %s requested -> random seed %d (ComfyUI samplers need 0 or above)" % (raw, value))
    return value


def random_seed():
    return int(uuid.uuid4().int % (2 ** 32))


def name_tokens(name):
    stem = os.path.basename(name)
    stem = re.sub(r"\.json$", "", stem, flags=re.I)
    return [t for t in re.split(r"[^a-z0-9]+", stem.lower()) if t]


def classify_graph_content(graph):
    if not isinstance(graph, dict) or isinstance(graph.get("nodes"), list):
        return None
    classes = set()
    for node in graph.values():
        if isinstance(node, dict):
            classes.add(str(node.get("class_type") or ""))
    if not classes:
        return None
    if any(c.startswith("SAM3") for c in classes):
        return "SEGMENT"
    if classes & {name for name, _key in VIDEO_SOURCE_INPUTS}:
        return "V2V"
    if classes & {name for name, _key in IMAGE_SOURCE_INPUTS} or any("ImageToVideo" in c for c in classes):
        return "I2V"
    return "T2V"


def classify_graph_name(name, graph=None):
    tokens = set(name_tokens(name))
    if "stills" in tokens and "environment" in tokens:
        return "STILLS", "Quality"
    if "storyboard" in tokens and "environment" in tokens:
        return "STORYBOARD", "Quality"

    replace_words = ("swap", "replace", "replacement")
    mode = None
    if (("environment" in tokens or "background" in tokens or "set" in tokens)
            and any(w in tokens for w in replace_words)):
        mode = "ENVSWAP"
    elif (any(w in tokens for w in ("character", "performer", "outfit", "wardrobe"))
            and any(w in tokens for w in replace_words)):
        mode = "SWAP"
    elif "first" in tokens and "last" in tokens:
        mode = "FLF2V"
    elif "angle" in tokens:
        mode = "ANGLE"
    elif "restyle" in tokens:
        mode = "V2V"
    elif "text" in tokens and "video" in tokens:
        mode = "T2V"
    elif "animate" in tokens and "still" in tokens:
        mode = "I2V"
    if mode is None:
        for candidate in MODE_MATCH_ORDER:
            if tokens & set(MODE_TOKENS[candidate]):
                mode = candidate
                break
    if mode is None and graph is not None:
        mode = classify_graph_content(graph)
    lane = None
    for candidate in LANES:
        if tokens & set(LANE_TOKENS[candidate]):
            lane = candidate
            break
    return mode, lane


def infer_graph_family(path, graph=None):
    haystack = str(path or "").replace("\\", "/").lower()
    refs = " ".join(value.lower() for _nid, _cls, _key, value in graph_model_refs(graph or {}))
    text = haystack + " " + refs
    if "juggernaut" in text and "qwen_image_edit_2511" in text:
        return "JUGGERNAUTQWEN"
    if "juggernaut" in text:
        return "JUGGERNAUT"
    if "ltx-2.5" in text or "ltx25" in text or "ltxv-2b-2.5" in text:
        return "LTX25"
    if "ltx-2.3" in text or "ltx23" in text or "ltx-video-2b-v0.9" in text:
        return "LTX23"
    if "minimax-h3" in text or "minimax_h3" in text or "/h3_" in text:
        return "MINIMAXH3"
    if "wan2.2" in text or "wan-2.2" in text or "/wan" in text or "wan_" in text:
        return "WAN22"
    if "sam-3.1" in text or "sam31" in text or "sam3" in text:
        return "SAM31"
    return None


def stamp_paths_for(graph_path):
    stem = re.sub(r"\.json$", "", graph_path, flags=re.I)
    return [graph_path + ".verified.json", stem + ".verified.json"]


def read_stamp(graph_path):
    for candidate in stamp_paths_for(graph_path):
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8-sig") as handle:
                stamp = json.load(handle)
        except Exception:
            return None
        if isinstance(stamp, dict):

            expected = str(stamp.get("graph_sha256") or "")
            if expected:
                try:
                    actual = _sha256_file(graph_path)
                except OSError:
                    actual = ""
                if actual != expected:
                    log("stamp ignored for %s: graph edited after stamping (sha %s != %s)"
                        % (os.path.basename(graph_path), actual[:12], expected[:12]))
                    return None
            stamp["_stamp_path"] = candidate
            return stamp
    return None


class GraphEntry(object):

    def __init__(self, path, mode, lane, stamp, family=None):
        self.path = path
        self.name = os.path.basename(path)
        self.mode = mode
        self.lane = lane
        self.family = family or infer_graph_family(path)
        self.stamp = stamp or {}
        self.local = bool(self.stamp.get("local", False))
        self.production_ready = self.stamp.get("production_ready", True) is not False
        self.user_requested_candidate = self.stamp.get("user_requested_candidate") is True
        self.quarantine_reason = str(self.stamp.get("quarantine_reason") or "")
        self.validation_status = str(self.stamp.get("validation_status") or "schema-only")
        self.release_eligible = self.stamp.get("release_eligible") is True
        self.visual_review = str(self.stamp.get("visual_review") or "")
        self.experimental = (self.stamp.get("experimental") is True
                             or self.validation_status == "experimental")
        self.user_workflow = self.stamp.get("user_workflow") is True
        self.proven = (self.validation_status == "render-proven" and self.release_eligible
                       and not self.experimental)

    def evidence_rank(self):
        return 0 if self.proven else (2 if self.experimental else 1)

    def evidence_word(self):
        return "custom" if self.user_workflow else "proven" if self.proven else ("experimental" if self.experimental else "unproven")

    def label(self):
        return "%s  [%s/%s/%s, %s]" % (
            self.name,
            self.family or "unknown model",
            self.mode or "?",
            self.lane or "any lane",
            ("local" if self.local else "CLOUD") + ", " + self.evidence_word(),
        )


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _atomic_json(path, value):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    temporary = "%s.tmp-%d-%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    try:
        with open(temporary, "wb") as handle:
            handle.write(json.dumps(
                value, ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            if os.path.isfile(temporary):
                os.unlink(temporary)
        except OSError:
            pass


def migrate_delivery_state(state):
    state = dict(state or {})
    if state.get("delivery_defaults_version") != 1:
        state["ltx_resolution"] = "1080P"
        if state.get("family") in ("LTX25", "LTX23"):
            state["resolution"] = "1080P"
        state["delivery_defaults_version"] = 1
    if state.get("ltx_resolution") not in RESOLUTIONS:
        state["ltx_resolution"] = "1080P"
    return state


def panel_state_path():
    override = os.environ.get("SECOND_UNIT_STATE")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.getcwd()
    return os.path.join(base, "SecondUnit", "panel-state.json")


def read_panel_state(path=None):
    try:
        with open(path or panel_state_path(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_panel_state(state, path=None):
    try:
        _atomic_json(path or panel_state_path(), state)
    except Exception as exc:
        log("panel state not saved: %s" % exc)


def _entry_payload(entry):
    return {
        "path": os.path.abspath(entry.path),
        "mode": entry.mode,
        "lane": entry.lane,
        "family": entry.family,
        "stamp": dict(entry.stamp or {}),
    }


def _params_payload(params):
    result = dict(params or {})
    entry = result.get("entry")
    if not isinstance(entry, GraphEntry):
        raise SecondUnitError("The selected preset could not cross the worker boundary.")
    result["entry"] = _entry_payload(entry)

    try:
        _canonical_json(result)
    except (TypeError, ValueError) as exc:
        raise SecondUnitError("The render request is not serializable: %s" % exc)
    return result


def _params_from_payload(value):
    if not isinstance(value, dict):
        raise SecondUnitError("External worker request has no parameter object.")
    result = dict(value)
    raw = result.get("entry")
    if not isinstance(raw, dict):
        raise SecondUnitError("External worker request has no preset record.")
    path = os.path.abspath(str(raw.get("path") or ""))
    if not path or not os.path.isfile(path):
        raise SecondUnitError("External worker preset is missing: %s" % path)
    result["entry"] = GraphEntry(
        path, raw.get("mode"), raw.get("lane"), raw.get("stamp") or {},
        family=raw.get("family"))
    return result


def _is_windows_store_python_alias(path):
    return "\\windowsapps\\" in str(path or "").replace("/", "\\").lower()


def _worker_python_candidates():
    candidates = []
    explicit = os.environ.get("SECOND_UNIT_PYTHON")
    if explicit:
        candidates.append(("SECOND_UNIT_PYTHON", explicit))
    configured = user_config_value("python")
    if configured:
        candidates.append(("second-unit.json python", configured))
    home = _stamped_home_data() or {}
    if home.get("python"):
        candidates.append(("Deploy-Panel.ps1", home["python"]))
    repo = home.get("repo")
    if repo:
        install_root = os.path.dirname(os.path.dirname(repo))
        candidates.append((
            "the local ComfyUI environment",
            os.path.join(install_root, "ComfyUI", ".venv", "Scripts", "python.exe")))
    executable = os.path.abspath(sys.executable or "")
    if os.path.basename(executable).lower() in ("python.exe", "python3.exe", "python"):
        candidates.append(("the current Python interpreter", executable))
    path_python = shutil.which("python.exe") or shutil.which("python")
    if path_python:
        candidates.append(("PATH", path_python))
    kept = []
    for why, candidate in candidates:
        if _is_windows_store_python_alias(candidate):
            log("worker python: rejected %s (%s) - the Microsoft Store app-execution alias is "
                "not an interpreter" % (candidate, why))
            continue
        kept.append((why, candidate))
    return kept


def find_worker_python():
    tried = []
    for why, candidate in _worker_python_candidates():
        resolved = candidate
        if candidate and not os.path.isabs(candidate):
            resolved = shutil.which(candidate) or candidate
        if _is_windows_store_python_alias(resolved):

            tried.append("%s: %s (REJECTED - Microsoft Store python alias)" % (why, resolved))
            continue
        tried.append("%s: %s" % (why, resolved))
        if resolved and os.path.isfile(resolved):
            return os.path.abspath(resolved)
    raise SecondUnitError(
        "No external Python is available for the Resolve-safe worker (the Microsoft Store "
        "python alias does not count). Re-run "
        "Deploy-Panel.ps1 with SECOND_UNIT_PYTHON set. Tried: %s"
        % "; ".join(tried))



LOADED_WORKFLOWS_SUBDIR = "loaded"


def verify_graph_tool_path(workflow_dir=None):
    root = os.path.dirname(os.path.abspath(str(workflow_dir or WORKFLOW_DIR).rstrip("\\/")))
    return os.path.join(root, "tools", "verify_graph.py")


def comfy_port(url=None):
    try:
        port = urllib.parse.urlparse(str(url or COMFY_URL)).port
    except ValueError:
        port = None
    return int(port or 8188)


def _run_capture(argv, timeout):
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "the verifier did not finish within %ds" % timeout
    except OSError as exc:
        return 127, str(exc)


def load_workflow_file(chosen, workflow_dir=None, comfy_url=None, python=None, run=None):
    workflow_dir = str(workflow_dir or WORKFLOW_DIR)
    chosen = str(chosen or "").strip()
    base = os.path.basename(chosen)
    if not chosen or not os.path.isfile(chosen):
        raise SecondUnitError("Workflow file not found: %s" % (chosen or "(none)"))
    if not chosen.lower().endswith(".json"):
        raise SecondUnitError("A workflow is a ComfyUI API-format .json file; %s is not one." % base)
    try:
        with open(chosen, "r", encoding="utf-8-sig") as handle:
            graph = json.load(handle)
    except ValueError as exc:
        raise SecondUnitError("%s is not valid JSON: %s" % (base, exc))
    if not isinstance(graph, dict) or not graph:
        raise SecondUnitError("%s is empty or not a JSON object." % base)
    if isinstance(graph.get("nodes"), list):
        raise SecondUnitError("%s is a UI-format workflow (it has a 'nodes' list). In ComfyUI use "
                              "Workflow > Export (API) and load that file instead." % base)
    if not all(isinstance(node, dict) and node.get("class_type") for node in graph.values()):
        raise SecondUnitError("%s does not look like an API-format graph: every entry needs a "
                              "class_type." % base)
    if not infer_graph_family(base, graph):
        raise SecondUnitError("Supported families are H3, LTX, WAN 2.2, SAM 3.1 and Juggernaut + Qwen environment storyboards. The model family could not be identified.")
    dest_dir = os.path.join(workflow_dir, LOADED_WORKFLOWS_SUBDIR)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    dest = os.path.join(dest_dir, base)
    if os.path.abspath(dest) != os.path.abspath(chosen):
        shutil.copyfile(chosen, dest)
    stamp_path = dest + ".verified.json"
    if os.path.isfile(stamp_path):
        try:
            os.remove(stamp_path)
        except OSError:
            pass
    tool = verify_graph_tool_path(workflow_dir)
    if not os.path.isfile(tool):
        raise SecondUnitError("The graph verifier is missing next to the workflows folder: %s" % tool)
    python = python or find_worker_python()
    port = comfy_port(comfy_url)
    code, output = (run or _run_capture)([python, tool, dest, "--port", str(port), "--stamp"], 180)
    lines = [line.rstrip() for line in (output or "").splitlines() if line.strip()]
    if code != 0 or not os.path.isfile(stamp_path):
        raise SecondUnitError("%s did not pass the verifier against ComfyUI on port %d, so it is not "
                              "offered. Verifier said: %s" % (base, port, " | ".join(lines[-6:]) or "nothing"))
    try:
        with open(stamp_path, "r", encoding="utf-8-sig") as handle:
            stamp = json.load(handle)
        if isinstance(stamp, dict):
            stamp["user_workflow"] = True
            with open(stamp_path, "w", encoding="utf-8") as handle:
                json.dump(stamp, handle, indent=2)
    except (OSError, ValueError):
        pass
    summary = next((line for line in lines if line.startswith("PASS")), "verified")
    log("load workflow: %s -> %s (%s)" % (chosen, dest, summary))
    return base, summary


def iter_graph_files(directory):
    found = []
    if not os.path.isdir(directory):
        return found
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for name in sorted(files):
            low = name.lower()
            if not low.endswith(".json") or low.endswith(".verified.json"):
                continue
            found.append(os.path.join(root, name))
    return found


def is_api_format(graph):
    if not isinstance(graph, dict) or not graph:
        return False
    if isinstance(graph.get("nodes"), list):
        return False
    return any(isinstance(v, dict) and "class_type" in v for v in graph.values())


LAST_UI_SKIPPED = 0


def discover_graphs(directory):
    global LAST_UI_SKIPPED
    ui_skipped = []
    entries = []
    problems = []
    if not os.path.isdir(directory):
        LAST_UI_SKIPPED = 0
        return entries, ["workflow directory does not exist: %s" % directory]
    for path in iter_graph_files(directory):
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                graph = json.load(handle)
        except Exception as exc:
            problems.append("%s: unreadable as JSON (%s)" % (name, exc))
            continue
        if not is_api_format(graph):
            ui_skipped.append(os.path.relpath(path, directory))
            continue
        stamp = read_stamp(path)
        if stamp is None:
            problems.append("%s: NOT stamped - run verify_graph.py --stamp on it" % name)
            continue
        mode, lane = classify_graph_name(name, graph)
        if mode is None:
            problems.append(
                "%s: neither the filename nor the graph's own nodes say what mode it is "
                "(add a t2v/i2v/v2v/segment token to the name)" % name
            )
            continue
        entries.append(GraphEntry(path, mode, lane, stamp, infer_graph_family(path, graph)))
    LAST_UI_SKIPPED = len(ui_skipped)
    if ui_skipped:
        log("discover_graphs: %d UI-format file(s) ignored (export API format to use them): %s" % (len(ui_skipped), "; ".join(ui_skipped[:5])))
    return entries, problems


def preset_label(entry):

    if entry.stamp.get("display_name"):
        status = str(entry.stamp.get("validation_status") or "schema-only")
        return "%s [%s]" % (entry.stamp["display_name"], status)
    stem = os.path.splitext(os.path.basename(entry.name))[0]

    variant = ""
    for noise, shown in (("_api_gguf", " \u00b7 GGUF"), ("_gguf", " \u00b7 GGUF"),
                         ("_api", ""), ("_fp8", " \u00b7 fp8")):
        if stem.endswith(noise):
            stem, variant = stem[:-len(noise)], shown
            break
    for prefix in ("ltx25_", "ltx23_", "h3_", "wan22_", "wan_", "sam31_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    for token in ("t2v_", "i2v_", "v2v_", "fl2v_", "flf2v_"):
        if stem.startswith(token):
            stem = stem[len(token):]
    words = stem.replace("-", " ").replace("_", " ").strip()
    text = ((words[:1].upper() + words[1:]) + variant) if words else entry.name
    evidence = getattr(entry, "evidence_word", None)
    return "%s [%s]" % (text, evidence()) if callable(evidence) else text


def declares_mode(entry):
    return classify_graph_name(entry.name)[0] is not None


def candidates_for(entries, mode, lane, allow_cloud, family=None, show_unproven=None):
    show = SHOW_UNPROVEN if show_unproven is None else bool(show_unproven)
    for_mode = [e for e in entries
                if (e.production_ready or e.user_requested_candidate) and e.mode == mode
                and not is_detail_upscale_entry(e)
                and (not family or e.family == family)
                and (show or getattr(e, "proven", False) or getattr(e, "user_workflow", False))]
    exact = [e for e in for_mode if e.lane == lane]
    laneless = [e for e in for_mode if e.lane is None]
    for_lane = exact or (laneless if lane == LANES[0] else [])
    allowed = for_lane if allow_cloud else [e for e in for_lane if e.local]
    return sorted(allowed, key=lambda e: (
        0 if DEFAULT_PRESETS.get((e.family, mode, lane)) == e.name else 1,
        e.evidence_rank() if hasattr(e, "evidence_rank") else 1,
        0 if declares_mode(e) else 1, e.name))


def select_graph(entries, mode, lane, allow_cloud, chosen=None, family=None, show_unproven=None):
    matching = [e for e in entries if e.mode == mode
                and not is_detail_upscale_entry(e)
                and (not family or e.family == family)]
    for_mode = [e for e in matching if e.production_ready or e.user_requested_candidate]
    if not for_mode:
        quarantined = [e for e in matching if not e.production_ready]
        if quarantined:
            reasons = sorted(set(e.quarantine_reason or "not release-proven"
                                 for e in quarantined))
            return None, (
                "No production-ready %s preset%s. Quarantined: %s"
                % (mode,
                   " for " + dict(FAMILY_LABELS).get(family, family) if family else "",
                   "; ".join(reasons))
            )
        family_text = " for %s" % dict(FAMILY_LABELS).get(family, family) if family else ""
        return None, ("No verified %s graph%s in %s. Stamp one with verify_graph.py --stamp."
                      % (mode, family_text, WORKFLOW_DIR))

    exact = [e for e in for_mode if e.lane == lane]
    laneless = [e for e in for_mode if e.lane is None]
    for_lane = exact or (laneless if lane == LANES[0] else [])
    if not for_lane:
        lanes = sorted(set(e.lane for e in for_mode if e.lane))
        if laneless:
            return None, (
                "No %s graph claims the %s lane. %d unlabelled %s graph(s) are available on the "
                "%s lane instead." % (mode, lane, len(laneless), mode, LANES[0])
            )
        return None, "No %s graph for the %s lane (have: %s)." % (mode, lane, ", ".join(lanes) or "none")
    allowed = candidates_for(entries, mode, lane, allow_cloud, family, show_unproven)
    if not allowed:
        unproven = candidates_for(entries, mode, lane, allow_cloud, family, True)
        if unproven:
            return None, (
                "No proven %s preset yet%s on the %s lane (%d unproven: %s). Turn on 'Show unproven "
                "presets' (checkbox under LENGTH, or \"show_unproven\": \"1\" in second-unit.json), or run "
                "the proof campaign and stamp a PASS with tools/stamp_evidence.py."
                % (dict(MODE_LABELS).get(mode, mode),
                   " for " + dict(FAMILY_LABELS).get(family, family) if family else "",
                   dict(LANE_LABELS).get(lane, lane), len(unproven),
                   "; ".join(preset_label(e) for e in unproven[:3])))
        return None, (
            "The only %s/%s graph is stamped local:false (it calls a paid cloud service). "
            "Tick 'Allow cloud graphs' if you really want it." % (mode, lane)
        )

    if chosen:
        for entry in allowed:
            if entry.name == chosen or preset_label(entry) == chosen:
                return entry, None
        hidden = candidates_for(entries, mode, lane, allow_cloud, family, True)
        if any(e.name == chosen or preset_label(e) == chosen for e in hidden):
            return None, ("The selected preset is unproven and 'Show unproven presets' is off. Tick it to "
                          "run this preset anyway.")
        return None, "The selected preset is unavailable for this model and mode. Select an available preset."
    return allowed[0], None


def is_link(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
        and not isinstance(value[0], bool)
    )


def node_inputs(graph, node_id):
    node = graph.get(str(node_id)) or {}
    return node.get("inputs") or {}


def text_input_key(node):
    inputs = node.get("inputs") or {}
    for key in ("text", "prompt", "string"):
        if isinstance(inputs.get(key), str):
            return key
    return None


def _trace_to_text_node(graph, node_id, role, hops=12):
    current = str(node_id)
    seen = set()
    for _ in range(hops):
        if current in seen or current not in graph:
            return None
        seen.add(current)
        node = graph[current]
        if text_input_key(node):
            return current
        inputs = node.get("inputs") or {}
        if is_link(inputs.get(role)):
            current = str(inputs[role][0])
            continue
        links = [v for v in inputs.values() if is_link(v)]
        if len(links) != 1:
            return None
        current = str(links[0][0])
    return None


_GUIDER_PREFERENCE = (
    "LTXVConditioning",
    "CFGGuider",
    "KSampler",
    "KSamplerAdvanced",
    "SamplerCustom",
    "SamplerCustomAdvanced",
)


def _prompt_pair(positive_id, negative_id):
    if not positive_id:
        raise SecondUnitError("Internal: no positive prompt node was resolved.")
    positive_id = str(positive_id)
    if negative_id is None:
        return positive_id, None
    negative_id = str(negative_id)
    if negative_id == positive_id:
        return positive_id, None
    return positive_id, negative_id


def find_prompt_nodes(graph):
    guiders = []
    for node_id, node in graph.items():
        inputs = node.get("inputs") or {}
        if is_link(inputs.get("positive")) and is_link(inputs.get("negative")):
            class_type = str(node.get("class_type") or "")
            rank = _GUIDER_PREFERENCE.index(class_type) if class_type in _GUIDER_PREFERENCE else len(_GUIDER_PREFERENCE)
            guiders.append((rank, str(node_id), node))
    for _rank, node_id, _node in sorted(guiders, key=lambda item: (item[0], item[1])):
        positive = _trace_to_text_node(graph, node_id, "positive")
        if positive:
            return _prompt_pair(positive, _trace_to_text_node(graph, node_id, "negative"))

    text_nodes = [nid for nid, node in graph.items() if text_input_key(node)]
    if len(text_nodes) == 1:
        return _prompt_pair(text_nodes[0], None)
    titled_negative = []
    for node_id in text_nodes:
        title = str(((graph[node_id].get("_meta") or {}).get("title") or "")).lower()
        if "neg" in title:
            titled_negative.append(node_id)
    remaining = [n for n in text_nodes if n not in titled_negative]
    if len(remaining) == 1:
        return _prompt_pair(remaining[0], titled_negative[0] if titled_negative else None)
    raise SecondUnitError(
        "Cannot tell which text node is the positive prompt (%d candidates: %s). "
        "Title the negative encoder 'negative' in the graph and re-stamp it."
        % (len(text_nodes), ", ".join(sorted(text_nodes)))
    )


def graph_accepts_negative(graph):
    try:
        _positive, negative = find_prompt_nodes(graph)
    except Exception:
        return True
    return negative is not None


def find_prompt_targets(graph):
    combined = []
    for node_id, node in graph.items():
        inputs = (node or {}).get("inputs") or {}
        if (isinstance(inputs.get("positive_prompt"), str)
                and isinstance(inputs.get("negative_prompt"), str)):
            combined.append(str(node_id))
    if len(combined) == 1:
        node_id = combined[0]
        return (node_id, "positive_prompt"), (node_id, "negative_prompt")
    if len(combined) > 1:
        raise SecondUnitError(
            "Cannot tell which combined WAN prompt node to edit (%d candidates: %s)."
            % (len(combined), ", ".join(sorted(combined))))
    positive_id, negative_id = find_prompt_nodes(graph)
    positive_key = text_input_key(graph[positive_id])
    negative_key = text_input_key(graph[negative_id]) if negative_id else None
    return (positive_id, positive_key), ((negative_id, negative_key) if negative_id else None)


def graph_fps(graph):
    for wanted_class, key in (("CreateVideo", "fps"), ("SaveWEBM", "fps"), ("SaveAnimatedWEBP", "fps")):
        for node in graph.values():
            if node.get("class_type") == wanted_class:
                value = (node.get("inputs") or {}).get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                    return float(value)
    for key in FPS_INPUTS:
        for node in graph.values():
            value = (node.get("inputs") or {}).get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                return float(value)
    return DEFAULT_FPS



FRAME_GRIDS = {"MiniMaxH3ImageToVideo": (17, 5), "MiniMaxH3ReferenceToVideo": (17, 5),
               "EmptyMiniMaxH3LatentAV": (17, 5)}


def snap_frames(frames, class_type):
    grid = FRAME_GRIDS.get(str(class_type or ""))
    if not grid:
        return int(frames)
    step, base = grid
    if frames <= base:
        return base
    steps = -(-(int(frames) - base) // step)
    return base + steps * step


def assert_h3_frame_grid(graph):
    for _nid, _node in (graph or {}).items():
        if not isinstance(_node, dict):
            continue
        _grid = FRAME_GRIDS.get(str(_node.get("class_type") or ""))
        _len = (_node.get("inputs") or {}).get("length")
        if _grid and isinstance(_len, int) and not isinstance(_len, bool) and (_len < _grid[1] or (_len - _grid[1]) % _grid[0]):
            raise SecondUnitError("Node %s (%s) asks for %d frames, which is off the model's %dk+%d grid. Nothing was queued." % (_nid, _node.get("class_type"), _len, _grid[0], _grid[1]))


def find_frame_targets(graph):
    targets = []
    for node_id in sorted(graph, key=lambda k: (len(str(k)), str(k))):
        node = graph[node_id]
        inputs = node.get("inputs") or {}
        class_type = str(node.get("class_type") or "")
        for key in FRAME_INPUTS:
            if key == "length" and class_type in NON_FRAME_LENGTH_CLASSES:
                continue
            value = inputs.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                targets.append((str(node_id), key))
    return targets


def find_exact_frame_trim_targets(graph):
    targets = []
    for node_id, node in (graph or {}).items():
        if not isinstance(node, dict) or node.get("class_type") != "ImageFromBatch":
            continue
        title = str(((node.get("_meta") or {}).get("title") or "")).upper()
        if title == "SECOND UNIT EXACT FRAME TRIM" and isinstance(
                (node.get("inputs") or {}).get("length"), (int, float)):
            targets.append((str(node_id), "length"))
    return targets


def slugify(text):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "")).strip("_").lower()
    return cleaned or "shot"


def enforce_lane_prefix(graph, mode):
    changes = []
    for node_id in sorted(graph, key=lambda k: (len(str(k)), str(k))):
        inputs = graph[node_id].get("inputs") or {}
        current = inputs.get("filename_prefix")
        if not isinstance(current, str):
            continue
        last_segment = current.replace("\\", "/").rstrip("/").split("/")[-1]
        if GPU_TAG in last_segment:
            continue
        last_segment = re.sub(r"^_?gpu\d+_", "", last_segment, flags=re.I)
        new_prefix = OUTPUT_PREFIX_ROOT + GPU_TAG + slugify(last_segment or mode)
        inputs["filename_prefix"] = new_prefix
        changes.append((str(node_id), current, new_prefix))
    return changes


def _new_graph_node_id(graph):
    numeric = [int(key) for key in graph if str(key).isdigit()]
    candidate = (max(numeric) + 1) if numeric else 1
    while str(candidate) in graph:
        candidate += 1
    return str(candidate)


def enforce_comfy_prores_hq(graph, fps, resolution="720P", output_size=None, vsr=False):
    if resolution not in OUTPUT_SIZES:
        raise SecondUnitError("Unknown output resolution %r." % resolution)
    if output_size is None:
        width, height = OUTPUT_SIZES[resolution]
        delivery_label = resolution
    else:
        try:
            width, height = int(output_size[0]), int(output_size[1])
        except (TypeError, ValueError, IndexError):
            raise SecondUnitError("Invalid native intermediate size %r." % (output_size,))
        if width < 1 or height < 1:
            raise SecondUnitError("Native intermediate dimensions must be positive.")
        delivery_label = "H3 NATIVE INTERMEDIATE"
    changes = []
    savers = [(str(node_id), node) for node_id, node in list(graph.items())
              if isinstance(node, dict)
              and node.get("class_type") in ("SaveVideo", "VHS_VideoCombine")]
    for node_id, node in savers:
        inputs = node.get("inputs") or {}
        images = None
        audio = None
        frame_rate = fps
        if node.get("class_type") == "SaveVideo":
            video_link = inputs.get("video")
            if not is_link(video_link):
                raise SecondUnitError(
                    "SaveVideo node %s has no linked VIDEO input, so it cannot be rewritten "
                    "as a Comfy-level ProRes HQ save." % node_id)
            creator = graph.get(str(video_link[0])) or {}
            if creator.get("class_type") != "CreateVideo":
                raise SecondUnitError(
                    "SaveVideo node %s is fed by %s, not CreateVideo; refusing rather than "
                    "silently transcoding after ComfyUI." %
                    (node_id, creator.get("class_type") or "an unknown node"))
            creator_inputs = creator.get("inputs") or {}
            images = creator_inputs.get("images")
            audio = creator_inputs.get("audio")
            if isinstance(creator_inputs.get("fps"), (int, float)):
                frame_rate = float(creator_inputs["fps"])
        else:
            images = inputs.get("images")
            audio = inputs.get("audio")
            if isinstance(inputs.get("frame_rate"), (int, float)):
                frame_rate = float(inputs["frame_rate"])
        if not is_link(images):
            raise SecondUnitError(
                "%s node %s has no linked IMAGE batch for Comfy-level ProRes delivery."
                % (node.get("class_type"), node_id))

        if vsr and output_size is None and resolution == "1080P":

            vsr_id = _new_graph_node_id(graph)
            graph[vsr_id] = {
                "class_type": "RTXVideoSuperResolution",
                "_meta": {"title": "SECOND UNIT RTX VSR 1080P"},
                "inputs": {
                    "images": images,
                    "resize_type": "target dimensions",
                    "resize_type.width": width,
                    "resize_type.height": height,
                    "quality": "ULTRA",
                },
            }
            images = [vsr_id, 0]
        upstream = graph.get(str(images[0])) or {}
        if (upstream.get("class_type") == "ImageScale"
                and (upstream.get("_meta") or {}).get("second_unit_role") == "delivery_scale"):
            scale_id = str(images[0])
            upstream["inputs"].update(width=width, height=height, upscale_method="lanczos", crop="center")
        else:
            scale_id = _new_graph_node_id(graph)
            graph[scale_id] = {
                "class_type": "ImageScale",
                "_meta": {"title": "SECOND UNIT %s DELIVERY SCALE" % delivery_label,
                          "second_unit_role": "delivery_scale"},
                "inputs": {"image": images, "upscale_method": "lanczos", "width": width,
                           "height": height, "crop": "center"},
            }
        new_inputs = {
            "images": [scale_id, 0],
            "frame_rate": frame_rate,
            "loop_count": 0,
            "filename_prefix": inputs.get("filename_prefix") or (OUTPUT_PREFIX_ROOT + "shot"),
            "format": "video/ProRes",
            "profile": "hq",
            "pingpong": False,
            "save_output": True,
        }
        if is_link(audio):
            new_inputs["audio"] = audio
        graph[node_id] = {
            "class_type": "VHS_VideoCombine",
            "_meta": {"title": "SECOND UNIT PRORES HQ Â· %s" % delivery_label},
            "inputs": new_inputs,
        }
        changes.append((node_id, scale_id, width, height))
    if not changes:

        has_moving_latent = any(
            any(key in (node.get("inputs") or {}) for key in FRAME_INPUTS)
            for node in graph.values() if isinstance(node, dict))
        if has_moving_latent:
            raise SecondUnitError(
                "Graph renders multiple frames but has no SaveVideo/VHS_VideoCombine node "
                "that can save ProRes HQ inside ComfyUI.")
    return changes


def find_source_inputs(graph, mode):
    wanted = IMAGE_SOURCE_INPUTS if mode in IMAGE_SOURCE_MODES else VIDEO_SOURCE_INPUTS
    found = []
    for class_type, key in wanted:
        for node_id in sorted(graph, key=lambda k: (len(str(k)), str(k))):
            node = graph[node_id]
            if node.get("class_type") == class_type and isinstance((node.get("inputs") or {}).get(key), str):
                found.append((str(node_id), key))
    return found


def find_source_input(graph, mode):
    found = find_source_inputs(graph, mode)
    return found[0] if found else None


def staged_source_value(graph, mode, staged_name, input_dir):
    target = find_source_input(graph, mode)
    if not target:
        return staged_name
    node = graph.get(str(target[0])) or {}
    if node.get("class_type") == "VHS_LoadVideoPath":
        return os.path.abspath(os.path.join(input_dir, staged_name))
    return staged_name


def describe_unstaged_loaders(graph, staged, mode):
    leftovers = []
    for node_id, key in find_source_inputs(graph, mode):
        if (node_id, key) == staged:
            continue
        node = graph[node_id]
        consumers = []
        for other_id, other in graph.items():
            for other_key, val in (other.get("inputs") or {}).items():
                if isinstance(val, list) and val and str(val[0]) == str(node_id):
                    consumers.append(other_key)
        leftovers.append((node_id, key, node["inputs"][key], sorted(set(consumers))))
    return leftovers


def scan_forbidden(graph):
    return sorted({
        str(node.get("class_type"))
        for node in graph.values()
        if str(node.get("class_type")) in FORBIDDEN_NODES
    })


def keyframe_targets(graph):
    roles = {}
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        for key in ("first_frame", "last_frame"):
            link = (node.get("inputs") or {}).get(key)
            if isinstance(link, list) and link:
                src = graph.get(str(link[0]))
                if src and src.get("class_type") in {name for name, _k in IMAGE_SOURCE_INPUTS}:
                    roles[key] = str(link[0])
    return roles


def plain_h3_world(graph):
    if infer_graph_family("", graph) != "MINIMAXH3":
        return False
    if h3_v3_kind(graph):

        return True
    for node in graph.values():
        if isinstance(node, dict) and node.get("class_type") in (
                "easy sam3VideoSegmentation", "DepthAnything_V3", "SecondUnitRetargetWorldProxy"):
            return False
    return True




H3_V3_MAX_PICTURES = 9

H3_AUTO_CARDS_MAX = max(1, min(6, _env_int("SECOND_UNIT_AUTO_CARDS_MAX", 4)))

AUTO_CARDS_ENABLED = str(_cfg("experimental_auto_cards", "SECOND_UNIT_EXPERIMENTAL_AUTO_CARDS", "") or ""
                         ).strip().lower() in ("1", "true", "yes", "on")
AUTO_CARDS_OFF_REASON = ("AUTO CARDS is experimental and off in this release: in testing, panel-path proofs "
                         "with harvested cards lost the performer. Fill the IDENTITY box with one still instead "
                         "(that path is proven), or set SECOND_UNIT_EXPERIMENTAL_AUTO_CARDS=1 to try it.")


def auto_cards_gate(params):
    if (params or {}).get("auto_cards") and not AUTO_CARDS_ENABLED:
        return AUTO_CARDS_OFF_REASON
    return None

_CARD_ROLES = {}
_CARD_ROLE_TABLE = (
    ("face_front", "primary facial identity, frontal"),
    ("face_3q", "facial identity, three-quarter"),
    ("three_quarter", "facial identity, three-quarter"),
    ("profile", "facial identity, profile"),
    ("face", "facial identity"),
    ("upper_body", "hair, head, shoulders, build and upper wardrobe"),
    ("full_body", "body proportions, silhouette and complete wardrobe"),
    ("wardrobe", "wardrobe construction, colour and accessories"),
    ("context", "original photographic appearance and lighting context"),
    ("extra", "additional real source view"),
)


def h3_card_role(card_file_name):
    lowered = str(card_file_name or "").lower()
    for token, role in _CARD_ROLE_TABLE:
        if token in lowered:
            return role
    return "real source view of the performer"



def h3_v3_kind(graph):
    if infer_graph_family("", graph) != "MINIMAXH3":
        return None
    fade = None
    depth = False
    turbo = False
    for node in (graph or {}).values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs") or {}
        if class_type == "MiniMaxH3ReferenceVideoFadeModelPatch":
            fade = str(inputs.get("preset") or "")
        elif class_type == "DepthAnything_V3":
            depth = True
        elif class_type in ("LoraLoaderModelOnly", "MiniMaxH3TurboLoRA") \
                and "turbo" in str(inputs.get("lora_name") or "").lower():
            turbo = True
    if fade is None:
        return None

    if depth:
        return "lock"
    if turbo:
        return "draft"
    return "angle" if fade == "balanced" else "lock"


H3_FIRST_FRAME_ARMS = ("off", "picture", "latent")
H3_FIRST_FRAME_DEFAULT_MASTER = "picture"
H3_FIRST_FRAME_PREPASS_FRAMES = 5
H3_FIRST_FRAME_GREEN_MAX = 0.02
H3_FIRST_FRAME_TITLE = "FIRST FRAME ANCHOR - [SHOT 1] - SECOND UNIT"


def h3_first_frame_anchor_arm(entry, graph):
    if entry is None or entry.family != "MINIMAXH3" or entry.mode != "ENVSWAP" or h3_v3_kind(graph) != "lock":
        return "off"
    value = str(_cfg("h3_first_frame_anchor", "SECOND_UNIT_H3_FIRST_FRAME_ANCHOR", "") or "").strip().lower()
    if value in H3_FIRST_FRAME_ARMS:
        return value
    if value:
        raise SecondUnitError("SECOND_UNIT_H3_FIRST_FRAME_ANCHOR must be off, picture or latent (got %r)." % value)
    return H3_FIRST_FRAME_DEFAULT_MASTER if entry.name in (H3_ENVSWAP_MASTER_NAME, H3_ENVSWAP_MASTER_LEGACY_NAME) else "off"


def h3_reference_node(graph):
    for node_id, node in (graph or {}).items():
        if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ReferenceToVideo":
            return str(node_id), node
    return None, None


def h3_v3_picture_loaders(graph):
    _ref_id, ref = h3_reference_node(graph)
    if ref is None:
        return []
    inputs = ref.get("inputs") or {}
    keys = [k for k in inputs if k.startswith("ref_images.ref_image_") and is_link(inputs[k])]
    keys.sort(key=lambda k: int(k.rsplit("_", 1)[1]))
    found = []
    for key in keys:
        loader_id = str(inputs[key][0])
        node = graph.get(loader_id) or {}
        title = str(((node.get("_meta") or {}).get("title") or "")).upper()
        found.append((loader_id, key, title))
    return found


def h3_v3_picture_role(title):
    title = (title or "").upper()
    if "CONTINUITY" in title:
        return "continuity"
    if "ENVIRONMENT" in title:
        return "environment"
    if "WARDROBE" in title:
        return "wardrobe"
    if "REPLACEMENT PERFORMER" in title:
        return "replacement"
    if "IDENTITY" in title:
        return "identity"
    return "reference"


def wire_h3_v3_pictures(graph, mode, source_name_last=None, identity_name=None, wardrobe_name=None,
                        prop1_name=None, prop2_name=None, card_names=None, continuity_name=None, first_frame_name=None):
    graph_ref_id, ref = h3_reference_node(graph)
    loaders = h3_v3_picture_loaders(graph)
    if ref is None or not loaders:
        return []
    identity_pool = [name for name in (identity_name, prop1_name, prop2_name) if name]
    identity_pool += [name for name in (card_names or []) if name and name not in identity_pool]
    environment_name = source_name_last if mode in ("ENVSWAP", "ANGLE") else None
    replacement_name = source_name_last if mode == "SWAP" else None

    ordered = []
    for loader_id, _key, title in loaders:
        role = h3_v3_picture_role(title)
        optional = "OPTIONAL" in title
        name = None
        if role == "environment":
            name = environment_name
        elif role == "wardrobe":
            name = wardrobe_name
        elif role == "replacement":
            name = replacement_name or (identity_pool.pop(0) if identity_pool else None)
        elif role == "identity":
            name = identity_pool.pop(0) if identity_pool else None
        if name:
            ordered.append((loader_id, name, role))
        elif not optional:
            box = {"environment": "the second file box (World reference)",
                   "replacement": "the second file box (Reference) or an IDENTITY card",
                   "wardrobe": "the WARDROBE box", "identity": "the IDENTITY box"}.get(role, "its box")
            raise SecondUnitError(
                "%s needs %s filled: this preset's %s picture is not optional."
                % (dict(MODE_LABELS).get(mode, mode), box, role))
        else:
            del graph[loader_id]

    while identity_pool and len(ordered) < H3_V3_MAX_PICTURES - (1 if continuity_name else 0) - (1 if first_frame_name else 0):
        new_id = _new_graph_node_id(graph)
        graph[new_id] = {"class_type": "LoadImage",
                         "_meta": {"title": "IDENTITY CARD (auto) - SECOND UNIT"},
                         "inputs": {"image": identity_pool[0]}}
        insert_at = next((i for i, (_lid, _n, role) in enumerate(ordered)
                          if role in ("environment", "continuity")), len(ordered))
        ordered.insert(insert_at, (new_id, identity_pool.pop(0), "identity"))
    if continuity_name:
        new_id = _new_graph_node_id(graph)
        graph[new_id] = {"class_type": "LoadImage",
                         "_meta": {"title": "CONTINUITY - PREVIOUS WINDOW LAST FRAME - SECOND UNIT"},
                         "inputs": {"image": continuity_name}}
        ordered.append((new_id, continuity_name, "continuity"))
    if first_frame_name:
        new_id = _new_graph_node_id(graph)
        graph[new_id] = {"class_type": "LoadImage", "_meta": {"title": H3_FIRST_FRAME_TITLE},
                         "inputs": {"image": first_frame_name}}
        ordered.append((new_id, first_frame_name, "first_frame"))
    _seen = {}
    for _lid, _name, _role in ordered:
        _key = os.path.basename(str(_name)).lower()
        if _key in _seen and _seen[_key] != _role:
            raise SecondUnitError("The same picture (%s) fills both the %s and the %s slot. Each H3 picture must be a different image: use a real face photo for identity and the no-head wardrobe sheet for wardrobe. Nothing was queued." % (os.path.basename(str(_name)), _seen[_key], _role))
        _seen.setdefault(_key, _role)
    if len(ordered) > H3_V3_MAX_PICTURES:
        raise SecondUnitError("H3 takes at most %d pictures; %d were supplied. Drop a card."
                              % (H3_V3_MAX_PICTURES, len(ordered)))

    inputs = ref.setdefault("inputs", {})
    for key in [k for k in inputs if k.startswith("ref_images.ref_image_")]:
        del inputs[key]
    targets = []
    for index, (loader_id, name, _role) in enumerate(ordered):
        inputs["ref_images.ref_image_%d" % index] = [loader_id, 0]
        graph[loader_id].setdefault("inputs", {})["image"] = name
        targets.append((loader_id, "image"))
    return targets


def extract_last_frame_png(video_path, png_path):
    if not video_path or not os.path.isfile(video_path):
        raise SecondUnitError("Cannot chain windows: previous window output is missing: %s" % video_path)
    directory = os.path.dirname(png_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    _run_tool(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-0.1", "-i", video_path,
               "-update", "1", "-frames:v", "1", png_path])
    if not os.path.isfile(png_path) or os.path.getsize(png_path) < 1024:
        raise SecondUnitError("Cannot chain windows: ffmpeg did not write the continuity frame %s" % png_path)
    return png_path


def extract_first_frame_png(video_path, png_path):
    if not video_path or not os.path.isfile(video_path):
        raise SecondUnitError("First-frame anchor: pre-pass output is missing: %s" % video_path)
    directory = os.path.dirname(png_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    _run_tool(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path, "-frames:v", "1", "-update", "1", png_path])
    if not os.path.isfile(png_path) or os.path.getsize(png_path) < 1024:
        raise SecondUnitError("First-frame anchor: ffmpeg did not write %s" % png_path)
    return png_path


def green_backdrop_fraction(png_path):
    exe = _tool_path("ffmpeg")
    if not exe:
        raise SecondUnitError("First-frame anchor needs ffmpeg to check the pre-pass frame (set SECOND_UNIT_FFMPEG).")
    completed = subprocess.run([exe, "-v", "error", "-i", png_path, "-vf", "scale=320:180",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=PROBE_TIMEOUT_S,
                               creationflags=_NO_WINDOW)
    raw = completed.stdout or b""
    if completed.returncode != 0 or not raw:
        raise SecondUnitError("First-frame anchor: ffmpeg could not read %s" % png_path)
    total = len(raw) // 3
    hits = 0
    for i in range(0, total * 3, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        if g > 90 and g > r * 1.35 and g > b * 1.25:
            hits += 1
    return float(hits) / float(total or 1)


def inject_h3_first_frame_guide(graph, image_name):
    ref_id, ref = h3_reference_node(graph)
    if ref is None:
        raise SecondUnitError("First-frame latent anchor needs a MiniMaxH3ReferenceToVideo node.")
    vae = (ref.get("inputs") or {}).get("vae")
    if not is_link(vae):
        raise SecondUnitError("First-frame latent anchor needs the H3 node's video VAE link.")
    loader_id = _new_graph_node_id(graph)
    graph[loader_id] = {"class_type": "LoadImage", "_meta": {"title": "FIRST FRAME GUIDE (LATENT) - SECOND UNIT"},
                        "inputs": {"image": image_name}}
    guide_id = _new_graph_node_id(graph)
    graph[guide_id] = {"class_type": "MiniMaxH3AddGuide", "_meta": {"title": "FIRST FRAME GUIDE at frame 0 - SECOND UNIT"},
                       "inputs": {"positive": [ref_id, 0], "latent": [ref_id, 1], "frame_idx": 0,
                                  "vae": list(vae), "image": [loader_id, 0]}}
    rewired = []
    for node_id, node in graph.items():
        if str(node_id) in (guide_id, loader_id) or not isinstance(node, dict):
            continue
        if node.get("class_type") == "ConditioningZeroOut":
            continue
        for key, value in list((node.get("inputs") or {}).items()):
            if key in ("conditioning", "positive") and is_link(value) and str(value[0]) == ref_id and int(value[1]) == 0:
                node["inputs"][key] = [guide_id, 0]
                rewired.append((str(node_id), key))
    if not rewired:
        raise SecondUnitError("First-frame latent anchor found nothing consuming the H3 conditioning.")
    return guide_id, loader_id


def h3_card_builder_paths(builder_dir=None):
    builder_dir = builder_dir or H3_CARD_BUILDER
    python_exe = os.path.join(builder_dir, ".venv", "Scripts", "python.exe")
    script = os.path.join(builder_dir, "h3_character_pack.py")
    if not (os.path.isfile(python_exe) and os.path.isfile(script)):
        raise SecondUnitError(
            "AUTO CARDS needs the H3 Character Pack Builder (h3_character_pack.py + its .venv). "
            "Point SECOND_UNIT_H3_CARD_BUILDER at it, or untick AUTO CARDS and fill the IDENTITY box.")
    return python_exe, script


def build_identity_cards(clip_path, input_dir, work_root, extra_stills=None, max_cards=None, log_fn=None):
    python_exe, script = h3_card_builder_paths()
    if max_cards is None:
        max_cards = H3_AUTO_CARDS_MAX
    tag = hashlib.sha256((os.path.abspath(clip_path) + "|" + "|".join(extra_stills or [])).encode("utf-8")).hexdigest()[:12]
    work = os.path.join(work_root, "cards-" + tag)
    harvest = os.path.join(work, "harvest")
    pack = os.path.join(work, "pack")
    if not os.path.isdir(harvest):
        os.makedirs(harvest)
    if not os.listdir(harvest):
        _run_tool(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", clip_path,
                   "-vf", "select='not(mod(n\\,2))'", "-fps_mode", "vfr",
                   os.path.join(harvest, "clip_%04d.png")])
        for index, still in enumerate(extra_stills or []):
            if still and os.path.isfile(still):
                shutil.copy2(still, os.path.join(harvest, "extra%d_%s.png" % (index, slugify(os.path.basename(still)))))
    if not os.listdir(harvest):
        raise SecondUnitError("AUTO CARDS: ffmpeg harvested no frames from %s" % clip_path)
    refs_dir = os.path.join(pack, "h3_refs")
    if not os.path.isdir(refs_dir) or not os.listdir(refs_dir):
        if log_fn:
            log_fn("AUTO CARDS: pack builder on %d harvested frames" % len(os.listdir(harvest)))
        try:
            subprocess.check_call([python_exe, script, "--input", harvest, "--output", pack,
                                   "--max-scan", "900", "--input-transfer", "display-srgb", "--exposure", "0.0"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SecondUnitError("AUTO CARDS: the pack builder failed (%s). Fill the IDENTITY box instead." % exc)
    cards = sorted(name for name in os.listdir(refs_dir) if name.lower().endswith(".png"))
    if not cards:
        raise SecondUnitError("AUTO CARDS: the pack builder produced no cards from this clip.")
    face_cards = [name for name in cards if "face" in name.lower() or "profile" in name.lower()]
    verdict = {}
    if face_cards:
        recheck = ("import sys, cv2, mediapipe as mp\n"
                   "fd = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.35)\n"
                   "for p in sys.argv[1:]:\n"
                   "    img = cv2.imread(p)\n"
                   "    res = fd.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))\n"
                   "    print(('FACE' if res.detections else 'NOFACE') + '\\t' + p)\n")
        try:
            out = subprocess.check_output([python_exe, "-c", recheck] + [os.path.join(refs_dir, n) for n in face_cards],
                                          stderr=subprocess.DEVNULL).decode("utf-8", "replace")
            for line in out.splitlines():
                if "\t" in line:
                    flag, path = line.split("\t", 1)
                    verdict[os.path.basename(path.strip())] = flag.strip()
        except (OSError, subprocess.CalledProcessError):
            verdict = {}
    keep = []
    for name in cards:
        if name in face_cards and verdict.get(name) == "NOFACE":
            if log_fn:
                log_fn("AUTO CARDS: culled %s (no detectable face - back-of-head mislabel)" % name)
            continue
        keep.append(name)
        if len(keep) >= max_cards:
            break
    staged = []
    for index, name in enumerate(keep):
        target = "su_card_%s_%02d.png" % (tag, index)
        shutil.copy2(os.path.join(refs_dir, name), os.path.join(input_dir, target))
        _CARD_ROLES[target] = h3_card_role(name)
        staged.append(target)
    if log_fn:
        log_fn("AUTO CARDS: %d card(s) staged: %s" % (len(staged), ", ".join(keep)))
    return staged


_H3_TRANSLATOR = None


def h3_translator():
    global _H3_TRANSLATOR
    if _H3_TRANSLATOR is not None:
        return _H3_TRANSLATOR or None
    candidates = [os.path.dirname(_self_path()),
                  os.path.join(os.path.dirname(os.path.abspath(WORKFLOW_DIR)), "resolve-panel"),
                  os.path.join(os.environ.get("SECOND_UNIT_REPO") or "", "resolve-panel")]
    for folder in candidates:
        path = os.path.join(folder, "h3_prompt_translator.py")
        if not os.path.isfile(path):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("h3_prompt_translator", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _H3_TRANSLATOR = module
            log("H3 prompt translator loaded from %s" % path)
            return module
        except Exception as exc:
            log("H3 prompt translator at %s failed to load: %s: %s" % (path, exc.__class__.__name__, exc))
    _H3_TRANSLATOR = False
    return None


def camera_reference_module():
    import importlib.util
    path = os.path.join(os.path.dirname(_self_path()), "camera_reference.py")
    if not os.path.isfile(path):
        path = os.path.join(os.path.dirname(os.path.abspath(WORKFLOW_DIR)), "resolve-panel", "camera_reference.py")
    spec = importlib.util.spec_from_file_location("second_unit_camera_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rv_camera_snapshot(project, source_path="", request=""):
    """Capture on the Resolve UI thread; only exact media paths establish provenance."""
    camera = camera_reference_module()
    timeline = _rv_call(project, "GetCurrentTimeline") if project else None
    item = _rv_call(timeline, "GetCurrentVideoItem") if timeline else None
    media = _rv_call(item, "GetMediaPoolItem") if item else None
    current_path = rv_media_file_path(media) or ""
    if timeline and not current_path:
        found, found_media, _track = rv_clip_under_playhead(timeline, rv_timeline_fps(timeline, project))
        if found is not None:
            item, media = found, found_media
            current_path = rv_media_file_path(media) or ""
    selected = source_path or current_path
    link, _reason = camera.linked_original(selected) if selected else (None, "no source")
    wanted = {camera.path_key(selected)}
    if link: wanted.add(camera.path_key(link["source"]))
    wanted.discard("")
    records = []
    pool = _rv_call(project, "GetMediaPool") if project else None
    root = _rv_call(pool, "GetRootFolder") if pool else None
    pending, visited = ([root] if root else []), 0
    while pending and visited < 2000:
        folder = pending.pop()
        for clip in (_rv_call(folder, "GetClipList") or []):
            visited += 1
            path = rv_media_file_path(clip) or ""
            if camera.path_key(path) in wanted:
                records.append({"path": path, "metadata": _rv_call(clip, "GetMetadata") or {}, "properties": _rv_call(clip, "GetClipProperty") or {}})
        pending.extend(_rv_call(folder, "GetSubFolderList") or [])
    optics, provenance = camera.choose_record(selected, records)
    same_item = bool(selected and camera.path_key(selected) == camera.path_key(current_path))
    selected_records = [r for r in records if camera.path_key(r["path"]) == camera.path_key(selected)]
    props = (selected_records[0].get("properties") or {}) if selected_records else {}
    if same_item and not props: props = _rv_call(media, "GetClipProperty") or {}
    sizing = (_rv_call(item, "GetProperty") or {}) if same_item else {}
    allowed = ("Pan", "Tilt", "ZoomX", "ZoomY", "RotationAngle", "CropLeft", "CropRight", "CropTop", "CropBottom", "CropSoftness", "FlipX", "FlipY", "Scaling")
    snapshot = {"version": 1, "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source_path": selected, "source_key": camera.path_key(selected), "shot": request,
                "optics": optics, "provenance": provenance,
                "reference_geometry": {"resolution": props.get("Resolution"), "pixel_aspect": props.get("PAR") or props.get("Pixel Aspect Ratio"),
                    "sizing": {k: v for k,v in sizing.items() if k in allowed and isinstance(v, (str,int,float,bool))},
                    "timeline_width": _rv_call(timeline, "GetSetting", "timelineResolutionWidth") if timeline else None,
                    "timeline_height": _rv_call(timeline, "GetSetting", "timelineResolutionHeight") if timeline else None,
                    "scope": "available source sizing only; camera height, floor scale and pose unknown"},
                "sensor_crop": "unknown", "camera_height": "unknown",
                "reference_kind": "uncropped source media; identity cards excluded"}
    return snapshot


def h3_prompt_is_guide_shaped(text):
    return bool(re.search(r"^(detailed_description|integrated_multimodal_description):", text or "", re.M))


def h3_compose_opts(graph, request="", mode=None):

    moving_camera = bool(re.search(
        r"\b(?:tracking shot|dolly shot|camera\s+(?:tracks?|follows?|orbits?|dollies|moves?|pushes|pulls)|"
        r"(?:track|follow|orbit|dolly)\s+(?:the\s+)?camera)\b", request or "", re.I))
    has_source_video = False
    for node in (graph or {}).values():
        if isinstance(node, dict) and "ReferenceToVideo" in str(node.get("class_type") or ""):
            has_source_video = any(k.startswith("ref_videos.ref_video_") and isinstance(v, list) and len(v) == 2
                                   for k, v in (node.get("inputs") or {}).items())
            break
    angle = h3_v3_kind(graph) == "angle" or mode == "ANGLE"
    requested_view = bool(re.search(r"\b(?:over.the.shoulder|OTS|follow(?:s|ing)?|tracking|hard cuts?|cut to|reverse angle)\b", request or "", re.I))
    cuts = bool(re.search(r"\b(?:hard cuts?|cut to|cuts between|multiple shots)\b", request or "", re.I))
    match_source_camera = bool(re.search(r"\b(?:match|keep|preserve) (?:the )?(?:original |source )camera (?:position|framing)\b", request or "", re.I))
    return {"continuous_take": not cuts, "reframe": not match_source_camera or angle or moving_camera or requested_view}


def h3_prompt_for_prepass(prompt_text, picture_count):
    text = prompt_text or ""
    for number in sorted(set(int(n) for n in re.findall(r"<Picture (\d+)>", text))):
        if number <= picture_count:
            continue
        tag = re.escape("<Picture %d>" % number)
        text = "\n".join(line for line in text.split("\n")
                         if not re.match(r"\s*%s (is the first frame of \[Shot 1\]|\(\[Shot 1\] first frame\))" % tag, line))
        text = re.sub(r"The shot begins from %s, with (<Subject \d+>) fully present" % tag, r"\1 is fully present", text)
        text = re.sub(r"The shot begins from %s\. ?" % tag, "", text)
        if re.search(tag, text):
            raise SecondUnitError("First-frame anchor pre-pass: the prompt still cites <Picture %d>, which the pre-pass "
                                  "does not wire. Nothing was queued." % number)
    return text.replace("keyframe completion + ", "").replace(" + keyframe completion", "").replace(
        "[keyframe completion]", "[reference generation]")


def h3_expander_config(translator):
    env = dict(os.environ)
    for key in ("provider", "url", "model", "timeout", "effort", "chain"):
        name = "SECOND_UNIT_EXPANDER_" + key.upper()
        value = _cfg("expander_" + key, name, "")
        if value:
            env[name] = value
    key_file = _cfg("expander_key_file", "SECOND_UNIT_EXPANDER_KEY_FILE", "")
    if key_file and not env.get("SECOND_UNIT_EXPANDER_KEY"):
        try:
            with open(key_file, "r", encoding="utf-8") as handle:
                env["SECOND_UNIT_EXPANDER_KEY"] = handle.read().strip()
        except OSError:
            raise SecondUnitError("The configured prompt-expander credential file could not be read.")
    return translator.expander_config(env)


def compose_h3_prompt(prompt, graph):
    request = (prompt or "").strip()
    if h3_prompt_is_guide_shaped(request):
        return request
    translator = h3_translator()
    if translator is None:
        return compose_h3_prompt_legacy(prompt, graph)
    mode, refs = translator.refs_from_graph(graph)
    if mode is None:
        return request
    for picture in refs.get("pictures") or []:
        note = _CARD_ROLES.get(picture.get("image") or "")
        if note:
            picture["note"] = note
    opts = h3_compose_opts(graph, request)
    if hasattr(translator, "translate_with_report"):
        body, report = translator.translate_with_report(mode, refs, request, translator.duration_seconds(graph), opts)
        if report.get("held_back"):
            log("H3 prompt: held back from the submitted prompt: %s"
                % "; ".join("'%s' (%s)" % (s, why) for s, why in report["held_back"]))
    else:
        body = translator.translate(mode, refs, request, translator.duration_seconds(graph), opts)
    realism = any(isinstance(n, dict) and ("r34l1sm" in json.dumps(n.get("_meta") or {}).lower()
                  or "realism" in str(((n or {}).get("inputs") or {}).get("lora_name") or "").lower())
                  for n in graph.values())
    return ("r34l1sm. " + body) if realism else body


def compose_h3_prompt_legacy(prompt, graph):
    request = (prompt or "").strip()
    _ref_id, node = h3_reference_node(graph)
    if node is None:
        for candidate in graph.values():
            if isinstance(candidate, dict) and candidate.get("class_type") == "MiniMaxH3ImageToVideo":
                node = candidate
                break
    if node is None:
        return request
    inputs = node.get("inputs") or {}
    kind = h3_v3_kind(graph)
    pictures = sorted((k for k in inputs if k.startswith("ref_images.ref_image_") and is_link(inputs[k])),
                      key=lambda k: int(k.rsplit("_", 1)[1]))
    titles = {}
    for key in pictures:
        src_node = graph.get(str(inputs[key][0])) or {}
        titles[key] = str((src_node.get("_meta") or {}).get("title") or "").strip().lower()
    has_video = any(k.startswith("ref_videos.ref_video_") and is_link(inputs[k]) for k in inputs)
    has_depth = is_link(inputs.get("ref_videos.ref_video_1"))
    has_audio = any(k.startswith("ref_video_audios.") and is_link(inputs[k]) for k in inputs)
    lines = []
    if kind is None:
        for index, key in enumerate(pictures, start=1):
            title = titles.get(key, "")
            if "environment" in title:
                lines.append("<Picture %d> is the environment." % index)
            elif "identity" in title:
                lines.append("<Picture %d> is the performer's identity." % index)
            elif "wardrobe" in title:
                lines.append("<Picture %d> is the wardrobe." % index)
            elif "replacement" in title or "character" in title:
                lines.append("<Picture %d> is the replacement performer." % index)
            else:
                lines.append("<Picture %d> is a reference." % index)
        if has_video:
            lines.insert(0, "<Video 1> is the source performance: keep its motion, timing, camera and framing.")
        if has_audio:
            lines.append("<Audio 1> is the source soundtrack.")
        return "\n".join(lines + ([request] if request else []))


    environment_index = None
    if has_video:
        lines.append("<Video 1> (performance: pose sequence, body language, gesture timing, head turns, eye-line, "
                     "expression timing, mouth movement): fully_preserved - reproduced from the source performance.")
        if kind == "angle":
            lines.append("<Video 1> (framing): weak_reference - the source camera position, framing and shot scale are "
                         "discarded; the shot is re-staged from the camera described below. Timing and performance stay.")
        else:
            lines.append("<Video 1> (camera: position, motion, lens, framing, shot scale): fully_preserved.")
    if has_depth:
        lines.append("<Video 2> (camera and depth): fully_preserved - the measured depth of the same footage; it locks "
                     "camera, framing, pose timing and the position of everything in the frame.")
    identity_indexes = [index for index, key in enumerate(pictures, start=1)
                        if h3_v3_picture_role(titles.get(key, "")) in ("replacement", "identity")]
    if len(identity_indexes) >= 2:
        lines.append("<Subject 1> is one real performer jointly defined by %s: every one of these pictures shows "
                     "the same person and they are fused as complementary evidence of one identity - never "
                     "duplicates, relatives, alternate designs or extra characters. <Subject 1> keeps a complete "
                     "body: head, neck, shoulders, torso, arms and hands, exactly where the footage places them."
                     % ", ".join("<Picture %d>" % i for i in identity_indexes))
    for index, key in enumerate(pictures, start=1):
        role = h3_v3_picture_role(titles.get(key, ""))
        staged_name = str(((graph.get(str(inputs[key][0])) or {}).get("inputs") or {}).get("image") or "")
        card_role = _CARD_ROLES.get(staged_name)
        if role == "environment":
            environment_index = index
            lines.append("<Picture %d> (environment geometry, props and materials): fully_preserved - the shot is "
                         "relocated into this place; its lighting is replaced by the lighting described below." % index)
        elif role == "continuity":
            lines.append("<Picture %d> (set dressing, props, lighting, framing): fully_preserved - this is the previous "
                         "window of the same shot; continue it exactly." % index)
        elif role == "wardrobe":
            lines.append("<Picture %d> (wardrobe): attribute_transfer - the clothing exactly as shown, worn by the "
                         "performer for the whole shot." % index)
        elif role in ("replacement", "identity") and card_role:
            lines.append("<Picture %d> (identity - %s): attribute_transfer - the same <Subject 1>; take this view's "
                         "evidence of the person, never its framing, head size, angle or lighting." % (index, card_role))
        elif role in ("replacement", "identity") and len(identity_indexes) >= 2:
            lines.append("<Picture %d> (identity): attribute_transfer - the same <Subject 1>; this person's face, hair, "
                         "skin tone and build; its framing, head size, angle and lighting are discarded." % index)
        elif role in ("replacement", "identity"):
            lines.append("<Picture %d> (identity): attribute_transfer - take only this person's face, hair, skin tone "
                         "and build from it; its framing, head size, angle and lighting are discarded." % index)
        else:
            lines.append("<Picture %d> is a reference." % index)
    if environment_index and has_video:
        lines.append("<Video 1> (environment): weak_reference - the source location is discarded, replaced by "
                     "<Picture %d>." % environment_index)
    if has_audio:
        lines.append("<Video 1> (audio): fully_copy - the source performance audio is the soundtrack of this shot.")
    realism = any(isinstance(n, dict) and "r34l1sm" in json.dumps(n.get("_meta") or {}).lower()
                  or "realism" in str(((n or {}).get("inputs") or {}).get("lora_name") or "").lower()
                  for n in graph.values() if isinstance(n, dict))
    body = "\n".join(lines + ([request] if request else []))
    return ("r34l1sm. " + body) if realism else body




def compose_v2v_prompt(prompt, family, retention="LOCK_ALL", ingredient_role="SUBJECT",
                       edit_amount="BALANCED", has_ingredient=False):
    request = (prompt or "").strip()
    locks = V2V_LOCK_TEXT.get(retention, V2V_LOCK_TEXT["LOCK_ALL"])
    role = V2V_INGREDIENT_TEXT.get(ingredient_role, V2V_INGREDIENT_TEXT["SUBJECT"])
    amount = V2V_EDIT_TEXT.get(edit_amount, V2V_EDIT_TEXT["BALANCED"])
    ingredient_line = (
        " Use the supplied ingredient reference only for %s; do not transfer unrelated "
        "composition, pose, lighting, or background traits." % role
        if has_ingredient else ""
    )

    if family == "MINIMAXH3":
        subjects = [
            "<Video 1> is the source video being edited and defines the target motion, timing, camera, and shot structure.",
            "<Audio 1> is the synchronized source soundtrack and is reused in the target video.",
        ]
        if has_ingredient:
            subjects.append("<Subject 1> is the %s defined by <Picture 1>." % role)
        task = "video editing + audio reuse"
        if has_ingredient:
            task += " + reference generation"
        retention_lines = [
            "<Video 1>: fully_preserved - preserve %s." % locks,
            "<Audio 1>: fully_copy - reuse the synchronized source soundtrack.",
        ]
        if has_ingredient:
            retention_lines.append(
                "<Subject 1>: attribute_transfer - transfer only %s from <Picture 1>." % role)
        return (
            "subject_definitions:\n%s\n\n"
            "summary:\n[%s] The target video is an edited version of <Video 1>. %s\n\n"
            "retention_analysis:\n%s\n\n"
            "detailed_description:\n[Shot 1] %s Preserve %s.%s %s\n\n"
            "overall_soundscape:\nReuse the synchronized source soundtrack from <Audio 1>.\n\n"
            "non_diegetic_music:\nPreserve the source video's existing music; add none."
        ) % ("\n".join(subjects), task, request, "\n".join(retention_lines),
             request, locks, ingredient_line, amount)

    return (
        "EDIT REQUEST: %s\n"
        "SOURCE LOCKS: Preserve %s.\n"
        "EDIT AMOUNT: %s%s\n"
        "FAIL CONDITIONS: no unintended identity drift, camera change, background change, "
        "warping, double edges, temporal flicker, crawling texture, or broken occlusion."
    ) % (request, locks, amount, ingredient_line)


def compose_swap_prompt(prompt, family):
    request = (prompt or "").strip()
    if family == "MINIMAXH3":
        return (
            "subject_definitions:\n"
            "<Video 1> is the source performance and defines timing, pose, body motion, "
            "camera, composition, lighting, background, and synchronized sound.\n"
            "<Subject 1> is the replacement performer defined by <Picture 1>.\n\n"
            "summary:\n[character replacement + audio reuse] %s\n\n"
            "retention_analysis:\n"
            "<Video 1>: fully_preserved except for the performer's identity and requested wardrobe.\n"
            "<Subject 1>: attribute_transfer - transfer face, hair, skin tone, body appearance, "
            "and requested wardrobe only; never transfer pose, framing, lighting, or background.\n\n"
            "detailed_description:\n[Shot 1] Replace only the source performer with <Subject 1>. "
            "Keep the original performance, eyeline, lip and body motion, occlusion, camera, "
            "environment, timing, and shot boundaries exactly coherent. %s\n\n"
            "overall_soundscape:\nReuse the synchronized source soundtrack unchanged."
        ) % (request, request)
    return (
        "CHARACTER REPLACEMENT: %s\n"
        "SOURCE VIDEO OWNS: performance, pose, expression timing, body motion, camera, "
        "composition, lighting, background, occlusion, duration, and sound.\n"
        "REFERENCE STILL OWNS: replacement face, hair, skin tone, body appearance, and only "
        "the wardrobe explicitly requested. Do not copy its pose, framing, lighting, or background.\n"
        "CONTINUITY: keep one recognizable replacement identity in every frame with coherent "
        "facial geometry, hands, edges, motion blur, and interactions.\n"
        "FAIL CONDITIONS: no source-identity leakage, face morphing, double performer, changed "
        "camera, changed environment, temporal flicker, halos, warping, or broken occlusion."
    ) % request


def compose_environment_relight_prompt(environment_prompt):
    return (
        "Keep the identical subject, face, hair, skin, body, wardrobe, performance, pose, "
        "and motion. Change only the light, colour interaction, reflections, and contact "
        "shadow so the subject belongs naturally in this new environment: %s. Preserve "
        "facial geometry and all clothing construction; create physically coherent key, "
        "fill, rim, bounce, spill, and shadow from the described set."
    ) % (environment_prompt or "the generated environment").strip()


def compose_environment_swap_prompt(environment_prompt):
    request = (environment_prompt or "").strip()
    return (
        "ENVIRONMENT REPLACEMENT: %s\n"
        "SOURCE FOOTAGE OWNS: the protected subject, identity, face, hair, skin, body, "
        "wardrobe, performance, pose, motion, camera, framing, timing, occlusion, and audio.\n"
        "SET REFERENCE OWNS: the replacement environment's architecture, geography, "
        "materials, props, colour palette, atmosphere, and lighting intent. Do not copy "
        "people, text, logos, or the reference image's camera framing.\n"
        "COMPOSITE: rebuild only the environment around the tracked subject, preserve clean "
        "occlusion boundaries, and create coherent contact shadows, reflections, spill, and "
        "perspective throughout the shot."
    ) % request


def compose_ltx_world_generation_prompt(_environment_prompt):
    return (
        "REFERENCE-LOCKED HERO ENVIRONMENT RE-PHOTOGRAPH.\n"
        "OUTPUT CONTRACT: Create one continuous, full-frame, photoreal live-action shot. "
        "The reference-locked Qwen hero frame is the sole visual owner of the replacement "
        "world and wardrobe. Do not redesign either one from text.\n"
        "VIDEO 1 OWNS: exact performance, choreography, body movement, timing, "
        "composition, framing, camera motion, and source audio.\n"
        "COMPOSITE DEPTH CONTROL OWNS: Depth Anything V3 source depth and camera path, "
        "the retargeted persistent-world geometry, parallax, occlusion, and spatial "
        "relationships. Preserve Video 1's camera trajectory.\n"
        "SAM 3.1 OWNS ONLY SCENE UNDERSTANDING: face and skin, hair, anatomical body "
        "occupancy, source-clothing exclusion, props, and background boundaries. SAM does "
        "not grant the source wardrobe visual ownership.\n"
        "PICTURE 1 OWNS, BY DIRECT IMAGE REFERENCE: the replacement world's architecture, "
        "geography, vegetation, materials, lighting, atmosphere, and colour palette. "
        "Preserve its recognizable structures, material language, palette, and lighting.\n"
        "PICTURE 2 OWNS: actor identity only. Never borrow pose, framing, light, camera, "
        "or background from Picture 2.\n"
        "PICTURE 3 OWNS, BY DIRECT IMAGE REFERENCE: the complete replacement wardrobe - "
        "garment design, cut, silhouette, construction, layering, materials, colours, "
        "textures, trim, hardware, accessories, footwear, and fit. Do not invent, simplify, "
        "or substitute any garment component from text.\n"
        "PICTURES 4 AND 5 OWN: the appearance, construction, materials, scale, and details "
        "of the requested props. Video 1 owns how carried or touched props move.\n"
        "FIT PICTURE 3'S WARDROBE TO THE ACTOR DEFINED BY VIDEO 1 AND PICTURE 2. Generate "
        "physically appropriate folds, tension, compression, secondary motion, collision, "
        "and contact. Do not preserve source clothing merely because it appears in Video 1 "
        "or the occupancy masks.\n"
        "REGENERATE ACTOR, WARDROBE, PROPS, AND WORLD TOGETHER. Seat them naturally in "
        "Picture 1's world with coherent key, fill, rim, bounce, fog, contact shadow, "
        "reflections, occlusion, depth of field, and motion blur. Preserve recognizable "
        "facial geometry and natural skin, hair, eye, hand, and fabric detail.\n"
        "Do not paste the source actor over a generated background. Do not preserve the "
        "source garment silhouette. Do not borrow pose, framing, background, or camera from "
        "Pictures 2-5. Never output a collage, contact sheet, image grid, split screen, "
        "reference panel, or catalog view."
    )


def compose_qwen_world_hero_prompt(_environment_prompt):
    return (
        "Reference-locked edit. Image 1 is the source performance frame and owns the exact "
        "actor identity, face, hair, anatomy, pose, hands, camera, composition, and framing. "
        "Image 2 is the sole visual source for the replacement environment. Reproduce its "
        "recognizable world, structures, geography, vegetation, materials, palette, lighting, "
        "and atmosphere; do not redesign them from text. Image 3 is the sole visual source "
        "for the complete replacement wardrobe. Reproduce its exact garment design, cut, "
        "silhouette, construction, layers, materials, colors, textures, trim, hardware, "
        "accessories, and footwear; do not invent or simplify them. Regenerate the actor, "
        "garment, and world together. Fit Image 3's wardrobe to Image 1's body without "
        "borrowing pose or framing. Integrate actor, garment, and world as one "
        "photoreal live-action exposure with natural skin, fabric response, environmental "
        "light, contact shadows, reflections, and occlusion. Output one frame only."
    )


def compose_h3_environment_swap_prompt(_environment_prompt):
    return (
        "HERO ENVIRONMENT RE-PHOTOGRAPH FROM THE SUPPLIED REFERENCES.\n"
        "<Video 1> OWNS: the exact performance, choreography, body movement, timing, composition, "
        "framing, and camera motion. Its synchronized source audio is remuxed unchanged after "
        "generation and is not sent through H3 conditioning.\n"
        "<Video 2> OWNS: the Picture 1 world reconstructed by Depth Anything V3 and rendered "
        "through <Video 1>'s recovered camera path. Preserve its parallax, camera structure, "
        "and spatial relationships while taking final appearance from <Picture 1>.\n"
        "<Video 3> OWNS: SAM 3.1 performer occupancy and anatomical silhouette through time, "
        "including face, hair, torso, limbs, hands, and feet. <Video 3> does NOT own the source "
        "wardrobe's appearance, construction, material, color, or garment silhouette when wardrobe "
        "replacement is requested.\n"
        "<Picture 1> OWNS: the replacement world's architecture, geography, vegetation, materials, "
        "lighting, atmosphere, and colour palette.\n"
        "<Picture 2> OWNS: actor identity only.\n"
        "<Picture 3> OWNS: complete replacement wardrobe - garment design, cut, silhouette, "
        "construction, layering, materials, colors, textures, trim, hardware, accessories, and footwear.\n"
        "FIT <Picture 3>'S WARDROBE TO THE ACTOR DEFINED BY <Video 1> AND <Picture 2>. The wardrobe must "
        "follow <Video 1>'s body motion while generating physically appropriate cloth deformation, "
        "folds, tension, compression, secondary motion, and collision. Do not preserve the source "
        "clothing merely because it appears in <Video 1> or <Video 3>.\n"
        "REGENERATE actor, wardrobe, and world together. The actor and new wardrobe must naturally "
        "exist inside <Picture 1>'s world with coherent environmental key, fill, rim, bounce, fog, "
        "contact shadow, reflections, occlusion, and motion blur.\n"
        "Do not paste the source actor over a generated background. Do not borrow pose, framing, "
        "background, or camera from <Picture 2> or <Picture 3>."
    )


def validate_ltx_world_generation_contract(graph):
    def node(node_id):
        return graph.get(str(node_id)) or {}

    def linked(inputs, key, expected, label, output=None):
        value = (inputs or {}).get(key)
        if not is_link(value):
            raise SecondUnitError("LTX World Generation is missing %s (%s)." % (label, key))
        upstream = node(value[0])
        expected_types = set(expected if isinstance(expected, (tuple, list, set)) else (expected,))
        if upstream.get("class_type") not in expected_types:
            raise SecondUnitError(
                "LTX World Generation %s must come from %s, not %s."
                % (label, "/".join(sorted(expected_types)),
                   upstream.get("class_type") or "an unknown node")
            )
        if output is not None and value[1] != output:
            raise SecondUnitError(
                "LTX World Generation %s uses output %s instead of %s."
                % (label, value[1], output)
            )
        return str(value[0]), upstream

    reference_titles = {
        "picture 1: target world / environment": "target world",
        "picture 2: actor identity only": "actor identity",
        "picture 3: complete replacement wardrobe": "replacement wardrobe",
        "picture 4: prop 1": "prop 1",
        "picture 5: prop 2": "prop 2",
    }
    references = {}
    for title, label in reference_titles.items():
        matches = [
            (str(node_id), item) for node_id, item in graph.items()
            if isinstance(item, dict) and item.get("class_type") == "LoadImage"
            and str((item.get("_meta") or {}).get("title") or "").lower() == title
        ]
        if len(matches) != 1:
            raise SecondUnitError(
                "LTX World Generation needs exactly one %s loader, found %d."
                % (label, len(matches))
            )
        references[title] = matches[0][0]

    source_da3 = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "DepthAnything_V3"
        and "da3 source" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    world_da3 = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "DepthAnything_V3"
        and "world reconstruction" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    proxy_depth = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "DepthAnything_V3"
        and "world depth from retargeted camera" in
        str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    bridges = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "SecondUnitRetargetWorldProxy"
    ]
    if not (len(source_da3) == len(world_da3) == len(proxy_depth) == len(bridges) == 1):
        raise SecondUnitError(
            "LTX World Generation needs one source DA3, one world DA3, one proxy-depth DA3, "
            "and one Second Unit WorldBridge."
        )
    source_da3_id, source_da3_node = source_da3[0]
    world_da3_id, world_da3_node = world_da3[0]
    proxy_depth_id, proxy_depth_node = proxy_depth[0]
    bridge_id, bridge = bridges[0]
    world_reference_id = references["picture 1: target world / environment"]
    if (world_da3_node.get("inputs") or {}).get("images") != [world_reference_id, 0]:
        raise SecondUnitError("LTX World Generation DA3 does not reconstruct Picture 1.")
    pointcloud_id, pointcloud = linked(
        bridge.get("inputs") or {}, "pointcloud", "DA3_MultiViewPointCloud",
        "persistent-world point cloud", 0,
    )
    point_inputs = pointcloud.get("inputs") or {}
    if (point_inputs.get("depths") != [world_da3_id, 0]
            or point_inputs.get("images") != [world_da3_id, 2]
            or point_inputs.get("extrinsics") != [world_da3_id, 5]
            or point_inputs.get("intrinsics") != [world_da3_id, 6]):
        raise SecondUnitError("LTX World Generation point cloud is not owned by Picture 1 DA3.")
    bridge_inputs = bridge.get("inputs") or {}
    if (bridge_inputs.get("source_extrinsics") != [source_da3_id, 8]
            or bridge_inputs.get("source_intrinsics") != [source_da3_id, 9]
            or bridge_inputs.get("world_extrinsics") != [world_da3_id, 5]
            or bridge_inputs.get("world_intrinsics") != [world_da3_id, 6]):
        raise SecondUnitError("LTX World Generation WorldBridge lost its source/world camera ownership.")
    if (proxy_depth_node.get("inputs") or {}).get("images") != [bridge_id, 0]:
        raise SecondUnitError("LTX World Generation world depth is not rendered from the retargeted world.")

    pre_sam = {
        str((item.get("_meta") or {}).get("title") or "").lower(): str(node_id)
        for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "easy sam3VideoSegmentation"
        and "sam 3.1 pre:" in str((item.get("_meta") or {}).get("title") or "").lower()
    }
    required_sam = {
        "sam 3.1 pre: face / skin", "sam 3.1 pre: hair", "sam 3.1 pre: body",
        "sam 3.1 pre: source clothing - exclusion", "sam 3.1 pre: props",
    }
    if set(pre_sam) != required_sam:
        raise SecondUnitError(
            "LTX World Generation needs FACE/SKIN, HAIR, BODY, SOURCE CLOTHING, and PROPS "
            "SAM 3.1 branches."
        )

    blends = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LayerUtility: ImageBlendAdvance V3"
        and "z-aware composite depth" in
        str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(blends) != 1:
        raise SecondUnitError("LTX World Generation needs one z-aware composite-depth node.")
    depth_composite_id, depth_composite = blends[0]
    blend_inputs = depth_composite.get("inputs") or {}
    if (blend_inputs.get("layer_image") != [source_da3_id, 0]
            or blend_inputs.get("background_image") != [proxy_depth_id, 0]
            or blend_inputs.get("blend_mode") != "lighten"
            or not is_link(blend_inputs.get("layer_mask"))):
        raise SecondUnitError(
            "LTX World Generation composite depth must be masked source depth over world depth "
            "with nearest/brightest depth winning."
        )

    depths = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LTXAddVideoICLoRAGuideAdvanced"
        and "z-aware actor + world depth" in
        str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(depths) != 1:
        raise SecondUnitError("LTX World Generation needs one Union composite-depth guide.")
    depth_id, depth = depths[0]
    if (depth.get("inputs") or {}).get("image") != [depth_composite_id, 0]:
        raise SecondUnitError("LTX World Generation Union Control is not using composite depth.")

    hero_prompts = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "TextEncodeQwenImageEditPlus"
        and str((item.get("_meta") or {}).get("title") or "").lower()
        == "hero frame compositor prompt"
    ]
    hero_negatives = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "TextEncodeQwenImageEditPlus"
        and str((item.get("_meta") or {}).get("title") or "").lower()
        == "hero frame compositor negative"
    ]
    if len(hero_prompts) != 1 or len(hero_negatives) != 1:
        raise SecondUnitError(
            "LTX World Generation needs one local Qwen hero-frame prompt and negative encoder."
        )
    hero_prompt_id, hero_prompt = hero_prompts[0]
    hero_negative_id, hero_negative = hero_negatives[0]
    hero_inputs = hero_prompt.get("inputs") or {}
    hero_negative_inputs = hero_negative.get("inputs") or {}
    wardrobe_reference_id = references["picture 3: complete replacement wardrobe"]
    world_lock_id, world_lock = linked(
        hero_inputs, "image2", "ImageScaleToTotalPixels",
        "bounded direct Picture 1 world reference", 0,
    )
    wardrobe_lock_id, wardrobe_lock = linked(
        hero_inputs, "image3", "ImageScaleToTotalPixels",
        "bounded direct Picture 3 wardrobe reference", 0,
    )
    for label, lock, source_id in (
            ("world", world_lock, world_reference_id),
            ("wardrobe", wardrobe_lock, wardrobe_reference_id)):
        lock_inputs = lock.get("inputs") or {}
        megapixels = lock_inputs.get("megapixels")
        if (lock_inputs.get("image") != [source_id, 0]
                or not isinstance(megapixels, (int, float))
                or megapixels > 0.30):
            raise SecondUnitError(
                "The Qwen %s reference lock must preserve its direct loader and stay at "
                "or below 0.30 MP for the Fast memory contract." % label
            )
    if (hero_negative_inputs.get("image2") != [world_lock_id, 0]
            or hero_negative_inputs.get("image3") != [wardrobe_lock_id, 0]):
        raise SecondUnitError(
            "Qwen positive and negative conditioning do not share the same bounded direct "
            "world and wardrobe references."
        )
    hero_source_scale_id, hero_source_scale = linked(
        hero_inputs, "image1", "FluxKontextImageScale", "hero-pose source scale", 0,
    )
    linked(hero_source_scale.get("inputs") or {}, "image", "ImageFromBatch",
           "Video 1 hero-pose frame", 0)

    hero_samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "KSampler"
        and "qwen hero frame" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(hero_samplers) != 1:
        raise SecondUnitError("LTX World Generation needs one Qwen hero-frame sampler.")
    hero_sampler_id, hero_sampler = hero_samplers[0]
    hero_sampler_inputs = hero_sampler.get("inputs") or {}
    if (hero_sampler_inputs.get("steps") != 4 or hero_sampler_inputs.get("cfg") != 1
            or hero_sampler_inputs.get("sampler_name") != "euler"
            or hero_sampler_inputs.get("scheduler") != "simple"):
        raise SecondUnitError("The Fast Qwen hero composer must use its 4-step Lightning Euler contract.")
    positive_method_id, positive_method = linked(
        hero_sampler_inputs, "positive", "FluxKontextMultiReferenceLatentMethod",
        "Qwen positive multi-reference method", 0,
    )
    negative_method_id, negative_method = linked(
        hero_sampler_inputs, "negative", "FluxKontextMultiReferenceLatentMethod",
        "Qwen negative multi-reference method", 0,
    )
    if ((positive_method.get("inputs") or {}).get("conditioning") != [hero_prompt_id, 0]
            or (negative_method.get("inputs") or {}).get("conditioning")
            != [hero_negative_id, 0]
            or (positive_method.get("inputs") or {}).get("reference_latents_method")
            != "index_timestep_zero"
            or (negative_method.get("inputs") or {}).get("reference_latents_method")
            != "index_timestep_zero"):
        raise SecondUnitError(
            "Qwen multi-reference latent methods are bypassed or crossed."
        )
    hero_source_latent_id, hero_source_latent = linked(
        hero_sampler_inputs, "latent_image", "VAEEncode",
        "Qwen source-frame latent", 0,
    )
    if (hero_source_latent.get("inputs") or {}).get("pixels") != [hero_source_scale_id, 0]:
        raise SecondUnitError("Qwen hero latent is not encoded from Video 1's first frame.")
    qwen_models = [
        item for item in graph.values() if isinstance(item, dict)
        and item.get("class_type") == "UNETLoader"
        and "qwen_image_edit_2509_fp8_e4m3fn_official.safetensors" ==
        model_ref_basename((item.get("inputs") or {}).get("unet_name") or "")
    ]
    qwen_loras = [
        item for item in graph.values() if isinstance(item, dict)
        and item.get("class_type") == "LoraLoaderModelOnly"
        and "qwen-image-edit-2509-lightning-4steps" in
        str((item.get("inputs") or {}).get("lora_name") or "").lower()
    ]
    if len(qwen_models) != 1 or len(qwen_loras) != 1:
        raise SecondUnitError(
            "Fast World Generation requires the verified Qwen 2509 FP8 model and matching 4-step LoRA."
        )
    hero_decodes = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "VAEDecode"
        and (item.get("inputs") or {}).get("samples") == [hero_sampler_id, 0]
    ]
    if len(hero_decodes) != 1:
        raise SecondUnitError("The Qwen hero frame is not decoded exactly once.")
    hero_decode_id = hero_decodes[0][0]
    qwen_releases = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "VRAM_Debug"
        and "release qwen" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if (len(qwen_releases) != 1
            or (qwen_releases[0][1].get("inputs") or {}).get("any_input")
            != [hero_decode_id, 0]):
        raise SecondUnitError("The Qwen hero model is not released before the LTX video pass.")
    hero_release_id = qwen_releases[0][0]
    hero_i2v = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LTXVImgToVideoInplace"
        and "hero frame / look frame" in
        str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(hero_i2v) != 1:
        raise SecondUnitError("LTX World Generation needs one hero-frame I2V conditioner.")
    hero_i2v_id, hero_i2v_node = hero_i2v[0]
    hero_i2v_inputs = hero_i2v_node.get("inputs") or {}
    if hero_i2v_inputs.get("image") != [hero_release_id, 0]:
        raise SecondUnitError("The LTX opening frame is not the Qwen-composed hero frame.")
    empty_id, _empty = linked(hero_i2v_inputs, "latent", "EmptyLTXVLatentVideo",
                              "empty regeneration latent", 0)
    if (depth.get("inputs") or {}).get("latent") != [hero_i2v_id, 0]:
        raise SecondUnitError("Union depth must be applied after hero-frame conditioning.")

    concats = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LTXVConcatAVLatent"
        and (item.get("inputs") or {}).get("video_latent") == [depth_id, 2]
    ]
    if len(concats) != 1:
        raise SecondUnitError("LTX World Generation must concatenate audio after Union depth.")
    concat_id = concats[0][0]
    samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "SamplerCustomAdvanced"
        and (item.get("inputs") or {}).get("latent_image") == [concat_id, 0]
    ]
    if len(samplers) != 1:
        raise SecondUnitError("LTX World Generation first sampler is not fed by its final AV concat.")
    first_sampler_id = samplers[0][0]
    crops = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LTXVCropGuides"
        and (item.get("inputs") or {}).get("positive") == [depth_id, 0]
        and (item.get("inputs") or {}).get("negative") == [depth_id, 1]
    ]
    if len(crops) != 1:
        raise SecondUnitError("LTX World Generation does not crop its hidden guide frames.")

    inpaint = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "LTXICLoRALoaderModelOnly"
        and "in-outpainting" in str((item.get("inputs") or {}).get("lora_name") or "").lower()
    ]
    quality = bool(inpaint)
    post_sam = [
        str(node_id) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "easy sam3VideoSegmentation"
        and "sam 3.1 post:" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if (quality and len(post_sam) != 1) or (not quality and post_sam):
        raise SecondUnitError(
            "LTX World Generation Best quality needs one post-SAM repair tracker; Fast needs none."
        )

    saves = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "SaveVideo"
    ]
    if len(saves) != 1:
        raise SecondUnitError("LTX World Generation needs exactly one SaveVideo delivery.")
    ancestors = set()
    stack = [saves[0][0]]
    while stack:
        current = str(stack.pop())
        if current in ancestors:
            continue
        ancestors.add(current)
        for value in (node(current).get("inputs") or {}).values():
            if is_link(value):
                stack.append(str(value[0]))
    pasted = [item for item in ancestors if node(item).get("class_type") == "ImageCompositeMasked"]
    if pasted:
        raise SecondUnitError(
            "LTX World Generation delivery still contains an original-pixel paste-back (%s)."
            % ", ".join(sorted(pasted))
        )
    temporal_ingredients = [
        item for item in ancestors
        if node(item).get("class_type") == "LTXICLoRALoaderModelOnly"
        and "ingredients" in str(
            (node(item).get("inputs") or {}).get("lora_name") or "").lower()
    ]
    if temporal_ingredients:
        raise SecondUnitError(
            "LTX World Generation uses direct Qwen world/wardrobe references; an incompatible "
            "Ingredients adapter is still active in the temporal delivery path (%s)."
            % ", ".join(sorted(temporal_ingredients))
        )

    return {
        "references": references, "source_da3": source_da3_id, "world_da3": world_da3_id,
        "pointcloud": pointcloud_id, "bridge": bridge_id, "world_depth": proxy_depth_id,
        "depth_composite": depth_composite_id,
        "empty": empty_id, "depth": depth_id, "hero_prompt": hero_prompt_id,
        "hero_negative": hero_negative_id, "hero_mask": None,
        "hero_frame": hero_decode_id, "hero_sampler": hero_sampler_id,
        "world_reference_lock": world_lock_id,
        "wardrobe_reference_lock": wardrobe_lock_id,
        "hero_positive_method": positive_method_id,
        "hero_negative_method": negative_method_id,
        "concat": concat_id, "sampler": first_sampler_id, "quality": quality,
        "post_sam": post_sam[0] if post_sam else None,
    }


def validate_ltx_environment_contract(graph):
    def node(node_id):
        return graph.get(str(node_id)) or {}

    def linked(inputs, key, class_type, label):
        value = (inputs or {}).get(key)
        if not is_link(value):
            raise SecondUnitError("LTX Environment Swap %s has no linked %s input." % (label, key))
        upstream = node(value[0])
        if upstream.get("class_type") != class_type:
            raise SecondUnitError(
                "LTX Environment Swap %s.%s must come from %s, not %s."
                % (label, key, class_type, upstream.get("class_type") or "an unknown node")
            )
        return str(value[0]), upstream

    references = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "LTXAddVideoICLoRAGuide"
        and "environment reference" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(references) != 1:
        raise SecondUnitError(
            "LTX Environment Swap needs exactly one target-environment IC-LoRA guide, found %d."
            % len(references)
        )
    reference_id, reference = references[0]
    reference_inputs = reference.get("inputs") or {}
    repeat_id, repeat = linked(
        reference_inputs, "image", "RepeatImageBatch", "target-environment guide",
    )
    linked(repeat.get("inputs") or {}, "image", "LoadImage", "target-environment repeat")
    depth_id, depth = linked(
        reference_inputs, "latent", "LTXAddVideoICLoRAGuideAdvanced",
        "target-environment guide",
    )
    depth_inputs = depth.get("inputs") or {}
    mask_id, mask_setter = linked(
        depth_inputs, "latent", "LTXVSetVideoLatentNoiseMasks", "depth guide",
    )
    mask_inputs = mask_setter.get("inputs") or {}
    linked(mask_inputs, "samples", "VAEEncode", "pass-A mask setter")
    _preprocess_id, preprocess = linked(
        mask_inputs, "masks", "LTXVPreprocessMasks", "pass-A mask setter",
    )
    preprocess_inputs = preprocess.get("inputs") or {}
    if (preprocess_inputs.get("ignore_first_mask") is not False
            or preprocess_inputs.get("clamp_min") != 0.0
            or preprocess_inputs.get("clamp_max") != 1.0):
        raise SecondUnitError(
            "LTX Environment Swap pass A must preserve the tracked 0..1 spatial mask on every frame."
        )
    grow_id, grow = linked(
        preprocess_inputs, "masks", "GrowMaskWithBlur", "pass-A mask preprocessing",
    )
    grow_inputs = grow.get("inputs") or {}
    if grow_inputs.get("expand") != 0 or grow_inputs.get("blur_radius") != 2.0:
        raise SecondUnitError(
            "LTX Environment Swap subject protection must use the production 0 px / 2 px "
            "matte edge; a wide protected fringe preserves the old green screen."
        )

    concats = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "LTXVConcatAVLatent"
        and (item.get("inputs") or {}).get("video_latent") == [reference_id, 2]
    ]
    if len(concats) != 1:
        raise SecondUnitError(
            "LTX Environment Swap must concatenate audio after the target-environment guide."
        )
    concat_id = concats[0][0]
    samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "SamplerCustomAdvanced"
        and (item.get("inputs") or {}).get("latent_image") == [concat_id, 0]
    ]
    if len(samplers) != 1:
        raise SecondUnitError("LTX Environment Swap pass A sampler is not fed by the final AV concat.")
    sampler_id = samplers[0][0]
    crops = [
        item for item in graph.values()
        if isinstance(item, dict)
        and item.get("class_type") == "LTXVCropGuides"
        and (item.get("inputs") or {}).get("positive") == [reference_id, 0]
        and (item.get("inputs") or {}).get("negative") == [reference_id, 1]
    ]
    if len(crops) != 1:
        raise SecondUnitError("LTX Environment Swap pass A does not crop its hidden guide frames.")
    separate_id, separate = linked(
        crops[0].get("inputs") or {}, "latent", "LTXVSeparateAVLatent", "pass-A guide crop",
    )
    if (separate.get("inputs") or {}).get("av_latent") != [sampler_id, 0]:
        raise SecondUnitError("LTX Environment Swap pass-A crop is not downstream of its sampler.")

    relight_guides = []
    for node_id, item in graph.items():
        if not isinstance(item, dict) or item.get("class_type") != "LTXAddVideoICLoRAGuideAdvanced":
            continue
        image_link = (item.get("inputs") or {}).get("image")
        if is_link(image_link) and node(image_link[0]).get("class_type") == "ImageCompositeMasked":
            relight_guides.append((str(node_id), item))
    if len(relight_guides) != 1:
        raise SecondUnitError(
            "LTX Environment Swap needs exactly one masked relight guide, found %d."
            % len(relight_guides)
        )
    relight_id, relight = relight_guides[0]
    relight_mask_id, relight_mask = linked(
        relight.get("inputs") or {}, "latent", "LTXVSetVideoLatentNoiseMasks", "relight guide",
    )
    relight_mask_inputs = relight_mask.get("inputs") or {}
    linked(relight_mask_inputs, "samples", "VAEEncode", "relight mask setter")
    _relight_pre_id, relight_pre = linked(
        relight_mask_inputs, "masks", "LTXVPreprocessMasks", "relight mask setter",
    )
    relight_pre_inputs = relight_pre.get("inputs") or {}
    if (relight_pre_inputs.get("ignore_first_mask") is not False
            or relight_pre_inputs.get("clamp_min") != 0.0
            or relight_pre_inputs.get("clamp_max") != 0.35):
        raise SecondUnitError(
            "LTX Environment Swap relight must keep the subject mask at 0..0.35 on every frame."
        )
    relight_concats = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "LTXVConcatAVLatent"
        and (item.get("inputs") or {}).get("video_latent") == [relight_id, 2]
    ]
    if len(relight_concats) != 1:
        raise SecondUnitError("LTX Environment Swap must concatenate audio after the relight guide.")
    relight_concat_id = relight_concats[0][0]
    relight_samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "SamplerCustomAdvanced"
        and (item.get("inputs") or {}).get("latent_image") == [relight_concat_id, 0]
    ]
    if len(relight_samplers) != 1:
        raise SecondUnitError("LTX Environment Swap relight sampler is not fed by its final AV concat.")
    relight_sampler_id = relight_samplers[0][0]
    relight_crops = [
        item for item in graph.values()
        if isinstance(item, dict)
        and item.get("class_type") == "LTXVCropGuides"
        and (item.get("inputs") or {}).get("positive") == [relight_id, 0]
        and (item.get("inputs") or {}).get("negative") == [relight_id, 1]
    ]
    if len(relight_crops) != 1:
        raise SecondUnitError("LTX Environment Swap relight does not crop its hidden guide frames.")
    _relight_separate_id, relight_separate = linked(
        relight_crops[0].get("inputs") or {}, "latent", "LTXVSeparateAVLatent",
        "relight guide crop",
    )
    if (relight_separate.get("inputs") or {}).get("av_latent") != [relight_sampler_id, 0]:
        raise SecondUnitError("LTX Environment Swap relight crop is not downstream of its sampler.")

    return {
        "mask": mask_id, "grow": grow_id, "depth": depth_id, "reference": reference_id,
        "repeat": repeat_id, "concat": concat_id, "sampler": sampler_id,
        "separate": separate_id,
        "relight_mask": relight_mask_id, "relight": relight_id,
    }


def _validate_h3_legacy_environment_contract(graph):
    generators = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "MiniMaxH3ReferenceToVideo"
    ]
    if len(generators) != 1:
        raise SecondUnitError(
            "The H3 environment preset needs exactly one Ref2VA generator, found %d."
            % len(generators)
        )
    generator_id, generator = generators[0]
    inputs = generator.get("inputs") or {}

    def source(key, expected, label, output=None):
        value = inputs.get(key)
        if not is_link(value):
            raise SecondUnitError(
                "H3 Environment Swap is missing its %s reference socket (%s)."
                % (label, key)
            )
        node_id = str(value[0])
        upstream = graph.get(node_id) or {}
        if upstream.get("class_type") != expected:
            raise SecondUnitError(
                "H3 Environment Swap %s must come from %s, not %s."
                % (label, expected, upstream.get("class_type") or "an unknown node")
            )
        if output is not None and value[1] != output:
            raise SecondUnitError(
                "H3 Environment Swap %s uses output %s instead of %s."
                % (label, value[1], output)
            )
        return node_id, upstream

    set_id, _set_loader = source(
        "ref_images.ref_image_0", "LoadImage", "target-set still", 0,
    )
    contaminated = sorted(
        key for key in inputs
        if key.startswith("ref_videos.") or key.startswith("ref_video_audios.")
    )
    if contaminated:
        raise SecondUnitError(
            "H3 Environment Swap must not condition its clean set plate on the old "
            "environment (%s)." % ", ".join(contaminated)
        )

    sam_nodes = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "easy sam3VideoSegmentation"
    ]
    if len(sam_nodes) != 1:
        raise SecondUnitError("H3 Environment Swap needs exactly one SAM subject tracker.")
    work_link = (sam_nodes[0][1].get("inputs") or {}).get("video_frames")
    if not is_link(work_link):
        raise SecondUnitError("H3 Environment Swap SAM tracker has no working source video.")
    work_id = str(work_link[0])
    work = graph.get(work_id) or {}
    if work.get("class_type") != "ImageScaleToTotalPixels" or work_link[1] != 0:
        raise SecondUnitError(
            "H3 Environment Swap SAM tracker must use the 0.8 MP working source video."
        )
    work_input = (work.get("inputs") or {}).get("image")
    if not is_link(work_input):
        raise SecondUnitError("H3 Environment Swap working plate has no source video.")
    loader_id = str(work_input[0])
    loader = graph.get(loader_id) or {}
    if loader.get("class_type") != "VHS_LoadVideo" or work_input[1] != 0:
        raise SecondUnitError(
            "H3 Environment Swap working plate must come from VHS_LoadVideo images."
        )
    grow_nodes = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "GrowMaskWithBlur"
        and (item.get("inputs") or {}).get("mask") == [sam_nodes[0][0], 0]
    ]
    if len(grow_nodes) != 1:
        raise SecondUnitError("H3 Environment Swap has no unique tracked-subject matte.")
    grow_id, grow = grow_nodes[0]
    grow_inputs = grow.get("inputs") or {}
    if grow_inputs.get("expand") != 0 or grow_inputs.get("blur_radius") != 2.0:
        raise SecondUnitError(
            "H3 Environment Swap subject protection must use the production 0 px / 2 px "
            "matte edge; a wide matte preserves the old environment fringe."
        )

    samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "SamplerCustomAdvanced"
        and (item.get("inputs") or {}).get("latent_image") == [generator_id, 1]
    ]
    if len(samplers) != 1:
        raise SecondUnitError("H3 Environment Swap sampler is not fed by its Ref2VA latent.")
    composite_nodes = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict)
        and item.get("class_type") == "ImageCompositeMasked"
        and "actor" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(composite_nodes) != 1:
        raise SecondUnitError(
            "The H3 environment preset needs one protected-subject pixel composite."
        )
    return {
        "generator": generator_id, "set_reference": set_id,
        "source_video": loader_id, "working_video": work_id,
        "sam": sam_nodes[0][0], "grow": grow_id,
        "sampler": samplers[0][0], "composite": composite_nodes[0][0],
    }


def validate_h3_environment_contract(graph):
    def node(node_id):
        return graph.get(str(node_id)) or {}

    def linked(inputs, key, expected, label, output=None):
        value = (inputs or {}).get(key)
        if not is_link(value):
            raise SecondUnitError("H3 Environment Swap is missing %s (%s)." % (label, key))
        upstream = node(value[0])
        expected_types = set(expected if isinstance(expected, (tuple, list, set)) else (expected,))
        if upstream.get("class_type") not in expected_types:
            raise SecondUnitError(
                "H3 Environment Swap %s must come from %s, not %s."
                % (label, "/".join(sorted(expected_types)), upstream.get("class_type") or "an unknown node")
            )
        if output is not None and value[1] != output:
            raise SecondUnitError(
                "H3 Environment Swap %s uses output %s instead of %s."
                % (label, value[1], output)
            )
        return str(value[0]), upstream

    generators = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "MiniMaxH3ReferenceToVideo"
    ]
    if len(generators) != 1:
        raise SecondUnitError(
            "The H3 environment preset needs exactly one Ref2VA generator, found %d."
            % len(generators)
        )
    generator_id, generator = generators[0]
    inputs = generator.get("inputs") or {}

    expected_keys = {
        "ref_images.ref_image_0", "ref_images.ref_image_1", "ref_images.ref_image_2",
        "ref_videos.ref_video_0", "ref_videos.ref_video_1", "ref_videos.ref_video_2",
    }
    actual_dynamic = {
        key for key in inputs
        if key.startswith("ref_images.") or key.startswith("ref_videos.")
        or key.startswith("ref_video_audios.")
    }
    allowed_dynamic = (expected_keys, expected_keys | {"ref_video_audios.ref_video_audio_0"})
    if actual_dynamic not in allowed_dynamic:
        raise SecondUnitError(
            "H3 Environment Swap reference sockets changed; expected %s, found %s."
            % (", ".join(sorted(expected_keys)), ", ".join(sorted(actual_dynamic)))
        )

    reference_titles = {
        "ref_images.ref_image_0": "environment beauty - picture 1",
        "ref_images.ref_image_1": "actor identity - picture 2",
        "ref_images.ref_image_2": "wardrobe - picture 3",
    }
    reference_ids = {}
    for key, title in reference_titles.items():
        reference_id, reference = linked(inputs, key, "LoadImage", title, 0)
        if title not in str((reference.get("_meta") or {}).get("title") or "").lower():
            raise SecondUnitError("H3 Environment Swap %s loader lost its ownership title." % title)
        reference_ids[key] = reference_id

    source_scale_id, source_scale = linked(
        inputs, "ref_videos.ref_video_0", "ImageScale", "Video 1 source performance", 0,
    )
    world_scale_id, world_scale = linked(
        inputs, "ref_videos.ref_video_1", "ImageScale", "Video 2 DA3 world/camera control", 0,
    )
    mask_scale_id, mask_scale = linked(
        inputs, "ref_videos.ref_video_2", "ImageScale", "Video 3 SAM performer control", 0,
    )
    work_id, work = linked(
        source_scale.get("inputs") or {}, "image", "ImageScaleToTotalPixels", "source working video", 0,
    )
    loader_id, loader = linked(
        work.get("inputs") or {}, "image", "VHS_LoadVideo", "source performance loader", 0,
    )
    audio_link = inputs.get("ref_video_audios.ref_video_audio_0")
    if audio_link is not None and audio_link != [loader_id, 2]:
        raise SecondUnitError("H3 Environment Swap source audio does not belong to Video 1.")

    world_scale_input = (world_scale.get("inputs") or {}).get("image")
    world_purge_id = None
    if is_link(world_scale_input) and node(world_scale_input[0]).get("class_type") == "LayerUtility: PurgeVRAM V2":
        world_purge_id, world_purge = linked(
            world_scale.get("inputs") or {}, "image", "LayerUtility: PurgeVRAM V2",
            "post-DA3 memory handoff", 0,
        )
        world_proxy_id, world_proxy = linked(
            world_purge.get("inputs") or {}, "anything", "SecondUnitRetargetWorldProxy",
            "retargeted Picture 1 world video", 0,
        )
    else:
        world_proxy_id, world_proxy = linked(
            world_scale.get("inputs") or {}, "image", "SecondUnitRetargetWorldProxy",
            "retargeted Picture 1 world video", 0,
        )
    world_proxy_inputs = world_proxy.get("inputs") or {}
    source_extrinsics = world_proxy_inputs.get("source_extrinsics")
    source_intrinsics = world_proxy_inputs.get("source_intrinsics")
    if (not is_link(source_extrinsics) or not is_link(source_intrinsics)
            or str(source_extrinsics[0]) != str(source_intrinsics[0])
            or source_extrinsics[1] != 8 or source_intrinsics[1] != 9):
        raise SecondUnitError(
            "H3 Video 2 must use one DA3 source-camera solve (extrinsics 8 / intrinsics 9)."
        )
    da3_id = str(source_extrinsics[0])
    if node(da3_id).get("class_type") != "DepthAnything_V3":
        raise SecondUnitError("H3 Video 2 source camera does not come from Depth Anything V3.")
    da3_inputs = node(da3_id).get("inputs") or {}
    if da3_inputs.get("images") != [work_id, 0]:
        raise SecondUnitError("H3 Environment Swap DA3 control does not analyze Video 1.")

    pointcloud_id, pointcloud = linked(
        world_proxy_inputs, "pointcloud", "DA3_MultiViewPointCloud",
        "persistent Picture 1 point cloud", 0,
    )
    pointcloud_inputs = pointcloud.get("inputs") or {}
    world_da3_link = pointcloud_inputs.get("depths")
    if not is_link(world_da3_link) or world_da3_link[1] != 0:
        raise SecondUnitError("H3 persistent world has no Picture 1 DA3 depth reconstruction.")
    world_da3_id = str(world_da3_link[0])
    world_da3 = node(world_da3_id)
    if world_da3.get("class_type") != "DepthAnything_V3":
        raise SecondUnitError("H3 persistent world depth is not produced by Depth Anything V3.")
    environment_id = reference_ids["ref_images.ref_image_0"]
    if (world_da3.get("inputs") or {}).get("images") != [environment_id, 0]:
        raise SecondUnitError("H3 persistent world must reconstruct Picture 1, not Video 1.")
    expected_world_links = {
        "images": [world_da3_id, 2], "extrinsics": [world_da3_id, 5],
        "intrinsics": [world_da3_id, 6], "confidence": [world_da3_id, 1],
        "sky_mask": [world_da3_id, 7],
    }
    for key, expected in expected_world_links.items():
        if pointcloud_inputs.get(key) != expected:
            raise SecondUnitError("H3 persistent-world %s link changed." % key)
    if (world_proxy_inputs.get("world_extrinsics") != [world_da3_id, 5]
            or world_proxy_inputs.get("world_intrinsics") != [world_da3_id, 6]
            or world_proxy_inputs.get("background_image") != [environment_id, 0]):
        raise SecondUnitError(
            "H3 Video 2 is no longer the Picture 1 world rendered through Video 1's camera."
        )

    purge_id, purge = linked(
        mask_scale.get("inputs") or {}, "image", "LayerUtility: PurgeVRAM V2", "pre-H3 memory handoff", 0,
    )
    mask_image_id, mask_image = linked(
        purge.get("inputs") or {}, "anything", "MaskToImage", "SAM guidance video", 0,
    )
    grow_id, grow = linked(
        mask_image.get("inputs") or {}, "mask", "GrowMaskWithBlur", "SAM performer edge", 0,
    )
    grow_inputs = grow.get("inputs") or {}
    if grow_inputs.get("expand") != 0 or grow_inputs.get("blur_radius") != 2.0:
        raise SecondUnitError("H3 performer guidance must use the production 0 px / 2 px SAM edge.")
    pre_sam = {
        str((item.get("_meta") or {}).get("title") or "").lower(): (str(node_id), item)
        for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "easy sam3VideoSegmentation"
        and "pre:" in str((item.get("_meta") or {}).get("title") or "").lower()
    }
    required_pre = {
        "sam 3.1 pre: face / skin", "sam 3.1 pre: hair", "sam 3.1 pre: body",
        "sam 3.1 pre: source clothing - exclusion", "sam 3.1 pre: props",
    }
    if set(pre_sam) != required_pre:
        raise SecondUnitError("H3 Environment Swap no longer exposes all five authored SAM masks.")
    for title, (_sam_id, sam_node) in pre_sam.items():
        if (sam_node.get("inputs") or {}).get("video_frames") != [work_id, 0]:
            raise SecondUnitError("H3 %s does not analyze Video 1." % title)

    anatomy_id, anatomy = linked(
        grow_inputs, "mask", "AddMask", "anatomical occupancy combiner", 0,
    )
    hair_id = pre_sam["sam 3.1 pre: hair"][0]
    face_id = pre_sam["sam 3.1 pre: face / skin"][0]
    body_id = pre_sam["sam 3.1 pre: body"][0]
    clothing_id = pre_sam["sam 3.1 pre: source clothing - exclusion"][0]
    anatomy_inputs = anatomy.get("inputs") or {}
    fast_body_core = (
        is_link(anatomy_inputs.get("mask1"))
        and node(anatomy_inputs["mask1"][0]).get("class_type") == "SubtractMask"
        and is_link(anatomy_inputs.get("mask2"))
        and node(anatomy_inputs["mask2"][0]).get("class_type") == "GrowMaskWithBlur"
    )
    if fast_body_core:

        body_core_id, body_core = anatomy_id, anatomy
        body_face_id = None
    else:
        if anatomy_inputs.get("mask2") != [hair_id, 0]:
            raise SecondUnitError("H3 Video 3 no longer adds the authored hair occupancy mask.")
        body_face_id, body_face = linked(
            anatomy_inputs, "mask1", "AddMask", "body plus face occupancy", 0,
        )
        if (body_face.get("inputs") or {}).get("mask2") != [face_id, 0]:
            raise SecondUnitError("H3 Video 3 no longer adds the authored face/skin mask.")
        body_core_id, body_core = linked(
            body_face.get("inputs") or {}, "mask1", "AddMask", "body occupancy core", 0,
        )
    exposed_id, exposed = linked(
        body_core.get("inputs") or {}, "mask1", "SubtractMask", "source-clothing exclusion", 0,
    )
    if ((exposed.get("inputs") or {}).get("mask1") != [body_id, 0]
            or (exposed.get("inputs") or {}).get("mask2") != [clothing_id, 0]):
        raise SecondUnitError("H3 Video 3 must subtract SOURCE CLOTHING from the body mask.")
    clothing_core_id, clothing_core = linked(
        body_core.get("inputs") or {}, "mask2", "GrowMaskWithBlur", "inner body occupancy", 0,
    )
    clothing_core_inputs = clothing_core.get("inputs") or {}
    if (clothing_core_inputs.get("mask") != [clothing_id, 0]
            or clothing_core_inputs.get("expand") != -12
            or clothing_core_inputs.get("blur_radius") != 8.0):
        raise SecondUnitError(
            "H3 source clothing must be reduced to the authored -12 px / 8 px inner body core."
        )

    post_sam = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "easy sam3VideoSegmentation"
        and "post:" in str((item.get("_meta") or {}).get("title") or "").lower()
    ]
    if len(post_sam) != 1:
        raise SecondUnitError("H3 Environment Swap needs exactly one post-H3 SAM QC tracker.")

    preflights = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "MiniMaxH3Preflight"
        and (item.get("inputs") or {}).get("conditioning") == [generator_id, 0]
        and (item.get("inputs") or {}).get("samples") == [generator_id, 1]
    ]
    latent_owner = preflights[0][0] if len(preflights) == 1 else generator_id
    samplers = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "SamplerCustomAdvanced"
        and (item.get("inputs") or {}).get("latent_image") == [latent_owner, 1]
    ]
    if len(samplers) != 1:
        raise SecondUnitError("H3 Environment Swap sampler is not fed by its Ref2VA latent.")
    trims = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "ImageFromBatch"
        and (item.get("_meta") or {}).get("title") == "SECOND UNIT EXACT ENVIRONMENT FRAME TRIM"
    ]
    if len(trims) != 1:
        raise SecondUnitError("H3 Environment Swap needs one exact delivery-frame trim.")
    trim_id = trims[0][0]
    creators = [
        (str(node_id), item) for node_id, item in graph.items()
        if isinstance(item, dict) and item.get("class_type") == "CreateVideo"
        and (item.get("inputs") or {}).get("images") == [trim_id, 0]
    ]
    if len(creators) != 1:
        raise SecondUnitError("H3 final video is not fed directly by the trimmed H3 regeneration.")
    creator_id, creator = creators[0]
    if (creator.get("inputs") or {}).get("audio") != [loader_id, 2]:
        raise SecondUnitError(
            "H3 final delivery must preserve Video 1 source audio instead of regenerated audio."
        )
    hard_composites = [
        item for item in graph.values()
        if isinstance(item, dict) and item.get("class_type") == "ImageCompositeMasked"
    ]
    if hard_composites:
        raise SecondUnitError("H3 hero environment swap must not paste source actor pixels over the final image.")

    return {
        "generator": generator_id,
        "environment_reference": reference_ids["ref_images.ref_image_0"],
        "identity_reference": reference_ids["ref_images.ref_image_1"],
        "wardrobe_reference": reference_ids["ref_images.ref_image_2"],
        "source_video": loader_id, "working_video": work_id,
        "da3": da3_id, "pre_sam": body_id, "pre_sam_masks": dict(
            (title, item[0]) for title, item in pre_sam.items()),
        "post_sam": post_sam[0][0],
        "grow": grow_id, "purge": purge_id,
        "anatomy": anatomy_id, "body_face": body_face_id, "body_core": body_core_id,
        "clothing_exclusion": exposed_id, "clothing_core": clothing_core_id,
        "source_control": source_scale_id, "world_control": world_scale_id,
        "depth_control": world_scale_id, "world_da3": world_da3_id,
        "pointcloud": pointcloud_id, "world_proxy": world_proxy_id,
        "world_purge": world_purge_id, "preflight": preflights[0][0] if preflights else None,
        "mask_control": mask_scale_id, "sampler": samplers[0][0], "trim": trim_id,
        "creator": creator_id,
    }


def patch_environment_swap_graph(graph, prompt, negative, subject_query, relight,
                                 exact_frames):
    family = infer_graph_family("", graph)
    query = (subject_query or "").strip()
    if not query:
        raise SecondUnitError(
            "Environment Swap needs a subject-mask query such as 'man in black jacket'."
        )
    sam_nodes = [
        (str(node_id), node) for node_id, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "easy sam3VideoSegmentation"
    ]
    ltx_world = bool(
        family == "LTX25" and any(
            isinstance(node, dict)
            and node.get("class_type") == "SecondUnitRetargetWorldProxy"
            for node in graph.values()
        )
    )
    post_sam = []
    if family == "MINIMAXH3" or ltx_world:
        pre_sam = {
            str((node.get("_meta") or {}).get("title") or "").lower(): node_id
            for node_id, node in sam_nodes
            if "pre:" in str((node.get("_meta") or {}).get("title") or "").lower()
        }
        post_sam = [node_id for node_id, node in sam_nodes
                    if "post:" in str((node.get("_meta") or {}).get("title") or "").lower()]
        required_pre = {
            "sam 3.1 pre: face / skin": "visible face and skin of %s",
            "sam 3.1 pre: hair": "hair of %s",
            "sam 3.1 pre: body": (
                "%s anatomical body occupancy including head torso arms hands legs and feet"
            ),
            "sam 3.1 pre: source clothing - exclusion": "source clothing worn by %s",
            "sam 3.1 pre: props": "props held touched or carried by %s",
        }
        if set(pre_sam) != set(required_pre) or (
                family == "MINIMAXH3" and len(post_sam) != 1):
            raise SecondUnitError(
                "%s World Generation needs FACE/SKIN, HAIR, BODY, SOURCE CLOTHING, PROPS%s."
                % ("H3" if family == "MINIMAXH3" else "LTX 2.5",
                   ", and one post-H3 SAM tracker" if family == "MINIMAXH3" else "")
            )
        for title, template in required_pre.items():
            graph[pre_sam[title]].setdefault("inputs", {})["prompt"] = template % query
        for post_id in post_sam:
            graph[post_id].setdefault("inputs", {})["prompt"] = (
                query + " including face hair hands and target clothing"
            )
        subject_sam_id = pre_sam["sam 3.1 pre: body"]
    else:
        if len(sam_nodes) != 1:
            raise SecondUnitError(
                "Environment Swap expected one SAM 3.1 subject tracker, found %d."
                % len(sam_nodes)
            )
        subject_sam_id = sam_nodes[0][0]
        graph[subject_sam_id].setdefault("inputs", {})["prompt"] = query

    if family == "LTX25" and ltx_world:
        contract = validate_ltx_world_generation_contract(graph)
        positives = []
        negatives = []
        hero_positives = []
        hero_negatives = []
        repair_positives = []
        repair_negatives = []
        for node_id, node in graph.items():
            if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
                continue
            title = str((node.get("_meta") or {}).get("title") or "").lower()
            if title == "world generation prompt":
                positives.append(str(node_id))
            elif title == "world generation negative":
                negatives.append(str(node_id))
            elif title == "quality repair prompt":
                repair_positives.append(str(node_id))
            elif title == "quality repair negative":
                repair_negatives.append(str(node_id))
        for node_id, node in graph.items():
            if not isinstance(node, dict) or node.get("class_type") != "TextEncodeQwenImageEditPlus":
                continue
            title = str((node.get("_meta") or {}).get("title") or "").lower()
            if title == "hero frame compositor prompt":
                hero_positives.append(str(node_id))
            elif title == "hero frame compositor negative":
                hero_negatives.append(str(node_id))
        expected_repair = 1 if contract["quality"] else 0
        if (len(positives) != 1 or len(negatives) != 1
                or len(hero_positives) != 1 or len(hero_negatives) != 1
                or len(repair_positives) != expected_repair
                or len(repair_negatives) != expected_repair):
            raise SecondUnitError(
                "The LTX World Generation prompt ownership changed; refusing an ambiguous edit."
            )
        graph[positives[0]]["inputs"]["text"] = compose_ltx_world_generation_prompt(prompt)
        graph[hero_positives[0]]["inputs"]["prompt"] = compose_qwen_world_hero_prompt(prompt)
        negative_text = (negative or graph[negatives[0]]["inputs"].get("text") or "").strip()
        required_negative = LTX_WORLD_REQUIRED_NEGATIVE.lower()
        if required_negative not in negative_text.lower():
            negative_text = ", ".join(
                part for part in (negative_text, LTX_WORLD_REQUIRED_NEGATIVE) if part
            )

        graph[hero_negatives[0]]["inputs"]["prompt"] = ""
        if negative_text:
            graph[negatives[0]]["inputs"]["text"] = negative_text
        if contract["quality"]:
            graph[repair_positives[0]]["inputs"]["text"] = (
                "PHOTOREAL HERO FINISH FOR THE REFERENCE-LOCKED WORLD GENERATION. Preserve the "
                "regenerated identity, complete target wardrobe and props, performance, camera, "
                "world geometry, lighting direction, timing, and source audio. Refine only "
                "natural face, skin, eyes, hair, hands, cloth microstructure, contact shadows, "
                "reflections, atmosphere, and stable photographic detail."
            )
            if negative_text:
                graph[repair_negatives[0]]["inputs"]["text"] = negative_text
        return {
            "family": family, "sam": subject_sam_id,
            "post_sam": contract.get("post_sam"), "positive": positives[0],
            "negative": negatives[0], "relight": bool(contract["quality"]),
            "quick_changes": [], "trim": None, "contract": contract,
        }

    if family == "LTX25":
        contract = validate_ltx_environment_contract(graph)
        graph[contract["repeat"]].setdefault("inputs", {})["amount"] = int(exact_frames)
        env_positive = []
        relight_positive = []
        negatives = []
        for node_id, node in graph.items():
            if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
                continue
            title = str((node.get("_meta") or {}).get("title") or "").lower()
            if "new environment" in title:
                env_positive.append(str(node_id))
            elif "relight prompt" in title:
                relight_positive.append(str(node_id))
            elif "negative" in title:
                negatives.append(str(node_id))
        if len(env_positive) != 1 or len(relight_positive) != 1 or len(negatives) != 2:
            raise SecondUnitError(
                "The LTX environment preset no longer exposes one environment prompt, one "
                "relight prompt, and two negative prompts; refusing an ambiguous edit."
            )
        graph[env_positive[0]]["inputs"]["text"] = compose_environment_swap_prompt(prompt)
        graph[relight_positive[0]]["inputs"]["text"] = compose_environment_relight_prompt(prompt)
        if negative:
            for node_id in negatives:
                graph[node_id]["inputs"]["text"] = negative

        quick_changes = []
        if not relight:
            previews = [node for node in graph.values()
                        if isinstance(node, dict)
                        and node.get("class_type") == "PreviewImage"
                        and "environment swap" in str((node.get("_meta") or {}).get("title") or "").lower()]
            loaders = [str(node_id) for node_id, node in graph.items()
                       if isinstance(node, dict) and node.get("class_type") == "VHS_LoadVideo"]
            creators = [str(node_id) for node_id, node in graph.items()
                        if isinstance(node, dict) and node.get("class_type") == "CreateVideo"]
            preview_link = ((previews[0].get("inputs") or {}).get("images")
                            if len(previews) == 1 else None)
            if (not is_link(preview_link) or len(loaders) != 1 or len(creators) != 1):
                raise SecondUnitError(
                    "The LTX environment preset's pass-A output cannot be isolated safely."
                )
            creator_inputs = graph[creators[0]].setdefault("inputs", {})
            creator_inputs["images"] = [str(preview_link[0]), preview_link[1]]
            creator_inputs["audio"] = [loaders[0], 2]
            quick_changes = [creators[0]]
        return {
            "family": family, "sam": subject_sam_id, "positive": env_positive[0],
            "negative": negatives[0], "relight": bool(relight),
            "quick_changes": quick_changes, "trim": None, "contract": contract,
        }

    if family == "MINIMAXH3":
        contract = validate_h3_environment_contract(graph)
        if (negative or "").strip():
            raise SecondUnitError(
                "MiniMax H3 Environment Swap has no negative-conditioning channel. Clear the "
                "Negative box; converting negative words into positive prompt text can generate "
                "the exact unwanted objects."
            )
        generators = [str(node_id) for node_id, node in graph.items()
                      if isinstance(node, dict)
                      and node.get("class_type") == "MiniMaxH3ReferenceToVideo"]
        if len(generators) != 1:
            raise SecondUnitError("The H3 environment preset needs one Ref2VA generator.")
        generator_inputs = graph[generators[0]].setdefault("inputs", {})
        generator_inputs["prompt"] = compose_h3_environment_swap_prompt(prompt)
        trim_id = contract["trim"]
        graph[trim_id].setdefault("inputs", {})["length"] = int(exact_frames)
        return {
            "family": family, "sam": subject_sam_id, "post_sam": post_sam[0],
            "positive": generators[0],
            "negative": None, "relight": False, "quick_changes": [], "trim": trim_id,
            "contract": contract,
        }

    raise SecondUnitError(
        "Environment Swap is currently release-gated for LTX 2.5 and MiniMax H3, not %s."
        % (family or "this model")
    )


def _next_graph_node_id(graph):
    numeric = [int(str(key)) for key in graph if str(key).isdigit()]
    if numeric:
        return str(max(numeric) + 1)
    index = 1
    while "su_ingredient_%d" % index in graph:
        index += 1
    return "su_ingredient_%d" % index


def _rewire_graph_links(graph, replacements):
    def rewrite(value):
        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int)):
            key = (str(value[0]), value[1])
            if key in replacements:
                target = replacements[key]
                return [target[0], target[1]]
            return value
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    for node in graph.values():
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"] = rewrite(node["inputs"])


def apply_v2v_edit_amount(graph, edit_amount):
    inplace_strength = {"SUBTLE": 0.86, "BALANCED": 0.72, "STRONG": 0.56}
    guide_strength = {"SUBTLE": 1.15, "BALANCED": 1.0, "STRONG": 0.78}
    img2img_sigmas = {
        "SUBTLE": "0.88, 0.725, 0.421875, 0.0",
        "BALANCED": "0.909375, 0.725, 0.421875, 0.0",
        "STRONG": "0.94, 0.909375, 0.725, 0.421875, 0.0",
    }
    nodes = [(str(node_id), node) for node_id, node in graph.items() if isinstance(node, dict)]
    img2img = (
        any(n.get("class_type") == "LTXVImgToVideoInplace"
            and isinstance((n.get("inputs") or {}).get("strength"), (int, float)) for _i, n in nodes)
        and any(n.get("class_type") == "ManualSigmas"
                and isinstance((n.get("inputs") or {}).get("sigmas"), str) for _i, n in nodes)
    )
    changes = []
    for node_id, node in nodes:
        inputs = node.get("inputs") or {}
        class_type = node.get("class_type")
        if class_type == "LTXVImgToVideoInplace" and isinstance(inputs.get("strength"), (int, float)):
            if img2img:
                inputs["strength"] = 0.0
            else:
                inputs["strength"] = inplace_strength.get(edit_amount, inplace_strength["BALANCED"])
            changes.append((node_id, "strength", inputs["strength"]))
        elif class_type == "ManualSigmas" and img2img and isinstance(inputs.get("sigmas"), str):
            inputs["sigmas"] = img2img_sigmas.get(edit_amount, img2img_sigmas["BALANCED"])
            changes.append((node_id, "sigmas", inputs["sigmas"]))
        elif class_type == "LTXVAddGuide" and isinstance(inputs.get("strength"), (int, float)):
            inputs["strength"] = guide_strength.get(edit_amount, guide_strength["BALANCED"])
            changes.append((node_id, "strength", inputs["strength"]))
    return changes


def inject_ltx_vram_handoffs(graph, family):
    if family not in ("LTX23", "LTX25"):
        return []

    guide_classes = {
        "LTXVAddGuide", "LTXAddVideoICLoRAGuide",
        "LTXAddVideoICLoRAGuideAdvanced",
    }
    guide_sources = [
        (str(node_id), 2, str(node.get("class_type")))
        for node_id, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") in guide_classes
    ]
    encoder_sources = [
        (str(node_id), 0, str(node.get("class_type")))
        for node_id, node in graph.items()
        if isinstance(node, dict)
        and node.get("class_type") in ("LTXVImgToVideoInplace", "VAEEncode")
    ]

    concat_sources = [
        (str(node_id), 0, str(node.get("class_type")))
        for node_id, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "LTXVConcatAVLatent"
    ]
    if family == "LTX25" and (guide_sources or encoder_sources) and concat_sources:
        sources = concat_sources
    elif guide_sources:
        sources = guide_sources
    else:
        sources = encoder_sources

    changes = []
    for source_id, output_index, source_class in sources:
        source_link = (source_id, output_index)
        used = any(
            value == [source_id, output_index]
            for node in graph.values() if isinstance(node, dict)
            for value in (node.get("inputs") or {}).values()
        )
        if not used:
            continue
        handoff_id = _next_graph_node_id(graph)

        _rewire_graph_links(graph, {source_link: (handoff_id, 0)})
        graph[handoff_id] = {
            "class_type": "VRAM_Debug",
            "inputs": {
                "empty_cache": True,
                "gc_collect": True,
                "unload_all_models": True,
                "any_input": [source_id, output_index],
            },
            "_meta": {
                "title": "SECOND UNIT RELEASE SOURCE VAE BEFORE LTX SAMPLER",
            },
        }
        changes.append({
            "node": handoff_id,
            "source": source_id,
            "source_class": source_class,
            "source_output": output_index,
        })
    return changes


def inject_v2v_ingredient(graph, staged_name, ingredient_strength=1.0):
    family = infer_graph_family("", graph)
    loader_id = _next_graph_node_id(graph)
    graph[loader_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": staged_name},
        "_meta": {"title": "SECOND UNIT V2V INGREDIENT"},
    }

    if family == "MINIMAXH3":
        targets = [str(node_id) for node_id, node in graph.items()
                   if isinstance(node, dict)
                   and node.get("class_type") == "MiniMaxH3ReferenceToVideo"]
        if len(targets) != 1:
            raise SecondUnitError(
                "This MiniMax H3 V2V preset has %d Ref2VA conditioning nodes; the panel needs exactly one to wire an ingredient."
                % len(targets)
            )
        target_id = targets[0]
        inputs = graph[target_id].setdefault("inputs", {})

        slot = 0
        while "ref_images.ref_image_%d" % slot in inputs:
            slot += 1
        if slot >= 9:
            raise SecondUnitError("MiniMax H3 already uses all nine reference-image slots.")
        dynamic_key = "ref_images.ref_image_%d" % slot
        inputs[dynamic_key] = [loader_id, 0]
        return {"family": family, "loader": loader_id, "conditioning": target_id,
                "slot": dynamic_key}

    if family not in ("LTX23", "LTX25"):
        raise SecondUnitError("Ingredient conditioning is supported for LTX and MiniMax H3 V2V presets, not %s." % (family or "this model"))

    ingredient_lora_id = None
    if family == "LTX25":
        existing = [str(node_id) for node_id, node in graph.items()
                    if isinstance(node, dict)
                    and "ingredients" in str((node.get("inputs") or {}).get("lora_name") or "").lower()]
        if existing:
            ingredient_lora_id = existing[-1]
        else:
            model_ids = [str(node_id) for node_id, node in graph.items()
                         if isinstance(node, dict) and node.get("class_type") == "UNETLoader"]
            if len(model_ids) != 1:
                raise SecondUnitError(
                    "This LTX 2.5 preset has %d UNET loaders; the Ingredients LoRA needs exactly one base model."
                    % len(model_ids)
                )
            model_id = model_ids[0]
            ingredient_lora_id = _next_graph_node_id(graph)

            _rewire_graph_links(graph, {(model_id, 0): (ingredient_lora_id, 0)})
            graph[ingredient_lora_id] = {
                "class_type": "LTXICLoRALoaderModelOnly",
                "inputs": {
                    "model": [model_id, 0],
                    "lora_name": LTX25_INGREDIENT_LORA,
                    "strength_model": 1.0,
                },
                "_meta": {"title": "SECOND UNIT LTX 2.5 INGREDIENTS IC-LORA"},
            }

    guide_classes = {"LTXVAddGuide", "LTXAddVideoICLoRAGuide"}
    guide_ids = [str(node_id) for node_id, node in graph.items()
                 if isinstance(node, dict) and node.get("class_type") in guide_classes]
    guide_id = _next_graph_node_id(graph)
    if guide_ids:

        source_id = sorted(guide_ids, key=lambda key: (int(key) if key.isdigit() else 10**9, key))[-1]
        source_inputs = graph[source_id].get("inputs") or {}
        replacements = {
            (source_id, 0): (guide_id, 0),
            (source_id, 1): (guide_id, 1),
            (source_id, 2): (guide_id, 2),
        }
        _rewire_graph_links(graph, replacements)
        guide_inputs = {
            "positive": [source_id, 0], "negative": [source_id, 1],
            "vae": copy.deepcopy(source_inputs.get("vae")),
            "latent": [source_id, 2], "image": [loader_id, 0],
            "frame_idx": 0, "strength": float(ingredient_strength),
        }
    else:
        conditioning = [str(node_id) for node_id, node in graph.items()
                        if isinstance(node, dict) and node.get("class_type") == "LTXVConditioning"]
        latents = [str(node_id) for node_id, node in graph.items()
                   if isinstance(node, dict) and node.get("class_type") == "LTXVImgToVideoInplace"]
        if not latents:
            latents = [str(node_id) for node_id, node in graph.items()
                       if isinstance(node, dict) and node.get("class_type") == "EmptyLTXVLatentVideo"]
        if len(conditioning) != 1 or len(latents) != 1:
            raise SecondUnitError(
                "This LTX V2V preset does not expose one conditioning node and one video latent, so an ingredient cannot be wired safely."
            )
        cond_id, latent_id = conditioning[0], latents[0]
        latent_inputs = graph[latent_id].get("inputs") or {}
        replacements = {
            (cond_id, 0): (guide_id, 0),
            (cond_id, 1): (guide_id, 1),
            (latent_id, 0): (guide_id, 2),
        }
        _rewire_graph_links(graph, replacements)
        vae_link = copy.deepcopy(latent_inputs.get("vae"))
        if not vae_link:
            video_vaes = [str(node_id) for node_id, node in graph.items()
                          if isinstance(node, dict)
                          and node.get("class_type") == "VAELoader"
                          and "video" in str((node.get("inputs") or {}).get("vae_name") or "").lower()]
            if len(video_vaes) == 1:
                vae_link = [video_vaes[0], 0]
        guide_inputs = {
            "positive": [cond_id, 0], "negative": [cond_id, 1],
            "vae": vae_link,
            "latent": [latent_id, 0], "image": [loader_id, 0],
            "frame_idx": 0, "strength": float(ingredient_strength),
        }

    if not guide_inputs.get("vae"):
        raise SecondUnitError("The LTX source guide has no VAE link; ingredient wiring was refused.")
    guide_class = "LTXAddVideoICLoRAGuide" if family == "LTX25" else "LTXVAddGuide"
    if guide_class == "LTXAddVideoICLoRAGuide":
        guide_inputs.update({
            "latent_downscale_factor": 1.0,
            "crop": "disabled",
            "use_tiled_encode": False,
            "tile_size": 256,
            "tile_overlap": 64,
        })
    graph[guide_id] = {
        "class_type": guide_class,
        "inputs": guide_inputs,
        "_meta": {"title": "SECOND UNIT INGREDIENT GUIDE"},
    }
    crop_id = None
    if family == "LTX25":
        crops = [str(node_id) for node_id, node in graph.items()
                 if isinstance(node, dict) and node.get("class_type") == "LTXVCropGuides"]
        if crops:
            crop_id = crops[-1]
            crop_inputs = graph[crop_id].setdefault("inputs", {})
            crop_inputs["positive"] = [guide_id, 0]
            crop_inputs["negative"] = [guide_id, 1]
        else:
            separates = [str(node_id) for node_id, node in graph.items()
                         if isinstance(node, dict)
                         and node.get("class_type") == "LTXVSeparateAVLatent"]
            if len(separates) != 1:
                raise SecondUnitError(
                    "This LTX 2.5 preset has %d AV latent splitters; the ingredient guide "
                    "cannot be cropped to the requested clip length safely." % len(separates)
                )
            separate_id = separates[0]
            crop_id = _next_graph_node_id(graph)

            _rewire_graph_links(graph, {(separate_id, 0): (crop_id, 2)})
            graph[crop_id] = {
                "class_type": "LTXVCropGuides",
                "inputs": {
                    "positive": [guide_id, 0],
                    "negative": [guide_id, 1],
                    "latent": [separate_id, 0],
                },
                "_meta": {"title": "SECOND UNIT CROP INGREDIENT GUIDE FRAMES"},
            }
    return {"family": family, "loader": loader_id, "conditioning": guide_id,
            "slot": "image", "lora": ingredient_lora_id, "crop": crop_id}


def source_loader_node(graph, mode):
    target = find_source_input(graph, mode)
    if not target:
        return None, None
    return str(target[0]), graph.get(str(target[0])) or {}


def source_loader_dims(graph, mode):
    _nid, node = source_loader_node(graph, mode)
    inputs = (node or {}).get("inputs") or {}
    try:
        width, height = int(inputs.get("custom_width") or 0), int(inputs.get("custom_height") or 0)
    except (TypeError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None


def source_loader_rate(graph, mode):
    _nid, node = source_loader_node(graph, mode)
    try:
        rate = float(((node or {}).get("inputs") or {}).get("force_rate") or 0)
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def inject_frame_sequence_loader(graph, mode, frames):
    loader_id, loader = source_loader_node(graph, mode)
    if not loader_id:
        raise SecondUnitError("%s graph has no clip loader to replace with a frame sequence" % mode)
    class_type = loader.get("class_type")
    if class_type not in ("VHS_LoadVideo", "VHS_LoadVideoPath"):
        raise SecondUnitError("this preset loads its clip with %s, which has no image-sequence form"
                              % class_type)
    consumers = []
    for node_id, node in graph.items():
        if not isinstance(node, dict) or str(node_id) == loader_id:
            continue
        for key, link in list((node.get("inputs") or {}).items()):
            if is_link(link) and str(link[0]) == loader_id:
                consumers.append((str(node_id), key, int(link[1])))
    if any(slot == 3 for _n, _k, slot in consumers):
        raise SecondUnitError("this preset reads video_info from its clip loader, which a frame "
                              "sequence cannot provide")
    directory = str((frames or {}).get("directory") or "")
    audio = str((frames or {}).get("audio") or "")
    if not directory or not audio:
        raise SecondUnitError("the frame sequence is missing its folder or its audio")
    try:
        count = int((loader.get("inputs") or {}).get("frame_load_cap") or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        count = int((frames or {}).get("count") or 0)
    available = int((frames or {}).get("count") or 0)
    if (mode in ("ENVSWAP", "SWAP", "ANGLE") or (mode == "V2V" and h3_reference_node(graph)[1] is not None)) and available and count > available:
        raise SecondUnitError(
            "The PNG sequence holds %d frames (%.2f s) but this shot generates %d frames (%.2f s); H3 would invent the rest "
            "of the take. Render a longer TIMELINE SEQ or shorten the shot. Nothing was queued."
            % (available, available / 24.0, count, count / 24.0))
    images_id = _new_graph_node_id(graph)
    graph[images_id] = {
        "class_type": "VHS_LoadImagesPath",
        "_meta": {"title": "SECOND UNIT PNG SEQUENCE"},
        "inputs": {"directory": directory, "image_load_cap": count,
                   "skip_first_images": 0, "select_every_nth": 1},
    }
    audio_id = _new_graph_node_id(graph)
    graph[audio_id] = {
        "class_type": "VHS_LoadAudio",
        "_meta": {"title": "SECOND UNIT PNG SEQUENCE AUDIO"},
        "inputs": {"audio_file": audio, "seek_seconds": 0.0, "duration": 0.0},
    }
    image_out = [images_id, 0]
    try:
        _cw = int((loader.get("inputs") or {}).get("custom_width") or 0)
        _ch = int((loader.get("inputs") or {}).get("custom_height") or 0)
    except (TypeError, ValueError):
        _cw = _ch = 0
    if mode in ("ENVSWAP", "SWAP", "ANGLE") and _cw > 0 and _ch > 0:
        scale_id = _new_graph_node_id(graph)
        graph[scale_id] = {"class_type": "ImageScale", "_meta": {"title": "SECOND UNIT PNG SEQUENCE -> LOADER SIZE"},
                           "inputs": {"image": [images_id, 0], "upscale_method": "lanczos",
                                      "width": _cw, "height": _ch, "crop": "disabled"}}
        image_out = [scale_id, 0]
    for node_id, key, slot in consumers:
        if slot == 0:
            graph[node_id]["inputs"][key] = list(image_out)
        elif slot == 1:
            graph[node_id]["inputs"][key] = [images_id, 2]
        elif slot == 2:
            graph[node_id]["inputs"][key] = [audio_id, 0]
    del graph[loader_id]
    return images_id, audio_id


def is_pose_follow_graph(graph):
    return any(isinstance(n, dict) and n.get("class_type") == "SecondUnitPoseFollowGuide" for n in (graph or {}).values())


def stage_pose_follow_source(source, input_dir, seconds, in_seconds=None):
    """Stage the selected moment at the recipe's native canvas and24fps."""
    if not os.path.isfile(source):
        raise SecondUnitError("Pose Follow requires a source video file.")
    count = max(1, int(round(float(seconds) *24)))
    name = "pose24a_" + proxy_input_name(source, seconds=seconds, dims=(1536,864), in_seconds=in_seconds)
    target = os.path.join(input_dir, name)
    if not os.path.isfile(target):
        args = ["ffmpeg", "-y", "-v", "error"]
        if in_seconds: args += ["-ss", str(float(in_seconds))]
        args += ["-i", source, "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                 "-map", "0:v:0", "-map", "1:a:0", "-vf",
                 "fps=24,scale=1536:864:force_original_aspect_ratio=increase,crop=1536:864",
                 "-frames:v", str(count), "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", str(count/24.0), target]
        if _run_tool(args, timeout=600) is None:
            raise SecondUnitError("Could not stage the24fps Pose Follow source; nothing was queued.")
    actual = probe_frame_count(target)
    if not actual or actual <1:
        raise SecondUnitError("Pose Follow source has no readable frames.")
    return name, int(actual)


def patch_pose_follow_graph(graph, prompt, seconds, seed, source, environment, cards):
    patched = copy.deepcopy(graph)
    roles = {(n.get("_meta") or {}).get("second_unit_role"): (str(i), n) for i,n in patched.items()}
    bindings = {"pose_source": source, "pose_environment": environment,
                "pose_identity_front": cards[0], "pose_identity_threequarter": cards[1],
                "pose_identity_profile": cards[2], "pose_identity_body": cards[3]}
    for role,value in bindings.items():
        if not value or role not in roles:
            raise SecondUnitError("Pose Follow needs footage, an environment and all four identity/body cards: missing " + role)
        _id,node=roles[role]
        key = ("file" if node["class_type"] == "LoadVideo" else "video") if role == "pose_source" else "image"
        node["inputs"][key] = value
    h3=roles["pose_h3"][1]
    if not str(prompt or "").strip():raise SecondUnitError("Describe the continuous follow shot before generating.")
    camera_lora = any("camera_motion" in str((n.get("inputs") or {}).get("lora_name", "")).lower()
                      for n in patched.values())
    h3["inputs"]["prompt"] = ("camera motion\n" if camera_lora else "") + compose_h3_prompt(prompt, patched)
    fps=graph_fps(patched);frames=max(1,int(round(float(seconds)*fps)))
    generated_frames = snap_frames(frames, "MiniMaxH3ReferenceToVideo")
    # H3 rounds a reference video DOWN to 17k+5. Pad only its tail so
    # the final real performance frames reach the model (83 -> 90, not 73).
    # This preserves reference coverage; it is not a fix for guide leakage.
    tail_padding = generated_frames - frames
    if tail_padding:
        for key, reference in list(h3["inputs"].items()):
            if not key.startswith("ref_videos.") or not is_link(reference):
                continue
            last_id = _new_graph_node_id(patched)
            patched[last_id] = {"class_type": "ImageFromBatch", "inputs": {
                "image": list(reference), "batch_index": frames - 1, "length": 1},
                "_meta": {"title": "Last real source frame"}}
            repeat_id = _new_graph_node_id(patched)
            patched[repeat_id] = {"class_type": "RepeatImageBatch", "inputs": {
                "image": [last_id, 0], "amount": tail_padding},
                "_meta": {"title": "Technical reference tail only"}}
            padded_id = _new_graph_node_id(patched)
            patched[padded_id] = {"class_type": "ImageBatch", "inputs": {
                "image1": list(reference), "image2": [repeat_id, 0]},
                "_meta": {"title": "Complete source reference on H3 frame grid"}}
            h3["inputs"][key] = [padded_id, 0]
    for node in patched.values():
        inputs=node.get("inputs") or {}
        if node.get("class_type")=="RandomNoise" and seed is not None:inputs["noise_seed"]=int(seed)
    before=set(patched)
    enforce_comfy_prores_hq(patched,fps,"720P",output_size=(1536,864),vsr=False)
    # Native delivery: remove the helper's redundant same-size resize, preserving links.
    for key in list(set(patched)-before):
        node=patched[key]
        if node.get("class_type")=="ImageScale":
            old=[key,0];new=node["inputs"]["image"]
            for item in patched.values():
                for k,v in list((item.get("inputs") or {}).items()):
                    if v==old:item["inputs"][k]=new
            del patched[key]
    enforce_lane_prefix(patched,"ENVSWAP")
    return patched,{"fps":fps,"frames":frames,"generated_frames":generated_frames,"reference_tail_padding":tail_padding,
                    "seconds":float(seconds),"output_size":(1536,864),"final_output_size":(1536,864),
                    "native_intermediate":True,"pose_follow":True,"source_targets":[(roles["pose_source"][0],"file" if roles["pose_source"][1]["class_type"]=="LoadVideo" else "video")],
                    "frame_targets":[],"delivery_trim_targets":[],"prefix_changes":[],"prores_nodes":[],
                    "resolution":"NATIVE","prefixes":[],"ingredient":None,"environment":None}


def patch_graph(graph, mode, prompt, seconds, negative=None, seed=None, source_name=None,
                source_name_last=None, identity_name=None, wardrobe_name=None,
                prop1_name=None, prop2_name=None,
                resolution="720P", v2v_retention="LOCK_ALL",
                ingredient_role="SUBJECT", edit_amount="BALANCED",
                subject_query="person", environment_relight=False,
                intermediate_size=None, card_names=None, continuity_name=None,
                finish_source_size=None, source_frames=None, first_frame_name=None, first_frame_arm="off"):
    if not isinstance(graph, dict) or not graph:
        raise SecondUnitError("Graph is empty or not a dict.")
    if isinstance(graph.get("nodes"), list):
        raise SecondUnitError("Graph is in UI format (has a top-level 'nodes' list). Need flat API format.")

    forbidden = scan_forbidden(graph)
    if forbidden:
        raise SecondUnitError(
            "Graph contains node(s) this panel refuses to run: %s. Re-verify it." % ", ".join(forbidden)
        )

    if is_pose_follow_graph(graph):
        return patch_pose_follow_graph(graph, prompt, seconds, seed, source_name, source_name_last,
                                       [identity_name, wardrobe_name, prop1_name, prop2_name])
    patched = copy.deepcopy(graph)
    family = infer_graph_family("", patched)
    if resolution == "4K" and family not in ("LTX25", "LTX23"):
        raise SecondUnitError("4K export is available for LTX workflows only. Choose 720p or 1080p for this model.")
    h3_reference_targets = []
    world_reference_targets = []
    ltx_world = bool(
        family == "LTX25" and mode == "ENVSWAP" and any(
            isinstance(node, dict)
            and node.get("class_type") == "SecondUnitRetargetWorldProxy"
            for node in patched.values()
        )
    )
    if ltx_world:
        required_refs = (
            ("picture 1: target world / environment", source_name_last, "target world"),
            ("picture 2: actor identity only", identity_name, "actor identity"),
            ("picture 3: complete replacement wardrobe", wardrobe_name, "replacement wardrobe"),
            ("picture 4: prop 1", prop1_name, "prop 1"),
            ("picture 5: prop 2", prop2_name, "prop 2"),
        )
        for title, staged_name, label in required_refs:
            matches = [
                (str(node_id), node) for node_id, node in patched.items()
                if isinstance(node, dict) and node.get("class_type") == "LoadImage"
                and str((node.get("_meta") or {}).get("title") or "").lower() == title
            ]
            if len(matches) != 1:
                raise SecondUnitError(
                    "LTX 2.5 World Generation needs exactly one %s loader, found %d."
                    % (label, len(matches))
                )
            if not staged_name:
                raise SecondUnitError(
                    "LTX 2.5 World Generation needs a separate %s reference." % label
                )
            node_id, node = matches[0]
            node.setdefault("inputs", {})["image"] = staged_name
            world_reference_targets.append((node_id, "image"))
    h3_v3 = h3_v3_kind(patched) if family == "MINIMAXH3" else None
    v3_handled_ids = set()
    if h3_v3 and mode in ("SWAP", "ENVSWAP", "ANGLE"):
        for node_id, key in wire_h3_v3_pictures(
                patched, mode, source_name_last=source_name_last, identity_name=identity_name,
                wardrobe_name=wardrobe_name, prop1_name=prop1_name, prop2_name=prop2_name,
                card_names=card_names, continuity_name=continuity_name,
                first_frame_name=(first_frame_name if first_frame_arm == "picture" else None)):
            v3_handled_ids.add(str(node_id))
            h3_reference_targets.append((node_id, key))
            world_reference_targets.append((node_id, key))
    if family == "MINIMAXH3" and mode == "ENVSWAP" and not h3_v3:
        required_refs = (
            ("environment beauty - picture 1", source_name_last, "environment beauty"),
            ("actor identity - picture 2", identity_name, "actor identity"),
            ("wardrobe - picture 3", wardrobe_name, "wardrobe"),
        )
        for title, staged_name, label in required_refs:
            matches = [
                (str(node_id), node) for node_id, node in patched.items()
                if isinstance(node, dict) and node.get("class_type") == "LoadImage"
                and title in str((node.get("_meta") or {}).get("title") or "").lower()
            ]
            if len(matches) != 1:
                raise SecondUnitError(
                    "H3 Environment Swap needs exactly one %s loader, found %d."
                    % (label, len(matches))
                )
            if not staged_name:
                raise SecondUnitError(
                    "H3 Environment Swap needs a separate %s reference." % label
                )
            node_id, node = matches[0]
            node.setdefault("inputs", {})["image"] = staged_name
            h3_reference_targets.append((node_id, "image"))
            world_reference_targets.append((node_id, "image"))
    image_loader_count = sum(
        1 for node in patched.values()
        if isinstance(node, dict)
        and node.get("class_type") in {name for name, _key in IMAGE_SOURCE_INPUTS}
    )
    dynamic_ingredient = bool(
        source_name_last
        and (
            (family in ("LTX23", "LTX25")
             and mode in ("T2V", "I2V", "V2V")
             and (mode != "I2V" or image_loader_count <= 1))
            or (family == "MINIMAXH3" and mode == "V2V")
        )
    )
    detail_graph = is_ltx_pixel_detail_graph(patched)
    v2v_edit_changes = apply_v2v_edit_amount(patched, edit_amount) if mode == "V2V" and not detail_graph else []
    fps = graph_fps(patched)
    derived_frames = derive_frames(fps, seconds)
    if family == "MINIMAXH3":

        derived_frames = derive_frames_h3(fps, seconds)

    frame_targets = find_frame_targets(patched)
    snapped = {}
    for node_id, key in frame_targets:
        value = snap_frames(derived_frames, patched[node_id].get("class_type"))
        patched[node_id]["inputs"][key] = value
        if value != derived_frames:
            snapped[str(node_id)] = value


    frames = max([derived_frames] + list(snapped.values()))
    delivery_trim_targets = find_exact_frame_trim_targets(patched)
    for node_id, key in delivery_trim_targets:
        patched[node_id]["inputs"][key] = frames

    prompt_text = (prompt or "").strip()
    if not prompt_text:
        raise SecondUnitError("Prompt is empty. Describe the shot before generating.")
    if mode == "ENVSWAP" and not source_name_last:
        raise SecondUnitError(
            "Environment Swap needs a target-set reference still in the Set reference box."
        )
    negative_text = (negative or "").strip()
    environment_info = None
    if mode == "ENVSWAP" and not plain_h3_world(patched):
        environment_info = patch_environment_swap_graph(
            patched, prompt_text, negative_text, subject_query,
            environment_relight, derived_frames,
        )
        positive_id = environment_info["positive"]
        positive_key = ("prompt" if family == "MINIMAXH3" else "text")
        negative_id = environment_info.get("negative")
        negative_key = "text" if negative_id else None
    else:
        positive_target, negative_target = find_prompt_targets(patched)
        positive_id, positive_key = positive_target
        negative_id, negative_key = negative_target if negative_target else (None, None)

        if (negative_id is not None and str(negative_id) == str(positive_id)
                and negative_key == positive_key):
            raise SecondUnitError(
                "Internal invariant broken: node %s was resolved as BOTH the positive and the "
                "negative prompt. Refusing rather than overwriting your prompt." % positive_id
            )
        if family == "MINIMAXH3":

            prompt_text = compose_h3_prompt(prompt_text, patched)
            if any("camera_motion_h3" in str((n.get("inputs") or {}).get("lora_name", "")).lower()
                   and float((n.get("inputs") or {}).get("strength_model", 0)) != 0
                   for n in patched.values() if isinstance(n, dict)):
                if not prompt_text.lower().startswith("camera motion"):
                    prompt_text = "camera motion, " + prompt_text
        elif mode == "V2V" and not detail_graph:
            prompt_text = compose_v2v_prompt(
                prompt_text, family, retention=v2v_retention,
                ingredient_role=ingredient_role, edit_amount=edit_amount,
                has_ingredient=dynamic_ingredient,
            )
        elif mode == "SWAP":
            prompt_text = compose_swap_prompt(prompt_text, family)
        elif dynamic_ingredient and mode in ("T2V", "I2V"):
            role = V2V_INGREDIENT_TEXT.get(ingredient_role, V2V_INGREDIENT_TEXT["SUBJECT"])
            prompt_text += (
                "\nINGREDIENT REFERENCE: Use the supplied still only for %s. Preserve the "
                "requested shot, framing, motion, lighting, and all unrelated traits."
            ) % role
        if negative_text:
            if not negative_id:
                if mode == "SEGMENT":
                    raise SecondUnitError(
                        "SEGMENT graphs have no negative prompt at all - the text box is the "
                        "detection query (what to track), not a shot description. "
                        "Clear the Negative box."
                    )
                raise SecondUnitError(
                    "This graph has no separate negative prompt node - its negative conditioning "
                    "is zeroed out (cfg 1), so a negative would have nowhere to go. "
                    "Clear the Negative box."
                )
            patched[negative_id]["inputs"][negative_key] = negative_text

        patched[positive_id]["inputs"][positive_key] = prompt_text

    seeds_set = []
    if seed is not None:
        for node_id in sorted(patched, key=lambda k: (len(str(k)), str(k))):
            inputs = patched[node_id].get("inputs") or {}
            for key in SEED_INPUTS:
                value = inputs.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    inputs[key] = int(seed)
                    seeds_set.append((str(node_id), key))

    source_target = None
    source_targets = []
    ingredient_info = None
    if dynamic_ingredient:
        ingredient_info = inject_v2v_ingredient(patched, source_name_last)
    if source_name:
        source_target = find_source_input(patched, mode)
        if not source_target:
            raise SecondUnitError(
                "%s graph has no loader input to point at a source file "
                "(looked for %s)." % (mode, ", ".join("%s.%s" % pair for pair in
                                                      (IMAGE_SOURCE_INPUTS if mode in IMAGE_SOURCE_MODES else VIDEO_SOURCE_INPUTS)))
            )

        keyframe_roles = keyframe_targets(patched)
        leftovers = describe_unstaged_loaders(patched, source_target, mode)
        if leftovers and not source_name_last:
            detail = "; ".join(
                "node %s (%s = %r%s)" % (nid, key, value,
                                         " -> " + ", ".join(consumers) if consumers else "")
                for nid, key, value, consumers in leftovers
            )
            raise SecondUnitError(
                "This graph needs %d keyframes. Fill in the End frame box as well - otherwise %s "
                "would keep its authored value and the render would silently use it. "
                "Unstaged: %s" % (len(leftovers) + 1,
                                  "it" if len(leftovers) == 1 else "they", detail)
            )

        aux_images = []
        if mode not in IMAGE_SOURCE_MODES and not v3_handled_ids:
            staged_ids = {source_target[0]}
            for node_id in sorted(patched, key=lambda k: (len(str(k)), str(k))):
                node = patched[node_id]
                if node.get("class_type") not in {n for n, _k in IMAGE_SOURCE_INPUTS}:
                    continue
                if str(node_id) in staged_ids:
                    continue
                if isinstance((node.get("inputs") or {}).get("image"), str):
                    aux_images.append((str(node_id), "image"))

        if mode in ("SWAP", "ENVSWAP") and aux_images and not source_name_last:
            purpose = ("a target-set reference still" if mode == "ENVSWAP"
                       else "a replacement-performer reference still")
            raise SecondUnitError(
                "%s needs %s in the second file box; the preset will not fall back to its "
                "authored placeholder." % (dict(MODE_LABELS).get(mode, mode), purpose)
            )

        if source_name_last and not ingredient_info and not leftovers and not aux_images \
                and not v3_handled_ids:
            raise SecondUnitError(
                "You supplied a second file, but this graph has only one file input. "
                "Clear that box, or pick a first+last / SWAP graph."
            )
        if source_name_last and not ingredient_info and aux_images:
            nid, key = aux_images[0]
            patched[nid]["inputs"][key] = source_name_last

        if keyframe_roles.get("first_frame") and keyframe_roles.get("last_frame") and source_name_last:

            first_id = keyframe_roles["first_frame"]
            last_id = keyframe_roles["last_frame"]
            patched[first_id]["inputs"]["image"] = source_name
            patched[last_id]["inputs"]["image"] = source_name_last
            source_targets = [(first_id, "image"), (last_id, "image")]
            source_target = source_targets[0]
        else:
            patched[source_target[0]]["inputs"][source_target[1]] = source_name
            source_targets = [source_target]
            if source_name_last and not ingredient_info and leftovers:
                nid, key, _value, _consumers = leftovers[0]
                patched[nid]["inputs"][key] = source_name_last
                source_targets.append((nid, key))
            elif source_name_last and not ingredient_info and aux_images:
                source_targets.append(aux_images[0])

    if detail_graph:
        apply_detail_realism_settings(patched)

    first_frame_guide = None
    if first_frame_name and first_frame_arm == "latent" and family == "MINIMAXH3":
        first_frame_guide = inject_h3_first_frame_guide(patched, first_frame_name)
        h3_reference_targets.append((first_frame_guide[1], "image"))
    if finish_source_size and is_ltx_pixel_detail_graph(patched):

        src_w, src_h = int(finish_source_size[0]), int(finish_source_size[1])
        snap_w, snap_h = max(32, (src_w // 32) * 32), max(32, (src_h // 32) * 32)
        if (snap_w, snap_h) != (src_w, src_h):
            guides = [(nid, node) for nid, node in patched.items()
                      if isinstance(node, dict) and node.get("class_type") == "LTXAddVideoICLoRAGuide"
                      and is_link((node.get("inputs") or {}).get("image"))]
            for guide_id, guide in guides:
                snap_id = _new_graph_node_id(patched)
                patched[snap_id] = {
                    "class_type": "ImageScale",
                    "_meta": {"title": "SECOND UNIT LTX GUIDE 32-GRID SNAP"},
                    "inputs": {"image": guide["inputs"]["image"], "upscale_method": "lanczos",
                               "width": snap_w, "height": snap_h, "crop": "disabled"},
                }
                guide["inputs"]["image"] = [snap_id, 0]
            log("LTX detail guide %dx%d is not on the 32 grid; snapped to %dx%d before the IC-LoRA guide"
                % (src_w, src_h, snap_w, snap_h))
        finish_w, finish_h = snap_w * 2, snap_h * 2
        for node in patched.values():
            if isinstance(node, dict) and node.get("class_type") in ("EmptyLTXVLatentVideo", "LTXVEmptyLatentVideo"):
                node.setdefault("inputs", {})["width"] = finish_w
                node["inputs"]["height"] = finish_h
    vram_handoffs = inject_ltx_vram_handoffs(patched, family)
    prores_changes = enforce_comfy_prores_hq(
        patched, fps, resolution, output_size=intermediate_size,
        vsr=(family == "MINIMAXH3" and intermediate_size is None))
    prefix_changes = enforce_lane_prefix(patched, mode)

    if source_frames:

        images_id, _audio_id = inject_frame_sequence_loader(patched, mode, source_frames)
        source_target = (images_id, "directory")
        source_targets = [source_target] + [t for t in source_targets
                                            if str(t[0]) in patched and str(t[0]) != images_id]

    delivery_frames = (derived_frames
                       if environment_info and environment_info.get("trim") else frames)
    info = {
        "fps": fps,
        "frames": delivery_frames,
        "generated_frames": frames,
        "derived_frames": derived_frames,
        "first_frame_anchor": first_frame_arm if first_frame_name else "off",
        "seconds": float(seconds),
        "frame_targets": frame_targets,
        "delivery_trim_targets": delivery_trim_targets,
        "snapped_frames": snapped,
        "positive_node": positive_id,
        "positive_key": positive_key,
        "negative_node": negative_id,
        "negative_key": negative_key,
        "seed_nodes": seeds_set,
        "source_target": source_target,
        "source_targets": source_targets,
        "h3_reference_targets": h3_reference_targets,
        "world_reference_targets": world_reference_targets,
        "ingredient": ingredient_info,
        "environment": environment_info,
        "vram_handoffs": vram_handoffs,
        "v2v_retention": v2v_retention if mode == "V2V" else None,
        "ingredient_role": ingredient_role if ingredient_info else None,
        "edit_amount": edit_amount if mode == "V2V" else None,
        "v2v_edit_changes": v2v_edit_changes,
        "resolution": resolution,
        "output_size": tuple(intermediate_size) if intermediate_size else OUTPUT_SIZES[resolution],
        "final_output_size": OUTPUT_SIZES[resolution],
        "native_intermediate": bool(intermediate_size),
        "prores_nodes": prores_changes,
        "prefix_changes": prefix_changes,
        "prefixes": sorted(
            v["inputs"]["filename_prefix"]
            for v in patched.values()
            if isinstance((v.get("inputs") or {}).get("filename_prefix"), str)
        ),
    }
    return patched, info


def force_graph_timing(graph, fps, frames):
    try:
        fps = float(fps)
        frames = int(frames)
    except (TypeError, ValueError):
        raise SecondUnitError("Detail pass received invalid timing (%r fps, %r frames)." %
                              (fps, frames))
    if fps <= 0 or frames <= 0:
        raise SecondUnitError("Detail pass timing must be positive (%r fps, %r frames)." %
                              (fps, frames))
    frame_changes = []
    for node_id, key in find_frame_targets(graph):
        class_type = str((graph.get(node_id) or {}).get("class_type") or "")
        value = frames

        if class_type in ("EmptyLTXVLatentVideo", "LTXVEmptyLatentVideo"):
            value = 1 + int(math.ceil(max(0, frames - 1) / 8.0)) * 8
        elif class_type in FRAME_GRIDS and key == "length":

            value = snap_frames(frames, class_type)
        graph[node_id]["inputs"][key] = value
        frame_changes.append((node_id, key, value))
    for node_id, key in find_exact_frame_trim_targets(graph):
        graph[node_id]["inputs"][key] = frames
        frame_changes.append((node_id, key, frames))
    fps_changes = []
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        for key in FPS_INPUTS:
            value = inputs.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                inputs[key] = fps
                fps_changes.append((str(node_id), key, fps))
    if not frame_changes:
        raise SecondUnitError("Detail upscaler exposes no frame-count input to lock to the source.")
    if not fps_changes:
        raise SecondUnitError("Detail upscaler exposes no fps input to lock to the source.")
    if is_ltx_pixel_detail_graph(graph):
        configure_detail_padding(graph, frames)
    return {"frames": frame_changes, "fps": fps_changes}


def detail_upscale_entry(workflow_dir=WORKFLOW_DIR):
    path = os.path.join(workflow_dir, DETAIL_UPSCALE_RELATIVE)
    if not os.path.isfile(path):
        raise SecondUnitError(
            "LTX detail pass is enabled, but its graph is missing: %s" % path)
    stamp = read_stamp(path)
    if stamp is None:
        raise SecondUnitError(
            "LTX detail pass is enabled, but %s has no verified stamp." %
            os.path.basename(path))
    if not stamp.get("local", False):
        raise SecondUnitError(
            "LTX detail pass graph is not stamped local:true; refusing a hidden cloud call.")
    if stamp.get("production_ready", True) is False and os.environ.get("SECOND_UNIT_DETAIL_PROOF") != "1":
        raise SecondUnitError(
            "DETAIL is ticked, but its finish graph %s is quarantined: %s. Untick DETAIL, or run the DETAIL "
            "proof that re-qualifies it." % (os.path.basename(path), stamp.get("quarantine_reason") or "not release-proven"))
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            graph = json.load(handle)
    except Exception as exc:
        raise SecondUnitError("LTX detail graph is unreadable: %s" % exc)
    if not is_api_format(graph):
        raise SecondUnitError("LTX detail graph is not API format.")
    apply_detail_realism_settings(graph)
    return GraphEntry(path, "V2V", "Distilled", stamp, "LTX25")


def is_detail_upscale_entry(entry):
    if entry is None:
        return False
    return os.path.normcase(os.path.normpath(entry.path)).endswith(
        os.path.normcase(os.path.normpath(DETAIL_UPSCALE_RELATIVE)))


def free_vram_gb(stats):
    try:
        devices = (stats or {}).get("devices") or []
        if not devices:
            return None
        free = devices[0].get("vram_free")
        return None if free is None else float(free) / (1024.0 ** 3)
    except (TypeError, ValueError):
        return None


def adapt_hardware_precision(graph, stats):
    devices = (stats or {}).get("devices") or []
    device = devices[0] if devices else {}
    name = str(device.get("name") or "")
    known_fast_fp8 = (str(device.get("type") or "").lower() == "cuda"
                      and bool(re.search(r"\bRTX\s+(?:40|50)\d{2}\b", name, re.I)))
    changes = []
    for nid, node in graph.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if node.get("class_type") == "UNETLoader" and not known_fast_fp8:
            dtype = str(inputs.get("weight_dtype") or "")
            if dtype.endswith("_fast"):
                inputs["weight_dtype"] = "default"
                changes.append("node %s: %s -> default precision for %s" % (nid, dtype, name or "unknown device"))
    return changes


def vram_warning(stats, threshold=None):
    threshold = VRAM_COMFORTABLE_GB if threshold is None else threshold
    free = free_vram_gb(stats)
    if free is None or free >= threshold:
        return None
    return ("The generation lane reports %.1f GB free right now. That can be a model already "
            "warm in ComfyUI, or another GPU app. The panel will continue; close another GPU "
            "app only if this render becomes unusually slow." % free)


def parse_dir_arg(stats, flag):
    argv = ((stats or {}).get("system") or {}).get("argv") or []
    for index, item in enumerate(argv):
        if item == flag and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(flag + "="):
            return item.split("=", 1)[1]
    return None


def history_outputs(entry):
    files = []
    for _node_id, outputs in sorted((entry or {}).get("outputs", {}).items()):
        if not isinstance(outputs, dict):
            continue
        for _key, value in sorted(outputs.items()):
            if not isinstance(value, list):
                continue
            for item in value:
                if (isinstance(item, dict) and item.get("filename")
                        and (item.get("type") or "output") == "output"):
                    files.append({
                        "filename": item.get("filename"),
                        "subfolder": item.get("subfolder") or "",
                        "type": item.get("type") or "output",
                    })
    return files



RENDER_ERROR_HINTS = (

    ("hostbuf_file_reader_read",
     "ComfyUI failed while reading a staged model block through Windows host memory",
     "Use the Second Unit launcher with --disable-pinned-memory. For MiniMax H3 use the "
     "fp8_scaled checkpoint; keep DynamicVRAM enabled."),
    ("read_file_slice",
     "ComfyUI failed while reading a staged model block through Windows host memory",
     "Use the Second Unit launcher with --disable-pinned-memory. For MiniMax H3 use the "
     "fp8_scaled checkpoint; keep DynamicVRAM enabled."),
    ("cast_modules_with_vbar",
     "the graphics card ran out of memory while moving the model onto it",
     "Close something using the GPU and try again."),
    ("out of memory",
     "the graphics card ran out of memory",
     "Render a shorter clip, pick a lighter preset, or close something using the GPU."),
    ("outofmemoryerror",
     "the graphics card ran out of memory",
     "Render a shorter clip, pick a lighter preset, or close something using the GPU."),
    ("value not in list",
     "ComfyUI does not have a model this preset asks for",
     "Run tools/verify_models_present.py to see which one."),
    ("saving image outside the output folder",
     "the preset tried to write outside ComfyUI's output folder",
     "That is a fault in the graph, not in your shot."),
    ("mat1 and mat2",
     "two parts of this preset do not fit together",
     "It is usually a model paired with the wrong text encoder or VAE."),
    ("no such file or directory",
     "something the preset needs is not where ComfyUI expects it",
     "Check the source clip is still on disk."),
)


def explain_render_error(raw):
    text = str(raw or "").strip()
    if not text:
        return "The render failed and ComfyUI gave no reason."
    lowered = text.lower()
    for needle, meaning, advice in RENDER_ERROR_HINTS:
        if needle in lowered:
            return "%s. %s  (ComfyUI said: %s)" % (meaning[:1].upper() + meaning[1:],
                                                   advice, text[:200])
    return text


def history_error(entry):
    status = (entry or {}).get("status") or {}
    if status.get("status_str") != "error" and status.get("completed", True):
        return None
    for message in status.get("messages") or []:
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error":
            detail = message[1] or {}
            text = str(detail.get("exception_message") or "unknown error").strip()
            first_line = text.splitlines()[0] if text.splitlines() else text
            return "node %s (%s): %s" % (
                detail.get("node_id", "?"), detail.get("node_type", "?"), first_line[:300]
            )
    if status.get("status_str") == "error":
        return "prompt failed (no execution_error detail in /history)"
    return None


def staged_input_name(source_path):
    stat = os.stat(source_path)
    digest = hashlib.sha1(
        (os.path.abspath(source_path) + "|" + str(int(stat.st_mtime)) + "|" + str(stat.st_size)).encode("utf-8")
    ).hexdigest()[:8]
    base = os.path.basename(source_path)
    return "su_%s_%s" % (digest, re.sub(r"[^A-Za-z0-9._-]+", "_", base))


def graph_dimensions(graph):
    best = None
    for node in (graph or {}).values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        try:
            width, height = int(inputs["width"]), int(inputs["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width > 0 and height > 0 and (best is None or width * height > best[0] * best[1]):
            best = (width, height)
    return best


def h3_generation_dimensions(graph):
    best = None
    h3_canvas_classes = {
        "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo",
        "EmptyMiniMaxH3LatentAV",
    }
    for node in (graph or {}).values():
        if not isinstance(node, dict) or node.get("class_type") not in h3_canvas_classes:
            continue
        inputs = node.get("inputs") or {}
        try:
            width, height = int(inputs["width"]), int(inputs["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width > 0 and height > 0 and (best is None or width * height > best[0] * best[1]):
            best = (width, height)
    return best


def h3_detail_intermediate_size(family, detail_enabled, final_resolution, graph):
    if family == "MINIMAXH3" and detail_enabled and final_resolution in OUTPUT_SIZES:
        return h3_generation_dimensions(graph)
    return None


def _normalise_stage_output_size(value):
    if value is None:
        return None
    try:
        width, height = int(value[0]), int(value[1])
    except (TypeError, ValueError, IndexError):
        raise SecondUnitError("Invalid H3 intermediate canvas %r." % (value,))
    if width < 1 or height < 1:
        raise SecondUnitError("H3 intermediate canvas dimensions must be positive.")
    return width, height


def resolve_h3_stage_output_size(params, family, graph):
    params = params or {}
    native = h3_generation_dimensions(graph)
    explicit = _normalise_stage_output_size(params.get("_h3_stage_output_size"))
    if explicit is not None:
        if family != "MINIMAXH3" or native is None or explicit != native:
            raise SecondUnitError(
                "REFUSED: internal H3 intermediate canvas %r does not match the graph's "
                "native generator canvas %r." % (explicit, native))
        return explicit
    automatic = h3_detail_intermediate_size(
        family, bool(params.get("detail_upscale")), params.get("resolution"), graph)
    if (family == "MINIMAXH3" and params.get("detail_upscale")
            and params.get("resolution") in OUTPUT_SIZES and automatic is None):
        raise SecondUnitError(
            "REFUSED: H3 + LTX detail needs an identifiable native H3 generator canvas.")
    return automatic


PROXY_ENABLED = os.environ.get("SECOND_UNIT_PROXY", "1") != "0"
NORMALISE_LOG = os.environ.get("SECOND_UNIT_NORMALISE", "0") == "1"
PROXY_CACHE_VERSION = 3


def proxy_input_name(source_path, seconds=None, dims=None, in_seconds=None):
    staged = staged_input_name(source_path)
    stem, _ext = os.path.splitext(staged)
    recipe = {
        "version": PROXY_CACHE_VERSION,
        "in_seconds": None if in_seconds is None else round(float(in_seconds), 6),
        "seconds": None if seconds is None else round(float(seconds), 6),
        "dims": list(dims) if dims else None,
        "normalise_log": bool(NORMALISE_LOG),
    }
    digest = hashlib.sha1(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")).hexdigest()[:10]
    return "%s_proxy_%s.mp4" % (stem, digest)


def has_audio_stream(path):
    out = _run_tool(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                     "stream=index", "-of", "csv=p=0", path])
    if out is None:
        return None
    return bool(out.strip())


def build_source_proxy(source_path, target, seconds=None, dims=None, in_seconds=None):
    if not PROXY_ENABLED or not _tool_path("ffmpeg"):
        return None

    audio = has_audio_stream(source_path)
    argv = ["ffmpeg", "-y", "-v", "error"]
    if in_seconds and in_seconds > 0:
        argv += ["-ss", "%.3f" % in_seconds]
    argv += ["-i", source_path]
    if audio is False:
        argv += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    if seconds and seconds > 0:

        argv += ["-t", "%.3f" % (float(seconds) + 0.5)]
    filters = []
    if dims:
        filters.append("scale=%d:%d:force_original_aspect_ratio=decrease" % dims)
        filters.append("pad=%d:%d:(ow-iw)/2:(oh-ih)/2" % dims)
    if NORMALISE_LOG:
        filters.append("curves=preset=lighter")
        filters.append("eq=contrast=1.35:saturation=1.25")
    if filters:
        argv += ["-vf", ",".join(filters)]
    argv += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
    if audio is False:
        argv += ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]

    argv += ["-c:a", "alac", target]
    started = time.perf_counter()
    out = _run_tool(argv, timeout=600)
    if out is None or not os.path.isfile(target) or os.path.getsize(target) == 0:
        log("proxy: ffmpeg produced nothing for %s" % os.path.basename(source_path))
        return None

    if has_audio_stream(target) is False:
        log("proxy: %s came out with NO audio - falling back to the original"
            % os.path.basename(target))
        try:
            os.remove(target)
        except OSError:
            pass
        return None
    log("proxy: %s -> %s  (%.1f MB -> %.2f MB in %.1fs, audio %s%s)"
        % (os.path.basename(source_path), os.path.basename(target),
           os.path.getsize(source_path) / 1e6, os.path.getsize(target) / 1e6,
           time.perf_counter() - started,
           "kept lossless" if audio else "generated silent",
           ", normalised" if NORMALISE_LOG else ""))
    return target


def _natural_key(name):
    return [int(token) if token.isdigit() else token.lower() for token in re.split(r"(\d+)", name)]


def sequence_frame_files(directory):
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    frames = [n for n in names
              if not n.startswith(".") and os.path.splitext(n)[1].lower() in SEQUENCE_FRAME_EXTENSIONS]
    return [os.path.join(directory, n) for n in sorted(frames, key=_natural_key)]


def sequence_source_dir(source_path):
    if not source_path:
        return None
    if os.path.isdir(source_path):
        return source_path if sequence_frame_files(source_path) else None
    ext = os.path.splitext(source_path)[1].lower()
    if ext in SEQUENCE_FRAME_EXTENSIONS and re.search(r"\d+\.[A-Za-z0-9]+$", os.path.basename(source_path)):
        folder = os.path.dirname(os.path.abspath(source_path))
        if len(sequence_frame_files(folder)) > 1:
            return folder
    return None


def sequence_audio_file(directory):
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    for name in names:
        if os.path.splitext(name)[1].lower() in SEQUENCE_AUDIO_EXTENSIONS:
            return os.path.join(directory, name)
    return None


def frames_input_name(source_path, seconds=None, dims=None, in_seconds=None, fps=None):
    source_path = os.path.normpath(source_path)
    staged = staged_input_name(source_path)
    stem = os.path.splitext(staged)[0] if os.path.isfile(source_path) else staged
    recipe = {
        "version": FRAMES_CACHE_VERSION,
        "in_seconds": None if in_seconds is None else round(float(in_seconds), 6),
        "seconds": None if seconds is None else round(float(seconds), 6),
        "dims": list(dims) if dims else None,
        "fps": None if fps is None else round(float(fps), 4),
        "normalise_log": bool(NORMALISE_LOG),
    }
    digest = hashlib.sha1(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")).hexdigest()[:10]
    return "%s_frames_%s" % (stem, digest)


def build_source_frames(source_path, target_dir, seconds=None, dims=None, in_seconds=None, fps=None, progress=None):
    if not _tool_path("ffmpeg"):
        return None
    rate = float(fps) if fps and float(fps) > 0 else DEFAULT_FPS
    frames_dir = sequence_source_dir(source_path)
    filters = []
    if dims:
        filters.append("scale=%d:%d:force_original_aspect_ratio=decrease" % tuple(dims))
        filters.append("pad=%d:%d:(ow-iw)/2:(oh-ih)/2" % tuple(dims))
    if NORMALISE_LOG:
        filters.append("curves=preset=lighter")
        filters.append("eq=contrast=1.35:saturation=1.25")
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir)
    started = time.perf_counter()
    cap = None
    if seconds and float(seconds) > 0:

        cap = int(round((float(seconds) + 0.5) * rate))
    video_argv = ["ffmpeg", "-y", "-v", "error"]
    audio_src = None
    list_path = None
    if frames_dir:
        files = sequence_frame_files(frames_dir)
        skip = int(round(float(in_seconds) * rate)) if in_seconds and float(in_seconds) > 0 else 0
        files = files[skip:]
        if cap:
            files = files[:cap]
        if not files:
            log("frames: %s has no frames after the in-point" % frames_dir)
            shutil.rmtree(target_dir, ignore_errors=True)
            return None
        list_path = os.path.join(target_dir, "frames.txt")
        with open(list_path, "w", encoding="utf-8") as handle:
            for path in files:
                handle.write("file '%s'\nduration %.6f\n"
                             % (path.replace("\\", "/").replace("'", "'\\''"), 1.0 / rate))
        video_argv += ["-f", "concat", "-safe", "0", "-i", list_path]
        audio_src = sequence_audio_file(frames_dir)
    else:
        if in_seconds and float(in_seconds) > 0:
            video_argv += ["-ss", "%.3f" % float(in_seconds)]
        video_argv += ["-i", source_path]
        if seconds and float(seconds) > 0:
            video_argv += ["-t", "%.3f" % (float(seconds) + 0.5)]
        audio_src = source_path if has_audio_stream(source_path) else None
    if filters:
        video_argv += ["-vf", ",".join(filters)]
    video_argv += ["-r", "%g" % rate]
    if cap:
        video_argv += ["-frames:v", str(cap)]
    video_argv += ["-pix_fmt", "rgb24", "-compression_level", "1", "-start_number", "1",
                   os.path.join(target_dir, "%06d.png")]
    out = _run_tool_polled(video_argv, 900, (lambda: progress(len(sequence_frame_files(target_dir)), cap or 0)) if progress else None)
    frames = sequence_frame_files(target_dir)
    if out is None or not frames:
        log("frames: ffmpeg produced no PNG frames for %s" % os.path.basename(source_path.rstrip("\\/")))
        shutil.rmtree(target_dir, ignore_errors=True)
        return None

    audio_target = os.path.join(target_dir, "audio.wav")
    audio_argv = ["ffmpeg", "-y", "-v", "error"]
    if audio_src:
        if in_seconds and float(in_seconds) > 0:
            audio_argv += ["-ss", "%.3f" % float(in_seconds)]
        audio_argv += ["-i", audio_src]
    else:
        audio_argv += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    audio_argv += ["-t", "%.3f" % (len(frames) / rate), "-vn", "-c:a", "pcm_s24le", audio_target]
    out = _run_tool(audio_argv, timeout=600)
    if out is None or not os.path.isfile(audio_target) or os.path.getsize(audio_target) == 0:
        log("frames: audio extraction failed for %s" % os.path.basename(source_path.rstrip("\\/")))
        shutil.rmtree(target_dir, ignore_errors=True)
        return None
    if list_path:
        try:
            os.remove(list_path)
        except OSError:
            pass
    result = {"directory": target_dir, "audio": audio_target, "count": len(frames)}
    with open(os.path.join(target_dir, ".complete.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle)
    log("frames: %s -> %s  (%d PNG frames at %g fps%s + %s, %.1fs)"
        % (os.path.basename(source_path.rstrip("\\/")), os.path.basename(target_dir), len(frames), rate,
           " %dx%d" % tuple(dims) if dims else "", "source audio" if audio_src else "silent audio",
           time.perf_counter() - started))
    return result


def stage_source_frames(source_path, input_dir, seconds=None, dims=None, in_seconds=None, fps=None, progress=None):
    source_path = os.path.normpath(source_path or "")
    if not source_path or not (os.path.isfile(source_path) or os.path.isdir(source_path)):
        raise SecondUnitError("Source not found: %s" % source_path)
    if not input_dir or not os.path.isdir(input_dir):
        raise SecondUnitError("ComfyUI did not report a writable --input-directory, and a frame "
                              "sequence cannot be uploaded one file at a time")
    if not _tool_path("ffmpeg"):
        raise SecondUnitError("ffmpeg is not on PATH, so frames cannot be extracted")
    if os.path.isdir(source_path) and not sequence_frame_files(source_path):
        raise SecondUnitError("%s holds no still frames (png/tif/exr/dpx/jpg)" % source_path)
    name = frames_input_name(source_path, seconds=seconds, dims=dims, in_seconds=in_seconds, fps=fps)
    target_dir = os.path.join(input_dir, name)
    marker = os.path.join(target_dir, ".complete.json")
    if os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            count = int(cached.get("count") or 0)
            if (count > 0 and len(sequence_frame_files(target_dir)) >= count
                    and os.path.isfile(str(cached.get("audio") or ""))):
                log("frames: reusing %s (%d frames)" % (name, count))
                return {"directory": target_dir, "audio": str(cached["audio"]), "count": count}
        except (OSError, ValueError):
            pass
    made = build_source_frames(source_path, target_dir, seconds=seconds, dims=dims,
                               in_seconds=in_seconds, fps=fps, progress=progress)
    if not made:
        raise SecondUnitError("ffmpeg could not extract frames from %s"
                              % os.path.basename(source_path.rstrip("\\/")))
    return made


def staging_directory(input_dir, cache_root=None):
    if input_dir and os.path.isdir(input_dir):
        probe = os.path.join(input_dir, ".second-unit-write-probe-%s.tmp" % uuid.uuid4().hex)
        try:
            with open(probe, "wb") as handle:
                handle.write(b"probe")
            os.remove(probe)
            return input_dir, False
        except (IOError, OSError) as exc:
            log("staging: %s is not writable from here (%s)" % (input_dir, exc))
    local = os.path.join(cache_root or LAB_CACHE, "input-staging")
    if not os.path.isdir(local):
        os.makedirs(local)
    return local, True


def upload_staged_inputs(client, local_dir, names):
    done = []
    for name in names:
        if not name or name in done:
            continue
        stored = client.upload_input(os.path.join(local_dir, name))
        if stored != name:
            raise SecondUnitError(
                "ComfyUI stored the upload of %s under a different name (%s), so the graph would "
                "not find it. Nothing was queued." % (name, stored))
        done.append(name)
    return done


def stage_source_file(source_path, input_dir, seconds=None, dims=None, in_seconds=None):
    if not source_path or not os.path.isfile(source_path):
        raise SecondUnitError("Source file not found: %s" % source_path)
    if not input_dir or not os.path.isdir(input_dir):
        raise SecondUnitError(
            "ComfyUI did not report an --input-directory, so the source cannot be staged. "
            "Point the graph at a file already inside ComfyUI/input instead."
        )
    target_name = staged_input_name(source_path)


    still = os.path.splitext(source_path)[1].lower() in (
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".exr", ".dpx")
    if (dims or seconds) and not still:
        proxy_name = proxy_input_name(source_path, seconds=seconds, dims=dims,
                                      in_seconds=in_seconds)
        proxy_target = os.path.join(input_dir, proxy_name)
        if os.path.isfile(proxy_target) and os.path.getsize(proxy_target) > 0:
            log("proxy: reusing %s" % proxy_name)
            return proxy_name
        made = build_source_proxy(source_path, proxy_target, seconds=seconds, dims=dims,
                                  in_seconds=in_seconds)
        if made:
            return proxy_name

    target = os.path.join(input_dir, target_name)
    if not os.path.isfile(target) or os.path.getsize(target) != os.path.getsize(source_path):
        log("staging the original (%.1f MB) - no proxy was built"
            % (os.path.getsize(source_path) / 1e6))
        shutil.copyfile(source_path, target)
    return target_name






_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def comfy_auth_headers(extra=None):
    headers = {}
    raw = _cfg("comfy_headers", "SECOND_UNIT_COMFY_HEADERS", "")
    if isinstance(raw, dict):
        headers.update({str(k): str(v) for k, v in raw.items()})
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                headers.update({str(k): str(v) for k, v in parsed.items()})
            else:
                log("SECOND_UNIT_COMFY_HEADERS ignored: not a JSON object")
        except ValueError:
            log("SECOND_UNIT_COMFY_HEADERS ignored: not valid JSON")
    key = str(_cfg("comfy_api_key", "SECOND_UNIT_COMFY_API_KEY", "") or "").strip()
    if key:
        scheme = str(_cfg("comfy_auth_header", "SECOND_UNIT_COMFY_AUTH_HEADER", "Authorization: Bearer") or "")
        name, _sep, prefix = scheme.partition(":")
        name = name.strip() or "Authorization"
        prefix = prefix.strip()
        headers[name] = (prefix + " " + key) if prefix else key
    if extra:
        headers.update(extra)
    return headers


def comfy_auth_configured():
    return bool(str(_cfg("comfy_api_key", "SECOND_UNIT_COMFY_API_KEY", "") or "").strip()
                or _cfg("comfy_headers", "SECOND_UNIT_COMFY_HEADERS", ""))



def multipart_form_data(fields, file_field, filename, data, content_type="application/octet-stream"):
    boundary = "----SecondUnit" + uuid.uuid4().hex
    parts = []
    for key, value in sorted((fields or {}).items()):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, key, value)).encode("utf-8"))
    safe_name = os.path.basename(str(filename)).replace('"', "_")
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (boundary, file_field, safe_name, content_type)).encode("utf-8"))
    parts.append(bytes(data or b""))
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    return "multipart/form-data; boundary=%s" % boundary, b"".join(parts)


class ComfyClient(object):
    def __init__(self, base=COMFY_URL):
        self.base = _with_scheme(base)

    def _get(self, path, timeout):
        url = self.base + path
        try:
            request = urllib.request.Request(url, headers=comfy_auth_headers({"Accept": "application/json"}))
            with _OPENER.open(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise SecondUnitError("GET %s -> HTTP %s" % (path, exc.code))
        except socket.timeout as exc:
            raise ComfyTimeout(
                "ComfyUI at %s accepted the connection but did not answer within %ds. It is "
                "running but busy or stuck - check its console. (%s)" % (self.base, timeout, exc))
        except Exception as exc:
            if isinstance(exc, urllib.error.URLError) and isinstance(
                    getattr(exc, "reason", None), socket.timeout):
                raise ComfyTimeout(
                    "ComfyUI at %s accepted the connection but did not answer within %ds. It is "
                    "running but busy or stuck - check its console." % (self.base, timeout))

            log("unreachable %s: %r" % (self.base, exc))
            raise ComfyUnreachable(UNREACHABLE_MSG.format(base=self.base))
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except ValueError as exc:
            raise SecondUnitError("GET %s returned non-JSON (%s)" % (path, exc))

    def ping(self, timeout=None, quiet=False):
        started = time.perf_counter()
        timeout = PING_TIMEOUT if timeout is None else max(0.1, float(timeout))
        if not quiet:
            log("ping -> %s (timeout %ss)" % (self.base, timeout))
        try:
            stats = self._get("/system_stats", timeout)
        except Exception as exc:
            if not quiet:
                log("ping <- FAILED after %.1fs: %s: %s"
                    % (time.perf_counter() - started, exc.__class__.__name__, exc))
            raise
        if not quiet:
            log("ping <- ok in %.1fs" % (time.perf_counter() - started))
        return stats

    def free_cache(self):
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/free", data=payload, headers=comfy_auth_headers({"Content-Type": "application/json"})
        )
        try:
            with _OPENER.open(request, timeout=SUBMIT_TIMEOUT) as response:
                response.read()
        except Exception as exc:
            log("cache release failed on %s: %r" % (self.base, exc))
            raise SecondUnitError(
                "ComfyUI could not release its warm model cache before this render (%s). "
                "Nothing was submitted." % exc
            )

    def submit(self, graph, client_id):
        assert_h3_frame_grid(graph)
        payload = json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/prompt", data=payload, headers=comfy_auth_headers({"Content-Type": "application/json"})
        )
        try:
            with _OPENER.open(request, timeout=SUBMIT_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            raise ComfySubmitRejected(self._format_submit_error(exc))
        except (socket.timeout, TimeoutError) as exc:

            log("submit timed out after %ss at %s: %r" % (SUBMIT_TIMEOUT, self.base, exc))
            raise ComfyUnreachable(
                "ComfyUI did not answer the submit within %d s. It MAY have accepted the prompt "
                "- check its queue and history before pressing Generate again." % SUBMIT_TIMEOUT)
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
                log("submit timed out after %ss at %s: %r" % (SUBMIT_TIMEOUT, self.base, exc))
                raise ComfyUnreachable(
                    "ComfyUI did not answer the submit within %d s. It MAY have accepted the "
                    "prompt - check its queue and history before pressing Generate again."
                    % SUBMIT_TIMEOUT)
            log("unreachable %s: %r" % (self.base, exc))
            raise ComfyUnreachable(UNREACHABLE_MSG.format(base=self.base))
        except Exception as exc:

            log("unreachable %s: %r" % (self.base, exc))
            raise ComfyUnreachable(UNREACHABLE_MSG.format(base=self.base))
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise SecondUnitError("ComfyUI accepted nothing: %s" % json.dumps(result)[:300])


        node_errors = result.get("node_errors") or {}
        if node_errors:
            node_id = sorted(node_errors)[0]
            problem = node_errors[node_id] or {}
            first = (problem.get("errors") or [{}])[0]
            detail = str(first.get("details") or first.get("message") or problem)[:200].splitlines()
            raise SecondUnitError(
                "ComfyUI accepted the prompt but DROPPED node %s (%s): %s. That node would not "
                "have run, so nothing was queued." % (node_id, problem.get("class_type", "?"),
                                                      detail[0] if detail else "no detail"))
        return prompt_id

    @staticmethod
    def _format_submit_error(exc):
        try:
            body = exc.read().decode("utf-8", "replace")
            detail = json.loads(body)
        except Exception:
            return "ComfyUI rejected this preset (HTTP %s). Nothing was queued." % exc.code
        log("submit rejected (HTTP %s): %s" % (exc.code, body[:2000]))


        for node_id in sorted(detail.get("node_errors") or {}):
            node_error = (detail["node_errors"] or {})[node_id]
            for item in (node_error.get("errors") or []):
                message = (item.get("message") or "").strip()
                if message:
                    return ("ComfyUI rejected this preset at node %s (%s): %s. Nothing was "
                            "queued - details in %s"
                            % (node_id, node_error.get("class_type", "?"),
                               message.rstrip("."), log_path()))

        error = detail.get("error") or {}
        message = (error.get("message") or "").strip()
        if message:
            return ("ComfyUI rejected this preset: %s. Nothing was queued - details in %s"
                    % (message.rstrip("."), log_path()))
        return "ComfyUI rejected this preset (HTTP %s). Nothing was queued." % exc.code

    def object_info(self, class_type):
        cache = getattr(self, "_class_cache", None)
        if cache is None:
            cache = self._class_cache = {}
        if class_type in cache:
            return cache[class_type]
        try:
            body = self._get("/object_info/" + urllib.parse.quote(class_type), PREFLIGHT_TIMEOUT)
        except Exception as exc:
            log("preflight: could not ask about %s (%s)" % (class_type, exc))
            body = None
        cache[class_type] = body
        return body

    def upload_input(self, path, overwrite=True, timeout=None):
        if not path or not os.path.isfile(path):
            raise SecondUnitError("Nothing to upload: %s" % path)
        with open(path, "rb") as handle:
            data = handle.read()
        content_type, body = multipart_form_data(
            {"overwrite": "true" if overwrite else "false", "subfolder": "", "type": "input"},
            "image", os.path.basename(path), data)
        request = urllib.request.Request(
            self.base + "/upload/image", data=body,
            headers=comfy_auth_headers({"Content-Type": content_type, "Content-Length": str(len(body))}))
        started = time.perf_counter()
        try:
            with _OPENER.open(request, timeout=timeout or DOWNLOAD_TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise SecondUnitError("ComfyUI refused the upload of %s (HTTP %s). Nothing was queued."
                                  % (os.path.basename(path), exc.code))
        except Exception as exc:
            log("upload failed %s: %r" % (self.base, exc))
            raise ComfyUnreachable(UNREACHABLE_MSG.format(base=self.base))
        try:
            result = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        except ValueError:
            result = {}
        name = str((result or {}).get("name") or os.path.basename(path))
        log("upload: %s -> %s/%s (%.2f MB in %.1fs)"
            % (os.path.basename(path), (result or {}).get("type") or "input", name,
               len(data) / 1e6, time.perf_counter() - started))
        return name

    def history(self, prompt_id, timeout=None):
        data = self._get("/history/" + urllib.parse.quote(str(prompt_id)), POLL_TIMEOUT if timeout is None else timeout)
        return (data or {}).get(str(prompt_id))

    def queue_position(self, prompt_id, timeout=None):
        data = self._get("/queue", POLL_TIMEOUT if timeout is None else timeout)
        for item in data.get("queue_running") or []:
            if len(item) > 1 and str(item[1]) == str(prompt_id):
                return "running", 0
        for index, item in enumerate(data.get("queue_pending") or []):
            if len(item) > 1 and str(item[1]) == str(prompt_id):
                return "pending", index + 1
        return "absent", -1

    def download(self, item, dest_dir):
        query = urllib.parse.urlencode({
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        })
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
        target = os.path.join(dest_dir, item["filename"])
        try:
            with _OPENER.open(urllib.request.Request(self.base + "/view?" + query, headers=comfy_auth_headers()),
                              timeout=DOWNLOAD_TIMEOUT) as response:
                with open(target, "wb") as handle:
                    shutil.copyfileobj(response, handle)
        except Exception as exc:
            raise SecondUnitError("Could not fetch %s from ComfyUI: %s" % (item["filename"], exc))


        if os.path.getsize(target) == 0:
            try:
                os.remove(target)
            except OSError:
                pass
            raise SecondUnitError(
                "ComfyUI returned an empty file for %s. The render did not produce usable "
                "output." % item["filename"])
        return target



class ComfyProgressListener(threading.Thread):
    def __init__(self, base, client_id):
        threading.Thread.__init__(self, name="comfy-progress", daemon=True)
        self.base, self.client_id, self.lock, self.prompt_id = base, client_id, threading.Lock(), None
        self.latest, self.first = None, {}
        self.sock, self.stopped = None, False
    def _recv_exact(self, buf, n):
        while len(buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                return None
            buf += chunk
        return buf
    def _frame(self, buf):
        buf = self._recv_exact(buf, 2)
        if buf is None:
            return None, b"", b""
        opcode, length, pos = buf[0] & 0x0F, buf[1] & 0x7F, 2
        if length == 126:
            buf = self._recv_exact(buf, 4)
            if buf is None: return None, b"", b""
            length, pos = int.from_bytes(buf[2:4], "big"), 4
        elif length == 127:
            buf = self._recv_exact(buf, 10)
            if buf is None: return None, b"", b""
            length, pos = int.from_bytes(buf[2:10], "big"), 10
        buf = self._recv_exact(buf, pos + length)
        if buf is None:
            return None, b"", b""
        return opcode, buf[pos:pos + length], buf[pos + length:]
    def _send(self, opcode, payload):
        payload = bytes(payload[:125])
        mask = os.urandom(4)
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    def _read_loop(self, buf):
        while not self.stopped:
            opcode, payload, buf = self._frame(buf)
            if opcode is None or opcode == 8:
                return
            if opcode == 9:
                self._send(10, payload)
                continue
            if opcode != 1:
                continue
            msg = json.loads(payload.decode("utf-8", "replace"))
            data = msg.get("data") or {}
            if msg.get("type") == "progress" and (self.prompt_id is None or data.get("prompt_id") == self.prompt_id):
                with self.lock:
                    node = str(data.get("node"))
                    self.first.setdefault(node, (time.monotonic(), float(data.get("value") or 0)))
                    self.latest = dict(data, at=time.monotonic(), first=self.first[node])
            elif (msg.get("type") == "executing" and data.get("node") is None
                  and self.prompt_id is not None and data.get("prompt_id") == self.prompt_id):
                return
    def run(self):
        try:
            parsed = urllib.parse.urlparse(self.base)
            self.sock = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=10)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            extra = "".join("%s: %s\r\n" % kv for kv in comfy_auth_headers().items())
            self.sock.sendall(("GET /ws?clientId=%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n%s\r\n"
                               % (self.client_id, parsed.netloc, key, extra)).encode("ascii"))
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = self.sock.recv(1024)
                if not chunk:
                    return
                head += chunk
            if b" 101 " not in head.split(b"\r\n", 1)[0]:
                log("progress socket refused: %r" % head[:80])
                return
            self.sock.settimeout(None)
            self._read_loop(head.split(b"\r\n\r\n", 1)[1])
        except Exception as exc:
            log("progress socket ended: %s: %s" % (exc.__class__.__name__, exc))
        finally:
            self.close()
    def snapshot(self):
        with self.lock:
            return dict(self.latest) if self.latest else None
    def close(self):
        self.stopped = True
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass





MODEL_EXT = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".sft", ".bin")

PREFLIGHT_TIMEOUT = 8

PREFLIGHT_BUDGET = 10.0


WORKER_SILENCE_S = _env_float("SECOND_UNIT_SILENCE", 90)

WORKER_LAUNCH_GRACE_S = _env_float("SECOND_UNIT_LAUNCH_GRACE", 90)

DELIVERY_RETRY_S = _env_float("SECOND_UNIT_DELIVERY_RETRY", 10)
BUILD_CHECK_S = _env_float("SECOND_UNIT_BUILD_CHECK", 10)
BUILD_STALE_TEXT = ("NEW BUILD ON DISK: Second Unit was redeployed while this panel was open. Close this panel "
                    "window and reopen it (Workspace > Workflow Integrations > Second Unit) before generating. "
                    "A render that is already running still lands.")
RECONCILE_TICK_S = _env_float("SECOND_UNIT_RECONCILE_TICK", 30)
RECONCILE_HTTP_TIMEOUT = 2.0
SEQ_STALL_S = _env_float("SECOND_UNIT_SEQ_STALL", 20)


VRAM_COMFORTABLE_GB = _env_float("SECOND_UNIT_VRAM_WARN", 20)

POLL_UNREACHABLE_GRACE_S = _env_float("SECOND_UNIT_POLL_GRACE", 600)

PROMPT_VANISHED_S = 45.0
DOWNLOAD_TIMEOUT = _env_int("SECOND_UNIT_DOWNLOAD_TIMEOUT", 300)

MIN_OUTPUT_BYTES = 1024
MIN_BYTES_PER_FRAME = 200
BLACK_FRACTION = 0.95
PROBE_TIMEOUT_S = 20
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".mxf", ".m4v")


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0



def _tool_path(name):
    base = os.path.splitext(os.path.basename(str(name or "")))[0].lower()
    hint = os.environ.get("SECOND_UNIT_FFMPEG", "").strip().strip('"')
    if hint and base in ("ffmpeg", "ffprobe"):
        folder = hint if os.path.isdir(hint) else os.path.dirname(hint)
        for candidate in (os.path.join(folder, base + ".exe"), os.path.join(folder, base)):
            if os.path.isfile(candidate):
                return candidate
    return shutil.which(name)


def tool_status():
    return {"ffmpeg": _tool_path("ffmpeg"), "ffprobe": _tool_path("ffprobe")}


def _run_tool(argv, timeout=PROBE_TIMEOUT_S):
    exe = _tool_path(argv[0])
    if not exe:
        return None
    try:
        completed = subprocess.run(
            [exe] + list(argv[1:]),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, creationflags=_NO_WINDOW,
        )
        output = (completed.stdout or b"").decode("utf-8", "replace")
        if completed.returncode != 0:
            log("probe %s exited %d: %s" % (argv[0], completed.returncode, output[-500:]))
            return None
        return output
    except Exception as exc:
        log("probe %s failed: %s" % (argv[0], exc))
        return None


def _start_tool(argv):
    exe = _tool_path(argv[0])
    if not exe:
        return None, None
    try:
        return subprocess.Popen([exe] + list(argv[1:]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW), exe
    except Exception as exc:
        log("start %s failed: %s" % (argv[0], exc))
        return None, None


def _run_tool_polled(argv, timeout, on_poll=None):
    exe = _tool_path(argv[0])
    if not exe:
        return None
    try:
        proc = subprocess.Popen([exe] + list(argv[1:]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    except Exception as exc:
        log("probe %s failed: %s" % (argv[0], exc))
        return None
    started, out = time.monotonic(), b""
    while True:
        try:
            out, _ = proc.communicate(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            if on_poll:
                try:
                    on_poll()
                except Exception:
                    pass
            if time.monotonic() - started > timeout:
                proc.kill()
                out, _ = proc.communicate()
                log("probe %s killed after %ss" % (argv[0], timeout))
                return None
    output = (out or b"").decode("utf-8", "replace")
    if proc.returncode != 0:
        log("probe %s exited %d: %s" % (argv[0], proc.returncode, output[-500:]))
        return None
    return output


def probe_duration(path):
    out = _run_tool(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", path])
    if not out:
        return None
    try:
        return float(out.strip().splitlines()[0])
    except Exception:
        return None


def probe_dimensions(path):
    out = _run_tool(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=width,height", "-of", "csv=p=0:s=x", path])
    if not out:
        return None
    try:
        width, height = out.strip().splitlines()[0].split("x")[:2]
        return int(width), int(height)
    except Exception:
        return None


def probe_frame_count(path):
    out = _run_tool(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                     "-show_entries", "stream=nb_read_frames,nb_frames,avg_frame_rate,duration",
                     "-of", "json", path])
    if not out:
        return None
    try:
        stream = (json.loads(out).get("streams") or [])[0]
        for key in ("nb_read_frames", "nb_frames"):
            value = stream.get(key)
            if value not in (None, "", "N/A"):
                return int(value)
        rate = str(stream.get("avg_frame_rate") or "0")
        if "/" in rate:
            numerator, denominator = rate.split("/", 1)
            fps = float(numerator) / float(denominator)
        else:
            fps = float(rate)
        return int(round(float(stream.get("duration") or 0) * fps)) or None
    except Exception:
        return None


def probe_delivery_format(path):
    out = _run_tool([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,profile,pix_fmt:format=format_name",
        "-of", "json", path,
    ])
    if not out:
        return None
    try:
        payload = json.loads(out)
        stream = (payload.get("streams") or [])[0]
        result = dict(stream)
        result["format_name"] = (payload.get("format") or {}).get("format_name")
        return result
    except Exception:
        return None


def delivery_is_prores_hq(info):
    info = info or {}
    formats = set(str(info.get("format_name") or "").lower().split(","))
    profile = str(info.get("profile") or "").upper()
    return (
        str(info.get("codec_name") or "").lower() == "prores"
        and (profile == "HQ" or "422 HQ" in profile)
        and str(info.get("pix_fmt") or "").lower() in ("yuv422p10le", "yuv444p10le")
        and bool(formats & {"mov", "quicktime"})
    )


def prepare_delivery_outputs(paths, frames=None):
    for path in paths:
        extension = os.path.splitext(path or "")[1].lower()
        if extension in VIDEO_EXTENSIONS:
            facts = probe_delivery_format(path)
            if not delivery_is_prores_hq(facts):
                raise SecondUnitError(
                    "ComfyUI returned a video that is not ProRes HQ 10-bit (%r). "
                    "Nothing was imported. File: %s" % (facts, path))
            log("Comfy ProRes HQ verified -> %s (%r)" % (path, facts))
    return list(paths)


def probe_audio_format(path):
    out = _run_tool([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,channel_layout,duration",
        "-of", "json", path,
    ])
    if not out:
        return None
    try:
        streams = json.loads(out).get("streams") or []
        return dict(streams[0]) if streams else None
    except Exception:
        return None


def audio_segment_md5(path, duration, in_seconds=None):
    argv = ["ffmpeg", "-v", "error"]
    if in_seconds is not None and float(in_seconds) > 0:
        argv += ["-ss", "%.9f" % float(in_seconds)]
    argv += [
        "-i", path, "-map", "0:a:0", "-t", "%.9f" % float(duration),
        "-c:a", "pcm_s16le", "-f", "md5", "-",
    ]
    out = _run_tool(argv, timeout=120)
    return out.strip() if out else None


def _next_video1_audio_path(path):
    root, extension = os.path.splitext(path)
    extension = extension or ".mov"
    candidate = root + "_video1_audio" + extension
    number = 2
    while os.path.exists(candidate):
        candidate = "%s_video1_audio_%d%s" % (root, number, extension)
        number += 1
    return candidate


def _next_exact_frame_path(path, frames):
    root, extension = os.path.splitext(path)
    extension = extension or ".mov"
    candidate = "%s_exact%df%s" % (root, int(frames), extension)
    number = 2
    while os.path.exists(candidate):
        candidate = "%s_exact%df_%d%s" % (root, int(frames), number, extension)
        number += 1
    return candidate


def trim_video_outputs_to_exact_frames(paths, frames, fps):
    try:
        expected_frames = int(frames)
        expected_fps = float(fps)
    except (TypeError, ValueError):
        raise SecondUnitError("Exact delivery trim received invalid timing.")
    if expected_frames < 1 or expected_fps <= 0:
        raise SecondUnitError("Exact delivery trim timing must be positive.")
    duration = expected_frames / expected_fps
    trimmed = []
    for path in list(paths or []):
        extension = os.path.splitext(path or "")[1].lower()
        if extension not in VIDEO_EXTENSIONS:
            trimmed.append(path)
            continue
        actual_frames = probe_frame_count(path)
        if actual_frames is None or actual_frames < expected_frames:
            raise SecondUnitError(
                "Exact delivery requires %d frames, but the render contains %s. "
                "The raw render was kept and nothing was imported."
                % (expected_frames, "an unknown frame count" if actual_frames is None else actual_frames))
        if actual_frames == expected_frames:
            trimmed.append(path)
            continue
        if not _tool_path("ffmpeg") or not _tool_path("ffprobe"):
            raise SecondUnitError(
                "H3 rendered %d frames for an exact %d-frame edit, but ffmpeg/ffprobe are "
                "unavailable for the lossless delivery crop. The raw render was kept and "
                "nothing was imported." % (actual_frames, expected_frames))
        final_path = _next_exact_frame_path(path, expected_frames)
        final_root, final_extension = os.path.splitext(final_path)
        temporary = "%s.%s.tmp%s" % (
            final_root, uuid.uuid4().hex[:10], final_extension)
        argv = [
            "ffmpeg", "-y", "-v", "error", "-i", path,
            "-map", "0:v:0", "-map", "0:a:0?", "-frames:v", str(expected_frames),
            "-t", "%.9f" % duration, "-c", "copy", "-movflags", "+faststart",
            temporary,
        ]
        try:
            made = _run_tool(argv, timeout=300)
            if made is None or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                raise SecondUnitError(
                    "H3 finished, but its lossless exact-frame delivery crop failed. The "
                    "raw render was kept and nothing was imported.")
            delivery = probe_delivery_format(temporary)
            delivered_frames = probe_frame_count(temporary)
            if not delivery_is_prores_hq(delivery) or delivered_frames != expected_frames:
                raise SecondUnitError(
                    "H3 exact-frame crop failed validation (%r, %r of %d frames). The raw "
                    "render was kept and nothing was imported."
                    % (delivery, delivered_frames, expected_frames))
            os.replace(temporary, final_path)
            trimmed.append(final_path)
            log("H3 exact delivery crop %s: %d -> %d frames (lossless ProRes copy)"
                % (os.path.basename(path), actual_frames, expected_frames))
        finally:
            if os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass
    return trimmed


def select_detail_final_paths(base_paths, detail_paths):
    base_paths = list(base_paths or [])
    detail_paths = list(detail_paths or [])
    if not detail_paths:
        raise SecondUnitError(
            "The LTX detail stage returned no final file. The H3 base was kept and nothing "
            "was imported.")
    log("detail base retained as diagnostic only: %s" % "; ".join(base_paths))
    return detail_paths


def plan_world_generation_windows(total_frames, fps,
                                  max_seconds=WORLD_WINDOW_MAX_SECONDS,
                                  overlap_seconds=WORLD_WINDOW_OVERLAP_SECONDS):
    try:
        total_frames = int(total_frames)
        fps = float(fps)
        max_seconds = float(max_seconds)
        overlap_seconds = float(overlap_seconds)
    except (TypeError, ValueError):
        raise SecondUnitError("World Generation received invalid window timing.")
    if total_frames < 1 or fps <= 0 or max_seconds <= 0:
        raise SecondUnitError("World Generation window timing must be positive.")
    max_frames = max(1, int(math.floor(fps * max_seconds + 1e-6)))
    if total_frames <= max_frames:
        return [{"index": 0, "start_frame": 0, "frames": total_frames,
                 "overlap_frames": 0}]
    overlap_frames = max(1, int(round(fps * overlap_seconds)))
    overlap_frames = min(overlap_frames, max_frames - 1)
    stride = max_frames - overlap_frames
    count = int(math.ceil(float(total_frames - overlap_frames) / float(stride)))
    count = max(2, count)
    rendered_frames = total_frames + overlap_frames * (count - 1)
    base, extra = divmod(rendered_frames, count)
    lengths = [base + (1 if index < extra else 0) for index in range(count)]
    if max(lengths) > max_frames or min(lengths) <= overlap_frames:
        raise SecondUnitError(
            "World Generation could not form safe overlapping windows for %d frames."
            % total_frames)
    windows = []
    start = 0
    for index, length in enumerate(lengths):
        windows.append({
            "index": index,
            "start_frame": start,
            "frames": length,
            "overlap_frames": 0 if index == 0 else overlap_frames,
        })
        start += length - overlap_frames
    if start + overlap_frames != total_frames:
        raise SecondUnitError("World Generation window math did not preserve exact length.")
    return windows


def estimate_world_orchestration(params, request, graph):
    params = dict(params or {})
    request = dict(request or {})
    windows = list(request.get("windows") or [])
    try:
        fps = float(request["fps"])
        total_frames = int(request["frames"])
    except (KeyError, TypeError, ValueError):
        raise SecondUnitError("World orchestration estimate received invalid timing.")
    if not windows or fps <= 0 or total_frames < 1 or not isinstance(graph, dict):
        raise SecondUnitError("World orchestration estimate needs windows and a graph.")
    family = str(request.get("family") or "")
    resolution = str(params.get("resolution") or "720P")
    frame_target_classes = [
        (graph.get(node_id) or {}).get("class_type")
        for node_id, _key in find_frame_targets(graph)
    ]
    window_generated_frames = []
    window_estimates = []
    for window in windows:
        exact_frames = int(window.get("frames") or 0)
        if exact_frames < 1:
            raise SecondUnitError("World orchestration contains an empty window.")
        derived = derive_frames(fps, float(exact_frames) / fps)
        generated = max(
            [derived] + [snap_frames(derived, class_type)
                         for class_type in frame_target_classes])
        window_generated_frames.append(generated)
        window_estimates.append(estimate_render_seconds(
            family, "ENVSWAP", resolution, generated, graph))

    source_seconds = float(total_frames) / fps
    assembly_seconds = (
        WORLD_ASSEMBLY_BASE_ESTIMATE_S
        + WORLD_ASSEMBLY_PER_WINDOW_ESTIMATE_S * len(windows)
        + 0.5 * WORLD_DELIVERY_PER_SOURCE_SECOND_ESTIMATE_S * source_seconds)
    audio_seconds = (
        WORLD_AUDIO_BASE_ESTIMATE_S
        + 0.5 * WORLD_DELIVERY_PER_SOURCE_SECOND_ESTIMATE_S * source_seconds)
    detail_seconds = (estimate_detail_upscale_seconds(total_frames, resolution)
                      if params.get("detail_upscale") else 0.0)
    total_seconds = (sum(window_estimates) + assembly_seconds
                     + audio_seconds + detail_seconds)
    return {
        "window_generated_frames": window_generated_frames,
        "window_estimates": window_estimates,
        "assembly_seconds": assembly_seconds,
        "audio_seconds": audio_seconds,
        "detail_seconds": detail_seconds,
        "total_seconds": total_seconds,
    }


def world_orchestration_timeout_message(deadline_seconds, elapsed_seconds, phase,
                                        prompt_ids, target):
    prompts = "+".join(str(value)[:8] for value in (prompt_ids or []) if value) or "none yet"
    return (
        "World orchestration watcher deadline %s reached after %s during %s on %s "
        "(completed/known prompts: %s). ComfyUI may still be running. Second Unit did NOT "
        "cancel any prompt and will NOT retry any stage automatically. The durable World "
        "job remains uncertain and Generate stays locked until it is reconciled."
        % (watcher_duration(deadline_seconds), mmss(elapsed_seconds), phase, target, prompts)
    )


def world_window_child_params(params, request, window, index):
    fps = float(request["fps"])
    count = len(request["windows"])
    nested = dict(params or {})
    nested.update({
        "window_internal": True,
        "world_window_index": int(index),
        "world_window_count": count,
        "skip_preflight": int(index) > 0,

        "detail_upscale": False,
        "seconds": float(window["frames"]) / fps,
        "exact_frames": int(window["frames"]),
        "exact_fps": fps,
        "source_in_seconds": (float((params or {}).get("source_in_seconds") or 0.0)
                              + float(window["start_frame"]) / fps),
        "restore_source_audio": False,
    })
    stage_size = _normalise_stage_output_size(request.get("stage_output_size"))
    if stage_size is not None:
        nested["_h3_stage_output_size"] = list(stage_size)
    else:
        nested.pop("_h3_stage_output_size", None)
    return nested


def _next_world_assembly_path(path):
    root, _extension = os.path.splitext(path)
    candidate = root + "_worldgen_assembled.mov"
    number = 2
    while os.path.exists(candidate):
        candidate = "%s_worldgen_assembled_%d.mov" % (root, number)
        number += 1
    return candidate


def assemble_world_generation_windows(paths, windows, total_frames, fps,
                                      expected_dimensions=None):
    paths = list(paths or [])
    windows = list(windows or [])
    if len(paths) != len(windows) or not paths:
        raise SecondUnitError(
            "World Generation window assembly received %d files for %d intervals."
            % (len(paths), len(windows)))
    if len(paths) == 1:
        return paths[0]
    expected_dimensions = _normalise_stage_output_size(expected_dimensions)
    try:
        total_frames = int(total_frames)
        fps = float(fps)
    except (TypeError, ValueError):
        raise SecondUnitError("World Generation assembly received invalid timing.")
    for path, window in zip(paths, windows):
        if not path or not os.path.isfile(path):
            raise SecondUnitError("A World Generation window is missing: %s" % path)
        actual = probe_frame_count(path)
        if actual != int(window["frames"]):
            raise SecondUnitError(
                "World Generation window %d has %r frames; expected %d. Nothing was assembled."
                % (int(window["index"]) + 1, actual, int(window["frames"])))
        dimensions = probe_dimensions(path)
        if expected_dimensions is not None and dimensions != expected_dimensions:
            raise SecondUnitError(
                "World Generation window %d is %r, not the native H3 intermediate canvas "
                "%r. Refusing a hidden pre-detail upscale; nothing was assembled."
                % (int(window["index"]) + 1, dimensions, expected_dimensions))
    if not _tool_path("ffmpeg") or not _tool_path("ffprobe"):
        raise SecondUnitError(
            "World Generation rendered its windows, but ffmpeg/ffprobe are unavailable to "
            "assemble and verify them. Nothing was imported.")

    final_path = _next_world_assembly_path(paths[0])
    root, extension = os.path.splitext(final_path)
    temporary = "%s.%s.tmp%s" % (root, uuid.uuid4().hex[:10], extension)
    argv = ["ffmpeg", "-y", "-v", "error"]
    for path in paths:
        argv += ["-i", path]
    filters = []
    for index in range(len(paths)):
        filters.append(
            "[%d:v:0]fps=%.9g,format=yuv422p10le,settb=AVTB,setpts=PTS-STARTPTS[v%d]"
            % (index, fps, index))
    current = "v0"
    for index in range(1, len(paths)):
        overlap_frames = int(windows[index]["overlap_frames"])
        duration = float(overlap_frames) / fps
        offset = float(windows[index]["start_frame"]) / fps
        out = "wx%d" % index
        filters.append(
            "[%s][v%d]xfade=transition=fade:duration=%.9f:offset=%.9f[%s]"
            % (current, index, duration, offset, out))
        current = out
    filters.append("[%s]trim=end_frame=%d,setpts=PTS-STARTPTS[outv]"
                   % (current, total_frames))
    argv += [
        "-filter_complex", ";".join(filters), "-map", "[outv]", "-an",
        "-frames:v", str(total_frames), "-c:v", "prores_ks", "-profile:v", "3",
        "-pix_fmt", "yuv422p10le", "-r", "%.9g" % fps, "-movflags", "+faststart",
        temporary,
    ]
    try:
        made = _run_tool(argv, timeout=1800)
        if made is None or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
            raise SecondUnitError(
                "World Generation windows rendered, but their ProRes assembly failed. "
                "The window files were kept and nothing was imported.")
        delivery = probe_delivery_format(temporary)
        actual_frames = probe_frame_count(temporary)
        actual_dimensions = probe_dimensions(temporary)
        if (not delivery_is_prores_hq(delivery) or actual_frames != total_frames
                or (expected_dimensions is not None
                    and actual_dimensions != expected_dimensions)):
            raise SecondUnitError(
                "World Generation assembly failed validation (%r, %r, %r of %d frames). "
                "The windows were kept and nothing was imported."
                % (delivery, actual_dimensions, actual_frames, total_frames))
        os.replace(temporary, final_path)
        log("World Generation assembled %d windows -> %s (%d frames at %.4g fps)"
            % (len(paths), os.path.basename(final_path), total_frames, fps))
        return final_path
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass


def sequence_first_cut(directory, threshold=0.30):
    files = sequence_frame_files(directory)
    exe = _tool_path("ffmpeg")
    if len(files) < 2 or not exe:
        return None
    work = os.path.join(LAB_CACHE, "cutscan")
    if not os.path.isdir(work):
        os.makedirs(work)
    listing = os.path.join(work, hashlib.sha256(os.path.abspath(directory).encode("utf-8")).hexdigest()[:12] + ".txt")
    with open(listing, "w", encoding="utf-8") as handle:
        for path in files:
            handle.write("file '%s'\nduration 0.0416667\n" % os.path.abspath(path).replace("\\", "/").replace("'", "'\\''"))
    try:
        completed = subprocess.run([exe, "-v", "error", "-f", "concat", "-safe", "0", "-i", listing, "-vf",
                                    "scale=160:90,select='gt(scene,%.2f)',metadata=print:file=-" % threshold,
                                    "-f", "null", "-"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600, creationflags=_NO_WINDOW)
    except Exception as exc:
        log("cut scan failed on %s: %s" % (directory, exc))
        return None
    match = re.search(r"pts_time:([0-9.]+)", (completed.stdout or b"").decode("utf-8", "replace"))
    return (int(round(float(match.group(1)) * 24.0)) + 1) if match else None


def source_audio_for(params):
    source = str((params or {}).get("source_path") or "")
    in_seconds = (params or {}).get("source_in_seconds")
    if source and os.path.isdir(source):
        manifest = read_sequence_manifest(source) or {}
        wav = str(manifest.get("wav") or "")
        if not (wav and os.path.isfile(wav)):
            wav = sequence_audio_file(source) or ""
        if wav:
            return wav, None
    return source, in_seconds


def restore_video1_audio(paths, source_path, frames, fps, source_in_seconds=None):
    if not source_path or not os.path.isfile(source_path):
        raise SecondUnitError(
            "Video 1 source audio could not be restored because the source file is missing: %s"
            % (source_path or "(none)"))
    if not _tool_path("ffmpeg") or not _tool_path("ffprobe"):
        raise SecondUnitError(
            "World Generation finished, but ffmpeg/ffprobe are unavailable to restore and "
            "verify Video 1's exact audio. Nothing was imported.")
    try:
        expected_frames = int(frames)
        expected_fps = float(fps)
        duration = expected_frames / expected_fps
    except (TypeError, ValueError, ZeroDivisionError):
        raise SecondUnitError(
            "World Generation finished, but its exact frame rate/duration was unavailable. "
            "Video 1 audio was not guessed and nothing was imported.")
    if expected_frames < 1 or expected_fps <= 0 or duration <= 0:
        raise SecondUnitError(
            "World Generation reported invalid timing (%r frames at %r fps). Nothing was imported."
            % (frames, fps))

    source_audio = probe_audio_format(source_path)
    restored = []
    for path in paths:
        extension = os.path.splitext(path or "")[1].lower()
        if extension not in VIDEO_EXTENSIONS:
            restored.append(path)
            continue
        final_path = _next_video1_audio_path(path)
        final_root, final_extension = os.path.splitext(final_path)
        temporary = "%s.%s.tmp%s" % (final_root, uuid.uuid4().hex[:10], final_extension)
        argv = ["ffmpeg", "-y", "-v", "error", "-i", path]
        if source_audio:
            if source_in_seconds is not None and float(source_in_seconds) > 0:
                argv += ["-ss", "%.9f" % float(source_in_seconds)]
            argv += ["-i", source_path, "-map", "0:v:0", "-map", "1:a:0",
                     "-c:v", "copy", "-c:a", "pcm_s16le"]
        else:
            argv += ["-map", "0:v:0", "-c:v", "copy", "-an"]
        argv += ["-t", "%.9f" % duration, "-movflags", "+faststart", temporary]
        try:
            made = _run_tool(argv, timeout=300)
            if made is None or not os.path.isfile(temporary) or os.path.getsize(temporary) == 0:
                raise SecondUnitError(
                    "World Generation finished, but the Video 1 audio delivery could not be "
                    "written. The raw render was kept and nothing was imported.")
            delivery = probe_delivery_format(temporary)
            actual_frames = probe_frame_count(temporary)
            if not delivery_is_prores_hq(delivery) or actual_frames != expected_frames:
                raise SecondUnitError(
                    "The Video 1 audio delivery failed image validation (%r, %r of %d frames). "
                    "The raw render was kept and nothing was imported."
                    % (delivery, actual_frames, expected_frames))
            delivered_audio = probe_audio_format(temporary)
            if source_audio:
                if not delivered_audio or str(delivered_audio.get("codec_name") or "").lower() != "pcm_s16le":
                    raise SecondUnitError(
                        "The Video 1 audio delivery did not contain verified PCM audio. The raw "
                        "render was kept and nothing was imported.")
                source_md5 = audio_segment_md5(
                    source_path, duration, in_seconds=source_in_seconds)
                delivery_md5 = audio_segment_md5(temporary, duration)
                if not source_md5 or source_md5 != delivery_md5:
                    raise SecondUnitError(
                        "The Video 1 audio checksum did not match the finished MOV. The raw "
                        "render was kept and nothing was imported.")
                log("Video 1 audio verified %s -> %s (%s)"
                    % (os.path.basename(source_path), os.path.basename(final_path), source_md5))
            elif delivered_audio:
                raise SecondUnitError(
                    "Video 1 is silent, but the finished MOV still contains generated audio. "
                    "The raw render was kept and nothing was imported.")
            os.replace(temporary, final_path)
            restored.append(final_path)
        finally:
            if os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass
    return restored


def probe_black_seconds(path):
    out = _run_tool(["ffmpeg", "-v", "info", "-i", path,
                     "-vf", "blackdetect=d=0.1:pix_th=0.10", "-an", "-f", "null", "-"])
    if out is None:
        return None
    return sum(float(m) for m in re.findall(r"black_duration:([0-9.]+)", out))


def reference_grid_scores(gray, width, height):
    try:
        width, height = int(width), int(height)
        values = bytearray(gray)
    except Exception:
        return None
    if width < 30 or height < 20 or len(values) != width * height:
        return None
    x0, x1 = int(width * 0.03), int(width * 0.97)
    y0, y1 = int(height * 0.05), int(height * 0.95)
    if x1 <= x0 or y1 <= y0:
        return None
    total = 0
    samples = 0
    for y in range(y0, y1):
        row = y * width
        for x in range(x0, x1):
            total += values[row + x]
            samples += 1
    overall = float(total) / float(max(1, samples))

    columns = []
    for x in range(width):
        columns.append(sum(values[y * width + x] for y in range(y0, y1))
                       / float(y1 - y0))
    rows = []
    for y in range(height):
        row = y * width
        rows.append(sum(values[row + x] for x in range(x0, x1))
                    / float(x1 - x0))

    def darkest_pair(items, start, end):
        start = max(0, int(start))
        end = min(len(items) - 1, int(end))
        choices = [((items[i] + items[i + 1]) / 2.0, i)
                   for i in range(start, end) if i + 1 < len(items)]
        return min(choices) if choices else (255.0, -1)

    vertical_1 = darkest_pair(columns, width * 0.30, width * 0.37)
    vertical_2 = darkest_pair(columns, width * 0.63, width * 0.70)
    horizontal = darkest_pair(rows, height * 0.44, height * 0.52)
    threshold = max(18.0, overall * 0.48)
    detected = bool(overall > 28.0 and vertical_1[0] < threshold
                    and vertical_2[0] < threshold and horizontal[0] < threshold)
    return {
        "detected": detected, "overall": overall, "threshold": threshold,
        "vertical_1": vertical_1, "vertical_2": vertical_2,
        "horizontal": horizontal,
    }


def probe_reference_grid(path):
    exe = _tool_path("ffmpeg")
    if not exe or not path or not os.path.isfile(path):
        return None
    width, height = 320, 180
    try:
        completed = subprocess.run(
            [exe, "-v", "error", "-i", path, "-vf",
             "scale=%d:%d,format=gray" % (width, height),
             "-frames:v", "1", "-an", "-f", "rawvideo", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=PROBE_TIMEOUT_S,
            creationflags=_NO_WINDOW,
        )
        if completed.returncode != 0:
            log("reference-grid probe failed: %s"
                % (completed.stderr or b"")[-500:].decode("utf-8", "replace"))
            return None
        return reference_grid_scores(completed.stdout, width, height)
    except Exception as exc:
        log("reference-grid probe failed: %s" % exc)
        return None


def verify_output(path, frames=None, duration=None, black_seconds=None, probe=True,
                  dimensions=None, actual_frames=None):
    if not path or not os.path.isfile(path):
        return "missing", "the render reported a file that is not on disk: %s" % (path or "(none)")
    size = os.path.getsize(path)
    if size == 0:
        return "empty", "the render wrote 0 bytes"


    if probe and dimensions is None:
        dimensions = probe_dimensions(path)
    if dimensions:
        readable = "%dx%d, %d bytes" % (dimensions[0], dimensions[1], size)
    else:
        readable = None
        if size < MIN_OUTPUT_BYTES:
            if _tool_path("ffprobe"):
                return "suspect", ("%d bytes at %s and ffprobe cannot read it as media - the "
                                   "render may be damaged"
                                   % (size, os.path.basename(path)))
            return "tiny", ("the render wrote only %d bytes and ffprobe is not installed to "
                            "check it - it may be damaged" % size)


    if frames and frames > 1:
        if probe and actual_frames is None:
            actual_frames = probe_frame_count(path)
        if actual_frames is not None and actual_frames < max(1, int(math.ceil(frames * 0.95))):
            return "short", ("the render wrote %d of %d requested frames (%.1f%%)" %
                             (actual_frames, frames, 100.0 * actual_frames / float(frames)))
        if actual_frames is not None and actual_frames > int(frames) + 1:
            return "long", ("the render wrote %d frames for a %d-frame request; hidden guide "
                            "frames were not cropped" % (actual_frames, frames))

    if probe and black_seconds is None:
        black_seconds = probe_black_seconds(path)
    if black_seconds is not None:
        if duration is None and probe:
            duration = probe_duration(path)
        if duration is None and dimensions is None and _tool_path("ffprobe"):

            return "suspect", ("ffprobe cannot read %d bytes at %s as media - the file may be "
                               "damaged" % (size, os.path.basename(path)))
        if duration and duration > 0 and black_seconds >= BLACK_FRACTION * duration:
            return "black", ("ffmpeg reports %.1fs of %.1fs black - the render came out blank"
                             % (black_seconds, duration))
        return "ok", ("%s, %.1fs, %.1fs black" % (readable or "%d bytes" % size,
                                                   duration or 0.0, black_seconds))

    if frames and frames > 1:

        per_frame = size / float(frames)
        if per_frame < MIN_BYTES_PER_FRAME:
            return "suspect", ("%d bytes for %d frames (%.0f B/frame) - that is far too small "
                               "for real footage, and ffmpeg is not installed to confirm it"
                               % (size, frames, per_frame))
    return "ok", "%s (size checks only - ffmpeg not installed)" % (readable or "%d bytes" % size)



BLOCKING_VERDICTS = ("missing", "empty", "black", "short", "long")


def gate_outputs(paths, frames=None, probe=True, reject_reference_grid=False):
    warnings = []
    for path in paths:
        verdict, detail = verify_output(path, frames=frames, probe=probe)
        log("output gate %s: %s (%s)" % (os.path.basename(path or "?"), verdict, detail))
        if verdict in BLOCKING_VERDICTS:
            raise SecondUnitError(
                "The render finished but the file is unusable - %s. Nothing was imported. "
                "File: %s" % (detail, path))
        if verdict in ("suspect", "tiny"):
            warnings.append("WARNING: %s" % detail)
        if reject_reference_grid and probe and os.path.splitext(path or "")[1].lower() in VIDEO_EXTENSIONS:
            grid = probe_reference_grid(path)
            log("reference-grid gate %s: %r" % (os.path.basename(path or "?"), grid))
            if grid and grid.get("detected"):
                raise SecondUnitError(
                    "The render reproduced the five-panel reference sheet instead of one "
                    "photoreal shot. The file was kept for diagnosis and nothing was imported. "
                    "File: %s" % path)
    return paths, warnings


def graph_model_refs(graph):
    refs = []
    for node_id, node in sorted((graph or {}).items()):
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "?")
        for key, value in sorted((node.get("inputs") or {}).items()):
            if not isinstance(value, str) or value.startswith("http"):
                continue
            if value.lower().endswith(MODEL_EXT):
                refs.append((node_id, class_type, key, value))
    return refs


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


def model_ref_basename(value):
    return str(value or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def model_option_by_basename(value, options):
    wanted = model_ref_basename(value).lower()
    if not wanted:
        return None
    matches = [option for option in (options or [])
               if isinstance(option, str) and model_ref_basename(option).lower() == wanted]
    return matches[0] if len(matches) == 1 else None


def _spec_combo_options(spec, class_type, key):
    try:
        inputs = (spec.get(class_type) or {}).get("input") or {}
        for group in ("required", "optional"):
            options = combo_options((inputs.get(group) or {}).get(key))
            if options is not None:
                return options
    except Exception:
        pass
    return None


def resolve_model_refs_by_basename(graph, refs, class_specs):
    renamed = []
    for node_id, class_type, key, value in refs:
        spec = class_specs.get(class_type, None)
        if not spec:
            continue
        options = _spec_combo_options(spec, class_type, key)
        if options is None or value in options:
            continue
        match = model_option_by_basename(value, options)
        if match is None:
            continue
        node = graph.get(node_id) if isinstance(graph, dict) else None
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict):
            node["inputs"][key] = match
            renamed.append((node_id, key, value, match))
    return renamed


def graph_class_types(graph):
    return sorted(set(
        str(node.get("class_type")) for node in (graph or {}).values()
        if isinstance(node, dict) and node.get("class_type")))


def preflight_class_order(refs, graph):
    order = []
    for _node_id, class_type, _key, _value in refs:
        if class_type not in order:
            order.append(class_type)
    for class_type in graph_class_types(graph):
        if class_type not in order:
            order.append(class_type)
    return order


def preflight_node_findings(graph, class_specs):
    findings = []
    for node_id, node in sorted((graph or {}).items()):
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        if class_type and class_specs.get(class_type, None) == {}:
            findings.append((node_id, class_type, None, None, "node"))
    return findings


def preflight_findings(refs, class_specs):
    findings = []
    for node_id, class_type, key, value in refs:
        spec = class_specs.get(class_type, None)
        if spec is None:
            continue
        if spec == {}:
            findings.append((node_id, class_type, key, value, "node"))
            continue
        options = None
        try:
            inputs = (spec.get(class_type) or {}).get("input") or {}
            for group in ("required", "optional"):
                entry = (inputs.get(group) or {}).get(key)
                options = combo_options(entry)
                if options is not None:
                    break
        except Exception:
            options = None
        if options is None:
            continue
        if value not in options and model_option_by_basename(value, options) is None:
            findings.append((node_id, class_type, key, value, "model"))
    return findings


def describe_preflight(findings):
    missing_nodes = [f for f in findings if f[4] == "node"]
    missing_models = [f for f in findings if f[4] == "model"]
    parts = []
    if missing_models:
        node_id, class_type, key, value, _ = missing_models[0]
        parts.append(
            "this preset needs the model '%s' and ComfyUI does not have it (node %s, %s.%s)"
            % (value, node_id, class_type, key))
        if len(missing_models) > 1:
            parts.append("%d other model(s) are missing too" % (len(missing_models) - 1))
    if missing_nodes:
        classes = sorted(set(f[1] for f in missing_nodes))
        parts.append("custom node pack missing: %s%s (install the ComfyUI custom node pack that "
                     "provides it, then restart ComfyUI)"
                     % (", ".join(classes[:3]),
                        " (+%d more)" % (len(classes) - 3) if len(classes) > 3 else ""))
    return "REFUSED: " + "; ".join(parts) + ". Nothing was queued."



FIRST_RUN_PING_TIMEOUT_S = 1.2
FIRST_RUN_TOOL_TIMEOUT_S = 0.8


def ffmpeg_status_word():
    helper = globals().get("tool_status")
    if callable(helper):
        try:
            status = helper()
            value = status.get("ffmpeg") if isinstance(status, dict) else None
            if isinstance(value, dict):
                value = value.get("path") or value.get("found") or value.get("ok")
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            if isinstance(value, bool):
                return "found" if value else "missing"
            if isinstance(value, str) and value.strip():
                lowered = value.strip().lower()
                if os.path.isfile(value) or shutil.which(value):
                    return "found"
                if "missing" in lowered or "not found" in lowered:
                    return "missing"
        except Exception as exc:
            log("first-run: tool_status() raised %s: %s" % (exc.__class__.__name__, exc))
    exe = str(_cfg("ffmpeg", "SECOND_UNIT_FFMPEG", "ffmpeg") or "ffmpeg")
    found = exe if (os.path.isabs(exe) and os.path.isfile(exe)) else shutil.which(exe)
    return "found" if found else "missing"


def worker_python_version(timeout=FIRST_RUN_TOOL_TIMEOUT_S):
    try:
        python = find_worker_python()
    except Exception as exc:
        log("first-run: no worker python: %s" % exc)
        return "MISSING"
    try:
        completed = subprocess.run(
            [python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
            creationflags=_NO_WINDOW)
        text = (completed.stdout or b"").decode("utf-8", "replace").strip()
        if completed.returncode == 0 and re.match(r"^\d+\.\d+$", text):
            return text
        log("first-run: %s answered %r (exit %s)" % (python, text[-200:], completed.returncode))
        return "unusable"
    except subprocess.TimeoutExpired:
        return "slow to answer"
    except Exception as exc:
        log("first-run: %s could not be probed: %s: %s" % (python, exc.__class__.__name__, exc))
        return "unusable"


def first_run_status_line(client, entries, problems, ping_timeout=FIRST_RUN_PING_TIMEOUT_S,
                          python_version=None, server_state=None):
    base = getattr(client, "base", None) or COMFY_URL
    try:
        target = comfy_short_target(base)
        if comfy_is_production(base):
            target += " PRODUCTION"
    except Exception:
        target = "?"
    try:
        if server_state is not None:
            ok, version = bool(server_state[0]), (server_state[1] if len(server_state) > 1 else "") or ""
        else:
            stats = client.ping(timeout=ping_timeout)
            ok, version = True, ((((stats or {}).get("system") or {}).get("comfyui_version")) or "")
        if ok:
            comfy = "ComfyUI %s reachable%s" % (target, (" (v%s)" % version) if version else "")
        else:
            comfy = "ComfyUI %s NOT reachable" % target
    except Exception as exc:
        log("first-run: ComfyUI %s not reachable: %s: %s" % (target, exc.__class__.__name__, exc))
        comfy = "ComfyUI %s NOT reachable" % target
    try:
        ffmpeg = "ffmpeg %s" % ffmpeg_status_word()
    except Exception:
        ffmpeg = "ffmpeg unknown"
    try:
        python = "worker python %s" % (python_version or worker_python_version())
    except Exception:
        python = "worker python unknown"
    try:
        presets = "presets %d (%d problems)" % (len(entries or []), len(problems or []))
    except Exception:
        presets = "presets ?"
    return u" \u00b7 ".join((comfy, ffmpeg, python, presets))


def first_run_line_is_worrying(line):
    lowered = (line or "").lower()
    return any(word in lowered for word in ("not reachable", "missing", "unusable", "slow to answer"))



DELIVERY_FOLDER_NAME = "Second Unit"


def delivery_dir_for(source_path=None, cache_dir=None, output_copy_dir=None):
    configured = output_copy_dir
    if configured is None:
        configured = _cfg("output_copy_dir", "SECOND_UNIT_OUTPUT_COPY_DIR", "")
    if configured:
        return os.path.abspath(str(configured))
    if source_path:
        folder = os.path.dirname(os.path.abspath(str(source_path)))
        parent = os.path.dirname(folder) or folder
        return os.path.join(parent, DELIVERY_FOLDER_NAME)
    return os.path.join(os.path.abspath(cache_dir or LAB_CACHE), DELIVERY_FOLDER_NAME)


def _next_free_delivery_name(target):
    root, extension = os.path.splitext(target)
    index = 2
    while os.path.exists("%s (%d)%s" % (root, index, extension)):
        index += 1
    return "%s (%d)%s" % (root, index, extension)


def deliver_outputs(paths, directory):
    paths = [p for p in (paths or []) if p]
    if not paths:
        raise SecondUnitError("Nothing to deliver: the render produced no file.")
    directory = os.path.abspath(directory)
    try:
        if not os.path.isdir(directory):
            os.makedirs(directory)
    except Exception as exc:
        raise SecondUnitError(
            "Cannot create the delivery folder %s (%s: %s). Nothing was imported; the verified "
            "render is still in ComfyUI's output folder: %s"
            % (directory, exc.__class__.__name__, exc, "; ".join(paths)))
    copies = []
    for path in paths:
        if not os.path.isfile(path):
            raise SecondUnitError("Cannot deliver %s: the rendered file is not on disk." % path)
        size = os.path.getsize(path)
        if os.path.normcase(os.path.abspath(os.path.dirname(path))) == os.path.normcase(directory):
            copies.append(os.path.abspath(path))
            continue
        target = os.path.join(directory, os.path.basename(path))
        if os.path.isfile(target) and os.path.getsize(target) == size:
            log("delivery: reusing the existing copy %s (%d bytes)" % (target, size))
            copies.append(target)
            continue
        if os.path.exists(target):
            target = _next_free_delivery_name(target)
        partial = target + ".part"
        try:
            shutil.copyfile(path, partial)
            if os.path.getsize(partial) != size:
                raise SecondUnitError("copied %d of %d bytes" % (os.path.getsize(partial), size))
            os.replace(partial, target)
        except Exception as exc:
            try:
                if os.path.exists(partial):
                    os.remove(partial)
            except Exception:
                pass
            raise SecondUnitError(
                "Delivery copy FAILED: %s -> %s (%s: %s). Nothing was imported; the verified "
                "render is still in ComfyUI's output folder." % (path, target, exc.__class__.__name__, exc))
        log("delivery: %s -> %s (%d bytes); the original stays as the diagnostic" % (path, target, size))
        copies.append(target)
    return copies


def resolve_output_paths(items, output_dir, client):
    paths = []
    for item in items:
        local = None
        if output_dir:
            candidate = os.path.join(output_dir, item.get("subfolder", ""), item["filename"])
            if os.path.isfile(candidate):
                local = candidate
        paths.append(local or client.download(item, LAB_CACHE))
    return paths





class _DetailPassRelay(object):

    def __init__(self, outbox, parent_world_watcher_seconds=None):
        self.outbox = outbox
        self.done = None
        self.error = None
        self.parent_world_watcher_seconds = parent_world_watcher_seconds

    def put(self, message):
        message = dict(message or {})
        kind = message.get("kind")
        if kind == "done":
            self.done = message
            return
        if kind == "error":
            self.error = message.get("text") or "LTX detail pass failed."
            return
        if kind == "status":
            text = message.get("text") or ""
            message["text"] = "LTX detail pass Â· " + text
            if self.parent_world_watcher_seconds:
                message["detail"] = "%s - parent World watcher %s total" % (
                    message.get("detail") or "final detail stage",
                    watcher_duration(self.parent_world_watcher_seconds))
            progress = message.get("progress")
            if isinstance(progress, (int, float)):
                message["progress"] = 55 + int(39.0 * max(0.0, min(100.0, progress)) / 100.0)
        self.outbox.put(message)


class _AnchorPassRelay(object):

    def __init__(self, outbox):
        self.outbox = outbox
        self.done = None
        self.error = None

    def put(self, message):
        message = dict(message or {})
        kind = message.get("kind")
        if kind == "done":
            self.done = message
            return
        if kind == "error":
            self.error = message.get("text") or "First-frame anchor pre-pass failed."
            return
        if kind == "status":
            message["text"] = "First-frame anchor pre-pass Â· " + (message.get("text") or "")
            progress = message.get("progress")
            if isinstance(progress, (int, float)):
                message["progress"] = 2 + int(8.0 * max(0.0, min(100.0, progress)) / 100.0)
        self.outbox.put(message)


class _WorldWindowRelay(object):

    def __init__(self, outbox, index, count, parent_watcher_seconds=None):
        self.outbox = outbox
        self.index = int(index)
        self.count = int(count)
        self.done = None
        self.parent_watcher_seconds = parent_watcher_seconds

    def put(self, message):
        message = dict(message or {})
        kind = message.get("kind")
        if kind == "done":
            self.done = message
            return
        if kind == "error":
            text = message.get("text") or "World Generation window failed."
            message["text"] = "World window %d/%d failed: %s" % (
                self.index + 1, self.count, text)
            self.outbox.put(message)
            return
        if kind == "status":
            prefix = "World window %d/%d" % (self.index + 1, self.count)
            message["text"] = prefix + " \u00b7 " + (message.get("text") or "Working...")
            progress = message.get("progress")
            if isinstance(progress, (int, float)):
                fraction = max(0.0, min(100.0, float(progress))) / 100.0
                message["progress"] = 5 + int(84.0 * (self.index + fraction) / self.count)
            message["detail"] = "%s \u00b7 %s" % (prefix, message.get("detail") or "aligned controls")
            if self.parent_watcher_seconds:
                message["detail"] += " - parent World watcher %s total" % watcher_duration(
                    self.parent_watcher_seconds)
        self.outbox.put(message)


def prepare_environment_still(graph, prompt, seed):
    patched = copy.deepcopy(graph)
    def one(role, kind):
        found = [n for n in patched.values() if (n.get("_meta") or {}).get("second_unit_role") == role and n.get("class_type") == kind]
        if len(found) != 1:
            raise SecondUnitError("Environment still needs exactly one " + role)
        return found[0]["inputs"]
    positive = one("environment_prompt", "CLIPTextEncode")
    sampler = one("environment_sampler", "KSampler")
    output = one("environment_output", "SaveImage")
    if str(prompt or "").strip():
        positive["text"] = str(prompt).strip()
    if seed is not None:
        sampler["seed"] = int(seed)
    output["filename_prefix"] = "SecondUnit/Environments/%s-%s/Environment-Master" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6])
    return patched


def prepare_environment_storyboard(graph, prompt, seed, folder=None):
    patched = copy.deepcopy(graph)
    roles = {}
    for node in patched.values():
        role = (node.get("_meta") or {}).get("second_unit_role")
        if role:
            roles.setdefault(role, []).append(node)
    for role, kind in (("environment_prompt", "CLIPTextEncode"),
                       ("environment_seed", "PrimitiveInt"),
                       ("environment_folder", "PrimitiveString")):
        if len(roles.get(role, [])) != 1 or roles[role][0]["class_type"] != kind:
            raise SecondUnitError("Environment storyboard is missing its %s control." % role)
    if len(roles.get("reference_output", [])) != 4 or len(roles.get("storyboard_output", [])) != 1:
        raise SecondUnitError("Environment storyboard must save four individual references and one sheet.")
    if str(prompt or "").strip():
        roles["environment_prompt"][0]["inputs"]["text"] = str(prompt).strip()
    roles["environment_seed"][0]["inputs"]["value"] = int(seed)
    folder = folder or ("SecondUnit/Environments/%s-%s" %
                        (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6]))
    parts = str(folder).replace("\\", "/").split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise SecondUnitError("Use a relative environment folder inside ComfyUI output.")
    roles["environment_folder"][0]["inputs"]["value"] = "/".join(parts)
    return patched


class GenerateJob(threading.Thread):

    def __init__(self, client, params, outbox, stop_event):
        threading.Thread.__init__(self)
        self.daemon = True
        self.client = client
        self.params = params
        self.outbox = outbox
        self.stop_event = stop_event

        self.world_clock = time.monotonic

    def post(self, kind, **fields):
        fields["kind"] = kind
        summary = fields.get("text") or fields.get("state") or ""
        log("worker %s: %s" % (kind, str(summary)[:400]))
        self.outbox.put(fields)

    def run(self):
        try:
            self._run()
        except SecondUnitError as exc:
            self.post("error", text=str(exc))
        except Exception:
            self.post("error", text="Unexpected panel failure:\n" + traceback.format_exc(limit=6))
        finally:
            _pl = getattr(self, "_progress_listener", None)
            if _pl is not None:
                _pl.close()

    def preflight(self, patched):
        if os.environ.get("SECOND_UNIT_SKIP_PREFLIGHT") == "1":
            return
        refs = graph_model_refs(patched)
        class_order = preflight_class_order(refs, patched)
        if not class_order:
            return
        self.post("status", text="Checking the models and node packs this preset needs...",
                  state="CHECKING", progress=12)
        deadline = time.monotonic() + PREFLIGHT_BUDGET
        class_specs = {}
        for class_type in class_order:
            if class_type in class_specs:
                continue
            if time.monotonic() > deadline:
                log("preflight: budget spent, submitting without checking the rest")
                break
            class_specs[class_type] = self.client.object_info(class_type)

        for node_id, key, authored, resolved in resolve_model_refs_by_basename(patched, refs, class_specs):
            log("preflight: node %s %s '%s' -> '%s' (matched by file name)"
                % (node_id, key, authored, resolved))
        refs = graph_model_refs(patched)
        findings = preflight_node_findings(patched, class_specs) + preflight_findings(refs, class_specs)
        if findings:
            log("preflight refused: %r" % (findings,))
            raise SecondUnitError(describe_preflight(findings))
        log("preflight ok: %d model reference(s) resolve, %d node class(es) answered for"
            % (len(refs), sum(1 for spec in class_specs.values() if spec is not None)))

    def run_detail_upscale(self, source_paths, source_info,
                           parent_world_watcher_seconds=None):
        source_paths = list(source_paths or [])
        if not source_paths:
            raise SecondUnitError("Generation supplied no video for the LTX detail pass.")
        source_path = source_paths[0]
        source_frames = probe_frame_count(source_path) or int(source_info.get("frames") or 0)
        source_fps = float(source_info.get("fps") or DEFAULT_FPS)
        source_duration = probe_duration(source_path)
        if not source_duration:
            source_duration = float(source_frames) / source_fps
        seed = self.params.get("seed")
        if seed is not None:
            seed = int(seed) + 7919
        params = {
            "entry": detail_upscale_entry(),
            "mode": "V2V",
            "prompt": DETAIL_UPSCALE_PROMPT,
            "negative": DETAIL_UPSCALE_NEGATIVE,
            "seconds": source_duration,
            "seed": seed,
            "source_path": source_path,
            "source_path_last": "",
            "source_in_seconds": None,
            "resolution": self.params["resolution"],
            "v2v_retention": "LOCK_ALL",
            "ingredient_role": "LOOK",
            "edit_amount": "SUBTLE",
            "allow_cloud": False,
            "detail_upscale": False,
            "exact_frames": source_frames,
            "exact_fps": source_fps,
            "_finish_source_size": probe_dimensions(source_path),
        }
        relay = _DetailPassRelay(
            self.outbox,
            parent_world_watcher_seconds=parent_world_watcher_seconds)
        finish_client = self.client
        if COMFY_URL_FINISH and COMFY_URL_FINISH != self.client.base:
            finish_client = ComfyClient(COMFY_URL_FINISH)
            log("detail pass routed to its own lane %s" % comfy_short_target(COMFY_URL_FINISH))
        nested = GenerateJob(finish_client, params, relay, self.stop_event)
        nested._run()
        if relay.error:
            raise SecondUnitError(relay.error)
        if not relay.done:
            raise SecondUnitError("LTX detail pass ended without a verified output.")
        return relay.done

    def run_first_frame_prepass(self, arm, canvas):
        params = self.params
        nested = dict(params)

        nested.update({"window_internal": True, "_first_frame_prepass": True, "detail_upscale": False,
                       "restore_source_audio": False, "_h3_stage_output_size": tuple(canvas)})
        relay = _AnchorPassRelay(self.outbox)
        nested_job = GenerateJob(self.client, nested, relay, self.stop_event)
        try:
            nested_job._run()
        finally:
            _pl = getattr(nested_job, "_progress_listener", None)
            if _pl is not None:
                _pl.close()
        if relay.error:
            raise SecondUnitError(relay.error)
        videos = [p for p in ((relay.done or {}).get("paths") or []) if os.path.splitext(p or "")[1].lower() in VIDEO_EXTENSIONS]
        if len(videos) != 1:
            raise SecondUnitError("First-frame anchor pre-pass produced %d videos; one was expected. Nothing full-length was queued." % len(videos))
        png = os.path.join(LAB_CACHE, "anchor", "%s_%s_seed%s_f0.png" % (
            slugify(os.path.basename(str(params.get("source_path") or "shot").rstrip("\\/"))), arm, params.get("seed")))
        extract_first_frame_png(videos[0], png)
        green = green_backdrop_fraction(png)
        log("first-frame anchor: arm=%s prepass=%s frame0=%s backdrop-green=%.4f" % (arm, videos[0], png, green))
        if green > H3_FIRST_FRAME_GREEN_MAX:
            raise SecondUnitError("First-frame anchor pre-pass still shows the backdrop (%.1f%% backdrop-green pixels, limit %.0f%%). "
                                  "Nothing full-length was queued. Change the seed, or set SECOND_UNIT_H3_FIRST_FRAME_ANCHOR=off."
                                  % (green * 100.0, H3_FIRST_FRAME_GREEN_MAX * 100.0))
        self.post("status", text="First-frame anchor ready (%s arm, %.1f%% backdrop-green)." % (arm, green * 100.0),
                  state="CHECKING", progress=10)
        return png

    def world_window_request(self):
        params = self.params
        entry = params.get("entry")
        if (params.get("window_internal") or not entry
                or entry.family not in ("MINIMAXH3", "LTX25")
                or params.get("mode") not in ("ENVSWAP", "SWAP", "ANGLE") or not params.get("source_path")):
            return None
        try:
            with open(entry.path, "r", encoding="utf-8-sig") as handle:
                graph = json.load(handle)
        except Exception as exc:
            raise SecondUnitError("World Generation preset is unreadable: %s" % exc)
        h3_chain = bool(entry.family == "MINIMAXH3" and h3_v3_kind(graph) in ("lock", "angle"))
        if not h3_chain and (params.get("mode") != "ENVSWAP" or not any(
                isinstance(node, dict)
                and node.get("class_type") == "SecondUnitRetargetWorldProxy"
                for node in graph.values())):
            return None
        fps = float(params.get("exact_fps") or graph_fps(graph))
        total_frames = params.get("exact_frames")
        if not total_frames:
            total_frames = derive_frames(fps, params.get("seconds"))
        total_frames = int(total_frames)
        if h3_chain:
            windows = plan_world_generation_windows(
                total_frames, fps, max_seconds=H3_WINDOW_MAX_FRAMES / fps,
                overlap_seconds=H3_WINDOW_OVERLAP_FRAMES / fps)
        else:
            windows = plan_world_generation_windows(total_frames, fps)
        if len(windows) <= 1:
            return None
        stage_output_size = resolve_h3_stage_output_size(params, entry.family, graph)
        request = {"fps": fps, "frames": total_frames, "windows": windows,
                   "family": entry.family, "h3_chain": h3_chain,
                   "stage_output_size": stage_output_size}
        estimate_plan = estimate_world_orchestration(params, request, graph)
        request["estimate_plan"] = estimate_plan
        request["parent_watcher_seconds"] = watcher_deadline_seconds(
            estimate_plan["total_seconds"])
        return request

    def check_world_orchestration_deadline(self, started, deadline_seconds,
                                           phase, prompt_ids):
        elapsed = self.world_clock() - started
        if elapsed > float(deadline_seconds):
            raise SecondUnitError(world_orchestration_timeout_message(
                deadline_seconds, elapsed, phase, prompt_ids,
                comfy_short_target(self.client.base)))
        return elapsed

    def run_world_generation_windows(self, request):
        params = self.params
        fps = float(request["fps"])
        total_frames = int(request["frames"])
        windows = list(request["windows"])
        estimate_plan = request.get("estimate_plan") or {}
        try:
            parent_estimate_s = float(estimate_plan["total_seconds"])
            parent_watcher_s = int(request["parent_watcher_seconds"])
        except (KeyError, TypeError, ValueError):
            raise SecondUnitError(
                "World orchestration is missing its complete estimate/deadline plan.")
        if parent_estimate_s <= 0 or parent_watcher_s <= 0:
            raise SecondUnitError(
                "World orchestration received a non-positive estimate/deadline plan.")
        started = self.world_clock()
        self.post(
            "status",
            text=("Planning %d aligned World Generation windows (max %.0fs, %.0fs overlap); "
                  "SAM 3.1, the DA3 camera/world proxy, and every reference stay locked "
                  "in every window. Complete estimate %s; parent watcher deadline %s "
                  "(not a render ETA)."
                  % (len(windows), WORLD_WINDOW_MAX_SECONDS,
                     WORLD_WINDOW_OVERLAP_SECONDS, mmss(parent_estimate_s),
                     watcher_duration(parent_watcher_s))),
            state="CHECKING",
            detail="one-click scheduler - parent watcher covers windows + finish",
            progress=3)
        log("World parent watcher windows=%d frames=%d estimate=%.1fs deadline=%ds (%s) "
            "breakdown=%s; deadline never cancels or retries ComfyUI"
            % (len(windows), total_frames, parent_estimate_s, parent_watcher_s,
               watcher_duration(parent_watcher_s),
               json.dumps(estimate_plan, sort_keys=True)))
        window_paths = []
        prompt_ids = []
        warnings = []
        completed_stage_estimates = 0.0
        for index, window in enumerate(windows):
            self.check_world_orchestration_deadline(
                started, parent_watcher_s,
                "before World window %d/%d" % (index + 1, len(windows)),
                prompt_ids)
            if self.stop_event.is_set():
                self.post(
                    "error",
                    text=("Stopped before World Generation window %d/%d. Already-rendered "
                          "diagnostic windows were kept; nothing was imported."
                          % (index + 1, len(windows))))
                return
            nested_params = world_window_child_params(
                params, request, window, index)
            if request.get("h3_chain") and window_paths:

                chain_png = os.path.join(
                    LAB_CACHE, "chain", "%s_w%02d.png" % (slugify(os.path.basename(str(params.get("source_path") or "shot"))), index))
                nested_params["_h3_chain_env_path"] = extract_last_frame_png(window_paths[-1], chain_png)
                log("window %d/%d chained on %s" % (index + 1, len(windows), os.path.basename(chain_png)))
            relay = _WorldWindowRelay(
                self.outbox, index, len(windows),
                parent_watcher_seconds=parent_watcher_s)
            nested = GenerateJob(self.client, nested_params, relay, self.stop_event)
            nested._run()
            if not relay.done:
                raise SecondUnitError(
                    "World Generation window %d/%d ended without a verified output."
                    % (index + 1, len(windows)))
            videos = [path for path in (relay.done.get("paths") or [])
                      if os.path.splitext(path or "")[1].lower() in VIDEO_EXTENSIONS]
            if len(videos) != 1:
                raise SecondUnitError(
                    "World Generation window %d/%d produced %d video files; one was expected. "
                    "Nothing was assembled."
                    % (index + 1, len(windows), len(videos)))
            window_paths.append(videos[0])
            prompt_ids.append(relay.done.get("prompt_id") or "window-%d" % (index + 1))
            warnings.extend(relay.done.get("warnings") or [])
            completed_stage_estimates += float(
                relay.done.get("estimated_seconds") or 0.0)
            self.check_world_orchestration_deadline(
                started, parent_watcher_s,
                "after World window %d/%d" % (index + 1, len(windows)),
                prompt_ids)

        self.check_world_orchestration_deadline(
            started, parent_watcher_s, "before World overlap assembly", prompt_ids)
        self.post("status", text="Blending aligned World Generation overlaps into exact ProRes HQ...",
                  state="VERIFYING HQ",
                  detail="%d windows \u00b7 %d frames - parent watcher %s total"
                  % (len(windows), total_frames,
                     watcher_duration(parent_watcher_s)), progress=91)
        assembled = assemble_world_generation_windows(
            window_paths, windows, total_frames, fps,
            expected_dimensions=request.get("stage_output_size"))
        paths = [assembled]
        paths = prepare_delivery_outputs(paths, frames=total_frames)
        paths, assembly_warnings = gate_outputs(
            paths, frames=total_frames, reject_reference_grid=True)
        warnings.extend(assembly_warnings)
        self.check_world_orchestration_deadline(
            started, parent_watcher_s, "after World overlap assembly", prompt_ids)

        if params.get("detail_upscale"):
            self.check_world_orchestration_deadline(
                started, parent_watcher_s, "before final LTX detail", prompt_ids)
            self.post(
                "status",
                text="World assembly is valid. Starting the optional LTX detail finish...",
                state="CHECKING",
                detail="final detail stage - parent watcher %s total"
                       % watcher_duration(parent_watcher_s), progress=92)
            source_info = {"frames": total_frames, "fps": fps}
            detail = self.run_detail_upscale(
                paths, source_info,
                parent_world_watcher_seconds=parent_watcher_s)
            detail_paths = list(detail.get("paths") or [])
            warnings.extend(detail.get("warnings") or [])
            paths = select_detail_final_paths(paths, detail_paths)
            prompt_ids.append(detail.get("prompt_id") or "detail")
            completed_stage_estimates += float(
                detail.get("estimated_seconds") or 0.0)
            self.check_world_orchestration_deadline(
                started, parent_watcher_s, "after final LTX detail", prompt_ids)

        self.check_world_orchestration_deadline(
            started, parent_watcher_s, "before Video 1 audio restoration", prompt_ids)
        self.post("status", text="Restoring and verifying exact Video 1 audio once...",
                  state="VIDEO 1 AUDIO",
                  detail="assembled delivery - parent watcher %s total"
                         % watcher_duration(parent_watcher_s), progress=98)
        window_audio_path, window_audio_in = source_audio_for(params)
        paths = restore_video1_audio(
            paths, window_audio_path, total_frames, fps,
            source_in_seconds=window_audio_in)
        paths = prepare_delivery_outputs(paths, frames=total_frames)
        paths, final_warnings = gate_outputs(
            paths, frames=total_frames, reject_reference_grid=True)
        warnings.extend(final_warnings)
        rendered_seconds = self.check_world_orchestration_deadline(
            started, parent_watcher_s, "after final delivery verification", prompt_ids)
        log("World parent complete actual=%.1fs estimated=%.1fs child_estimates=%.1fs"
            % (rendered_seconds, parent_estimate_s, completed_stage_estimates))
        self.post(
            "done", paths=paths, prompt_id="+".join(prompt_ids), frames=total_frames,
            fps=fps, warnings=warnings, render_seconds=rendered_seconds,
            estimated_seconds=parent_estimate_s)

    def run_environment_still(self):
        params = self.params
        with open(params["entry"].path, "r", encoding="utf-8-sig") as handle:
            graph = prepare_environment_still(json.load(handle), params.get("prompt"), params.get("seed"))
        stats = self.client.ping()
        output_dir = parse_dir_arg(stats, "--output-directory")
        self.preflight(graph)
        if self.stop_event.is_set():
            raise SecondUnitError("Cancelled before submit. Nothing was queued.")
        prompt_id = self.client.submit(graph, uuid.uuid4().hex)
        started = time.monotonic()
        while not self.stop_event.is_set():
            if time.monotonic() - started > watcher_deadline_seconds(120):
                raise SecondUnitError("Still watcher deadline reached; prompt may still be running: " + prompt_id)
            try:
                history = self.client.history(prompt_id)
            except (ComfyUnreachable, ComfyTimeout):
                history = None
            if history:
                failure = history_error(history)
                if failure:
                    raise SecondUnitError("Environment render failed: " + str(failure))
                items = history_outputs(history)
                if len(items) != 1 or not items[0]["filename"].lower().endswith(".png"):
                    raise SecondUnitError("Expected one environment PNG.")
                paths = resolve_output_paths(items, output_dir, self.client)
                self.post("done", paths=paths, prompt_id=prompt_id, frames=1, fps=0,
                          storyboard=True, environment_still=True, warnings=[],
                          render_seconds=time.monotonic()-started)
                return
            self.post("status", state="RENDERING", prompt_id=prompt_id,
                      elapsed=time.monotonic()-started, text="Generating environment still at the preset resolution...")
            self.stop_event.wait(POLL_INTERVAL)
        raise SecondUnitError("Stopped watching; render may still be running: " + prompt_id)

    def run_environment_storyboard(self):
        params = self.params
        with open(params["entry"].path, "r", encoding="utf-8-sig") as handle:
            graph = prepare_environment_storyboard(
                json.load(handle), params.get("prompt"), params["seed"],
                params.get("environment_folder"))
        stats = self.client.ping()
        output_dir = parse_dir_arg(stats, "--output-directory")
        self.preflight(graph)
        if self.stop_event.is_set():
            raise SecondUnitError("Cancelled before submit. Nothing was queued.")
        prompt_id = self.client.submit(graph, uuid.uuid4().hex)
        started = time.monotonic()
        deadline = watcher_deadline_seconds(720)
        self.post("status", state="RENDERING", prompt_id=prompt_id, progress=10,
                  text="Generating environment references and the complete storyboard sheet...")
        while not self.stop_event.is_set():
            if time.monotonic() - started > deadline:
                raise SecondUnitError("Environment storyboard watcher deadline reached; the prompt may still be running: %s" % prompt_id)
            try:
                history = self.client.history(prompt_id)
            except (ComfyUnreachable, ComfyTimeout):
                self.post("status", state="RENDERING", elapsed=time.monotonic()-started,
                          text="Waiting for ComfyUI; the storyboard has not been resubmitted.")
                self.stop_event.wait(POLL_INTERVAL)
                continue
            if history:
                failure = history_error(history)
                if failure:
                    raise SecondUnitError("Render FAILED on %s - %s" % (self.client.base, failure))
                self.post("status", state="FETCHING", progress=95, text="Fetching all four references and the sheet...")
                items = history_outputs(history)
                if len(items) != 5 or any(not item["filename"].lower().endswith(".png") for item in items):
                    raise SecondUnitError("Expected four reference PNGs and one storyboard PNG; received %d files." % len(items))
                paths = resolve_output_paths(items, output_dir, self.client)
                self.post("done", paths=paths, prompt_id=prompt_id, frames=4, fps=0,
                          storyboard=True, warnings=[], render_seconds=time.monotonic()-started)
                return
            self.post("status", state="RENDERING", elapsed=time.monotonic()-started,
                      text="Generating environment references; outputs stay at 1216 x 832.")
            self.stop_event.wait(POLL_INTERVAL)
        raise SecondUnitError("Stopped watching prompt %s; it may still be running." % prompt_id)

    def _run(self):
        if self.params.get("entry") and self.params["entry"].stamp.get("pipeline") == "h3_pose_follow":
            self.params.update(detail_upscale=False, auto_cards=False, source_format="VIDEO")
        if self.params.get("detail_upscale") and not self.params.get("window_internal")                 and not self.params.get("_first_frame_prepass"):
            detail_upscale_entry()
        if self.params.get("mode") == "STILLS":
            return self.run_environment_still()
        if self.params.get("mode") == "STORYBOARD":
            return self.run_environment_storyboard()
        window_request = self.world_window_request()
        if window_request:
            self.run_world_generation_windows(window_request)
            return
        params = self.params
        if not params.get("_first_frame_prepass") and not params.get("window_internal") and not params.get("_h3_first_frame_path"):
            with open(params["entry"].path, "r", encoding="utf-8-sig") as _anchor_handle:
                _anchor_graph = json.load(_anchor_handle)
            _arm = h3_first_frame_anchor_arm(params["entry"], _anchor_graph)
            if _arm != "off":
                _canvas = h3_generation_dimensions(_anchor_graph)
                if not _canvas:
                    raise SecondUnitError("First-frame anchor needs the preset's H3 generator canvas. Nothing was queued.")
                self.params = params = dict(params)
                params["_h3_first_frame_arm"] = _arm
                params["_h3_first_frame_path"] = self.run_first_frame_prepass(_arm, _canvas)
        self.post("status", text="Checking ComfyUI on %s..." % comfy_short_target(self.client.base),
                  state="CHECKING", progress=2)
        stats = self.client.ping()
        version = ((stats.get("system") or {}).get("comfyui_version")) or "?"
        output_dir = parse_dir_arg(stats, "--output-directory")
        input_dir = parse_dir_arg(stats, "--input-directory")
        input_dir, upload_inputs = staging_directory(input_dir)
        if upload_inputs:
            log("staging: no writable ComfyUI input directory from here - staging in %s and "
                "uploading through POST /upload/image" % input_dir)


        headroom = vram_warning(stats)
        if headroom:
            log("vram: %s" % headroom)
            self.post("status", text=headroom, state="CHECKING", progress=4)
        free_before = free_vram_gb(stats)
        may_release_cache = (not params.get("window_internal")
                             or int(params.get("world_window_index") or 0) == 0)
        if may_release_cache and free_before is not None and free_before < VRAM_AUTO_FREE_GB:
            self.post(
                "status",
                text=("Releasing ComfyUI's warm model cache (%.1f GB free) before loading "
                      "this job..." % free_before),
                state="CHECKING", progress=5,
            )
            self.client.free_cache()
            stats = self.client.ping()
            free_after = free_vram_gb(stats)
            log("cache release: %.1f GB -> %s GB free"
                % (free_before, "?" if free_after is None else "%.1f" % free_after))


        entry = params["entry"]
        stamp = read_stamp(entry.path)
        if stamp is None:
            raise SecondUnitError("REFUSED: %s has no .verified.json stamp any more." % entry.name)
        if not stamp.get("local", False) and not params["allow_cloud"]:
            raise SecondUnitError("REFUSED: %s is stamped local:false and 'Allow cloud graphs' is off." % entry.name)

        self.post("status", text="Loading %s (ComfyUI %s)" % (entry.name, version), progress=6)
        with open(entry.path, "r", encoding="utf-8-sig") as handle:
            graph = json.load(handle)

        for change in adapt_hardware_precision(graph, stats):
            log("hardware compatibility: " + change)
            self.post("status", text=change, state="CHECKING", progress=6)


        dims = graph_dimensions(graph)
        source_name = None
        source_frames = None
        if params["source_path"]:

            wants_frames = (str(params.get("source_format") or "VIDEO") == "PNGSEQ"
                            and params["mode"] in FRAME_SEQUENCE_MODES)
            if wants_frames:
                try:
                    if upload_inputs:
                        raise SecondUnitError("no writable ComfyUI input directory from here")
                    loader_id, _loader = source_loader_node(graph, params["mode"])
                    if not loader_id:
                        raise SecondUnitError("this preset has no clip loader to swap")
                    manifest = (read_sequence_manifest(params["source_path"])
                                if os.path.isdir(params["source_path"]) else None)
                    if (manifest and manifest.get("verified") and manifest.get("wav")
                            and os.path.isfile(str(manifest.get("wav")))
                            and int(manifest.get("frames") or 0) > 0):

                        source_frames = {"directory": params["source_path"],
                                         "audio": str(manifest["wav"]),
                                         "count": int(manifest["frames"])}
                        self.post("status", text="Using the verified PNG sequence in place (%d frames)."
                                  % source_frames["count"], state="CHECKING", progress=6)
                        log("source: verified Second Unit sequence used in place: %s (%d frames)"
                            % (params["source_path"], source_frames["count"]))
                    else:
                        self.post("status", text="Extracting lossless PNG frames of the source moment...",
                                  state="CHECKING", progress=6)
                        _stage_dims = source_loader_dims(graph, params["mode"]) or dims
                        _stage_t0 = time.monotonic()
                        source_frames = stage_source_frames(
                            params["source_path"], input_dir,
                            seconds=params.get("seconds"),
                            dims=_stage_dims,
                            in_seconds=params.get("source_in_seconds"),
                            fps=source_loader_rate(graph, params["mode"]) or graph_fps(graph),
                            progress=lambda n, m: self.post("status", text=("Staging source: %d/%d frames at %dx%d (%s)" % (n, m, _stage_dims[0], _stage_dims[1], mmss(time.monotonic() - _stage_t0))) if _stage_dims else ("Staging source: %d/%d frames (%s)" % (n, m, mmss(time.monotonic() - _stage_t0))), state="STAGING", progress=6),
                            )
                        log("source: PNG sequence %s (%d frames)"
                            % (os.path.basename(source_frames["directory"]), source_frames["count"]))
                    if source_frames:

                        source_name = source_frames["directory"]
                except SecondUnitError as exc:
                    if sequence_source_dir(params["source_path"]):
                        raise SecondUnitError("A frame folder can only be fed as a PNG sequence, and "
                                              "that failed: %s" % exc)
                    log("source: PNG sequence not possible (%s) - using the video proxy" % exc)
                    self.post("status", text="PNG sequence unavailable (%s); using the video proxy." % exc,
                              state="CHECKING", progress=6)
                    source_frames = None
            elif params.get("mode") not in STILL_SOURCE_MODES and sequence_source_dir(params["source_path"]):
                raise SecondUnitError(
                    "%s is a folder of frames. Set the source format to PNG sequence (V2V) to use it."
                    % params["source_path"])
            if is_pose_follow_graph(graph):
                source_name, pose_count = stage_pose_follow_source(
                    params["source_path"], input_dir, params["seconds"], params.get("source_in_seconds"))
                params["seconds"] = pose_count /24.0
            elif not source_frames:
                source_name = stage_source_file(
                    params["source_path"], input_dir,
                    seconds=params.get("seconds"), dims=dims,
                    in_seconds=params.get("source_in_seconds"))
                source_name = staged_source_value(
                    graph, params["mode"], source_name, input_dir)
        if (source_frames and (params["mode"] in ("ENVSWAP", "SWAP", "ANGLE") or (params["mode"] == "V2V" and entry.family == "MINIMAXH3")) and os.environ.get("SECOND_UNIT_ALLOW_SOURCE_CUTS") != "1"):
            _cut = sequence_first_cut(source_frames["directory"])
            if _cut is not None:
                raise SecondUnitError(
                    "The source frames change picture at frame %d of %s. H3 reads <Video 1> as one continuous take, so the "
                    "render would copy that change. Render a TIMELINE SEQ that stays inside one clip. Nothing was queued."
                    % (_cut, os.path.basename(source_frames["directory"].rstrip("\\/"))))

        audio_source_path = params["source_path"]
        audio_in_seconds = params.get("source_in_seconds")
        if source_frames and source_frames.get("audio") and not os.path.isfile(str(params["source_path"] or "")):
            audio_source_path = source_frames["audio"]
            audio_in_seconds = None
        source_name_last = None
        if params.get("source_path_last"):

            source_name_last = stage_source_file(params["source_path_last"], input_dir)
        identity_name = None
        if params.get("identity_path"):
            identity_name = stage_source_file(params["identity_path"], input_dir)
        wardrobe_name = None
        if params.get("wardrobe_path"):
            wardrobe_name = stage_source_file(params["wardrobe_path"], input_dir)
        prop1_name = None
        if params.get("prop1_path"):
            prop1_name = stage_source_file(params["prop1_path"], input_dir)
        prop2_name = None
        if params.get("prop2_path"):
            prop2_name = stage_source_file(params["prop2_path"], input_dir)
        card_names = []
        _cards_refusal = auto_cards_gate(params)
        if _cards_refusal:
            raise SecondUnitError(_cards_refusal)
        if (params.get("auto_cards") and source_name and entry.family == "MINIMAXH3"
                and params["mode"] in ("SWAP", "ENVSWAP", "ANGLE") and h3_v3_kind(graph)):
            self.post("status", text="AUTO CARDS: harvesting identity cards from the footage "
                      "(H3 Character Pack Builder)...", state="CHECKING",
                      detail="dense frame harvest -> pack builder -> face recheck", progress=4)
            card_names = build_identity_cards(
                os.path.join(input_dir, source_name), input_dir,
                os.path.join(LAB_CACHE, "cards"),
                extra_stills=[params.get(k) for k in ("identity_path", "prop1_path", "prop2_path") if params.get(k)],
                log_fn=log)
            self.post("status", text="AUTO CARDS: %d card(s) from the footage - %s" % (
                len(card_names), "; ".join(_CARD_ROLES.get(n, "view") for n in card_names) or "none"),
                state="CHECKING", detail="one <Subject 1> block, a role per card", progress=5)
        continuity_name = None
        if params.get("_h3_chain_env_path"):
            continuity_name = stage_source_file(params["_h3_chain_env_path"], input_dir)
        first_frame_name = None
        first_frame_arm = str(params.get("_h3_first_frame_arm") or "off")
        if params.get("_h3_first_frame_path"):
            first_frame_name = stage_source_file(params["_h3_first_frame_path"], input_dir)
        if upload_inputs:
            if source_name and os.path.isabs(source_name):
                raise SecondUnitError(
                    "This preset loads its source through VHS_LoadVideoPath, which needs a path on "
                    "ComfyUI's own disk, and ComfyUI's input directory is not writable from this "
                    "machine. Start ComfyUI with --input-directory on a folder this panel can write, "
                    "or pick a preset that loads by name. Nothing was queued.")
            staged = [source_name, source_name_last, identity_name, wardrobe_name,
                      prop1_name, prop2_name, continuity_name, first_frame_name] + list(card_names or [])
            staged = [name for name in staged if name]
            if staged:
                self.post("status", text="Uploading %d staged file(s) to ComfyUI input" % len(staged), state="UPLOADING", progress=7)
                upload_staged_inputs(self.client, input_dir, staged)

        detail_enabled = bool(params.get("detail_upscale"))
        intermediate_size = resolve_h3_stage_output_size(
            params, entry.family, graph)
        native_h3_detail = bool(intermediate_size and detail_enabled)
        native_world_window = bool(
            intermediate_size and params.get("window_internal")
            and params.get("_h3_stage_output_size"))
        patched, info = patch_graph(
            graph,
            params["mode"],
            params["prompt"],
            params["seconds"],
            negative=params["negative"],
            seed=params["seed"],
            source_name=source_name,
            source_name_last=source_name_last,
            identity_name=identity_name,
            wardrobe_name=wardrobe_name,
            prop1_name=prop1_name,
            prop2_name=prop2_name,
            resolution=params["resolution"],
            v2v_retention=params.get("v2v_retention", "LOCK_ALL"),
            ingredient_role=params.get("ingredient_role", "SUBJECT"),
            edit_amount=params.get("edit_amount", "BALANCED"),
            subject_query=params.get("subject_query", "person"),
            environment_relight=params.get("environment_relight", False),
            intermediate_size=intermediate_size,
            card_names=card_names,
            continuity_name=continuity_name,
            first_frame_name=first_frame_name,
            first_frame_arm=first_frame_arm,
            finish_source_size=params.get("_finish_source_size"),
            source_frames=source_frames,
        )
        if (params.get("exact_frames") or params.get("exact_fps")) and not is_pose_follow_graph(patched):
            exact_frames = params.get("exact_frames") or info["frames"]
            exact_fps = params.get("exact_fps") or info["fps"]
            info["forced_timing"] = force_graph_timing(patched, exact_fps, exact_frames)
            info["frames"] = int(exact_frames)
            info["fps"] = float(exact_fps)
            info["seconds"] = float(exact_frames) / float(exact_fps)
        if params.get("_first_frame_prepass"):

            _pref_id, _pref = h3_reference_node(patched)
            if _pref is None:
                raise SecondUnitError("First-frame anchor pre-pass needs a MiniMaxH3ReferenceToVideo node.")
            _pref["inputs"]["length"] = H3_FIRST_FRAME_PREPASS_FRAMES
            for _tid, _tkey in info.get("delivery_trim_targets") or []:
                patched[_tid]["inputs"][_tkey] = H3_FIRST_FRAME_PREPASS_FRAMES
            _npics = len([k for k in _pref["inputs"] if k.startswith("ref_images.ref_image_") and is_link(_pref["inputs"][k])])
            _pos = patched[info["positive_node"]]["inputs"]
            _pos[info["positive_key"]] = h3_prompt_for_prepass(_pos[info["positive_key"]], _npics)
            info["frames"] = info["generated_frames"] = H3_FIRST_FRAME_PREPASS_FRAMES
            info["seconds"] = float(H3_FIRST_FRAME_PREPASS_FRAMES) / float(info["fps"])
        estimate_s = estimate_render_seconds(
            entry.family, params["mode"], params["resolution"],
            info.get("generated_frames") or info["frames"], patched)
        detail_estimate_s = (estimate_detail_upscale_seconds(
            info["frames"], params["resolution"])
            if detail_enabled else 0.0)
        overall_estimate_s = estimate_s + detail_estimate_s
        watcher_s = watcher_deadline_seconds(overall_estimate_s)
        if native_h3_detail:
            delivery_text = (
                "H3 %dx%d native intermediate -> LTX detail -> 1080p ProRes HQ final"
                % (intermediate_size[0], intermediate_size[1]))
        elif native_world_window:
            delivery_text = (
                "H3 %dx%d native World window intermediate; one 1080p LTX final follows"
                % (intermediate_size[0], intermediate_size[1]))
        elif is_pose_follow_graph(patched):
            delivery_text = "Native1536x864 ProRes HQ; no LTX or RTX upscale"
        else:
            delivery_text = "%s ProRes HQ" % dict(RESOLUTION_LABELS)[params["resolution"]]
        self.post(
            "status",
            text=("%.4g fps x %.4g s -> %d frames; %s; %sestimate %s; "
                  "watcher deadline %s (not a render ETA)") % (
                info["fps"], info["seconds"], info["frames"], delivery_text,
                "generation + LTX detail " if detail_enabled else "first ",
                mmss(overall_estimate_s), watcher_duration(watcher_s)),
            progress=10,
        )
        log("watcher deadline family=%s mode=%s frames=%d estimate=%.1fs deadline=%ds (%s); "
            "deadline never cancels or retries ComfyUI"
            % (entry.family, params["mode"], info["frames"], overall_estimate_s,
               watcher_s, watcher_duration(watcher_s)))
        if self.stop_event.is_set():
            self.post("error", text="Cancelled before submit. Nothing was queued.")
            return

        if not params.get("skip_preflight"):
            self.preflight(patched)

        if self.stop_event.is_set():
            self.post("error", text="Cancelled before submit. Nothing was queued.")
            return

        client_id = uuid.uuid4().hex
        listener = ComfyProgressListener(self.client.base, client_id)
        self._progress_listener = listener
        listener.start()
        prompt_id = self.client.submit(patched, client_id)
        listener.prompt_id = prompt_id
        self.post(
            "status",
            text="Queued on %s (prompt %s); watcher deadline %s"
                 % (comfy_short_target(self.client.base), prompt_id[:8],
                    watcher_duration(watcher_s)),
            state="QUEUED",
            detail="prompt %s \u00b7 watcher only, no auto-cancel" % prompt_id[:8],
            progress=15, prompt_id=prompt_id)

        started = time.monotonic()
        poll_failures = 0
        poll_failure_started = None
        absent_since = None
        while not self.stop_event.is_set():
            if time.monotonic() - started > watcher_s:
                raise SecondUnitError(watcher_timeout_message(
                    prompt_id, comfy_short_target(self.client.base), watcher_s))


            try:
                entry_history = self.client.history(prompt_id)
                poll_failures = 0
                poll_failure_started = None
            except (ComfyUnreachable, ComfyTimeout) as exc:
                poll_failures += 1
                poll_failure_started = poll_failure_started or time.monotonic()
                unreachable_s = time.monotonic() - poll_failure_started
                log("poll failure %d (%.1fs/%.1fs grace): %s"
                    % (poll_failures, unreachable_s, POLL_UNREACHABLE_GRACE_S, exc))
                if unreachable_s > POLL_UNREACHABLE_GRACE_S:
                    raise SecondUnitError(
                        "Lost contact with ComfyUI at %s while prompt %s was rendering (%d "
                        "failed checks across %s). The render may still be running - check "
                        "ComfyUI before resubmitting, or you will queue it twice."
                        % (self.client.base, prompt_id[:8], poll_failures, mmss(unreachable_s)))
                self.post("status",
                          text="ComfyUI is busy - retrying (%s of %s grace). The render has "
                               "NOT been cancelled."
                               % (mmss(unreachable_s), mmss(POLL_UNREACHABLE_GRACE_S)),
                          state="RENDERING",
                          detail="prompt %s - watcher deadline %s"
                                 % (prompt_id[:8], watcher_duration(watcher_s)),
                          elapsed=time.monotonic() - started, progress=None)
                self.stop_event.wait(POLL_INTERVAL)
                continue

            if entry_history:
                failure = history_error(entry_history)
                if failure:
                    raise SecondUnitError(
                        "Render FAILED on %s - %s"
                        % (comfy_short_target(self.client.base), explain_render_error(failure)))
                items = history_outputs(entry_history)
                if not items:
                    raise SecondUnitError(
                        "Prompt %s finished but saved no file. Does the graph have a Save node?" % prompt_id[:8]
                    )
                self.post("status", text="Fetching %d output(s)..." % len(items),
                          state="FETCHING", progress=95)
                paths = resolve_output_paths(items, output_dir, self.client)

                self.post("status", text="Verifying ComfyUI's ProRes HQ output...",
                          state="VERIFYING HQ", progress=96)
                if entry.family == "MINIMAXH3" or params.get("exact_frames") is not None:
                    paths = trim_video_outputs_to_exact_frames(
                        paths, info["frames"], info["fps"])
                paths = prepare_delivery_outputs(paths, frames=info["frames"])


                self.post("status", text="Checking the file before importing it...",
                          state="CHECKING FILE", progress=97)
                reject_reference_grid = bool(
                    params["mode"] == "ENVSWAP"
                    and entry.family in ("LTX25", "MINIMAXH3"))
                paths, warnings = gate_outputs(
                    paths, frames=info["frames"],
                    reject_reference_grid=reject_reference_grid)
                rendered_s = time.monotonic() - started
                log("render timing family=%s mode=%s resolution=%s frames=%d actual=%.1fs estimated=%.1fs"
                    % (entry.family, params["mode"], params["resolution"], info["frames"],
                       rendered_s, estimate_s))
                if detail_enabled:
                    self.post(
                        "status",
                        text="Stage 1 is valid ProRes HQ. Starting LTX 2.5 detail pass (pixel-spatial x2)...",
                        state="CHECKING", detail="stage 2 of 2", progress=54)
                    detail = self.run_detail_upscale(paths, info)
                    detail_paths = list(detail.get("paths") or [])
                    detail_warnings = list(detail.get("warnings") or [])
                    paths = select_detail_final_paths(paths, detail_paths)
                    warnings = list(warnings) + detail_warnings
                    prompt_id = "%s+%s" % (prompt_id, detail.get("prompt_id") or "detail")
                    rendered_s = time.monotonic() - started
                    log("two-stage render timing actual=%.1fs estimated=%.1fs outputs=%d"
                        % (rendered_s, overall_estimate_s, len(paths)))
                restore_source_audio = params.get("restore_source_audio", True)
                if (entry.family in ("MINIMAXH3", "LTX25")
                        and (params["mode"] == "ENVSWAP"
                             or (entry.family == "MINIMAXH3"
                                 and params["mode"] == "V2V"))
                        and params.get("source_path") and restore_source_audio):
                    self.post(
                        "status",
                        text="Restoring and verifying exact Video 1 audio...",
                        state="VIDEO 1 AUDIO", progress=99)
                    paths = restore_video1_audio(
                        paths, audio_source_path, info["frames"], info["fps"],
                        source_in_seconds=audio_in_seconds)

                    paths = prepare_delivery_outputs(paths, frames=info["frames"])
                    paths, delivery_warnings = gate_outputs(
                        paths, frames=info["frames"],
                        reject_reference_grid=reject_reference_grid)
                    warnings = list(warnings) + list(delivery_warnings)

                self.post("done", paths=paths, prompt_id=prompt_id, frames=info["frames"],
                          fps=info["fps"], warnings=warnings, render_seconds=rendered_s,
                          estimated_seconds=overall_estimate_s,
                          source_path=str(params.get("source_path") or ""))
                return
            try:
                state, position = self.client.queue_position(prompt_id)
                poll_failures = 0
                poll_failure_started = None
            except (ComfyUnreachable, ComfyTimeout):
                poll_failures += 1
                self.stop_event.wait(POLL_INTERVAL)
                continue
            elapsed = time.monotonic() - started


            if state == "absent":
                absent_since = absent_since or time.monotonic()
                if time.monotonic() - absent_since > PROMPT_VANISHED_S:
                    raise SecondUnitError(
                        "Prompt %s is in neither the queue nor the history on %s. ComfyUI most "
                        "likely restarted, which discards both. Nothing was rendered - submit "
                        "again." % (prompt_id[:8], comfy_short_target(self.client.base)))
            else:
                absent_since = None
            if state == "pending":
                self.post("status",
                          text="Waiting in the %s queue (position %d)..."
                               % (comfy_short_target(self.client.base), position),
                          state="QUEUED",
                          detail="prompt %s - position %d - watcher deadline %s"
                                 % (prompt_id[:8], position,
                                    watcher_duration(watcher_s)),
                          elapsed=elapsed, progress=18)
            elif state == "running":
                snap = listener.snapshot()
                if snap and snap.get("max"):
                    node = str(snap.get("node"))
                    klass = str((patched.get(node) or {}).get("class_type") or ("node " + node))
                    value, total = int(snap.get("value") or 0), int(snap.get("max") or 0)
                    t0, v0 = snap.get("first") or (snap["at"], 0.0)
                    eta = None
                    if value > v0 and snap["at"] > t0:
                        eta = max(0.0, (snap["at"] - t0) / (value - v0) * (total - value) - (time.monotonic() - snap["at"]))
                    if klass in ("KSampler", "KSamplerAdvanced", "SamplerCustomAdvanced", "SamplerCustom", "MiniMaxH3TurboSampler"):
                        text = "Rendering on %s: step %d/%d (%s), %s elapsed%s" % (
                            comfy_short_target(self.client.base), value, total, klass, mmss(elapsed),
                            (", ETA %s" % mmss(eta)) if eta is not None else "")
                        bar = 22 + int(70.0 * value / max(1, total))
                    else:
                        text = "Rendering on %s: %s %d/%d, %s elapsed" % (
                            comfy_short_target(self.client.base), klass, value, total, mmss(elapsed))
                        bar = 22
                    self.post("status", text=text, state="RENDERING",
                              detail="prompt %s - watcher deadline %s" % (prompt_id[:8], watcher_duration(watcher_s)),
                              elapsed=elapsed, eta=eta, progress=bar)
                else:

                    self.post("status",
                              text="Rendering on %s... %s elapsed; remaining time not measured"
                                   % (comfy_short_target(self.client.base), mmss(elapsed)),
                              state="RENDERING",
                              detail=("prompt %s - preliminary total estimate %s; "
                                      "not measured progress - watcher deadline %s"
                                      % (prompt_id[:8], mmss(estimate_s), watcher_duration(watcher_s))),
                              elapsed=elapsed, progress=22)
            else:
                self.post("status",
                          text="Submitted; waiting for %s to pick it up (%s)"
                               % (comfy_short_target(self.client.base), mmss(elapsed)),
                          state="QUEUED",
                          detail="prompt %s - watcher deadline %s"
                                 % (prompt_id[:8], watcher_duration(watcher_s)),
                          elapsed=elapsed, progress=16)
            self.stop_event.wait(POLL_INTERVAL)
        self.post(
            "error",
            text="Stopped watching prompt %s. The render on %s was NOT interrupted "
                 "(the lane is shared - only its owner may cancel it)."
                 % (prompt_id[:8], comfy_short_target(self.client.base)),
        )


HEALTH_INTERVAL = _env_float("SECOND_UNIT_HEALTH_INTERVAL", 60)
HEALTH_PING_TIMEOUT = _env_float("SECOND_UNIT_HEALTH_TIMEOUT", 8)


class HealthProbe(threading.Thread):

    def __init__(self, url, outbox, stop_event, is_busy):
        threading.Thread.__init__(self)
        self.daemon = True
        self.client = ComfyClient(url)
        self.outbox = outbox
        self.stop_event = stop_event
        self.is_busy = is_busy

    def run(self):
        last_ok = None
        while not self.stop_event.is_set():
            if not self.is_busy():
                try:
                    stats = self.client.ping(timeout=HEALTH_PING_TIMEOUT, quiet=True)
                    version = ((stats.get("system") or {}).get("comfyui_version")) or ""
                    message = {"kind": "health", "ok": True, "version": version}
                except ComfyUnreachable as exc:
                    message = {"kind": "health", "ok": False, "error": str(exc)}
                except Exception as exc:
                    message = {"kind": "health", "ok": True, "error": exc.__class__.__name__}
                self.outbox.put(message)
                if message["ok"] != last_ok:
                    log("health: ComfyUI %s at %s" % ("up" if message["ok"] else "DOWN", self.client.base))
                    last_ok = message["ok"]
            self.stop_event.wait(HEALTH_INTERVAL)





class _FileStopEvent(object):

    def __init__(self, path):
        self.path = path

    def is_set(self):
        return os.path.isfile(self.path)

    def wait(self, timeout=None):
        if self.is_set():
            return True
        if timeout is None:
            while not self.is_set():
                time.sleep(0.1)
            return True
        deadline = time.monotonic() + max(0.0, float(timeout))
        while not self.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.1, remaining))
        return True


def _uncertain_worker_error(text, submitted):
    if not submitted:
        return False
    lower = str(text or "").lower()
    return any(phrase in lower for phrase in (
        "may still be running", "stopped watching prompt", "timed out after",
        "watcher deadline",
        "lost contact with comfyui", "worker exited after submitting",
    ))


class _JsonlOutbox(object):

    def __init__(self, path, request_id, intent_path=None):
        self.path = path
        self.request_id = request_id
        self.intent_path = intent_path
        self.prompt_id = None
        self.prompt_terminal_proven = False
        self.terminal = None

    def put(self, message):
        event = dict(message or {})
        event["request_id"] = self.request_id
        if event.get("prompt_id"):
            self.prompt_id = str(event["prompt_id"])
        kind = event.get("kind")
        if (kind == "status"
                and event.get("state") in (
                    "FETCHING", "VERIFYING HQ", "CHECKING FILE", "VIDEO 1 AUDIO")):

            self.prompt_terminal_proven = True
        if kind in ("done", "error"):
            if self.prompt_id and not event.get("prompt_id"):
                event["prompt_id"] = self.prompt_id
            if kind == "error":

                intent_record = {}
                if self.intent_path and os.path.isfile(self.intent_path):
                    try:
                        with open(self.intent_path, "r", encoding="utf-8-sig") as handle:
                            intent_record = json.load(handle) or {}
                    except Exception:
                        intent_record = {"state": "unreadable"}
                intent_without_response = bool(
                    intent_record and intent_record.get("state") != "rejected"
                    and not self.prompt_id)
                error_text = str(event.get("text") or "")
                history_terminal = bool(
                    self.prompt_terminal_proven
                    or error_text.startswith("Render FAILED on ")
                    or "finished but saved no file" in error_text)
                event["uncertain"] = bool(
                    intent_without_response
                    or (self.prompt_id and not history_terminal)
                    or _uncertain_worker_error(error_text, bool(self.prompt_id)))
            self.terminal = dict(event)
        encoded = _canonical_json(event) + b"\n"
        with open(self.path, "ab") as handle:
            handle.write(encoded)
            handle.flush()


class _IntentComfyClient(ComfyClient):

    def __init__(self, base, intent_path, request_id):
        ComfyClient.__init__(self, base)
        self.intent_path = intent_path
        self.request_id = request_id

    def submit(self, graph, client_id):
        assert_h3_frame_grid(graph)
        _atomic_json(self.intent_path, {
            "request_id": self.request_id,
            "state": "posting",
            "client_id": client_id,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        try:
            prompt_id = ComfyClient.submit(self, graph, client_id)
        except ComfySubmitRejected as exc:

            _atomic_json(self.intent_path, {
                "request_id": self.request_id,
                "state": "rejected",
                "client_id": client_id,
                "error": str(exc),
                "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            raise
        _atomic_json(self.intent_path, {
            "request_id": self.request_id,
            "state": "accepted",
            "client_id": client_id,
            "prompt_id": prompt_id,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return prompt_id


def _external_request_payload(params, client_base, request_id, script_path):
    request = {
        "schema_version": EXTERNAL_WORKER_SCHEMA,
        "request_id": request_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "client_base": str(client_base).rstrip("/"),
        "script_path": os.path.abspath(script_path),
        "script_sha256": _sha256_file(script_path),
        "params": _params_payload(params),
    }
    request["request_sha256"] = hashlib.sha256(_canonical_json(request)).hexdigest()
    return request


def _require_loaded_build_on_disk(script_path, loaded_sha256):
    current = _sha256_file(script_path) if os.path.isfile(script_path) else ""
    if not loaded_sha256 or current != loaded_sha256:
        raise SecondUnitError(
            "Second Unit was updated on disk while this panel was already open. Nothing "
            "was queued. Close and reopen the Second Unit panel so Generate uses the newly "
            "deployed build.")
    return current


def _validated_external_request(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        request = json.load(handle)
    if not isinstance(request, dict):
        raise SecondUnitError("External worker request is not a JSON object.")
    if request.get("schema_version") != EXTERNAL_WORKER_SCHEMA:
        raise SecondUnitError("External worker request schema does not match this panel build.")
    expected = str(request.get("request_sha256") or "")
    unsigned = dict(request)
    unsigned.pop("request_sha256", None)
    actual = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    if not expected or actual != expected:
        raise SecondUnitError("External worker request changed after the Generate click.")
    script_path = os.path.abspath(str(request.get("script_path") or ""))
    if script_path != os.path.abspath(_self_path()):
        raise SecondUnitError("External worker was launched with a different panel file.")
    if not os.path.isfile(script_path) or _sha256_file(script_path) != request.get("script_sha256"):
        raise SecondUnitError("Panel build changed before the external worker could start.")
    return request


def _claim_external_request(path, request_id):
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        json.dump({"request_id": request_id, "pid": os.getpid(),
                   "claimed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, handle,
                  sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def _pid_is_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                                     ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetExitCodeProcess.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                error = ctypes.get_last_error()
                if error == 5:
                    return None
                return False if error in (87, 1168) else None
            try:
                code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return None
                return code.value == 259
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except Exception:
        return None


def panel_job_recovery_command(job_dir):
    home = _stamped_home_data() or {}
    repo = home.get("repo") or os.path.dirname(WORKFLOW_DIR)
    tool_path = os.path.join(repo, "tools", "reconcile_second_unit_panel_job.py")
    try:
        python_path = find_worker_python()
    except Exception:
        python_path = "python"
    return subprocess.list2cmdline(
        [python_path, tool_path, "inspect", os.path.abspath(job_dir)])


def external_worker_main(request_path):
    request_path = os.path.abspath(request_path)
    job_dir = os.path.dirname(request_path)
    events_path = os.path.join(job_dir, "events.jsonl")
    cancel_path = os.path.join(job_dir, "cancel.json")
    claim_path = os.path.join(job_dir, "claim.json")
    intent_path = os.path.join(job_dir, "submit-intent.json")
    exit_path = os.path.join(job_dir, "exit.json")

    try:
        request = _validated_external_request(request_path)
        request_id = str(request.get("request_id") or "")
        if not request_id:
            raise SecondUnitError("External worker request has no request id.")
    except Exception:
        text = "External worker refused its request:\n" + traceback.format_exc(limit=6)
        try:
            _atomic_json(exit_path, {
                "request_id": "", "pid": os.getpid(), "result": "invalid-request",
                "submit_intent": False, "uncertain": False, "error": text, "return_code": 2,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except Exception:
            pass
        return 2
    try:
        _claim_external_request(claim_path, request_id)
    except FileExistsError:

        return 4

    outbox = _JsonlOutbox(events_path, request_id, intent_path=intent_path)
    exit_record = {
        "request_id": request_id,
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "result": "error",
    }
    return_code = 1
    try:
        params = _params_from_payload(request.get("params"))
        stop_event = _FileStopEvent(cancel_path)
        job = GenerateJob(
            _IntentComfyClient(
                str(request.get("client_base") or COMFY_URL), intent_path, request_id),
            params, outbox, stop_event)

        job.run()
        if outbox.terminal is None:
            outbox.put({"kind": "error",
                        "text": "External worker ended without a terminal result."})
        exit_record["result"] = outbox.terminal.get("kind") or "error"
        exit_record["prompt_id"] = outbox.prompt_id
        exit_record["submit_intent"] = os.path.isfile(intent_path)
        exit_record["uncertain"] = bool(outbox.terminal.get("uncertain"))
        return_code = 0 if outbox.terminal.get("kind") == "done" else 1
    except Exception:
        text = "Unexpected external worker failure:\n" + traceback.format_exc(limit=8)
        try:
            outbox.put({"kind": "error", "text": text})
        except Exception:
            pass
        exit_record["error"] = text
        exit_record["prompt_id"] = outbox.prompt_id
        exit_record["submit_intent"] = os.path.isfile(intent_path)
        exit_record["uncertain"] = bool(outbox.prompt_id)
        return_code = 3 if outbox.prompt_id else 1
    finally:
        exit_record["return_code"] = return_code
        exit_record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            _atomic_json(exit_path, exit_record)
        except Exception:
            pass
    return return_code


class ExternalGenerateJob(object):

    real_popen_calls = 0

    def __init__(self, python_path, script_path, client, params, outbox,
                 cache_root=LAB_CACHE, popen_factory=None,
                 loaded_script_sha256=_LOADED_SCRIPT_SHA256):
        self.python_path = os.path.abspath(python_path)
        self.script_path = os.path.abspath(script_path)
        self.client = client
        self.params = params
        self.outbox = outbox
        self.cache_root = os.path.abspath(cache_root)
        self.popen_factory = popen_factory or subprocess.Popen
        self.loaded_script_sha256 = loaded_script_sha256
        self.request_id = uuid.uuid4().hex
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.job_dir = os.path.join(
            self.cache_root, EXTERNAL_JOB_FOLDER, "%s-%s" % (stamp, self.request_id))
        self.request_path = os.path.join(self.job_dir, "request.json")
        self.events_path = os.path.join(self.job_dir, "events.jsonl")
        self.cancel_path = os.path.join(self.job_dir, "cancel.json")
        self.launcher_path = os.path.join(self.job_dir, "launcher.json")
        self.intent_path = os.path.join(self.job_dir, "submit-intent.json")
        self.exit_path = os.path.join(self.job_dir, "exit.json")
        self.consumed_path = os.path.join(self.job_dir, "consumed.json")
        self.process = None
        self.attached = False
        self._started = False
        self._event_offset = 0
        self._event_buffer = b""
        self._terminal_seen = False
        self._failure_reported = False
        self.prompt_id = None
        self.pid_probe = _pid_is_alive

    @classmethod
    def attach(cls, job_dir, outbox):
        request_path = os.path.join(os.path.abspath(job_dir), "request.json")
        with open(request_path, "r", encoding="utf-8-sig") as handle:
            request = json.load(handle)
        if (not isinstance(request, dict)
                or request.get("schema_version") != EXTERNAL_WORKER_SCHEMA
                or not request.get("request_id")):
            raise SecondUnitError("unreadable external worker request: %s" % request_path)
        obj = cls.__new__(cls)
        obj.python_path = ""
        obj.script_path = os.path.abspath(str(request.get("script_path") or _self_path()))
        obj.client = ComfyClient(str(request.get("client_base") or COMFY_URL))
        obj.params = None
        obj.outbox = outbox
        obj.cache_root = os.path.dirname(os.path.abspath(job_dir))
        obj.popen_factory = None
        obj.loaded_script_sha256 = str(request.get("script_sha256") or "")
        obj.request_id = str(request["request_id"])
        obj.job_dir = os.path.abspath(job_dir)
        obj.request_path = request_path
        obj.events_path = os.path.join(obj.job_dir, "events.jsonl")
        obj.cancel_path = os.path.join(obj.job_dir, "cancel.json")
        obj.launcher_path = os.path.join(obj.job_dir, "launcher.json")
        obj.intent_path = os.path.join(obj.job_dir, "submit-intent.json")
        obj.exit_path = os.path.join(obj.job_dir, "exit.json")
        obj.consumed_path = os.path.join(obj.job_dir, "consumed.json")
        obj.process = None
        obj.attached = True
        obj._started = True
        obj._event_offset = 0
        obj._event_buffer = b""
        obj._terminal_seen = False
        obj._failure_reported = False
        obj.prompt_id = None
        obj.pid_probe = _pid_is_alive
        log("reattached external worker request=%s dir=%s"
            % (obj.request_id[:12], obj.job_dir))
        return obj

    def start(self):
        if self._started:
            raise SecondUnitError("This render request was already started; refusing a duplicate.")
        if self.popen_factory is subprocess.Popen:
            ExternalGenerateJob.real_popen_calls += 1
            if os.environ.get("SECOND_UNIT_SELFTEST") == "1":
                raise SecondUnitError("Self-test: a real render worker launch was blocked. Nothing was queued.")
        _require_loaded_build_on_disk(self.script_path, self.loaded_script_sha256)
        self._started = True
        os.makedirs(self.job_dir)
        request = _external_request_payload(
            self.params, self.client.base, self.request_id, self.script_path)
        _atomic_json(self.request_path, request)
        environment = dict(os.environ)

        for _poison in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
            environment.pop(_poison, None)
        environment["PYTHONUTF8"] = "1"
        environment["SECOND_UNIT_COMFY_URL"] = self.client.base
        environment["SECOND_UNIT_WORKFLOWS"] = WORKFLOW_DIR
        environment["SECOND_UNIT_CACHE"] = self.cache_root
        environment["SECOND_UNIT_LOG"] = os.path.join(self.job_dir, "worker-panel.log")
        command = [self.python_path, self.script_path,
                   "--external-worker", self.request_path]
        bootstrap_path = os.path.join(self.job_dir, "worker-bootstrap.log")
        bootstrap = None
        try:
            bootstrap = open(bootstrap_path, "ab")
            self.process = self.popen_factory(
                command, cwd=os.path.dirname(self.script_path), env=environment,
                stdin=subprocess.DEVNULL, stdout=bootstrap, stderr=subprocess.STDOUT,
                shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as exc:

            try:
                _atomic_json(self.exit_path, {
                    "request_id": self.request_id, "result": "launch-error",
                    "submit_intent": False, "return_code": None,
                    "error": "%s: %s" % (exc.__class__.__name__, exc),
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                self.mark_consumed("launch-error")
            except Exception:
                pass
            self._started = False
            raise
        finally:
            if bootstrap is not None:
                bootstrap.close()
        try:
            _atomic_json(self.launcher_path, {
                "request_id": self.request_id,
                "pid": getattr(self.process, "pid", None),
                "launched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        except Exception as exc:

            log("external worker launched but launcher record failed: %s" % exc)
        log("external worker started request=%s pid=%s dir=%s"
            % (self.request_id[:12], getattr(self.process, "pid", "?"), self.job_dir))

    def is_alive(self):
        if self._terminal_seen:
            return False
        return self._process_finished() is not True

    def _pid_from_record(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                record = json.load(handle) or {}
            if record.get("request_id") == self.request_id and record.get("pid"):
                return int(record["pid"])
        except Exception:
            pass
        return None

    def _claimed_worker_pid(self):
        return self._pid_from_record(os.path.join(self.job_dir, "claim.json"))

    def _launcher_pid(self):
        return self._pid_from_record(self.launcher_path)

    def _known_worker_pid(self):
        return self._claimed_worker_pid() or self._launcher_pid()

    def _process_finished(self):
        if os.path.isfile(self.exit_path):
            return True

        claimed_pid = self._claimed_worker_pid()
        if claimed_pid is not None:
            alive = self.pid_probe(claimed_pid)
            return None if alive is None else not alive

        if not self.attached and self.process is not None and self.process.poll() is None:
            return False
        launcher_pid = self._launcher_pid()
        launcher_alive = None
        if launcher_pid is not None:
            launcher_alive = self.pid_probe(launcher_pid)
            if launcher_alive is True:
                return False

        popen_dead = (not self.attached and self.process is not None
                      and self.process.poll() is not None)
        if ((launcher_alive is False or popen_dead)
                and not os.path.isfile(self.intent_path)
                and self._launch_age_seconds() > WORKER_LAUNCH_GRACE_S):
            self.request_stop()
            self._dead_launcher = True
            return True

        return None

    def _launch_age_seconds(self):
        try:
            with open(self.launcher_path, "r", encoding="utf-8-sig") as handle:
                record = json.load(handle) or {}
            launched = time.mktime(time.strptime(str(record.get("launched_at")), "%Y-%m-%dT%H:%M:%S"))
            return max(0.0, time.time() - launched)
        except Exception:
            return 0.0

    def _bootstrap_tail(self, limit=1200):
        path = os.path.join(self.job_dir, "worker-bootstrap.log")
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - limit))
                text = handle.read().decode("utf-8", "replace").strip()
            return text or "(worker-bootstrap.log is empty: the interpreter never started)"
        except Exception:
            return "(no worker-bootstrap.log)"

    def is_consumed(self):
        return os.path.isfile(self.consumed_path)

    def mark_consumed(self, kind, uncertain=False):
        if uncertain:
            return
        try:
            _atomic_json(self.consumed_path, {
                "request_id": self.request_id,
                "kind": kind,
                "prompt_id": self.prompt_id,
                "consumed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
        except Exception as exc:
            log("could not mark external worker result consumed: %s" % exc)

    def request_stop(self):
        if not self._started or os.path.isfile(self.cancel_path):
            return
        try:
            _atomic_json(self.cancel_path, {
                "request_id": self.request_id,
                "requested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "meaning": "stop watching only; never interrupt the shared Comfy lane",
            })
        except Exception as exc:
            log("could not write external worker cancel sentinel: %s" % exc)

    def drain_to(self, outbox):
        if os.path.isfile(self.events_path):
            try:
                with open(self.events_path, "rb") as handle:
                    handle.seek(self._event_offset)
                    chunk = handle.read()
                    self._event_offset = handle.tell()
                data = self._event_buffer + chunk
                lines = data.split(b"\n")
                self._event_buffer = lines.pop() if lines else b""
                for raw in lines:
                    if not raw.strip():
                        continue
                    try:
                        event = json.loads(raw.decode("utf-8"))
                    except Exception as exc:
                        log("external worker event was unreadable: %s" % exc)
                        continue
                    if event.get("request_id") != self.request_id:
                        log("ignored event for another external request")
                        continue
                    event.pop("request_id", None)
                    if event.get("prompt_id"):
                        self.prompt_id = str(event["prompt_id"])
                    if event.get("kind") in ("done", "error"):
                        self._terminal_seen = True
                    outbox.put(event)
            except Exception as exc:
                log("could not drain external worker events: %s" % exc)


        process_finished = self._process_finished() is True
        process_returncode = (None if self.attached else
                              (self.process.returncode if self.process is not None else None))
        if (process_finished and not self._terminal_seen and not self._failure_reported):
            self._failure_reported = True
            self._terminal_seen = True
            exit_record = {}
            try:
                if os.path.isfile(self.exit_path):
                    with open(self.exit_path, "r", encoding="utf-8-sig") as handle:
                        exit_record = json.load(handle) or {}
            except Exception:
                exit_record = {}
            intent_record = {}
            try:
                if os.path.isfile(self.intent_path):
                    with open(self.intent_path, "r", encoding="utf-8-sig") as handle:
                        intent_record = json.load(handle) or {}
            except Exception:

                intent_record = {"state": "unreadable"}
            prompt_id = (self.prompt_id or exit_record.get("prompt_id")
                         or intent_record.get("prompt_id"))
            uncertain_intent = bool(
                intent_record and intent_record.get("state") != "rejected")
            uncertain = bool(
                prompt_id or exit_record.get("uncertain") or uncertain_intent)
            if uncertain:
                text = (
                    "UNCERTAIN: external worker exited after submitting prompt %s. The render "
                    "may still be running on %s. Generate remains locked across panel/Resolve "
                    "reopen so the shot cannot be submitted twice. Inspect ComfyUI and the "
                    "durable job record at %s. Read-only inspection command: %s"
                    % (str(prompt_id or "unknown")[:8], comfy_short_target(self.client.base),
                       self.job_dir, panel_job_recovery_command(self.job_dir)))
            elif getattr(self, "_dead_launcher", False) and not exit_record:
                text = (
                    "The external worker never started (its interpreter exited within %ds without "
                    "claiming the job). Nothing was queued. Last words from worker-bootstrap.log:\n%s\n"
                    "Fix the worker Python (SECOND_UNIT_PYTHON) and press Generate again. Record: %s"
                    % (WORKER_LAUNCH_GRACE_S, self._bootstrap_tail(), self.job_dir))
            elif exit_record.get("result") == "invalid-request":
                text = (
                    "The external worker refused its request before anything was queued:\n%s\nRecord: %s"
                    % (str(exit_record.get("error") or "").strip()[-900:], self.job_dir))
            else:
                text = (
                    "External worker exited before ComfyUI accepted a prompt (exit %s). "
                    "Nothing was queued. Details: %s"
                    % (exit_record.get("return_code", process_returncode), self.job_dir))
            outbox.put({"kind": "error", "text": text, "uncertain": uncertain,
                        "prompt_id": prompt_id})


class _RecoveryBlocker(object):

    def __init__(self, job_dir, reason):
        self.job_dir = job_dir
        self.reason = reason
        self._emitted = False

    def is_alive(self):
        return False

    def is_consumed(self):
        return False

    def request_stop(self):
        pass

    def mark_consumed(self, _kind, uncertain=False):
        pass

    def drain_to(self, outbox):
        if not self._emitted:
            self._emitted = True
            outbox.put({
                "kind": "error", "uncertain": True,
                "text": ("UNCERTAIN: an unfinished external worker record could not be "
                         "recovered (%s). Generate is locked to prevent a duplicate. "
                         "Durable record: %s. Read-only inspection command: %s"
                         % (self.reason, self.job_dir,
                            panel_job_recovery_command(self.job_dir))),
            })


def recover_external_job(outbox, cache_root=LAB_CACHE):
    root = os.path.join(os.path.abspath(cache_root), EXTERNAL_JOB_FOLDER)
    if not os.path.isdir(root):
        return None
    for name in sorted(os.listdir(root)):
        job_dir = os.path.join(root, name)
        if (not os.path.isdir(job_dir)
                or not os.path.isfile(os.path.join(job_dir, "request.json"))
                or os.path.isfile(os.path.join(job_dir, "consumed.json"))):
            continue
        try:
            return ExternalGenerateJob.attach(job_dir, outbox)
        except Exception as exc:
            log("could not recover external worker %s: %s" % (job_dir, exc))
            return _RecoveryBlocker(job_dir, str(exc))
    return None





def rv_current_project(resolve_obj, injected_project):
    if resolve_obj is not None:
        try:
            manager = resolve_obj.GetProjectManager()
            current = manager.GetCurrentProject() if manager else None
            if current:
                return current
        except Exception:
            pass
    return injected_project


def rv_get_or_create_bin(project, bin_name):
    media_pool = project.GetMediaPool()
    if media_pool is None:
        raise SecondUnitError("Project has no Media Pool.")
    root = media_pool.GetRootFolder()
    for folder in (root.GetSubFolderList() or []):
        if folder.GetName() == bin_name:
            return media_pool, folder
    folder = media_pool.AddSubFolder(root, bin_name)
    if not folder:
        raise SecondUnitError("Could not create the '%s' bin." % bin_name)
    return media_pool, folder


def rv_keyword_items(items, keyword):
    tagged = 0
    for item in items or []:
        try:
            existing = str(item.GetMetadata("Keywords") or "") if hasattr(item, "GetMetadata") else ""
            if keyword.lower() in existing.lower():
                tagged += 1
                continue
            value = (existing + "," + keyword) if existing else keyword
            if item.SetMetadata("Keywords", value):
                tagged += 1
        except Exception as exc:
            log("keyword not set on a clip: %s" % exc)
    if tagged:
        log("keyword %r on %d clip(s)" % (keyword, tagged))
    return tagged


def rv_find_clips_in_folder(folder, paths):
    wanted = {}
    for path in paths:
        key = os.path.normcase(os.path.abspath(path))
        wanted[key] = path
        wanted.setdefault(os.path.normcase(os.path.basename(path)), path)
    found = []
    try:
        clips = folder.GetClipList() or []
    except Exception:
        return found
    for clip in clips:
        try:
            file_path = clip.GetClipProperty("File Path") or ""
            file_name = clip.GetClipProperty("File Name") or clip.GetName() or ""
        except Exception:
            continue
        if (os.path.normcase(os.path.abspath(file_path)) in wanted if file_path else False) \
                or (file_name and os.path.normcase(file_name) in wanted):
            found.append(clip)
    return found


def rv_import_clips(resolve_obj, project, bin_name, paths):
    paths = [os.path.abspath(p) for p in paths if p]
    if not paths:
        raise SecondUnitError("Nothing to import.")
    media_pool, folder = rv_get_or_create_bin(project, bin_name)
    media_pool.SetCurrentFolder(folder)

    items = media_pool.ImportMedia(paths) or []
    if not items:

        items = rv_find_clips_in_folder(folder, paths)
    if not items:
        media_storage = resolve_obj.GetMediaStorage()
        if len(paths) <= 100:
            items = media_storage.AddItemListToMediaPool(*paths) or []
        else:
            items = []
            for offset in range(0, len(paths), 100):
                items.extend(media_storage.AddItemListToMediaPool(*paths[offset:offset + 100]) or [])
        if not items:
            items = rv_find_clips_in_folder(folder, paths)
    if not items:
        raise SecondUnitError(
            "Resolve imported nothing for %s. The file exists but the Media Pool refused it." % ", ".join(paths)
        )
    names = []
    for item in items:
        try:
            names.append(item.GetName() or item.GetClipProperty("File Name"))
        except Exception:
            names.append(os.path.basename(paths[len(names)] if len(names) < len(paths) else paths[-1]))
    return names, items




def _rv_call(obj, name, *args):
    try:
        method = getattr(obj, name, None)
        if method is None:
            return None
        return method(*args)
    except Exception as exc:
        log("rv: %s.%s failed: %s" % (type(obj).__name__, name, exc))
        return None


def rv_timeline_fps(timeline, project=None):
    for source, key in ((timeline, "timelineFrameRate"), (project, "timelineFrameRate")):
        if source is None:
            continue
        value = _rv_call(source, "GetSetting", key)
        try:
            rate = float(value)
            if rate > 0:
                return rate
        except (TypeError, ValueError):
            continue
    return None


def rv_media_file_path(media):
    if media is None:
        return None
    path = _rv_call(media, "GetClipProperty", "File Path")
    if not path:

        properties = _rv_call(media, "GetClipProperty") or {}
        if isinstance(properties, dict):
            for key in ("File Path", "File Name", "Clip Location"):
                if properties.get(key):
                    path = properties[key]
                    break
    return path or None


def rv_timecode_to_frames(timecode, fps):
    try:
        text = str(timecode).strip()
        rate = float(fps)
    except (TypeError, ValueError):
        return None
    if not text or rate <= 0:
        return None
    drop = ";" in text or "," in text
    parts = text.replace(";", ":").replace(",", ":").split(":")
    if len(parts) != 4:
        return None
    try:
        hh, mm, ss, ff = (int(p) for p in parts)
    except ValueError:
        return None
    nominal = int(round(rate))
    frames = ((hh * 60 + mm) * 60 + ss) * nominal + ff
    if drop and nominal in (30, 60):
        minutes = hh * 60 + mm
        frames -= (nominal // 15) * (minutes - minutes // 10)
    return frames


def frames_to_timecode(frame, fps):
    base = int(round(float(fps or DEFAULT_FPS))) or 24
    f = int(frame)
    return "%02d:%02d:%02d:%02d" % (f // (base * 3600), (f // (base * 60)) % 60, (f // base) % 60, f % base)


def rv_clip_under_playhead(timeline, fps):
    playhead = rv_timecode_to_frames(_rv_call(timeline, "GetCurrentTimecode"), fps)
    if playhead is None:
        return None, None, None
    try:
        count = int(_rv_call(timeline, "GetTrackCount", "video") or 0)
    except (TypeError, ValueError):
        count = 0
    for index in range(count, 0, -1):
        for candidate in (_rv_call(timeline, "GetItemListInTrack", "video", index) or []):
            try:
                start = float(_rv_call(candidate, "GetStart"))
                end = float(_rv_call(candidate, "GetEnd"))
            except (TypeError, ValueError):
                continue
            if not (start <= playhead < end):
                continue
            media = _rv_call(candidate, "GetMediaPoolItem")
            if media is None or not rv_media_file_path(media):
                continue
            return candidate, media, index
    return None, None, None


def rv_timeline_source(project, allow_virtual=False):
    if project is None:
        raise SecondUnitError("No project is open in Resolve, so there is no timeline to read.")

    timeline = _rv_call(project, "GetCurrentTimeline")
    if timeline is None:
        raise SecondUnitError("No timeline is open. Open the timeline you are cutting on, "
                              "put the playhead over a clip, and press this again.")

    timeline_name = _rv_call(timeline, "GetName") or "(unnamed)"
    fps = rv_timeline_fps(timeline, project)
    item = _rv_call(timeline, "GetCurrentVideoItem")
    name = None
    media = None
    if item is not None:
        name = _rv_call(item, "GetName") or "(unnamed clip)"
        media = _rv_call(item, "GetMediaPoolItem")
    path = rv_media_file_path(media)
    track = None
    over = None
    if not path:

        found, found_media, found_track = rv_clip_under_playhead(timeline, fps)
        if found is not None:
            over = name
            item, media, track = found, found_media, found_track
            name = _rv_call(item, "GetName") or "(unnamed clip)"
            path = rv_media_file_path(media)
            log("timeline source: %r has no media - using %r from V%s underneath it"
                % (over, name, track))

    if item is None:
        raise SecondUnitError(
            "Nothing is under the playhead on '%s'. Park the playhead over the clip you want "
            "to work from and press this again." % timeline_name)
    if media is None:
        raise SecondUnitError(
            "'%s' has no media behind it - titles, generators, adjustment layers and some "
            "compound clips are not files on disk, and no clip with real footage sits under "
            "the playhead on a lower video track. Pick a clip with real footage." % name)
    virtual = bool(path) and not os.path.isabs(str(path)) and not os.path.isfile(str(path))
    if virtual and not allow_virtual:
        raise SecondUnitError("'%s' is a compound clip (Resolve reports '%s', not a file on disk). Press TIMELINE "
                              "SEQ instead: it renders that range out of Resolve as PNG frames plus audio."
                              % (name, path))
    if virtual:
        path = None
    elif not path:
        raise SecondUnitError("Resolve did not report a file path for '%s', so there is "
                              "nothing to send to ComfyUI." % name)
    elif not os.path.isfile(path):
        raise SecondUnitError("'%s' points at %s, which is not on this machine." % (name, path))


    start_frame = None
    end_frame = None
    try:
        start_frame = int(float(_rv_call(item, "GetStart")))
        end_frame = int(float(_rv_call(item, "GetEnd")))
    except (TypeError, ValueError):
        start_frame = end_frame = None


    frames = None
    for getter in ("GetDuration", "GetEnd"):
        value = _rv_call(item, getter)
        if getter == "GetEnd" and value is not None:
            start = _rv_call(item, "GetStart")
            value = (value - start) if start is not None else None
        try:
            frames = int(value)
            if frames > 0:
                break
        except (TypeError, ValueError):
            frames = None

    if fps is None:
        try:
            fps = float(_rv_call(media, "GetClipProperty", "FPS"))
        except (TypeError, ValueError):
            fps = None

    seconds = None
    if frames and fps:
        seconds = frames / float(fps)


    left_offset = _rv_call(item, "GetLeftOffset")
    in_seconds = None
    try:
        if left_offset is not None and fps:
            in_seconds = float(left_offset) / float(fps)
    except (TypeError, ValueError, ZeroDivisionError):
        in_seconds = None

    return {
        "path": path,
        "name": name,
        "frames": frames,
        "fps": fps,
        "seconds": seconds,
        "in_seconds": in_seconds,
        "timeline": timeline_name,

        "track": track,
        "over": over,

        "start": start_frame,
        "end": end_frame,
        "virtual": virtual,
    }



SEQUENCE_MANIFEST = "second-unit-sequence.json"
SEQUENCE_MAX_WIDTH = 1920
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

SEQUENCE_RESOLVE_WAV = os.environ.get("SECOND_UNIT_SEQUENCE_RESOLVE_WAV", "0") == "1"


def sequence_root():
    if SEQUENCE_DIR:
        return SEQUENCE_DIR
    return os.path.join(LAB_CACHE, "sequences")


def png_dimensions(path):
    try:
        with open(path, "rb") as handle:
            head = handle.read(33)
    except OSError:
        return None
    if len(head) < 33 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        return None
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def sequence_render_folder(root, timeline_name, clip_name, start, end):
    stem = slugify(os.path.splitext(str(clip_name or "clip"))[0])
    return os.path.join(root, slugify(timeline_name), "%s_f%d-%d" % (stem, int(start), int(end)))


def sequence_manifest_path(folder):
    return os.path.join(folder, SEQUENCE_MANIFEST)


def read_sequence_manifest(folder):
    try:
        with open(sequence_manifest_path(folder), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def verify_sequence_folder(folder, expected):
    frames = [p for p in sequence_frame_files(folder) if p.lower().endswith(".png")]
    wav = sequence_audio_file(folder)
    expected = int(expected or 0)
    if len(frames) < expected or not frames:
        return False, "%d of %d frames on disk" % (len(frames), expected), frames, wav
    first, last = png_dimensions(frames[0]), png_dimensions(frames[-1])
    if not first or not last:
        broken = frames[0] if not first else frames[-1]
        return False, "%s is not a readable PNG" % os.path.basename(broken), frames, wav
    if not wav or os.path.getsize(wav) <= 44:
        return False, "no WAV beside the frames", frames, wav
    return (True, "%d frames %dx%d + %s" % (len(frames), first[0], first[1], os.path.basename(wav)),
            frames, wav)


def rv_sequence_dimensions(timeline):
    try:
        width = int(float(_rv_call(timeline, "GetSetting", "timelineResolutionWidth") or 0))
        height = int(float(_rv_call(timeline, "GetSetting", "timelineResolutionHeight") or 0))
    except (TypeError, ValueError):
        width = height = 0
    if width <= 0 or height <= 0:
        return 1920, 1080
    if width > SEQUENCE_MAX_WIDTH:
        scale = SEQUENCE_MAX_WIDTH / float(width)
        width, height = SEQUENCE_MAX_WIDTH, int(round(height * scale / 2.0)) * 2
    return width, height


def rv_queue_sequence_render(project, info, folder, width, height):
    if _rv_call(project, "IsRenderingInProgress"):
        raise SecondUnitError("Resolve is already rendering something. Let it finish (or stop it "
                              "on the Deliver page) and press TIMELINE SEQ again.")
    start, end = info.get("start"), info.get("end")
    if start is None or end is None or int(end) <= int(start):
        raise SecondUnitError("Resolve did not report where '%s' sits on the timeline, so there "
                              "is no range to render." % info.get("name"))
    expected = int(end) - int(start)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    name = slugify(os.path.splitext(str(info.get("name") or "clip"))[0])
    base = {"SelectAllFrames": False, "MarkIn": int(start), "MarkOut": int(end) - 1,
            "TargetDir": folder, "CustomName": name, "UseUniqueFilenames": False}

    previous = _rv_call(project, "GetCurrentRenderFormatAndCodec") or {}
    previous_mode = _rv_call(project, "GetCurrentRenderMode")
    if _rv_call(project, "SetCurrentRenderMode", 1) is False:
        raise SecondUnitError("Resolve refused 'Single clip' render mode.")
    if not _rv_call(project, "SetCurrentRenderFormatAndCodec", "png", "RGB8"):
        raise SecondUnitError("This Resolve refused PNG / RGB 8-bit as a render format. Check the "
                              "Deliver page's format list.")
    settings = dict(base)
    settings.update({"ExportVideo": True, "ExportAudio": False,
                     "FormatWidth": int(width), "FormatHeight": int(height)})
    if not _rv_call(project, "SetRenderSettings", settings):
        raise SecondUnitError("Resolve refused the PNG render settings for frames %d-%d into %s."
                              % (int(start), int(end) - 1, folder))
    png_job = _rv_call(project, "AddRenderJob")
    if not png_job:
        raise SecondUnitError("Resolve did not add the PNG render job to the queue.")
    wav_job = None
    if SEQUENCE_RESOLVE_WAV:
        if _rv_call(project, "SetCurrentRenderFormatAndCodec", "wav", "lpcm"):
            audio = dict(base)
            audio.update({"ExportVideo": False, "ExportAudio": True,
                          "AudioBitDepth": 24, "AudioSampleRate": 48000})
            if _rv_call(project, "SetRenderSettings", audio):
                wav_job = _rv_call(project, "AddRenderJob") or None
        if not wav_job:
            log("sequence: Resolve refused the WAV job - the soundtrack will be pulled from the "
                "source file by ffmpeg once the frames are complete")
    else:
        log("sequence: Resolve WAV job disabled; the soundtrack comes from the source file once "
            "the frames are complete")
    jobs = [png_job] + ([wav_job] if wav_job else [])
    if not _rv_call(project, "StartRendering", jobs, False):
        raise SecondUnitError("Resolve refused to start render job %s. Open the Deliver page and "
                              "look at the Render Queue." % png_job)
    log("sequence: queued png=%s wav=%s frames %d-%d (%d) %dx%d -> %s"
        % (png_job, wav_job, int(start), int(end) - 1, expected, int(width), int(height), folder))

    return {"png_job": png_job, "wav_job": wav_job, "folder": folder, "expected": expected,
            "name": name, "width": int(width), "height": int(height), "info": dict(info),
            "started": time.time(), "verified": False,
            "previous_format": previous, "previous_mode": previous_mode}


def restore_deliver_settings(project, pending):
    previous = pending.get("previous_format") or {}
    fmt, codec = str(previous.get("format") or ""), str(previous.get("codec") or "")
    if fmt and fmt != "unknown":
        if not _rv_call(project, "SetCurrentRenderFormatAndCodec", fmt, codec):
            log("sequence: could not restore the Deliver format %s/%s" % (fmt, codec))
    previous_mode = pending.get("previous_mode")
    if previous_mode in (0, 1) and previous_mode != 1:
        _rv_call(project, "SetCurrentRenderMode", previous_mode)


def rv_queue_compound_audio(project, pending):
    info = pending.get("info") or {}
    if _rv_call(project, "IsRenderingInProgress"):
        return None
    if not _rv_call(project, "SetCurrentRenderFormatAndCodec", "wav", "lpcm"):
        return None
    settings = {"SelectAllFrames": False, "MarkIn": int(info["start"]), "MarkOut": int(info["end"]) - 1,
                "TargetDir": pending["folder"], "CustomName": "audio", "UseUniqueFilenames": False,
                "ExportVideo": False, "ExportAudio": True, "AudioBitDepth": 24, "AudioSampleRate": 48000}
    if not _rv_call(project, "SetRenderSettings", settings):
        return None
    job = _rv_call(project, "AddRenderJob") or None
    if job and not _rv_call(project, "StartRendering", [job], False):
        return None
    log("sequence: compound audio job %s queued for frames %d-%d" % (job, int(info["start"]), int(info["end"]) - 1))
    return job


def rv_sequence_status(project, pending):
    status = _rv_call(project, "GetRenderJobStatus", pending["png_job"]) or {}
    wav_status = None
    if pending.get("wav_job"):
        wav_status = _rv_call(project, "GetRenderJobStatus", pending["wav_job"]) or {}
    on_disk = len([p for p in sequence_frame_files(pending["folder"]) if p.lower().endswith(".png")])
    try:
        percent = int(status.get("CompletionPercentage") or 0)
    except (TypeError, ValueError):
        percent = 0
    return {"job": str(status.get("JobStatus") or "?"), "percent": percent,
            "error": str(status.get("Error") or ""),
            "wav_job": (str(wav_status.get("JobStatus") or "?") if wav_status is not None else "n/a"),
            "on_disk": on_disk, "eta_ms": status.get("EstimatedTimeRemainingInMs")}


def extract_audio_wav_argv(source_path, target, in_seconds=None, seconds=None, audio=False):
    argv = ["ffmpeg", "-y", "-v", "error"]
    if audio:
        if in_seconds and float(in_seconds) > 0:
            argv += ["-ss", "%.3f" % float(in_seconds)]
        argv += ["-i", source_path]
    else:
        argv += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    if seconds and float(seconds) > 0:
        argv += ["-t", "%.3f" % float(seconds)]
    return argv + ["-vn", "-c:a", "pcm_s24le", target]


def extract_audio_wav(source_path, target, in_seconds=None, seconds=None):
    if not _tool_path("ffmpeg") or not source_path:
        return None
    audio = os.path.isfile(source_path) and has_audio_stream(source_path)
    argv = extract_audio_wav_argv(source_path, target, in_seconds, seconds, audio=bool(audio))
    out = _run_tool(argv, timeout=600)
    if out is None or not os.path.isfile(target) or os.path.getsize(target) <= 44:
        return None
    return target


def rv_timeline_video_tracks(timeline):
    out = []
    try:
        count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        return out
    for i in range(1, count + 1):
        locked = False
        try:
            locked = bool(timeline.GetIsTrackLocked("video", i))
        except Exception:
            pass
        out.append((i, locked))
    return out


def rv_capture_placement(project):
    timeline = _rv_call(project, "GetCurrentTimeline")
    item = _rv_call(timeline, "GetCurrentVideoItem") if timeline else None
    if not timeline or not item:
        return None
    return {"timeline_id": timeline.GetUniqueId(), "start": int(item.GetStart())}


def rv_append_to_timeline(project, media_pool, items, clip_paths=None, placement=None):
    receipt = {
        "appended": [], "created_timeline": False, "warnings": [],
        "timeline": None, "fps": None, "track": None,
    }
    if project is None:
        raise SecondUnitError("No project is open in Resolve, so there is no timeline to add to.")
    if not items:
        raise SecondUnitError("Nothing was imported, so nothing can be added to a timeline.")

    timeline = None
    try:
        timeline = project.GetCurrentTimeline()
    except Exception:
        timeline = None


    if timeline is None:
        if placement:
            raise SecondUnitError("The original timeline is no longer open. The result remains in the Media Pool.")
        name = "Second Unit %s" % time.strftime("%H%M%S")
        try:
            timeline = media_pool.CreateTimelineFromClips(name, items)
        except Exception as exc:
            raise SecondUnitError("No timeline was open and one could not be created (%s)." % exc)
        if not timeline:
            raise SecondUnitError("No timeline was open and Resolve refused to create one.")
        try:
            project.SetCurrentTimeline(timeline)
        except Exception:
            pass
        receipt["created_timeline"] = True
        receipt["timeline"] = name
        receipt["appended"] = [_rv_item_name(i) for i in items]
        receipt["warnings"].append("No timeline was open, so '%s' was created." % name)
        _rv_stamp_fps(receipt, timeline, items)
        return receipt

    try:
        receipt["timeline"] = timeline.GetName()
    except Exception:
        receipt["timeline"] = "(unnamed)"


    if placement and timeline.GetUniqueId() != placement["timeline_id"]:
        raise SecondUnitError("The active timeline changed during generation. Open the original timeline to place the result.")
    tracks = rv_timeline_video_tracks(timeline)
    unlocked = [i for i, locked in tracks if not locked]
    if tracks and not unlocked and not placement:
        raise SecondUnitError(
            "Every video track on '%s' is locked. Unlock one and press Generate again."
            % receipt["timeline"])
    receipt["track"] = unlocked[0] if unlocked else 1

    _rv_stamp_fps(receipt, timeline, items)

    append_items = items
    if placement:
        track = int(timeline.GetTrackCount("video") or 0) + 1
        if not timeline.AddTrack("video"):
            raise SecondUnitError("Could not add a track above the source clip. The result remains in the Media Pool.")
        while int(timeline.GetTrackCount("audio") or 0) < track:
            if not timeline.AddTrack("audio", "stereo"):
                raise SecondUnitError("Could not add the audio delivery track. The result remains in the Media Pool.")
        receipt["track"] = track
        receipt["placement"] = "above-source"
        append_items = [{"mediaPoolItem": item, "trackIndex": track,
                         "recordFrame": placement["start"]} for item in items]
    try:
        appended = media_pool.AppendToTimeline(append_items) or []
    except Exception as exc:
        raise SecondUnitError("Resolve refused the timeline append: %s" % exc)

    if not appended:
        raise SecondUnitError(
            "Resolve accepted the clip into the Media Pool but put nothing on '%s'. "
            "This is usually a locked or hidden video track." % receipt["timeline"])

    for ti in appended:
        entry = {"name": None, "start": None, "duration": None}
        try:
            entry["name"] = ti.GetName()
        except Exception:
            pass
        for key, fn in (("start", "GetStart"), ("duration", "GetDuration")):
            try:
                entry[key] = int(getattr(ti, fn)())
            except Exception:
                pass
        receipt["appended"].append(entry)
    return receipt


def _rv_item_name(item):
    try:
        return {"name": item.GetName(), "start": None, "duration": None}
    except Exception:
        return {"name": None, "start": None, "duration": None}


def _rv_stamp_fps(receipt, timeline, items):
    tl_fps = None
    for getter in ("timelineFrameRate", "timelineFrameRateMismatchBehavior"):
        try:
            v = timeline.GetSetting(getter)
            if getter == "timelineFrameRate" and v:
                tl_fps = float(v)
                break
        except Exception:
            continue
    receipt["fps"] = tl_fps
    if tl_fps is None:
        return
    for item in items:
        try:
            clip_fps = item.GetClipProperty("FPS")
            if clip_fps and abs(float(clip_fps) - tl_fps) > 0.01:
                receipt["warnings"].append(
                    "Clip is %s fps on a %g fps timeline - Resolve will conform it."
                    % (clip_fps, tl_fps))
                break
        except Exception:
            continue




WIN_ID = "com.cmdmedia.secondunit.panel"

WIN_GEOMETRY = [200, 32, 700, 760]
TIMER_ID = "su_timer"
TIMER_INTERVAL_MS = 300


class SecondUnitPanel(object):
    def __init__(self, fusion_obj, bmd_obj, resolve_obj, project_obj,
                 recovery_cache_root=LAB_CACHE, recover_job_func=recover_external_job):
        self.fusion = fusion_obj
        self.ui = fusion_obj.UIManager
        self.dispatcher = bmd_obj.UIDispatcher(self.ui)
        self.resolve = resolve_obj
        self.injected_project = project_obj
        self.client = ComfyClient(COMFY_URL)
        self.outbox = queue.Queue()
        self.stop_event = threading.Event()

        self.recovery_cache_root = os.path.abspath(recovery_cache_root)
        self.job = recover_job_func(
            self.outbox, cache_root=self.recovery_cache_root)
        self.recovered_job = self.job is not None
        self.entries = []
        self.problems = []
        self.win = None
        self.has_timer = False
        self.timer_element = None
        self._timer_ticks = 0
        self._timer_started_at = None
        self.pending_sequence = None
        self._sequence_poll_at = 0.0
        self.own_loop = OWN_LOOP
        self._own_loop_active = False
        self._loop_ticks = 0
        self._loop_degraded = None
        self._tick_errors = 0
        self.landing = None
        self._op_status = None
        self._op_status_at = None
        self._reconcile_thread = None
        self._reconcile_at = 0.0
        self._last_slow_tick = 0.0
        self._clock_painted_at = 0.0
        self.build_stale = False
        self.job_state = "READY"
        self.health_ok = None
        self.health_stop = threading.Event()
        self.health = None
        self._clearing_state = False
        self.submission_uncertain = False
        self.pending_delivery = None
        self.source_in_seconds = None
        self.source_exact_frames = None
        self.source_exact_fps = None
        self.expander_original = None
        self.expander_last = None
        self.expander_presses = 0



    def find(self, widget_id):
        try:
            return self.win.Find(widget_id)
        except Exception:
            return None

    def set_attr(self, widget_id, attr, value):
        widget = self.find(widget_id)
        if widget is None:
            return
        try:
            setattr(widget, attr, value)
        except Exception:
            pass

    def get_text(self, widget_id):
        widget = self.find(widget_id)
        if widget is None:
            return ""
        fallback = ""
        for attr in ("CurrentText", "PlainText", "Text"):
            try:
                value = getattr(widget, attr)
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, str) and not fallback:
                fallback = value
        return fallback

    def get_checked(self, widget_id):
        widget = self.find(widget_id)
        try:
            return bool(widget.Checked)
        except Exception:
            return False

    def status(self, text, progress=None, severity=None):
        log("status%s: %s" % ("[%s]" % severity if severity else "", text))
        self.set_attr("status", "Text", text)
        if severity in STATUS_SHEETS:
            self.set_attr("status", "StyleSheet", STATUS_SHEETS[severity])
        if progress is not None:
            self.set_attr("progress", "Value", int(max(0, min(100, progress))))

    def state(self, key, detail=None, elapsed=None, eta=None, severity=None, text=None, progress=None):

        self._outcome_writes = getattr(self, "_outcome_writes", 0) + 1
        current = getattr(self, "job_state", None)
        if current in STICKY_STATES and key not in STICKY_STATES and not self._clearing_state:
            key = current
            detail = None if detail is None else detail
        else:
            self.job_state = key
            chip_text, chip_sheet = job_chip(key)
            self.set_attr("jobstate", "Text", chip_text)
            self.set_attr("jobstate", "StyleSheet", chip_sheet)
        if detail is not None:
            self.set_attr("jobdetail", "Text", detail)
        if elapsed is not None:
            timing = mmss(elapsed)
            if eta is not None:
                timing += " Â· ETA " + mmss(eta)
            self.set_attr("jobtime", "Text", timing)
        if text is not None:
            self.status(text, progress, severity)
        elif progress is not None:
            self.set_attr("progress", "Value", int(max(0, min(100, progress))))



    def build(self):
        timer_element = None
        try:
            timer_element = self.ui.Timer({"ID": TIMER_ID, "Interval": TIMER_INTERVAL_MS})
        except Exception:
            timer_element = None

        self.timer_element = timer_element


        self.styled = True
        last_error = None
        attempts = (
            (True, True, True), (True, True, False), (True, False, False),
            (False, True, True), (False, True, False), (False, False, False),
        )
        for styled, use_timer, use_slider in attempts:
            try:
                self.win = self.dispatcher.AddWindow(
                    {"ID": WIN_ID, "WindowTitle": "RENEGADE // SECOND UNIT",
                     "Geometry": list(WIN_GEOMETRY),
                     "StyleSheet": ST_WINDOW if styled else ""},
                    self._layout(timer_element if use_timer else None, use_slider, styled),
                )
                self.styled = styled
                break
            except Exception as exc:
                last_error = exc
                self.win = None
                try:
                    stale = self.ui.FindWindow(WIN_ID)
                    if stale:
                        stale.Close()
                except Exception:
                    pass
        if self.win is None:
            raise SecondUnitError("Could not build the Second Unit window: %s" % last_error)

        self._wire(timer_element is not None)
        return self.win

    def _layout(self, timer_element, use_slider, styled=True):
        ui = self.ui
        if not styled:
            def ui_plain(factory):
                def make(spec, *rest):
                    spec = {k: v for k, v in spec.items() if k != "StyleSheet"}
                    return factory(spec, *rest) if rest else factory(spec)
                return make
            ui = type("PlainUI", (), {name: staticmethod(ui_plain(getattr(self.ui, name)))
                                      for name in ("Label", "Button", "ComboBox", "LineEdit",
                                                   "TextEdit", "CheckBox", "Slider", "VGroup",
                                                   "HGroup")})
            ui.Font = self.ui.Font
            ui.HGap = self.ui.HGap

        mono = ui.Font({"Family": "Consolas", "PixelSize": 11, "MonoSpaced": True})
        face = ui.Font({"Family": "Segoe UI", "PixelSize": 13})
        face_small = ui.Font({"Family": "Segoe UI", "PixelSize": 11})
        eyebrow_font = ui.Font({"Family": "Bahnschrift SemiCondensed", "PixelSize": 10})
        display_font = ui.Font({"Family": "Bahnschrift SemiCondensed", "PixelSize": 15})
        action_font = ui.Font({"Family": "Bahnschrift SemiCondensed", "PixelSize": 13})
        row_label_width = 78


        def rule():
            return ui.Label({"Text": "", "Weight": 0, "MinimumSize": [0, 1],
                             "MaximumSize": [16777215, 1], "StyleSheet": ST_RULE})

        def row(name, contents, group_id=None, label_id=None):
            label = {"Text": name, "Weight": 0, "Font": eyebrow_font,
                     "StyleSheet": ST_ROWLABEL, "MinimumSize": [row_label_width, 0],
                     "MaximumSize": [row_label_width, 16777215]}
            if label_id:
                label["ID"] = label_id
            group = {"Weight": 0, "Spacing": 7}
            if group_id:
                group["ID"] = group_id
            return ui.HGroup(group, [ui.Label(label)] + list(contents))

        def section(number, title, meta, section_id):
            return ui.HGroup({"ID": section_id, "Weight": 0, "Spacing": 9,
                              "StyleSheet": ST_SECTION}, [
                ui.Label({"Text": number, "Weight": 0, "Font": eyebrow_font,
                          "MinimumSize": [24, 0], "MaximumSize": [24, 16777215],
                          "StyleSheet": ST_SECTION_NUMBER}),
                ui.Label({"Text": title, "Weight": 0, "Font": display_font,
                          "StyleSheet": ST_SECTION_TITLE}),
                ui.HGap(5),
                ui.Label({"Text": meta, "Weight": 1, "Font": eyebrow_font,
                          "StyleSheet": ST_SECTION_META}),
            ])

        children = [

            ui.HGroup({"ID": "renegade_masthead", "Weight": 0, "Spacing": 11,
                       "StyleSheet": ST_HEADER}, [
                ui.Label({"Text": "", "Weight": 0, "MinimumSize": [3, 52],
                          "MaximumSize": [3, 52], "StyleSheet": ST_ACCENT_BAR}),
                ui.VGroup({"Weight": 1, "Spacing": 0,
                           "MaximumSize": [390, 16777215]}, [
                    ui.Label({
                        "ID": "renegade_eyebrow",
                        "Text": ("<span style='font-size:9px; font-weight:800; color:%s;"
                                 " letter-spacing:2.4px;'>CMD&nbsp;ORIGINAL&nbsp;//&nbsp;"
                                 "RENEGADE&nbsp;PRODUCTION&nbsp;SYSTEM</span>" % C_ACCENT),
                        "Weight": 0,
                    }),
                    ui.Label({
                        "ID": "renegade_title",
                        "Text": ("<span style=\"font-family:'Bahnschrift SemiCondensed';"
                                 "font-size:25px;font-weight:900;font-style:italic;"
                                 "letter-spacing:1px;color:%s;\">SECOND&nbsp;"
                                 "<span style='color:%s;'>UNIT</span></span>"
                                 % (C_TEXT, C_ACCENT)),
                        "Weight": 0,
                    }),
                    ui.Label({
                        "ID": "renegade_descriptor",
                        "Text": ("<span style='font-size:9px; color:%s;"
                                 " letter-spacing:1.8px;'>AI&nbsp;SHOT&nbsp;DEPARTMENT&nbsp;//&nbsp;"
                                 "LOCAL&nbsp;GPU&nbsp;PIPELINE</span>" % C_META),
                        "Weight": 0,
                    }),
                ]),

                ui.Label({
                    "ID": "server", "Text": server_chip(COMFY_URL, None)[0], "Weight": 0,
                    "Font": eyebrow_font, "StyleSheet": server_chip(COMFY_URL, None)[1],
                }),
            ]),

            section("01", "BUILD THE SHOT", "MODEL / FORMAT / METHOD", "section_build"),

            row("MODEL", [
                ui.ComboBox({"ID": "family", "Weight": 1, "Font": face, "StyleSheet": ST_COMBO}),
            ]),
            row("EXPORT", [
                ui.ComboBox({"ID": "resolution", "Weight": 1, "Font": face,
                             "StyleSheet": ST_COMBO}),
                ui.Label({"Text": "PRORES HQ Â· MOV", "Weight": 0,
                          "Font": eyebrow_font, "StyleSheet": ST_META}),
            ]),
            row("DETAIL", [
                ui.CheckBox({"ID": "detail_upscale",
                             "Text": "LTX 2.5 photographic detail (optional x2)",
                             "ToolTip": "Generative refinement can alter faces or fine detail. Preserves selected export size; adds processing time.",
                             "Checked": False, "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_CHECK}),
            ]),
            row("MAKE", [
                ui.ComboBox({"ID": "mode", "Weight": 1, "Font": face, "StyleSheet": ST_COMBO}),
                ui.ComboBox({"ID": "lane", "Weight": 1, "Font": face, "StyleSheet": ST_COMBO}),
            ]),

            row("PRESET", [
                ui.ComboBox({"ID": "preset", "Weight": 1, "Font": face, "StyleSheet": ST_COMBO}),
                ui.Button({"ID": "load_workflow", "Text": "LOAD WORKFLOW", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ]),
            row("", [
                ui.Label({"ID": "graph", "Text": "Finding a graph...", "Weight": 1,
                          "Font": face_small, "StyleSheet": ST_SUBTLE, "WordWrap": True}),
            ]),

            section("02", "DIRECT THE FRAME", "INTENT / EXCLUSIONS", "section_direct"),


            ui.HGroup({"Weight": 1, "Spacing": 7}, [
                ui.Label({"Text": "SHOT", "Weight": 0, "Font": eyebrow_font,
                          "StyleSheet": ST_ROWLABEL, "MinimumSize": [row_label_width, 0],
                          "MaximumSize": [row_label_width, 16777215]}),
                ui.TextEdit({
                    "ID": "prompt", "Weight": 1, "Font": face, "StyleSheet": ST_INPUT,
                    "MinimumSize": [0, 64], "MaximumSize": [16777215, 120],
                    "PlaceholderText": "A lone figure walks away down a rain-slicked street "
                                       "at blue hour, neon reflections, slow dolly push-in...",
                }),
            ]),
            row("EXPAND", [
                ui.Button({"ID": "expand_prompt", "Text": "PROMPT EXPANDER", "Enabled": False, "Weight": 0, "Font": eyebrow_font,
                           "MinimumSize": [150, 28], "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "revert_prompt", "Text": "REVERT", "Weight": 0, "Font": eyebrow_font, "MinimumSize": [80, 28], "StyleSheet": ST_BTN_GHOST}),
                ui.Label({"ID": "expander_status", "Weight": 1, "Font": face_small, "StyleSheet": ST_META,
                          "Text": "expands SHOT for the selected model while preserving your scene and camera request"}),
            ]),
            ui.Label({"ID": "camera_status", "Text": "Camera metadata captured before expansion or generation", "WordWrap": True, "Font": face_small}),
            row("AVOID", [
                ui.LineEdit({"ID": "negative", "Text": "", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "leave blank to keep the preset's"}),
            ], group_id="negativerow", label_id="negativelabel"),

            section("03", "FEED THE WORLD", "PLATE / REFERENCES / TIMING", "section_world"),


            row("SOURCE", [
                ui.LineEdit({"ID": "source", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "the clip this shot is built from - a file, or a folder of frames"}),
                ui.Button({"ID": "usetimeline", "Text": "TIMELINE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "usetimeline_seq", "Text": "TIMELINE SEQ", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "browse", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "browse_dir", "Text": "FOLDER", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="sourcerow", label_id="sourcelabel"),

            row("FORMAT", [
                ui.ComboBox({"ID": "source_format", "Weight": 1, "Font": face, "StyleSheet": ST_COMBO}),
                ui.Label({"ID": "source_format_note", "Weight": 2, "Font": face_small, "StyleSheet": ST_META,
                          "Text": "PNG = lossless frames at the preset's canvas; video = H.264 proxy. "
                                  "TIMELINE SEQ renders the graded clip out of Resolve as PNG + WAV.",
                          "WordWrap": True}),
                ui.Button({"ID": "open_sequence", "Text": "OPEN", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="sourceformatrow", label_id="sourceformatlabel"),
            row("END", [
                ui.LineEdit({"ID": "source2", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT, "PlaceholderText": "closing keyframe"}),
                ui.Button({"ID": "browse2", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="source2row", label_id="source2label"),
            row("IDENTITY", [
                ui.LineEdit({"ID": "source3", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "actor identity reference - no pose ownership"}),
                ui.Button({"ID": "browse3", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="source3row", label_id="source3label"),
            row("WARDROBE", [
                ui.LineEdit({"ID": "source4", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "complete replacement wardrobe reference"}),
                ui.Button({"ID": "browse4", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="source4row", label_id="source4label"),
            row("PROP 1", [
                ui.LineEdit({"ID": "source5", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "complete prop reference - appearance only"}),
                ui.Button({"ID": "browse5", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="source5row", label_id="source5label"),
            row("PROP 2", [
                ui.LineEdit({"ID": "source6", "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_INPUT,
                             "PlaceholderText": "second prop reference - appearance only"}),
                ui.Button({"ID": "browse6", "Text": "FILE", "Weight": 0,
                           "Font": eyebrow_font, "StyleSheet": ST_BTN_GHOST}),
            ], group_id="source6row", label_id="source6label"),

            ui.VGroup({"ID": "v2vcontrols", "Weight": 0, "Spacing": 7}, [
                row("LOCK", [
                    ui.ComboBox({"ID": "v2v_retention", "Weight": 1,
                                 "Font": face_small, "StyleSheet": ST_COMBO}),
                ]),
                row("ROLE", [
                    ui.ComboBox({"ID": "ingredient_role", "Weight": 1,
                                 "Font": face_small, "StyleSheet": ST_COMBO}),
                ]),
                row("CHANGE", [
                    ui.ComboBox({"ID": "edit_amount", "Weight": 1,
                                 "Font": face_small, "StyleSheet": ST_COMBO}),
                ]),
            ]),
            ui.VGroup({"ID": "envcontrols", "Weight": 0, "Spacing": 7}, [
                row("MASK", [
                    ui.LineEdit({
                        "ID": "subject_query", "Text": "person", "Weight": 1,
                        "Font": face_small, "StyleSheet": ST_INPUT,
                        "PlaceholderText": "what must stay: man in black jacket",
                    }),
                ]),
                row("RELIGHT", [
                    ui.CheckBox({
                        "ID": "environment_relight",
                        "Text": "Seat subject into the new lighting (slower second pass)",
                        "Checked": False, "Weight": 1, "Font": face_small,
                        "StyleSheet": ST_CHECK,
                    }),
                ], group_id="relightrow"),
            ]),
            ui.VGroup({"ID": "h3controls", "Weight": 0, "Spacing": 7}, [
                row("CARDS", [
                    ui.CheckBox({
                        "ID": "auto_cards",
                        "Text": "AUTO CARDS (experimental): harvest identity cards from the footage itself (pack builder)",
                        "Checked": False, "Weight": 1, "Font": face_small,
                        "StyleSheet": ST_CHECK,
                    }),
                ]),
            ]),
            row("LENGTH", [
                ui.LineEdit({"ID": "seconds", "Text": "5", "Weight": 0,
                             "MinimumSize": [46, 0], "MaximumSize": [46, 16777215],
                             "Font": face, "StyleSheet": ST_INPUT}),
                ui.Label({"Text": "SEC", "Weight": 0, "Font": eyebrow_font, "StyleSheet": ST_META}),
                ui.HGap(6),
                ui.Label({"Text": "SEED", "Weight": 0, "Font": eyebrow_font, "StyleSheet": ST_ROWLABEL}),
                ui.LineEdit({"ID": "seed", "Text": "-1", "Weight": 0,
                             "MinimumSize": [56, 0], "MaximumSize": [56, 16777215],
                             "Font": face, "StyleSheet": ST_INPUT}),
                ui.HGap(6),
                ui.Label({"ID": "frames", "Text": "", "Weight": 1, "Font": mono,
                          "StyleSheet": ST_META}),
            ]),
            row("", [
                ui.CheckBox({"ID": "allow_cloud",
                             "Text": "Allow presets that call a paid cloud service",
                             "Checked": False, "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_CHECK}),
                ui.CheckBox({"ID": "show_unproven",
                             "Text": "Show unproven presets",
                             "Checked": bool(SHOW_UNPROVEN), "Weight": 1, "Font": face_small,
                             "StyleSheet": ST_CHECK}),
            ]),

            section("04", "RUN THE TAKE", "GENERATE / VERIFY / DELIVER", "section_run"),


            ui.HGroup({"Weight": 0, "Spacing": 7}, [
                ui.Button({"ID": "generate", "Text": "GENERATE SHOT", "Weight": 1,
                           "Font": action_font,
                           "MinimumSize": [0, 42], "StyleSheet": ST_BTN_PRIMARY}),
                ui.Button({"ID": "cancel", "Text": "STOP", "Weight": 0, "Font": eyebrow_font,
                           "MinimumSize": [74, 42], "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "rescan", "Text": "RELOAD", "Weight": 0, "Font": eyebrow_font,
                           "MinimumSize": [74, 42], "StyleSheet": ST_BTN_GHOST}),
                ui.Button({"ID": "refresh", "Text": "REFRESH", "Weight": 0, "Font": eyebrow_font,
                           "MinimumSize": [74, 42], "StyleSheet": ST_BTN_GHOST}),
            ]),


            ui.HGroup({"ID": "staterow", "Weight": 0, "Spacing": 7}, [
                ui.Label({"ID": "jobstate", "Text": job_chip("READY")[0], "Weight": 0,
                          "Font": eyebrow_font, "StyleSheet": job_chip("READY")[1]}),
                ui.Label({"ID": "jobdetail", "Text": "", "Weight": 1, "Font": mono,
                          "StyleSheet": ST_META}),
                ui.Label({"ID": "jobtime", "Text": "", "Weight": 0, "Font": mono,
                          "StyleSheet": ST_META}),
            ]),
        ]

        if use_slider:
            children.append(ui.Slider({
                "ID": "progress", "Weight": 0, "Orientation": "Horizontal",
                "Minimum": 0, "Maximum": 100, "Value": 0, "Enabled": False,
                "StyleSheet": ST_PROGRESS,
            }))

        children.append(ui.Label({
            "ID": "status", "Text": "Starting up...", "WordWrap": True, "Weight": 0,
            "Font": face, "StyleSheet": ST_STATUS,
        }))


        return ui.VGroup({"Spacing": 6, "StyleSheet": ST_WINDOW, "Font": face}, children)

    def start_timer(self):
        if not self.has_timer:
            return
        element = self.timer_element if self.timer_element is not None else self.find(TIMER_ID)
        try:
            if element is not None and hasattr(element, "Start"):
                element.Start()
                self._timer_started_at = time.monotonic()
                log("TIMER: started after Show(), interval %sms" % TIMER_INTERVAL_MS)
            else:
                log("TIMER: no Start() on the element - it may never fire")
        except Exception as exc:
            log("TIMER: Start() failed: %s: %s" % (exc.__class__.__name__, exc))

    def timer_alive(self):
        return bool(self.has_timer and self._timer_ticks > 0)

    def live_updates(self):
        if getattr(self, "_own_loop_active", False):
            return not getattr(self, "_loop_degraded", None)
        return self.timer_alive()

    def refresh_hint(self):
        if self.live_updates():
            return ""
        if getattr(self, "_own_loop_active", False):
            return "Updates continue by themselves; they may arrive late while Resolve is busy."
        return "Live updates are OFF on this Resolve build: press REFRESH to see progress and land a finished clip."

    def check_build_on_disk(self, force=False):
        now = time.monotonic()
        if not force and now - getattr(self, "_build_checked_at", 0.0) < BUILD_CHECK_S:
            return not getattr(self, "build_stale", False)
        self._build_checked_at = now
        try:
            current = _sha256_file(_self_path())
        except OSError:
            return True
        if _LOADED_SCRIPT_SHA256 and current != _LOADED_SCRIPT_SHA256:
            if not getattr(self, "build_stale", False):
                self.build_stale = True
                log("build: on-disk %s differs from loaded %s" % (current[:12], _LOADED_SCRIPT_SHA256[:12]))
                self.status(BUILD_STALE_TEXT, 0, severity="fail")
            self.set_attr("generate", "Text", "REOPEN PANEL - NEW BUILD")
            self.set_attr("generate", "Enabled", False)
            self.set_attr("graph", "Text", BUILD_STALE_TEXT)
            return False
        return True

    def on_tick(self, event=None):
        try:
            self.pump(event if event is not None else {})
            if getattr(self, "_own_loop_active", False): self.paint_clock(time.monotonic())
        except Exception:
            self._tick_errors = getattr(self, "_tick_errors", 0) + 1
            now = time.monotonic()
            if now - getattr(self, "_tick_error_logged_at", 0.0) > 60.0:
                self._tick_error_logged_at = now
                log("LOOP: tick raised:\n%s" % traceback.format_exc())

    def paint_clock(self, now):
        if now - getattr(self, "_clock_painted_at", 0.0) < 1.0:
            return
        if not (self.job and self.job.is_alive()) or not getattr(self, "_op_status", None):
            return
        if getattr(self, "job_state", "") in STICKY_STATES:
            return
        self._clock_painted_at = now
        since = now - self._op_status_at
        elapsed = (self._op_status.get("elapsed") or 0) + since
        eta = self._op_status.get("eta")
        if eta is not None:
            eta = max(0, eta - since)
        self.set_attr("jobtime", "Text", mmss(elapsed) + ("" if eta is None else " Â· ETA " + mmss(eta)))

    def note_dead_timer(self):
        if getattr(self, "_own_loop_active", False): return
        if not self.has_timer or self._timer_ticks or self._timer_started_at is None:
            return
        waited = time.monotonic() - self._timer_started_at
        if waited > 5.0:
            self.has_timer = False
            log("TIMER: wired and started but never fired in %.0fs - live updates OFF (click-driven)" % waited)

    def _guard(self, widget_id, event, handler):
        def wrapped(event_payload=None):
            started = time.perf_counter()
            outcome = "ok"
            try:

                if widget_id != TIMER_ID:
                    try:
                        self.pump(None)
                    except Exception:
                        log("pump inside %s.%s raised:\n%s"
                            % (widget_id, event, traceback.format_exc()))
                return handler(event_payload)
            except SecondUnitError as exc:

                outcome = "refused"
                self.status(str(exc))
            except Exception as exc:
                outcome = "error"
                log("UNHANDLED in %s.%s: %s" % (widget_id, event, traceback.format_exc()))
                self.status("%s failed: %s   Details: %s"
                            % (widget_id.capitalize(), exc.__class__.__name__, log_path()))
            finally:
                log("click %s.%s ack=%.1fms %s"
                    % (widget_id, event, (time.perf_counter() - started) * 1000.0, outcome))
        return wrapped

    def _wire(self, has_timer_element):
        family_box = self.find("family")
        if family_box:
            family_box.AddItems([label for _key, label in FAMILY_LABELS])
        resolution_box = self.find("resolution")
        if resolution_box:
            resolution_box.AddItems([label for _key, label in RESOLUTION_LABELS])
        mode_box = self.find("mode")
        if mode_box:
            mode_box.AddItems([label for _key, label in MODE_LABELS])
        lane_box = self.find("lane")
        if lane_box:
            lane_box.AddItems([label for _key, label in LANE_LABELS])
        retention_box = self.find("v2v_retention")
        if retention_box:
            retention_box.AddItems([label for _key, label in V2V_RETENTION_LABELS])
        ingredient_box = self.find("ingredient_role")
        if ingredient_box:
            ingredient_box.AddItems([label for _key, label in V2V_INGREDIENT_LABELS])
        edit_box = self.find("edit_amount")
        if edit_box:
            edit_box.AddItems([label for _key, label in V2V_EDIT_LABELS])
        format_box = self.find("source_format")
        if format_box:
            format_box.AddItems([label for _key, label in SOURCE_FORMAT_LABELS])


        wiring = [
            (WIN_ID, "Close", self.on_close),
            (WIN_ID, "ExpanderReady", self.pump),
            ("generate", "Clicked", self.on_generate),
            ("expand_prompt", "Clicked", self.on_expand_prompt),
            ("revert_prompt", "Clicked", self.on_revert_prompt),
            ("cancel", "Clicked", self.on_cancel),
            ("rescan", "Clicked", self.on_rescan),
            ("refresh", "Clicked", self.on_refresh_readiness),
            ("browse", "Clicked", self.on_browse),
            ("browse2", "Clicked", self.on_browse2),
            ("browse3", "Clicked", self.on_browse3),
            ("browse4", "Clicked", self.on_browse4),
            ("browse5", "Clicked", self.on_browse5),
            ("browse6", "Clicked", self.on_browse6),
            ("usetimeline", "Clicked", self.on_use_timeline),
            ("family", "CurrentIndexChanged", self.on_family_changed),
            ("resolution", "CurrentIndexChanged", self.on_selection_changed),
            ("detail_upscale", "Clicked", self.on_selection_changed),
            ("mode", "CurrentIndexChanged", self.on_mode_changed),
            ("preset", "CurrentIndexChanged", self.on_selection_changed),
            ("lane", "CurrentIndexChanged", self.on_mode_changed),
            ("v2v_retention", "CurrentIndexChanged", self.on_selection_changed),
            ("ingredient_role", "CurrentIndexChanged", self.on_selection_changed),
            ("edit_amount", "CurrentIndexChanged", self.on_selection_changed),
            ("source_format", "CurrentIndexChanged", self.on_selection_changed),
            ("browse_dir", "Clicked", self.on_browse_dir),
            ("usetimeline_seq", "Clicked", self.on_use_timeline_seq),
            ("open_sequence", "Clicked", self.on_open_sequence),
            ("load_workflow", "Clicked", self.on_load_workflow),
            ("environment_relight", "Clicked", self.on_selection_changed),
            ("subject_query", "TextChanged", self.on_selection_changed),
            ("allow_cloud", "Clicked", self.on_selection_changed),
            ("show_unproven", "Clicked", self.on_mode_changed),
            ("seconds", "TextChanged", self.on_selection_changed),
        ]
        self.unwired = []
        for widget_id, event, handler in wiring:
            try:
                setattr(self.win.On[widget_id], event, self._guard(widget_id, event, handler))
            except Exception as exc:
                self.unwired.append("%s.%s (%s)" % (widget_id, event, exc))
        self.set_attr("revert_prompt", "Enabled", bool(getattr(self, "expander_original", None)))


        if any(u.startswith("generate.") for u in self.unwired):
            self.unwired.insert(0, "GENERATE IS NOT WIRED - this build cannot submit a render")


        self.has_timer = False
        if not has_timer_element or self.timer_element is None:
            log("TIMER: this build refused to create the element at all")
        else:

            try:

                self.win.On[TIMER_ID].Timeout = self.on_tick
                self.has_timer = True
                try:
                    self.dispatcher.On[TIMER_ID].Timeout = self.on_tick
                except Exception as exc:
                    log("TIMER: dispatcher-level wiring unavailable (%s: %s); window-level only"
                        % (exc.__class__.__name__, exc))
                log("TIMER: wired on the window and dispatcher On tables (a timer is not a "
                    "widget, win.Find never sees it); will start after the window is shown")
            except Exception as exc:
                self.has_timer = False
                log("TIMER: created, but Timeout could not be wired: %s: %s"
                    % (exc.__class__.__name__, exc))



    def current_preset(self):
        return (self.get_text("preset") or "").strip()

    def show_unproven(self):
        widget = self.find("show_unproven")
        return self.get_checked("show_unproven") if widget is not None else SHOW_UNPROVEN

    def save_panel_state(self):
        if not getattr(self, "_state_ready", False):
            return
        entry, _ = select_graph(self.entries, self.current_mode(), self.current_lane(), self.get_checked("allow_cloud"),
                                self.current_preset(), self.current_family(), show_unproven=self.show_unproven())
        state = {"family": self.current_family(), "mode": self.current_mode(), "lane": self.current_lane(),
                 "preset": entry.name if entry else "", "resolution": self.current_resolution(),
                 "detail_upscale": bool(self.get_checked("detail_upscale")),
                 "ltx_resolution": getattr(self, "_ltx_resolution", "1080P"), "delivery_defaults_version": 1}
        if state != getattr(self, "_state_last", None):
            self._state_last = dict(state)
            write_panel_state(state)

    def restore_panel_state(self):
        state = migrate_delivery_state(read_panel_state())
        self._ltx_resolution = state["ltx_resolution"]
        self._delivery_family = state.get("family")
        try:
            for widget_id, pairs, key in (("family", FAMILY_LABELS, "family"), ("mode", MODE_LABELS, "mode"),
                                          ("lane", LANE_LABELS, "lane"), ("resolution", RESOLUTION_LABELS, "resolution")):
                keys = [k for k, _label in pairs]
                if state.get(key) in keys:
                    self.set_attr(widget_id, "CurrentIndex", keys.index(state[key]))
            if "detail_upscale" in state:
                self.set_attr("detail_upscale", "Checked", bool(state["detail_upscale"]))
            self.repopulate_presets()
            entry = next((e for e in self.entries if e.name == state.get("preset")), None)
            labels = getattr(self, "_preset_labels", None) or []
            if entry is not None and preset_label(entry) in labels:
                self.set_attr("preset", "CurrentIndex", labels.index(preset_label(entry)))
            self.refresh_selection()
        finally:
            self._state_ready = True

    def vsr_note(self, entry):
        if entry and entry.stamp.get("pipeline") == "h3_pose_follow": return None
        if not entry or entry.family != "MINIMAXH3" or self.current_resolution() != "1080P" or self.get_checked("detail_upscale"):
            return None
        client = getattr(self, "client", None)
        if not isinstance(client, ComfyClient):
            return None
        if not hasattr(self, "_vsr_present"):
            try:
                self._vsr_present = bool(client._get("/object_info/RTXVideoSuperResolution", 2))
            except Exception:
                self._vsr_present = None
        if self._vsr_present is not False:
            return None
        return ("1080P on MiniMax H3 needs RTX Video Super Resolution on the generation lane, and ComfyUI at %s does not "
                "have that node. Tick DETAIL (LTX 2.5 x2) for a real 1080P, or choose 720P." % comfy_short_target(COMFY_URL))

    def on_family_changed(self, event=None):
        # A model choice is authoritative. Do not let the previous Stills mode
        # immediately reset it to Juggernaut through on_mode_changed.
        family = self.current_family()
        choices = []
        modes = [self.current_mode()] + [key for key, _ in MODE_LABELS
                                        if key != self.current_mode()]
        lanes = [self.current_lane()] + [key for key, _ in LANE_LABELS
                                        if key != self.current_lane()]
        for mode in modes:
            for lane in lanes:
                if candidates_for(self.entries, mode, lane,
                                  self.get_checked("allow_cloud"), family,
                                  show_unproven=self.show_unproven()):
                    choices.append((mode, lane))
        if choices:
            mode, lane = choices[0]
            self.set_attr("mode", "CurrentIndex", [k for k, _ in MODE_LABELS].index(mode))
            self.set_attr("lane", "CurrentIndex", [k for k, _ in LANE_LABELS].index(lane))
        self.repopulate_presets()
        self.on_selection_changed(event)

    def on_mode_changed(self, event=None):
        if self.current_mode() in ("STORYBOARD", "STILLS"):
            self.set_attr("family", "CurrentIndex", [key for key, _ in FAMILY_LABELS].index("JUGGERNAUT" if self.current_mode() == "STILLS" else "JUGGERNAUTQWEN"))
            self.set_attr("lane", "CurrentIndex", [key for key, _ in LANE_LABELS].index("Quality"))
        self.repopulate_presets()
        self.on_selection_changed(event)

    def repopulate_presets(self):
        box = self.find("preset")
        if box is None:
            return
        wanted = candidates_for(self.entries, self.current_mode(), self.current_lane(),
                                self.get_checked("allow_cloud"), self.current_family(),
                                show_unproven=self.show_unproven())
        labels = [preset_label(entry) for entry in wanted]
        if labels == getattr(self, "_preset_labels", None):
            return
        previous = self.current_preset()
        for clearing in ("Clear", "RemoveItems", "clear"):
            try:
                getattr(box, clearing)()
                break
            except Exception:
                continue
        try:
            box.AddItems(labels)
        except Exception as exc:
            log("preset menu could not be refilled: %s" % exc)
            return
        self._preset_labels = labels
        if previous in labels:
            try:
                box.CurrentIndex = labels.index(previous)
            except Exception:
                pass

    def current_mode(self):
        return _label_to_key(self.get_text("mode"), MODE_LABELS, MODES[0])

    def current_family(self):
        return _label_to_key(self.get_text("family"), FAMILY_LABELS, FAMILIES[0])

    def current_resolution(self):
        return _label_to_key(self.get_text("resolution"), RESOLUTION_LABELS, RESOLUTIONS[0])

    def current_lane(self):
        return _label_to_key(self.get_text("lane"), LANE_LABELS, LANES[0])

    def current_v2v_retention(self):
        return _label_to_key(self.get_text("v2v_retention"), V2V_RETENTION_LABELS,
                             V2V_RETENTION_LABELS[0][0])

    def current_ingredient_role(self):
        return _label_to_key(self.get_text("ingredient_role"), V2V_INGREDIENT_LABELS,
                             V2V_INGREDIENT_LABELS[0][0])

    def current_source_format(self):
        return _label_to_key(self.get_text("source_format"), SOURCE_FORMAT_LABELS,
                             SOURCE_FORMAT_LABELS[0][0])

    def current_edit_amount(self):
        return _label_to_key(self.get_text("edit_amount"), V2V_EDIT_LABELS,
                             V2V_EDIT_LABELS[0][0])

    def rescan(self):
        self.entries, self.problems = discover_graphs(WORKFLOW_DIR)

        self.repopulate_presets()
        self.refresh_selection()


    MODE_BLURB = {
        "STILLS": "Generate one environment image at the selected preset resolution.",
        "STORYBOARD": "Create four environment references and one complete storyboard sheet.",
        "T2V": "Invent a shot from the description alone.",
        "I2V": "Animate a still into a moving shot.",
        "FLF2V": "Travel from an opening frame to a closing frame.",
        "V2V": "Restyle footage you already have, keeping its motion.",
        "ENVSWAP": "Rebuild the world around the performer; the source camera, framing and depth stay locked.",
        "SWAP": "Replace the performer in a clip using a reference.",
        "ANGLE": "Re-stage a performed line from a new camera; timing, voice and performance stay.",
        "SEGMENT": "Track a subject and cut a matte from it.",
    }

    def refresh_selection(self):
        mode = self.current_mode()
        family = self.current_family()
        prior_family = getattr(self, "_delivery_family", None)
        if family in ("LTX25", "LTX23"):
            if prior_family not in ("LTX25", "LTX23"):
                chosen = getattr(self, "_ltx_resolution", "1080P")
                self.set_attr("resolution", "CurrentIndex", list(RESOLUTIONS).index(chosen))
            self._ltx_resolution = self.current_resolution()
        elif self.current_resolution() == "4K":
            self.set_attr("resolution", "CurrentIndex", list(RESOLUTIONS).index("1080P"))
        self._delivery_family = family
        self.set_attr("prompt", "PlaceholderText",
                      "Keep the camera still in this cave; water drips from the rock..."
                      if family == "LTX25" else ("A wet limestone cave at blue hour, eye-level view, no people..."
                      if family == "JUGGERNAUT" else "Describe the scene, action and camera movement..."))
        for widget in ("seconds", "resolution", "negative"):
            self.set_attr(widget, "Enabled", mode not in ("STORYBOARD", "STILLS"))

        entry, reason = select_graph(self.entries, mode, self.current_lane(),
                                     self.get_checked("allow_cloud"), self.current_preset(),
                                     self.current_family(), show_unproven=self.show_unproven())


        self.set_attr("expand_prompt", "Enabled", bool(entry and entry.family in ("MINIMAXH3", "LTX25", "JUGGERNAUT")
                      and not getattr(self, "expander_inflight", False)))
        blurb = self.MODE_BLURB.get(mode, "")
        if entry:
            self.set_attr("graph", "Text",
                          u"%s   Â·   %s   Â·   %s" %
                          (dict(FAMILY_LABELS).get(entry.family, entry.family or "Model"),
                           blurb, entry.name.replace("_api.json", "")))
        else:
            self.set_attr("graph", "Text", "Load your ComfyUI API workflow to begin." if not self.entries else "Nothing available here. %s" % (reason or ""))
        note = self.vsr_note(entry)
        if note and note != getattr(self, "_vsr_note", None):
            self.status(note, severity="warn")
        self._vsr_note = note

        graph = None
        if entry:
            try:
                with open(entry.path, "r", encoding="utf-8-sig") as handle:
                    graph = json.load(handle)
            except Exception:
                graph = None


        pose_follow = bool(graph and is_pose_follow_graph(graph))
        self.set_attr("resolution", "Enabled", not pose_follow)
        roles = keyframe_targets(graph) if graph else {}
        self.set_attr("negativerow", "Hidden", bool(graph) and not graph_accepts_negative(graph))
        needs_two = bool(roles.get("first_frame") and roles.get("last_frame"))
        wants_source = mode in SOURCE_REQUIRED_MODES
        self.set_attr("sourcerow", "Hidden", not wants_source)
        ltx_ingredient = bool(entry and entry.family in ("LTX23", "LTX25")
                              and mode in ("T2V", "I2V", "V2V"))

        environment_reference = mode == "ENVSWAP"
        h3_v3 = bool(entry and entry.family == "MINIMAXH3" and graph and h3_v3_kind(graph))
        self.set_attr("source2row", "Hidden",
                      not (needs_two or mode in ("SWAP", "V2V", "ANGLE") or ltx_ingredient
                           or environment_reference))
        h3_environment = bool(
            mode == "ENVSWAP" and entry and entry.family == "MINIMAXH3"
        )
        ltx_world = bool(
            mode == "ENVSWAP" and entry and entry.family == "LTX25"
            and graph and any(
                isinstance(node, dict)
                and node.get("class_type") == "SecondUnitRetargetWorldProxy"
                for node in graph.values()
            )
        )
        self.set_attr("source3row", "Hidden", not (h3_environment or ltx_world or h3_v3))
        self.set_attr("source4row", "Hidden", not (h3_environment or ltx_world or h3_v3))
        self.set_attr("source5row", "Hidden", not (ltx_world or h3_v3 or pose_follow))
        self.set_attr("source6row", "Hidden", not (ltx_world or h3_v3 or pose_follow))
        self.set_attr("v2vcontrols", "Hidden", mode != "V2V")

        self.set_attr("envcontrols", "Hidden", mode != "ENVSWAP" or h3_v3)
        self.set_attr("h3controls", "Hidden", not (h3_v3 and AUTO_CARDS_ENABLED))
        self.set_attr("source3label", "Text", "CARD 1" if h3_v3 else "IDENTITY")
        self.set_attr("source5label", "Text", "CARD 2" if h3_v3 else "PROP 1")
        self.set_attr("source6label", "Text", "CARD 3" if h3_v3 else "PROP 2")
        if pose_follow:
            for widget,label in (("source3label","FRONT CARD"),("source4label","THREE-QUARTER"),("source5label","PROFILE CARD"),("source6label","BODY CARD")):
                self.set_attr(widget,"Text",label)
        if h3_v3:
            self.set_attr("source3", "PlaceholderText",
                          "identity card 1: the replacement's face, close, straight to lens" if mode == "SWAP"
                          else "identity card 1: the performer's own face, close, straight to lens"
                          + (" (or AUTO CARDS)" if AUTO_CARDS_ENABLED else ""))
            self.set_attr("source4", "PlaceholderText", "wardrobe reference (optional)")
            self.set_attr("source5", "PlaceholderText", "identity card 2: three-quarter or profile (optional)")
            self.set_attr("source6", "PlaceholderText", "identity card 3: full body (optional)")
        legacy_ltx_world = bool(
            mode == "ENVSWAP" and entry and entry.family == "LTX25" and not ltx_world
        )
        self.set_attr("relightrow", "Hidden", not legacy_ltx_world)
        self.set_attr("environment_relight", "Enabled", legacy_ltx_world)
        can_chain_detail = mode not in ("SEGMENT", "STORYBOARD", "STILLS") and not is_detail_upscale_entry(entry) and not pose_follow
        if pose_follow: self.set_attr("detail_upscale", "Checked", False)
        self.set_attr("detail_upscale", "Enabled", can_chain_detail)
        self.set_attr("sourcelabel", "Text",
                      "Opening frame" if mode in IMAGE_SOURCE_MODES else "Footage")
        self.set_attr("source2label", "Text",
                      "Closing frame" if needs_two else (
                          "World reference" if environment_reference else (
                          "World (optional)" if mode == "ANGLE" else (
                          "Ingredient" if (mode == "V2V" or ltx_ingredient) else (
                              "Reference" if mode == "SWAP" else "")))))
        if entry and entry.family == "MINIMAXH3" and mode == "I2V" and needs_two:
            self.set_attr("sourcelabel", "Text", "Identity reference")
            self.set_attr("source2label", "Text", "Scene / composite")
        self.set_attr("source2", "PlaceholderText",
                      "still of the new environment"
                      if environment_reference else (
                      "optional: a still of the place this angle is staged in"
                      if mode == "ANGLE" else (
                      "character, wardrobe, product, look, or environment still"
                      if (mode == "V2V" or ltx_ingredient) else (
                          "the replacement performer's face, close, straight to lens" if mode == "SWAP"
                          else "closing keyframe"))))


        try:
            seconds = parse_seconds(self.get_text("seconds"))
            fps = graph_fps(graph) if graph else DEFAULT_FPS
            frames = derive_frames(fps, seconds)
            snapped = max([snap_frames(frames, n.get("class_type"))
                           for n in (graph or {}).values() if isinstance(n, dict)] or [frames])
            resolution = dict(RESOLUTION_LABELS)[self.current_resolution()]
            guidance = duration_guidance(entry.family if entry else self.current_family(), seconds)
            if snapped != frames:

                self.set_attr("frames", "Text", u"%d frames Â· %.4g fps Â· %s Â· from %d"
                              % (snapped, fps, resolution, frames))
            else:
                self.set_attr("frames", "Text", u"%d frames Â· %.4g fps Â· %s"
                              % (frames, fps, resolution))
            if guidance:
                self.set_attr("frames", "Text", self.get_text("frames") + " | " + guidance)
            native_h3_size = (h3_generation_dimensions(graph)
                              if entry and entry.family == "MINIMAXH3" else None)
            if self.get_checked("detail_upscale") and can_chain_detail:
                native_size = h3_detail_intermediate_size(
                    entry.family if entry else None, True,
                    self.current_resolution(), graph)
                if native_size:
                    detail_text = "H3 native %dx%d -> LTX detail -> %s final" % (
                        native_size[0], native_size[1], self.current_resolution().lower())
                elif native_h3_size:
                    detail_text = "H3 diffusion native %dx%d -> LTX detail final" % native_h3_size
                else:
                    detail_text = "LTX detail final"
                self.set_attr("frames", "Text", self.get_text("frames") + " | " + detail_text)
            elif native_h3_size:
                self.set_attr(
                    "frames", "Text", self.get_text("frames")
                    + " | H3 diffusion native %dx%d" % native_h3_size)
        except SecondUnitError as exc:
            self.set_attr("frames", "Text", str(exc))
        if entry and entry.family in ("LTX25", "LTX23") and mode not in ("STILLS", "STORYBOARD"):
            self.set_attr("frames", "Text", self.get_text("frames") + " | 16:9 export resize / center crop; generation canvas unchanged")
        if pose_follow:
            self.set_attr("frames", "Text", "PREVIEW | Native 1536 x 864 | source pose to 2D follow to H3 | no LTX / RTX upscale")
        if mode == "STILLS":
            self.set_attr("frames", "Text", "Environment PNG at preset resolution")
        if mode == "STORYBOARD":
            self.set_attr("frames", "Text", "4 references at 1216 x 832 + 2432 x 1664 storyboard")
        if getattr(self, "build_stale", False):
            self.set_attr("graph", "Text", BUILD_STALE_TEXT)
        if self.get_checked("detail_upscale") and mode not in ("STORYBOARD", "STILLS"):
            try:
                detail_upscale_entry()
                self._detail_note = None
            except SecondUnitError as exc:
                if getattr(self, "_detail_note", None) != str(exc):
                    self._detail_note = str(exc)
                    self.status(str(exc), severity="warn")
        _rv_call(self.win, "RecalcLayout")
        return entry, reason



    def run_event_loop(self, max_passes=None, clock=None, sleep=None):
        clock = clock or time.monotonic
        sleep = sleep or time.sleep
        passes = 0
        ui, disp = self.ui, self.dispatcher
        get_event = getattr(ui, "GetEvent", None)
        dispatch = getattr(disp, "Dispatch", None)
        data = getattr(disp, "_data", None)
        if not callable(get_event) or not callable(dispatch) or not isinstance(data, dict):
            log("LOOP: not available on this build (GetEvent %s, Dispatch %s, _data %s) - using RunLoop"
                % (callable(get_event), callable(dispatch), isinstance(data, dict)))
            self._own_loop_active = False
            self.status("Live updates could not start on this Resolve build. " + self.refresh_hint(), severity="warn")
            return disp.RunLoop()
        self._own_loop_active = True
        interval = TIMER_INTERVAL_MS / 1000.0
        last_pump = 0.0
        dispatched = 0
        foreign_logged = set()
        raise_streak = 0

        watch = {"ms_max": 0.0, "ms_sum": 0.0, "count": 0, "slow_logged_at": None}
        max_gap_ms = 0.0
        last_tick_at = None
        last_dispatched = (None, None)
        alive_at = clock()

        def _timed_get_event():
            started = clock()
            got = get_event(False)
            dt = clock() - started
            watch["ms_max"] = max(watch["ms_max"], dt * 1000.0)
            watch["ms_sum"] += dt * 1000.0
            watch["count"] += 1
            if dt > 1.0:
                self._last_slow_at = clock()
                slow_streak = getattr(self, "_slow_streak", 0) + 1
                self._slow_streak = slow_streak
                if watch["slow_logged_at"] is None or clock() - watch["slow_logged_at"] >= 60:
                    watch["slow_logged_at"] = clock()
                    log("LOOP: GetEvent(False) slow %.0f ms (streak %d) - Resolve was busy; the loop keeps running"
                        % (dt * 1000.0, slow_streak))
                if slow_streak >= LOOP_DEGRADE_STREAK and not getattr(self, "_loop_degraded", None):
                    self._loop_degraded = "GetEvent(False) took %.1fs, %d times in a row" % (dt, slow_streak)
                    self.status("Resolve is busy (%d slow event checks in a row, last %.1f s). Updates continue by "
                                "themselves; they may arrive late until Resolve frees up." % (slow_streak, dt),
                                severity="warn")
            else:
                self._slow_streak = 0
            return got

        log("LOOP: own loop (GetEvent(False)+Dispatch), pump every %d ms, sleep %d ms" % (TIMER_INTERVAL_MS, int(round(OWN_LOOP_SLEEP_S * 1000))))
        try:
            while not data.get("done"):
                try:
                    ev = _timed_get_event()
                    raise_streak = 0
                except Exception as exc:
                    raise_streak += 1
                    if raise_streak >= 5:
                        log("LOOP: GetEvent(False) raised 5 times in a row (%s: %s) - Resolve is closing or the script connection is gone; leaving the loop (no RunLoop fallback)"
                            % (exc.__class__.__name__, exc))
                        return
                    if raise_streak == 1:
                        log("LOOP: GetEvent(False) raised (%s: %s) - retrying" % (exc.__class__.__name__, exc))
                    sleep(OWN_LOOP_SLEEP_S)
                    continue
                drained = 0
                while ev and not data.get("done"):
                    try:
                        dispatch(ev)
                    except KeyError as exc:
                        try:
                            window = ev["window"]
                        except Exception:
                            window = None
                        try:
                            who = ev["who"]
                        except Exception:
                            who = None
                        try:
                            what = ev["what"]
                        except Exception:
                            what = None
                        if window not in foreign_logged:
                            foreign_logged.add(window)
                            log("LOOP: Dispatch KeyError %s for window=%r who=%r what=%r - not this panel's event, dropped"
                                % (exc, window, who, what))
                    except Exception:
                        log("LOOP: handler raised:\n%s" % traceback.format_exc())
                    try:
                        last_dispatched = (ev["who"], ev["what"])
                    except Exception:
                        last_dispatched = (None, None)
                    dispatched += 1
                    drained += 1
                    if drained >= 500:
                        break
                    try:
                        ev = _timed_get_event()
                    except Exception:
                        raise_streak += 1
                        ev = None
                if data.get("done"): break
                now = clock()
                if getattr(self, "_loop_degraded", None) and now - getattr(self, "_last_slow_at", now) > 15:
                    self._loop_degraded = None
                    self._slow_streak = 0
                    log("LOOP: degraded cleared")
                if now - last_pump >= interval:
                    if last_tick_at is not None:
                        gap_ms = (now - last_tick_at) * 1000.0
                        max_gap_ms = max(max_gap_ms, gap_ms)
                        if gap_ms > 2000:
                            log("LOOP: tick gap %.0f ms (last dispatched %s.%s)" % (gap_ms, last_dispatched[0], last_dispatched[1]))
                    last_pump = now
                    last_tick_at = now
                    self.on_tick({"own_loop": True})
                if now - alive_at >= 60:
                    alive_at = now
                    log("LOOP: alive ticks=%d max_gap_ms=%.0f getevent_ms_avg=%.1f getevent_ms_max=%.1f dispatched=%d"
                        % (self._loop_ticks, max_gap_ms, (watch["ms_sum"] / watch["count"]) if watch["count"] else 0.0,
                           watch["ms_max"], dispatched))
                    max_gap_ms = 0.0
                    watch["ms_max"], watch["ms_sum"], watch["count"] = 0.0, 0.0, 0
                sleep(OWN_LOOP_SLEEP_S)
                passes += 1
                if max_passes is not None and passes >= max_passes:
                    break
        finally:
            self._own_loop_active = False
            try:
                disp.ExitCode()
            except Exception:
                pass
            log("LOOP: ended after %d events, %d ticks" % (dispatched, self._loop_ticks))

    def on_close(self, _event):
        log("PANEL CLOSE  build=%s" % build_id())

        self.stop_event.set()
        self.health_stop.set()
        self.dispatcher.ExitLoop()

    def on_selection_changed(self, _event):
        try:
            self.refresh_selection()
            self.save_panel_state()

            if self.current_mode() == "SEGMENT":
                self.set_attr("prompt", "PlaceholderText",
                              "What to track, e.g. 'person'. This is SAM 3's detection query, "
                              "not a shot description.")
            elif self.current_mode() == "V2V":
                self.set_attr("prompt", "PlaceholderText",
                              "Describe only the intended edit. Source locks, ingredient role, "
                              "and edit amount are applied as explicit controls below.")
            else:
                self.set_attr("prompt", "PlaceholderText",
                              "Describe the shot. This replaces the graph's positive prompt.")
        except Exception:
            pass

    def on_rescan(self, _event):
        self.rescan()
        note = "Found %d stamped graph(s) in %s." % (len(self.entries), WORKFLOW_DIR)
        if self.problems:
            note += "  Skipped: " + "; ".join(self.problems[:4])
        self.status(note, 0)

    def on_refresh(self, _event):
        self._delivery_retry_at = None
        idle = not self.job or not self.job.is_alive()
        if idle:

            self.probe_server_now()
        self.pump(None)
        if idle:
            if self.submission_uncertain:

                self.reconcile_uncertain_job()
            self.refresh_selection()



    def first_run_status(self, why="open", server_probed=False):
        try:
            started = time.perf_counter()
            if getattr(self, "_worker_python_version", None) is None:
                self._worker_python_version = worker_python_version()
            server_state = None
            if server_probed and getattr(self, "health_ok", None) is not None:
                server_state = (bool(self.health_ok), "")
            line = first_run_status_line(self.client, self.entries, self.problems,
                                         python_version=self._worker_python_version,
                                         server_state=server_state)
            log("first-run (%s, %.0f ms): %s" % (why, (time.perf_counter() - started) * 1000.0, line))
            return line
        except Exception:
            log("first-run readout raised:\n%s" % traceback.format_exc())
            return ""

    def on_refresh_readiness(self, event):
        seen = getattr(self, "_readiness_outcomes_seen", 0)
        self.on_refresh(event)
        try:
            if self.job and self.job.is_alive():
                return
            probed = callable(getattr(self, "probe_server_now", None))
            readiness = self.first_run_status("refresh", server_probed=probed)
            if (readiness and self.pending_delivery is None and not self.submission_uncertain
                    and getattr(self, "_outcome_writes", 0) == seen):
                self.status(u"Ready \u00b7 %d presets.   %s" % (len(self.entries), readiness), 0,
                            severity="fail" if not self.entries else (
                                "warn" if first_run_line_is_worrying(readiness) else None))
        finally:
            self._readiness_outcomes_seen = getattr(self, "_outcome_writes", 0)

    def delivery_source_path(self, message):
        try:
            for candidate in ((message or {}).get("source_path"),
                              (getattr(self.job, "params", None) or {}).get("source_path")):
                if candidate:
                    return str(candidate)
        except Exception:
            pass
        return None

    def on_browse(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.source_in_seconds = None
            self.source_exact_frames = None
            self.source_exact_fps = None
            self.set_attr("source", "Text", str(chosen))

    def on_use_timeline(self, _event):
        project = rv_current_project(self.resolve, self.injected_project)
        info = rv_timeline_source(project)

        self.set_attr("source", "Text", info["path"])

        self.source_in_seconds = info.get("in_seconds")
        self.source_exact_frames = info.get("frames")
        self.source_exact_fps = info.get("fps")
        where = "'%s'" % info["timeline"]
        if info.get("track") and info.get("over"):
            where += " (V%s, underneath '%s')" % (info["track"], info["over"])
        elif info.get("track"):
            where += " (V%s)" % info["track"]
        parts = ["%s from %s" % (info["name"], where)]

        seconds = info.get("seconds")
        if seconds:
            clamped = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
            self.set_attr("seconds", "Text", ("%.2f" % clamped).rstrip("0").rstrip("."))
            if abs(clamped - seconds) > 0.005:
                parts.append("its %.1fs was clipped to the %g-%gs this pipeline renders"
                             % (seconds, MIN_SECONDS, MAX_SECONDS))
            else:
                parts.append("%d frames at %.4g fps = %.2fs"
                             % (info["frames"], info["fps"], seconds))
        else:
            parts.append("Resolve did not report its duration, so the length is unchanged")

        log("timeline source: %r" % (info,))
        self.refresh_selection()
        self.status("Using " + ". ".join(parts) + ".", severity="ok")

    def on_load_workflow(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if not chosen:
            return
        chosen = str(chosen)
        self.status("Verifying %s against ComfyUI %s..."
                    % (os.path.basename(chosen), comfy_short_target(COMFY_URL)))
        name, summary = load_workflow_file(chosen, WORKFLOW_DIR, COMFY_URL)
        self.rescan()
        entry = next((e for e in self.entries if e.name == name), None)
        if entry is None:
            raise SecondUnitError("%s passed the verifier but the library scan did not offer it: %s"
                                  % (name, "; ".join(self.problems[:2]) or "no detail"))
        self.select_entry(entry)
        self.status("Loaded %s: %s. Selected as the preset (%s / %s)."
                    % (name, summary, dict(MODE_LABELS).get(entry.mode, entry.mode or "?"),
                       dict(FAMILY_LABELS).get(entry.family, entry.family or "any model")),
                    severity="ok")

    def select_entry(self, entry):
        for widget_id, pairs, value in (("mode", MODE_LABELS, entry.mode),
                                        ("family", FAMILY_LABELS, entry.family),
                                        ("lane", LANE_LABELS, entry.lane)):
            keys = [key for key, _label in pairs]
            if value in keys:
                self.set_attr(widget_id, "CurrentIndex", keys.index(value))
        self.repopulate_presets()
        labels = getattr(self, "_preset_labels", None) or []
        wanted = preset_label(entry)
        if wanted in labels:
            self.set_attr("preset", "CurrentIndex", labels.index(wanted))
        self.refresh_selection()

    def on_use_timeline_seq(self, _event):
        if self.pending_sequence and not self.pending_sequence.get("verified"):
            raise SecondUnitError("A PNG sequence is still rendering for '%s'. Wait for READY."
                                  % self.pending_sequence["name"])
        project = rv_current_project(self.resolve, self.injected_project)
        info = rv_timeline_source(project, allow_virtual=True)
        info["camera_reference"] = rv_camera_snapshot(project, info.get("path") or "", self.get_text("prompt") or "")
        timeline = _rv_call(project, "GetCurrentTimeline")
        width, height = rv_sequence_dimensions(timeline)
        if info.get("start") is None or info.get("end") is None:
            raise SecondUnitError("Resolve did not report where '%s' sits on the timeline, so "
                                  "there is no range to render." % info["name"])
        expected = int(info["end"]) - int(info["start"])
        root = sequence_root()
        folder = sequence_render_folder(root, info["timeline"], info["name"], info["start"], info["end"])
        where = "'%s'" % info["timeline"]
        if info.get("track") and info.get("over"):
            where += " (V%s, underneath '%s')" % (info["track"], info["over"])
        elif info.get("track"):
            where += " (V%s)" % info["track"]
        manifest = read_sequence_manifest(folder)
        if manifest and manifest.get("verified") and int(manifest.get("frames") or 0) == expected \
                and (manifest.get("width"), manifest.get("height")) == (width, height):
            ok, detail, _frames, _wav = verify_sequence_folder(folder, expected)
            if ok:
                self.adopt_sequence(folder, manifest)
                self.status("Already rendered: %s from %s, %s in %s. Using it - press TIMELINE "
                            "SEQ again after deleting the folder to force a fresh render."
                            % (info["name"], where, detail, folder), severity="ok")
                return
        if os.path.isdir(folder):

            stale = "%s.stale-%s" % (folder, time.strftime("%Y%m%d-%H%M%S"))
            try:
                os.rename(folder, stale)
            except OSError as exc:
                raise SecondUnitError("A leftover, unverified render folder is in use and cannot be cleared: %s (%s). "
                                      "Close whatever holds it and press TIMELINE SEQ again." % (folder, exc))
            threading.Thread(target=shutil.rmtree, args=(stale, True), name="su-stale-seq", daemon=True).start()
            log("sequence: leftover %s moved aside to %s and is being deleted in the background" % (folder, stale))
        if _rv_call(project, "IsRenderingInProgress"):
            raise SecondUnitError("Resolve is already rendering something. Let it finish (or stop it on the Deliver page) and press TIMELINE SEQ again.")
        previous_source = self.get_text("source") or ""
        pending = {"stage": "queue", "info": dict(info), "folder": folder, "expected": expected, "width": width,
                   "height": height, "name": slugify(os.path.splitext(str(info.get("name") or "clip"))[0]),
                   "verified": False, "queued_at": time.monotonic(), "previous_source": previous_source}
        self.pending_sequence = pending
        self._sequence_poll_at = 0.0
        self.set_attr("source", "Text", folder)
        self.source_in_seconds = None
        self.source_exact_frames = None
        self.source_exact_fps = None
        self.set_attr("source_format", "CurrentIndex", 0)
        self.state("CHECKING", detail="rendering %d frames" % expected, elapsed=0, progress=0)
        live_text = ("Progress updates here by itself as frames land" if (self.live_updates() or getattr(self, "own_loop", False))
                     else "Press REFRESH to see frames land")
        self.status("Queuing Resolve render: %s from %s: TC %s-%s (timeline frames %d-%d), %d frames at %.4g fps, %dx%d "
                    "PNG 8-bit + WAV -> %s. %s; GENERATE SHOT waits until every frame is verified."
                    % (info["name"], where, frames_to_timecode(info["start"], info.get("fps")),
                       frames_to_timecode(int(info["end"]) - 1, info.get("fps")), int(info["start"]), int(info["end"]) - 1,
                       expected, float(info.get("fps") or 0), width, height, folder, live_text),
                    progress=0, severity="ok")
        if not getattr(self, "_own_loop_active", False):
            self._queue_pending_sequence()

    def _queue_pending_sequence(self):
        pending = self.pending_sequence
        if not pending or pending.get("stage") != "queue":
            return
        pending["stage"] = "queuing"
        try:
            project = rv_current_project(self.resolve, self.injected_project)
            if project is None:
                raise SecondUnitError("Resolve has no project open; nothing was queued.")
            queued = rv_queue_sequence_render(project, pending["info"], pending["folder"], pending["width"], pending["height"])
        except Exception as exc:
            if not isinstance(exc, SecondUnitError):
                log("sequence queue raised:\n%s" % traceback.format_exc())
            text = str(exc) if isinstance(exc, SecondUnitError) else (
                "Queuing the PNG sequence raised %s. Nothing was adopted. Details: %s" % (exc.__class__.__name__, log_path()))
            self.pending_sequence = None
            self.set_attr("source", "Text", pending.get("previous_source") or "")
            self._clearing_state = True
            try:
                self.state("FAILED", detail="sequence render", text=text, severity="fail")
            finally:
                self._clearing_state = False
            return
        queued["stage"] = "render"
        queued["last_disk"] = 0
        queued["last_disk_change"] = time.monotonic()
        self.pending_sequence = queued

    def adopt_sequence(self, folder, manifest):
        self.set_attr("source", "Text", folder)
        self.source_in_seconds = None
        frames = int(manifest.get("frames") or 0) or None
        fps = float(manifest.get("fps") or 0) or None
        self.source_exact_frames = frames
        self.source_exact_fps = fps
        self.set_attr("source_format", "CurrentIndex", 0)
        if frames and fps:
            seconds = frames / fps
            clamped = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
            self.set_attr("seconds", "Text", ("%.2f" % clamped).rstrip("0").rstrip("."))
        self.refresh_selection()

    def _advance_wav_fallback(self, pending, frame_count, expected):
        info = pending.get("info") or {}
        target = os.path.join(pending["folder"], "audio.wav")
        seconds = expected / float(info.get("fps") or DEFAULT_FPS)
        fb = pending.get("wav_fallback")
        now = time.monotonic()
        if fb is None:
            path = info.get("path")
            if not _tool_path("ffmpeg") or (not path and not info.get("virtual")):
                log("sequence: WAV from Resolve missing - ffmpeg fallback FAILED")
                pending["wav_fallback"] = {"stage": "done"}
                return "finished"
            fb = pending["wav_fallback"] = {"stage": "probe", "proc": None, "started": now, "audio": False}
            if info.get("virtual"):
                pending["silent_audio"] = True
                log("sequence: Resolve did not render the compound audio - writing a silent audio.wav")
                fb["stage"] = "encode_start"
            elif os.path.isfile(path):
                fb["proc"], _exe = _start_tool(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                                "stream=index", "-of", "csv=p=0", path])
                if fb["proc"] is None:
                    fb["stage"] = "encode_start"
            else:
                fb["stage"] = "encode_start"
        if fb["stage"] == "probe":
            if fb["proc"].poll() is None:
                self.status("Frames complete (%d); Resolve wrote no WAV - checking the source for sound with ffprobe (%s)"
                            % (frame_count, mmss(now - fb["started"])), progress=96)
                return "running"
            out = (fb["proc"].communicate()[0] or b"").decode("utf-8", "replace")
            fb["audio"] = fb["proc"].returncode == 0 and bool(out.strip())
            fb["stage"] = "encode_start"
        if fb["stage"] == "encode_start":
            argv = extract_audio_wav_argv(info.get("path"), target, in_seconds=info.get("in_seconds"), seconds=seconds,
                                          audio=bool(fb["audio"]))
            fb["proc"], _exe = _start_tool(argv)
            if fb["proc"] is None:
                log("sequence: WAV from Resolve missing - ffmpeg fallback FAILED")
                fb["stage"] = "done"
                return "finished"
            fb["stage"], fb["encode_started"] = "encode", now
            self.status("Pulling the soundtrack with ffmpeg (0:00)", progress=96)
            return "running"
        if fb["stage"] == "encode":
            if fb["proc"].poll() is None:
                if now - fb["encode_started"] > 600:
                    fb["proc"].kill()
                    fb["proc"].communicate()
                    log("sequence: ffmpeg WAV fallback killed after 600 s")
                    fb["stage"] = "done"
                    return "finished"
                self.status("Pulling the soundtrack with ffmpeg (%s)" % mmss(now - fb["encode_started"]), progress=96)
                return "running"
            fb["proc"].communicate()
            made = os.path.isfile(target) and os.path.getsize(target) > 44
            log("sequence: WAV from Resolve missing - ffmpeg fallback %s" % ("wrote audio.wav" if made else "FAILED"))
            fb["stage"] = "done"
        return "finished"

    def poll_sequence_render(self):
        pending = self.pending_sequence
        if not pending or pending.get("verified"):
            return
        if pending.get("stage") == "queue":
            self._queue_pending_sequence()
            return
        if pending.get("stage") == "queuing":
            return
        now = time.monotonic()
        if now - (self._sequence_poll_at or 0.0) < 1.0:
            return
        self._sequence_poll_at = now
        project = rv_current_project(self.resolve, self.injected_project)
        if project is None:
            return
        progress = rv_sequence_status(project, pending)
        job = progress["job"]
        expected = int(pending["expected"])
        if job in ("Failed", "Cancelled", "Background Render Cancelled", "Remote Render Cancelled"):
            self.pending_sequence = None
            restore_deliver_settings(project, pending)
            self.state("FAILED", detail="sequence render", severity="fail")
            self.status("PNG sequence render %s: %s. Nothing was adopted; %d of %d frames are in %s."
                        % (job.lower(), progress["error"] or "Resolve gave no detail",
                           progress["on_disk"], expected, pending["folder"]), severity="fail")
            log("sequence: %s png=%s error=%r" % (job, pending["png_job"], progress["error"]))
            return
        if job != "Complete":
            pct = progress["percent"] or int(100.0 * min(progress["on_disk"], expected) / max(1, expected))
            self.state("CHECKING", detail="%d/%d frames" % (progress["on_disk"], expected), progress=pct)
            if progress["on_disk"] != pending.get("last_disk"):
                pending["last_disk"] = progress["on_disk"]
                pending["last_disk_change"] = time.monotonic()
            stalled = (job == "Rendering" and time.monotonic() - pending.get("last_disk_change", time.monotonic()) >= SEQ_STALL_S)
            self.status("Rendering PNG sequence '%s': %d of %d frames on disk (Resolve: %s %d%%%s%s).%s"
                        % (pending["name"], progress["on_disk"], expected, job, progress["percent"],
                           (", ETA %s" % mmss(progress["eta_ms"] / 1000.0)) if progress.get("eta_ms") else "",
                           ", WAV %s" % progress["wav_job"] if pending.get("wav_job") else "",
                           (" - no new frame for %s: Resolve pauses background renders while you edit (Preferences > System > "
                            "General > Background Tasks), or open the Deliver page to see the job."
                            % mmss(time.monotonic() - pending["last_disk_change"])) if stalled else ""),
                        progress=pct, severity=("warn" if stalled else None))
            return
        if pending.get("wav_job") and progress["wav_job"] not in ("Complete", "Failed", "Cancelled",
                                                                   "Background Render Cancelled"):
            self.status("Frames complete (%d); waiting for the WAV job (%s)..."
                        % (progress["on_disk"], progress["wav_job"]), progress=95)
            return
        info = pending.get("info") or {}
        if info.get("virtual"):

            _frames_now = [p for p in sequence_frame_files(pending["folder"]) if p.lower().endswith(".png")]
            if len(_frames_now) >= expected and not sequence_audio_file(pending["folder"]):
                if "audio_job" not in pending:
                    restore_deliver_settings(project, pending)
                    pending["audio_job"] = rv_queue_compound_audio(project, pending)
                    if pending["audio_job"]:
                        self.status("Frames complete (%d). Rendering the compound clip's audio out of Resolve..."
                                    % len(_frames_now), progress=96)
                        return
                elif pending["audio_job"]:
                    job_state = str((_rv_call(project, "GetRenderJobStatus", pending["audio_job"]) or {}).get("JobStatus") or "?")
                    if job_state not in ("Complete", "Failed", "Cancelled", "Background Render Cancelled"):
                        self.status("Frames complete (%d); Resolve is rendering the compound clip's audio (%s)..."
                                    % (len(_frames_now), job_state), progress=96)
                        return
        if not pending.get("restored"):
            restore_deliver_settings(project, pending)
            pending["restored"] = True
        if getattr(self, "_own_loop_active", False) and not pending.get("verify_painted"):
            pending["verify_painted"] = True
            self.state("CHECKING", detail="verifying %d frames" % expected, progress=97)
            self.status("Verifying %d frames + audio.wav in %s..." % (expected, pending["folder"]), progress=97)
            return
        fb = pending.get("wav_fallback")
        if fb and fb.get("stage") != "done":
            _count = len([p for p in sequence_frame_files(pending["folder"]) if p.lower().endswith(".png")])
            if self._advance_wav_fallback(pending, _count, expected) == "running":
                return
        ok, detail, frames, wav = verify_sequence_folder(pending["folder"], expected)
        if not ok and not wav and frames and len(frames) >= expected and not pending.get("wav_fallback"):
            if self._advance_wav_fallback(pending, len(frames), expected) == "running":
                return
            ok, detail, frames, wav = verify_sequence_folder(pending["folder"], expected)
        if not ok:
            self.pending_sequence = None
            self.state("FAILED", detail="sequence verification", severity="fail")
            self.status("PNG sequence for '%s' finished but did not verify: %s (%s). Nothing was adopted."
                        % (pending["name"], detail, pending["folder"]), severity="fail")
            log("sequence: verification failed: %s" % detail)
            return
        info = pending.get("info") or {}
        first, last = png_dimensions(frames[0]), png_dimensions(frames[-1])
        manifest = {
            "verified": True, "clip": info.get("name"), "source_path": info.get("path"),
            "camera_reference": info.get("camera_reference"),
            "timeline": info.get("timeline"), "track": info.get("track"), "over": info.get("over"),
            "start": info.get("start"), "end": info.get("end"), "frames": len(frames),
            "fps": info.get("fps"), "width": (first or (0, 0))[0], "height": (first or (0, 0))[1],
            "wav": wav, "first_frame": os.path.basename(frames[0]), "last_frame": os.path.basename(frames[-1]),
            "png_job": pending.get("png_job"), "wav_job": pending.get("wav_job"),
            "render_seconds": round(time.time() - float(pending.get("started") or time.time()), 1),
            "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            with open(sequence_manifest_path(pending["folder"]), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            camera_snapshot = info.get("camera_reference") or {}
            focal_source = ((camera_snapshot.get("provenance") or {}).get("fields") or {}).get("focal_length_mm") or {}
            original = focal_source.get("source") or info.get("path")
            if original:
                with open(os.path.join(pending["folder"], "second-unit-source.json"), "w", encoding="utf-8") as handle:
                    json.dump({"target": os.path.abspath(pending["folder"]), "source": original,
                               "start_frame": info.get("start"), "end_frame_exclusive": info.get("end"),
                               "camera_reference": camera_snapshot, "basis": "Resolve source capture; optics only"}, handle, indent=2)
        except OSError as exc:
            log("sequence: manifest not written: %s" % exc)
        pending["verified"] = True
        self.pending_sequence = None

        for job_id in (pending.get("png_job"), pending.get("wav_job"), pending.get("audio_job")):
            if job_id and not _rv_call(project, "DeleteRenderJob", job_id):
                log("sequence: could not remove finished job %s from the Render Queue" % job_id)
        self.adopt_sequence(pending["folder"], manifest)
        self.state("READY", detail="%d frames verified" % len(frames), progress=100)
        self.status("READY: %s - %d PNG frames %dx%d + %s verified in %s (%.0f s). Source set to "
                    "the folder as a PNG sequence; press GENERATE SHOT when you are ready."
                    % (info.get("name"), len(frames), (first or (0, 0))[0], (first or (0, 0))[1],
                       os.path.basename(wav), pending["folder"], manifest["render_seconds"]) + ("  WARNING: the compound clip's audio did not render, so this sequence is SILENT; nothing was guessed from the clips inside it." if pending.get("silent_audio") else ""),
                    progress=100, severity=("warn" if pending.get("silent_audio") else "ok"))
        log("sequence: READY %s (%d frames, %s)" % (pending["folder"], len(frames), os.path.basename(wav)))

    def on_open_sequence(self, _event):
        source = (self.get_text("source") or "").strip()
        folder = source if source and os.path.isdir(source) else sequence_root()
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder)
            except OSError as exc:
                raise SecondUnitError("Could not create %s: %s" % (folder, exc))
        opener = getattr(os, "startfile", None)
        if opener is None:
            raise SecondUnitError("Opening folders is only wired on Windows; the folder is %s" % folder)
        opener(folder)
        self.status("Opened %s" % folder)

    def on_browse_dir(self, _event):
        try:
            chosen = self.fusion.RequestDir()
        except Exception as exc:
            self.status("Could not open the folder browser: %s" % exc)
            return
        if not chosen:
            return
        chosen = str(chosen)
        self.set_attr("source", "Text", chosen)
        self.source_in_seconds = None
        self.source_exact_frames = None
        self.source_exact_fps = None
        frames = sequence_frame_files(chosen)
        if frames:
            self.status("Frame folder: %d stills, first %s. Source format is PNG sequence; set the "
                        "length, then GENERATE SHOT." % (len(frames), os.path.basename(frames[0])),
                        severity="ok")
        else:
            self.status("%s holds no still frames (png/tif/exr/dpx/jpg)." % chosen, severity="warn")
        self.refresh_selection()

    def on_browse2(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.set_attr("source2", "Text", str(chosen))

    def on_browse3(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.set_attr("source3", "Text", str(chosen))

    def on_browse4(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.set_attr("source4", "Text", str(chosen))

    def on_browse5(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.set_attr("source5", "Text", str(chosen))

    def on_browse6(self, _event):
        try:
            chosen = self.fusion.RequestFile()
        except Exception as exc:
            self.status("Could not open the file browser: %s" % exc)
            return
        if chosen:
            self.set_attr("source6", "Text", str(chosen))

    def on_cancel(self, _event):
        if self.job and self.job.is_alive():
            if hasattr(self.job, "request_stop"):
                self.job.request_stop()
            else:
                self.stop_event.set()
            self.status("Stopping the watcher... (the render on %s is NOT interrupted)"
                    % comfy_short_target(), severity="warn")
        else:
            self.status("Nothing running.")

    def camera_source_key(self):
        camera = camera_reference_module()
        source = (self.get_text("source") or "").strip()
        if not source:
            project = rv_current_project(self.resolve, self.injected_project)
            timeline = _rv_call(project, "GetCurrentTimeline") if project else None
            item = _rv_call(timeline, "GetCurrentVideoItem") if timeline else None
            source = rv_media_file_path(_rv_call(item, "GetMediaPoolItem")) if item else ""
            if timeline and not source:
                _item, media, _track = rv_clip_under_playhead(timeline, rv_timeline_fps(timeline, project))
                source = rv_media_file_path(media) if media else ""
        return camera.path_key(source)

    def capture_camera_reference(self, request):
        source = (self.get_text("source") or "").strip()
        project = rv_current_project(self.resolve, self.injected_project)
        snapshot = rv_camera_snapshot(project, source, request)
        camera = camera_reference_module()
        context = camera.prompt_context(snapshot, request)
        folder = os.path.join(LAB_CACHE, "camera-references")
        os.makedirs(folder, exist_ok=True)
        receipt = os.path.join(folder, "camera-%s.json" % uuid.uuid4().hex)
        with open(receipt, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2)
        self.camera_snapshot = snapshot
        focal = snapshot["optics"].get("focal_length_mm")
        label = ("Recorded lens %g mm (clip metadata)" % focal if focal else "Camera metadata %s" % snapshot["provenance"]["status"])
        if camera.LENS_OVERRIDE.search(request or ""): label += " | SHOT lens override retained"
        self.set_attr("camera_status", "Text", label)
        return snapshot, context, receipt

    def on_expand_prompt(self, _event):
        if getattr(self, "expander_inflight", False):
            return
        entry, reason = select_graph(self.entries, self.current_mode(), self.current_lane(),
            self.get_checked("allow_cloud"), self.current_preset(), self.current_family(),
            show_unproven=self.show_unproven())
        if not entry or entry.family not in ("MINIMAXH3", "LTX25", "JUGGERNAUT"):
            self.status(reason or "Select a Juggernaut, MiniMax H3 or LTX 2.5 workflow to expand SHOT.")
            return
        raw_request = self.get_text("prompt") or ""
        previous_context = getattr(self, "expander_camera_context", "")
        request = raw_request.replace(previous_context, "").strip() if previous_context else raw_request
        if not request.strip():
            self.status("Describe your shot in SHOT before expanding it.")
            return
        try:
            translator = h3_translator()
            if translator is None:
                raise SecondUnitError("The prompt translator is missing from this installation.")
            cfg = h3_expander_config(translator)
            with open(entry.path, "r", encoding="utf-8-sig") as handle:
                graph = json.load(handle)
        except Exception as exc:
            self.status(str(exc), severity="fail")
            return
        try:
            camera_snapshot, camera_context, camera_receipt = self.capture_camera_reference(request)
        except Exception as exc:
            camera_snapshot, camera_context, camera_receipt = {}, "", None
            self.set_attr("camera_status", "Text", "Camera metadata unavailable; SHOT remains authoritative")
        selection = (self.current_family(), self.current_mode(), self.current_preset())
        source_key = camera_snapshot.get("source_key", "")
        if request != getattr(self, "expander_last", None):
            self.expander_original = request
        self.expander_inflight = True
        self.set_attr("expand_prompt", "Enabled", False)
        self.set_attr("expand_prompt", "Text", "EXPANDING...")
        self.set_attr("expander_status", "Text", "Expanding for %s..." % dict(FAMILY_LABELS).get(entry.family, entry.family))
        opts = h3_compose_opts(graph, request, self.current_mode()) if entry.family == "MINIMAXH3" else {}
        opts["camera_context"] = camera_context
        def work():
            try:
                text, info = translator.expand_for_family(entry.family, graph, request, cfg=cfg, opts=opts)
            except Exception as exc:
                text, info = "", {"source": "error", "detail": str(exc)}
            self.outbox.put({"kind": "expanded", "prompt": text, "info": info,
                             "original_request": raw_request, "selection_key": selection, "source_key": source_key, "camera_context": camera_context})
        self.expander_thread = threading.Thread(target=work, name="second-unit-prompt-expander", daemon=True)
        self.expander_thread.start()

    def on_expanded(self, message):
        self.expander_inflight = False
        self.set_attr("expand_prompt", "Enabled", self.current_family() in ("MINIMAXH3", "LTX25", "JUGGERNAUT"))
        if message.get("selection_key") and tuple(message["selection_key"]) != (self.current_family(), self.current_mode(), self.current_preset()):
            self.set_attr("expand_prompt", "Text", "PROMPT EXPANDER")
            self.set_attr("expander_status", "Text", "Workflow changed while expanding. Your SHOT was kept; expand again for this model.")
            return
        self.set_attr("expand_prompt", "Text", "PROMPT EXPANDER")
        if "original_request" in message and self.get_text("prompt") != message["original_request"]:
            self.set_attr("expander_status", "Text", "SHOT changed while expanding. Your newer text was kept; expand again when ready.")
            return
        if "source_key" in message and message["source_key"] != self.camera_source_key():
            self.set_attr("expander_status", "Text", "Reference source changed while expanding. Your SHOT was kept.")
            return
        text = message.get("prompt") or ""
        info = message.get("info") or {}
        issues = info.get("issues") or []
        if not text:
            self.set_attr("expander_status", "Text", "expander returned nothing: %s" % info.get("detail", ""))
            self.status("PROMPT EXPANDER returned nothing: %s" % info.get("detail", ""), severity="fail")
            return
        passthrough = info.get("source") == "passthrough"
        if not passthrough:
            self.set_attr("prompt", "PlainText", text)
            self.expander_last = text
            self.expander_camera_context = message.get("camera_context") or ""
        self.set_attr("revert_prompt", "Enabled", bool(getattr(self, "expander_original", None)))
        if info.get("source") == "llm":
            source = "LLM: %s" % info.get("detail", "")
        elif passthrough:
            source = "unchanged: %s" % info.get("detail", "")
        elif info.get("fallback"):
            source = "TEMPLATE (fallback): %s" % info.get("detail", "")
        else:
            source = "guide template: %s" % info.get("detail", "")
        held = info.get("held_back") or []
        held_text = (" | held back: " + "; ".join("'%s' (%s)" % (s[:50], why) for s, why in held))[:220] if held else ""
        verdict = "passed prompt text checks; review scene details" if not issues else ("check: " + "; ".join(issues))[:220]
        self.set_attr("expander_status", "Text", "READY: %s | %s%s" % (source, verdict, held_text))
        if info.get("attempts"):
            log("expander attempts: %s" % " | ".join(info["attempts"]))
        self.status("PROMPT EXPANDER wrote %d words into SHOT (%s). Read it, edit it, then GENERATE SHOT submits it verbatim."
                    % (len(text.split()), source), severity=("warn" if (issues or held or info.get("fallback")) else None))

    def on_revert_prompt(self, _event):
        original = getattr(self, "expander_original", None)
        if not original:
            self.set_attr("expander_status", "Text", "REVERT: nothing to restore - SHOT has not been expanded in this panel session.")
            return
        self.set_attr("prompt", "PlainText", original)
        self.expander_last = None
        self.expander_presses = 0
        self.set_attr("revert_prompt", "Enabled", False)
        self.set_attr("expander_status", "Text", "REVERTED: SHOT holds your original text again.")
        self.status("PROMPT EXPANDER: SHOT restored to the text you typed (%d words)." % len(original.split()))

    def on_generate(self, _event):
        if not self.check_build_on_disk(force=True):
            self.status("REFUSED: " + BUILD_STALE_TEXT, 0, severity="fail")
            return
        if self.submission_uncertain:
            job_dir = getattr(self.job, "job_dir", "the panel worker cache")
            self.status(
                "REFUSED: the previous external worker lost certainty after a prompt was "
                "submitted. Generate remains locked across panel/Resolve reopen. Inspect "
                "ComfyUI and %s. Run: %s. This panel will not risk queueing that shot twice."
                % (job_dir, panel_job_recovery_command(job_dir)),
                severity="fail")
            return
        if self.pending_sequence and not self.pending_sequence.get("verified"):

            pending = self.pending_sequence
            on_disk = len([p for p in sequence_frame_files(pending["folder"])
                           if p.lower().endswith(".png")])
            self.status("REFUSED: the PNG sequence for '%s' is still rendering (%d of %d frames "
                        "on disk). It becomes READY on its own; then press GENERATE SHOT."
                        % (pending["name"], on_disk, pending["expected"]), severity="warn")
            return

        self._clearing_state = True
        try:
            self.state("CHECKING", detail="", elapsed=0)
        finally:
            self._clearing_state = False
        if self.job and self.job.is_alive():
            self.status("A job is already running. Stop watching it first.")
            return
        if not self.probe_server_now():

            self.status(
                "ComfyUI at %s is not answering right now. Trying anyway - the render will "
                "refuse within seconds if it is really down." % comfy_short_target(COMFY_URL),
                severity="warn")
        try:
            self.rescan()
            entry, reason = select_graph(
                self.entries, self.current_mode(), self.current_lane(),
                self.get_checked("allow_cloud"), self.current_preset(), self.current_family(), show_unproven=self.show_unproven()
            )
            if not entry:
                detail = "  Skipped files: " + "; ".join(self.problems[:4]) if self.problems else ""
                self.status("REFUSED: " + (reason or "no graph") + detail, 0)
                return
            note = self.vsr_note(entry)
            if note:
                self.status("REFUSED: " + note, 0)
                return
            mode = self.current_mode()
            source_path = (self.get_text("source") or "").strip()
            if mode in SOURCE_REQUIRED_MODES and not source_path:
                self.status("REFUSED: %s needs a source file. Pick one with Browse..." % mode, 0)
                return
            source_path_last = (self.get_text("source2") or "").strip()
            if mode == "ENVSWAP" and not source_path_last:
                self.status(
                    "REFUSED: Environment Swap needs a target-set reference still. "
                    "Choose one in Set reference.", 0)
                return
            identity_path = (self.get_text("source3") or "").strip()
            wardrobe_path = (self.get_text("source4") or "").strip()
            prop1_path = (self.get_text("source5") or "").strip()
            prop2_path = (self.get_text("source6") or "").strip()
            if mode == "ENVSWAP" and entry.family in ("MINIMAXH3", "LTX25"):
                if not identity_path:
                    self.status(
                        "REFUSED: World Generation needs a separate actor identity reference.", 0)
                    return
                if not wardrobe_path:
                    self.status(
                        "REFUSED: World Generation needs a complete wardrobe reference.", 0)
                    return
            if entry.stamp.get("pipeline") == "h3_pose_follow" and not (prop1_path and prop2_path):
                self.status("REFUSED: Pose Follow needs front, three-quarter, profile and body cards.", 0)
                return
            if mode == "ENVSWAP" and entry.family == "LTX25":
                if not prop1_path or not prop2_path:
                    self.status(
                        "REFUSED: LTX 2.5 World Generation needs Picture 4 and Picture 5 "
                        "prop references. Use the same prop sheet twice when both props share one image.", 0)
                    return
            if mode in ("T2V", "STORYBOARD", "STILLS"):
                source_path = ""
            requested_seconds = 0 if mode in ("STORYBOARD", "STILLS") else parse_seconds(self.get_text("seconds"))
            exact_frames = getattr(self, "source_exact_frames", None)
            exact_fps = getattr(self, "source_exact_fps", None)

            if exact_frames and exact_fps:
                timeline_seconds = float(exact_frames) / float(exact_fps)
                if abs(float(requested_seconds) - timeline_seconds) > 0.011:
                    exact_frames = None
                    exact_fps = None
            negative_text = self.get_text("negative") or ""
            negative_note = ""
            if negative_text.strip():
                try:
                    with open(entry.path, "r", encoding="utf-8-sig") as _handle:
                        _accepts = graph_accepts_negative(json.load(_handle))
                except Exception:
                    _accepts = True
                if not _accepts:
                    self.set_attr("negative", "Text", "")
                    negative_text = ""
                    negative_note = ("  Note: the AVOID text was cleared - this preset runs at cfg 1 with its negative "
                                     "zeroed out, so every word is positive conditioning. Say what you want in SHOT.")
                    log("negative cleared for %s (cfg-1 zeroed negative)" % entry.name)
            request = self.get_text("prompt") or ""
            previous_context = getattr(self, "expander_camera_context", "")
            if previous_context: request = request.replace(previous_context, "").strip()
            snapshot, camera_context, camera_receipt = self.capture_camera_reference(request)
            generation_prompt = camera_reference_module().add_context(request, camera_context)
            params = {
                "entry": entry,
                "mode": mode,
                "prompt": generation_prompt,
                "camera_reference": snapshot,
                "camera_reference_receipt": camera_receipt,
                "negative": negative_text,
                "seconds": requested_seconds,
                "seed": parse_seed(self.get_text("seed")),
                "source_path": source_path,
                "source_path_last": source_path_last,
                "identity_path": identity_path,
                "wardrobe_path": wardrobe_path,
                "prop1_path": prop1_path,
                "prop2_path": prop2_path,
                "source_in_seconds": getattr(self, "source_in_seconds", None),
                "source_format": self.current_source_format(),
                "exact_frames": exact_frames,
                "exact_fps": exact_fps,
                "resolution": self.current_resolution(),
                "v2v_retention": self.current_v2v_retention(),
                "ingredient_role": self.current_ingredient_role(),
                "edit_amount": self.current_edit_amount(),
                "subject_query": self.get_text("subject_query"),
                "auto_cards": self.get_checked("auto_cards"),
                "environment_relight": (
                    mode == "ENVSWAP" and entry.family == "LTX25"
                    and self.get_checked("environment_relight")
                ),
                "allow_cloud": self.get_checked("allow_cloud"),
                "detail_upscale": (self.get_checked("detail_upscale")
                                   and mode not in ("SEGMENT", "STORYBOARD", "STILLS")
                                   and not is_detail_upscale_entry(entry)),
            }
        except SecondUnitError as exc:
            self.status("REFUSED: %s" % exc, 0)
            return

        try:
            self.stop_event = threading.Event()

            self.ensure_second_unit_bin()
            self.timeline_placement = (None if mode in ("STORYBOARD", "STILLS") else
                                      rv_capture_placement(rv_current_project(self.resolve, self.injected_project)))
            self.job = ExternalGenerateJob(
                find_worker_python(), _self_path(), self.client, params, self.outbox,
                cache_root=getattr(self, "job_cache_root", LAB_CACHE),
                popen_factory=getattr(self, "job_popen_factory", None))
            self.set_attr("generate", "Enabled", False)
            self.status("Starting %s / %s / %s using %s ..." %
                        (dict(FAMILY_LABELS).get(self.current_family(), self.current_family()),
                         params["mode"], self.current_lane(), entry.name) + negative_note, 1)
            self.last_worker_word = time.monotonic()
            self.job.start()
        except Exception as exc:
            log("external worker launch failed:\n%s" % traceback.format_exc())
            self.job = None
            self.set_attr("generate", "Enabled", True)
            self._clearing_state = True
            try:
                self.state(
                    "FAILED", text="Could not start the Resolve-safe worker: %s. Nothing "
                    "was queued. Details: %s" % (exc, log_path()), progress=0,
                    severity="fail")
            finally:
                self._clearing_state = False
            return
        if not self.live_updates():

            self.state("LIVE UPDATES OFF", detail="external worker is independent", text="Started in an external worker. It renders without clicks. " + self.refresh_hint(), progress=1, severity="warn")



    def pump(self, _event=None):
        if getattr(self, "_in_pump", False):
            return
        self._in_pump = True
        try:
            return self._pump_body(_event)
        finally:
            self._in_pump = False

    def _pump_body(self, _event=None):

        if isinstance(_event, dict) and _event.get("own_loop"):
            self._loop_ticks += 1
        elif _event is not None:
            self._timer_ticks += 1
            if self._timer_ticks == 1:
                since = ((time.monotonic() - self._timer_started_at) * 1000.0
                         if self._timer_started_at else -1)
                log("TIMER: first tick, %.0fms after Start() - progress updates automatically"
                    % since)
        else:
            self.note_dead_timer()
        self.check_build_on_disk()
        try:
            self.advance_landing()
        except Exception:
            log("landing step raised:\n%s" % traceback.format_exc())
        try:
            self.poll_sequence_render()
        except Exception:
            log("sequence poll raised:\n%s" % traceback.format_exc())

        if self.job and hasattr(self.job, "drain_to"):
            self.job.drain_to(self.outbox)
        if self.pending_delivery is not None:

            now = time.monotonic()
            last_try = getattr(self, "_delivery_retry_at", None)
            if last_try is None or now - last_try >= DELIVERY_RETRY_S:
                self._delivery_retry_at = now
                pending = self.pending_delivery
                if getattr(self, "_own_loop_active", False):
                    self.pending_delivery = None
                    self.begin_landing(pending)
                elif self.finish(pending):
                    self.pending_delivery = None
                    self._delivery_retry_at = None
                    if self.job and hasattr(self.job, "mark_consumed"):
                        self.job.mark_consumed("done")
        drained = 0
        last_status = None
        terminal_seen = False
        while True:
            try:
                message = self.outbox.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self.last_worker_word = time.monotonic()
            kind = message.get("kind")
            if kind == "status":
                if last_status is not None:
                    log("status (coalesced): %s" % (last_status.get("text") or last_status.get("state")))
                last_status = message
            elif kind == "health":
                self.on_health(message)
            elif kind == "expanded":
                self.on_expanded(message)
            elif kind == "reconcile":
                self.apply_reconcile(message.get("evidence"), quiet_repeat=True)
            elif kind == "error":
                terminal_seen = True
                self._op_status = None
                text = message.get("text", "Unknown error.")
                if text.startswith("REFUSED"):
                    key, severity = "REFUSED", "fail"
                elif text.startswith("Stopped watching"):
                    key, severity = "STOPPED", "warn"
                else:
                    key, severity = "FAILED", "fail"
                self._clearing_state = True
                try:
                    self.state(key, text=text, progress=0, severity=severity)
                finally:
                    self._clearing_state = False
                if message.get("uncertain"):
                    self.submission_uncertain = True
                    self.set_attr("generate", "Enabled", False)
                else:
                    self.set_attr("generate", "Enabled", True)
                if self.job and hasattr(self.job, "mark_consumed"):
                    self.job.mark_consumed("error", uncertain=bool(message.get("uncertain")))
            elif kind == "done":
                terminal_seen = True
                self._op_status = None
                if getattr(self, "_own_loop_active", False):
                    self.begin_landing(message)
                elif self.finish(message):
                    if self.job and hasattr(self.job, "mark_consumed"):
                        self.job.mark_consumed("done")
                else:
                    self.pending_delivery = dict(message)
                    self.set_attr("generate", "Enabled", False)
        if last_status is not None and not terminal_seen:
            self._op_status = last_status
            self._op_status_at = time.monotonic()
            self.state(last_status.get("state") or getattr(self, "job_state", "READY"),
                       detail=last_status.get("detail"),
                       elapsed=last_status.get("elapsed"),
                       eta=last_status.get("eta"),
                       text=last_status.get("text", ""),
                       progress=last_status.get("progress"))
        self.notice_silence(drained)
        if self.submission_uncertain and not (self.job and self.job.is_alive()):
            now = time.monotonic()
            thread = getattr(self, "_reconcile_thread", None)
            if now - getattr(self, "_reconcile_at", 0.0) >= RECONCILE_TICK_S and not (thread and thread.is_alive()):
                self._reconcile_at = now
                job, outbox = self.job, self.outbox
                self._reconcile_thread = threading.Thread(
                    target=lambda: outbox.put({"kind": "reconcile",
                                               "evidence": self.reconcile_evidence(job, http_timeout=RECONCILE_HTTP_TIMEOUT)}),
                    name="su-reconcile", daemon=True)
                self._reconcile_thread.start()

    def notice_silence(self, drained):
        try:
            if drained or not (self.job and self.job.is_alive()):
                return
            since = time.monotonic() - (getattr(self, "last_worker_word", None) or time.monotonic())
            if since < WORKER_SILENCE_S:
                return
            self.set_attr("jobtime", "Text", mmss(since))
            self.set_attr("jobdetail", "Text",
                          "no word from the render for %s" % mmss(since))
            log("watchdog: the worker has been silent for %.0fs" % since)
        except Exception:
            log("watchdog raised:\n%s" % traceback.format_exc())

    def probe_server_now(self, budget_seconds=1.5):
        started = time.monotonic()
        message = {"kind": "health", "ok": False, "error": "unreachable"}
        client = getattr(self, "client", None)
        base = str(getattr(client, "base", None) or COMFY_URL).rstrip("/")
        if client is not None and not isinstance(client, ComfyClient):

            try:
                stats = client.ping() or {}
                message = {"kind": "health", "ok": True,
                           "version": ((stats.get("system") or {}).get("comfyui_version")) or ""}
            except Exception as exc:
                message = {"kind": "health", "ok": False, "error": "%s: %s" % (exc.__class__.__name__, exc)}
        else:
            try:
                parsed = urllib.parse.urlparse(base)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                sock = socket.create_connection((host, port), timeout=min(1.0, budget_seconds))
                sock.close()
                remaining = max(0.3, budget_seconds - (time.monotonic() - started))
                try:
                    request = urllib.request.Request(base + "/system_stats", headers=comfy_auth_headers())
                    with _OPENER.open(request, timeout=remaining) as response:
                        stats = json.loads(response.read().decode("utf-8", "replace") or "{}")
                    version = ((stats.get("system") or {}).get("comfyui_version")) or ""
                    message = {"kind": "health", "ok": True, "version": version}
                except Exception as exc:

                    message = {"kind": "health", "ok": True, "error": exc.__class__.__name__}
            except Exception as exc:
                message = {"kind": "health", "ok": False, "error": "%s: %s" % (exc.__class__.__name__, exc)}
        try:
            self.on_health(message)
        except Exception:
            log("probe_server_now: on_health raised:\n%s" % traceback.format_exc())
        log("probe_server_now: %r in %.0f ms" % (message.get("ok"), (time.monotonic() - started) * 1000))
        return bool(message.get("ok"))

    def ensure_second_unit_bin(self):
        try:
            project = rv_current_project(self.resolve, self.injected_project)
            if project is None:
                log("bin: no project open yet; '%s' will be created at import" % BIN_NAME)
                return False
            _media_pool, folder = rv_get_or_create_bin(project, BIN_NAME)
            created = getattr(self, "_bin_announced", None) != BIN_NAME
            self._bin_announced = BIN_NAME
            if created:
                log("bin '%s' ready under Master (%s)" % (BIN_NAME, folder.GetName() if hasattr(folder, "GetName") else "folder"))
            return True
        except Exception as exc:
            log("bin '%s' could not be prepared at Generate: %s" % (BIN_NAME, exc))
            return False

    def reconcile_evidence(self, job, http_timeout=None):
        if job is None or not getattr(job, "job_dir", None):
            return None
        again = (("Checking again by itself every %d s." % int(RECONCILE_TICK_S)) if self.live_updates()
                 else "Wait for it, then press REFRESH.")
        try:
            def _read(name):
                try:
                    with open(os.path.join(job.job_dir, name), "r", encoding="utf-8-sig") as handle:
                        return json.load(handle) or {}
                except Exception:
                    return {}
            intent = _read("submit-intent.json")
            exit_record = _read("exit.json")
            if intent.get("state") == "rejected":
                return {"proven": True, "severity": "warn", "text": "",
                        "verdict": "ComfyUI rejected the prompt with an HTTP error (durable record); nothing was queued."}
            prompt_ids = [pid for pid in (getattr(job, "prompt_id", None), intent.get("prompt_id"),
                                          exit_record.get("prompt_id")) if pid]
            prompt_ids = list(dict.fromkeys(str(pid) for pid in prompt_ids))
            if not prompt_ids:
                return {"proven": False, "verdict": "", "severity": "warn",
                        "text": "Still uncertain: the submit intent carries no prompt id, so the POST-response gap cannot be "
                                "reconciled from here. Run: %s" % panel_job_recovery_command(job.job_dir)}
            client = job.client if getattr(job, "client", None) else ComfyClient(COMFY_URL)
            states = {}
            for pid in prompt_ids:
                position, _index = client.queue_position(pid, timeout=http_timeout)
                if position == "absent":
                    position = "history" if client.history(pid, timeout=http_timeout) else "absent"
                states[pid] = position
            if any(state in ("running", "pending") for state in states.values()):
                return {"proven": False, "verdict": "", "severity": "warn",
                        "text": "Still uncertain: prompt %s is %s on %s. %s" % (
                            prompt_ids[0][:8], ", ".join(sorted(set(states.values()))), comfy_short_target(client.base), again)}
            if all(state == "history" for state in states.values()):
                return {"proven": True, "severity": "warn", "text": "",
                        "verdict": ("ComfyUI holds terminal history for prompt %s; the render finished. "
                                    "Its outputs are in ComfyUI/output (durable record: %s)." % (prompt_ids[0][:8], job.job_dir))}
            return {"proven": False, "verdict": "", "severity": "warn",
                    "text": "Still uncertain: prompt %s is in neither the queue nor the history of %s and there is no HTTP "
                            "rejection on record. Run: %s" % (prompt_ids[0][:8], comfy_short_target(client.base),
                                                              panel_job_recovery_command(job.job_dir))}
        except (ComfyTimeout, ComfyUnreachable) as exc:
            log("reconcile: ComfyUI did not answer in time (%s); retrying on the next tick" % exc.__class__.__name__)
            return {"proven": False, "verdict": "", "severity": "warn",
                    "text": "Still uncertain: ComfyUI at %s is busy and did not answer in time. Generate stays locked. %s"
                            % (comfy_short_target(COMFY_URL), again)}
        except Exception:
            log("reconcile_evidence raised:\n%s" % traceback.format_exc())
            return {"proven": False, "verdict": "", "severity": "warn",
                    "text": "Could not reconcile the uncertain job (see log). Generate stays locked."}

    def _reconcile_status(self, text):
        if text != getattr(self, "_reconcile_last", None):
            self._reconcile_last = text
            self.status(text, severity="warn")

    def apply_reconcile(self, ev, quiet_repeat=False):
        if not ev or not self.submission_uncertain:
            return False
        if not ev.get("proven"):
            if quiet_repeat:
                self._reconcile_status(ev.get("text") or "Still uncertain. Generate stays locked.")
            else:
                self.status(ev.get("text") or "Still uncertain. Generate stays locked.", severity=ev.get("severity") or "warn")
            return False
        job = self.job
        try:
            if job is not None and hasattr(job, "mark_consumed"):
                job.mark_consumed("reconciled", uncertain=False)
        except Exception as exc:
            log("reconcile: mark_consumed failed: %s" % exc)
        self.submission_uncertain = False
        self.set_attr("generate", "Enabled", not getattr(self, "build_stale", False))
        self._clearing_state = True
        try:
            self.state("READY", text="UNLOCKED: " + ev["verdict"], progress=0, severity="warn")
        finally:
            self._clearing_state = False
        log("reconcile: unlocked - %s" % ev["verdict"])
        return True

    def reconcile_uncertain_job(self, http_timeout=None):
        return self.apply_reconcile(self.reconcile_evidence(self.job, http_timeout=http_timeout))

    def on_health(self, message):
        ok = bool(message.get("ok"))
        error = message.get("error") or None
        text, sheet = server_chip(COMFY_URL, ok, message.get("version"), error)
        self.set_attr("server", "Text", text)
        self.set_attr("server", "StyleSheet", sheet)
        previous = getattr(self, "health_ok", None)
        if previous == ok:
            return
        self.health_ok = ok
        log("health: %s -> %s" % (previous, text))
        if not ok:

            if getattr(self, "job_state", "READY") in ("READY", "CHECKING", "LIVE UPDATES OFF"):
                self.status("ComfyUI is not answering on %s. Nothing has been queued. %s" % (comfy_target_label(), "This line updates by itself when it answers." if self.live_updates() else "Start it, then press REFRESH."), severity="warn")
        elif comfy_is_production(COMFY_URL):
            self.status("TARGET IS PRODUCTION: %s. Every Generate queues onto the instance "
                        "someone may be working on." % comfy_target_label(), severity="warn")
        elif previous is False:
            self.status("ComfyUI is back on %s." % comfy_target_label(), severity="ok")

    def write_timeline_receipt(self, receipt, paths):
        try:
            out = os.path.join(os.path.dirname(paths[0]) if paths else os.getcwd(),
                               "second-unit-timeline-receipt.json")
            payload = dict(receipt)
            payload["files"] = list(paths)
            payload["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            log("timeline receipt -> %s" % out)
        except Exception as exc:
            log("could not write timeline receipt: %s" % exc)

    def _landing_failed(self, exc, paths):
        self._clearing_state = True
        try:
            self.state("FAILED",
                       text="Rendered OK but the import failed: %s   File(s): %s"
                            % (exc, "; ".join(paths)),
                       progress=100, severity="fail")
        finally:
            self._clearing_state = False

    def _landing_raised(self, exc, paths):

        log("import raised:\n%s" % traceback.format_exc())
        self._clearing_state = True
        try:
            self.state("FAILED",
                       text="Rendered OK but the import raised %s. The file is on disk: %s"
                            "   Details: %s" % (exc.__class__.__name__, "; ".join(paths), log_path()),
                       progress=100, severity="fail")
        finally:
            self._clearing_state = False

    def _landed(self, receipt, paths, diagnostic_paths):
        self.last_receipt = receipt
        where = receipt.get("timeline") or "the timeline"
        placed = ", ".join(
            (a.get("name") or "clip") + (
                " @%d" % a["start"] if a.get("start") is not None else "")
            for a in receipt.get("appended", [])) or "clip"
        note = ("  " + "  ".join(receipt["warnings"])) if receipt.get("warnings") else ""
        if getattr(self, "gate_warnings", None):
            note += "  " + "  ".join(self.gate_warnings)
        self.state("ON TIMELINE",
                   detail="%s - %s" % (where, placed),
                   text="ON TIMELINE '%s': %s%s" % (where, placed, note),
                   progress=100, severity="ok")
        receipt["delivered_files"] = list(paths)
        receipt["diagnostic_files"] = list(diagnostic_paths)
        self.write_timeline_receipt(receipt, paths)

    def _landed_in_bin(self, names, exc):
        self._clearing_state = True
        try:
            self.state("IN BIN",
                       text="Imported into '%s' (%s) but NOT placed on a timeline: %s"
                            % (BIN_NAME, ", ".join(names), exc),
                       progress=100, severity="warn")
        finally:
            self._clearing_state = False

    def finish_environment_storyboard(self, message):
        paths = list(message.get("paths") or [])
        succeeded = False
        try:
            expected = 1 if message.get("environment_still") else 5
            if len(paths) != expected or len(set(paths)) != expected:
                raise SecondUnitError("Expected %d environment PNG files." % expected)
            for path in paths:
                with open(path, "rb") as handle:
                    if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                        raise SecondUnitError("Invalid reference PNG: %s" % path)
            project = rv_current_project(self.resolve, self.injected_project)
            if project is None:
                raise SecondUnitError("Open a Resolve project to import the references.")
            names, items = rv_import_clips(self.resolve, project, "Second Unit Environments", paths)
            if len(items) != len(paths):
                raise SecondUnitError("Resolve did not import all environment images; retry the import.")
            self._clearing_state = True
            try:
                self.state("REFERENCES READY", text=("Environment still is in Second Unit Environments. Files: %s" if message.get("environment_still") else "Four individual references and the full storyboard are in Second Unit Environments. Files: %s") % os.path.dirname(paths[0]), progress=100)
            finally:
                self._clearing_state = False
            succeeded = True
        except Exception as exc:
            self._landing_raised(exc, paths)
        self.set_attr("generate", "Enabled", succeeded)
        return succeeded

    def finish(self, message):
        if message.get("storyboard"):
            return self.finish_environment_storyboard(message)
        paths = message.get("paths") or []
        import_succeeded = False
        self.gate_warnings = list(message.get("warnings") or [])
        self._clearing_state = True
        try:
            self.state("IMPORTING",
                       text="Rendered %d frames in %s. Importing into '%s'..."
                            % (message.get("frames", 0),
                               mmss(message.get("render_seconds", 0)), BIN_NAME),
                       progress=97)
        finally:
            self._clearing_state = False
        try:
            project = rv_current_project(self.resolve, self.injected_project)
            if project is None:
                raise SecondUnitError("No project is open in Resolve, so there is nowhere to import to.")

            diagnostic_paths = list(paths)
            paths = deliver_outputs(
                paths, delivery_dir_for(self.delivery_source_path(message), self.recovery_cache_root))
            log("delivery: importing %s (diagnostic originals: %s)"
                % ("; ".join(paths), "; ".join(diagnostic_paths)))
            names, items = rv_import_clips(self.resolve, project, BIN_NAME, paths)
            import_succeeded = True
            rv_keyword_items(items, CLIP_KEYWORD)
            self.status("Imported. Placing on the timeline...", 99)


            media_pool = project.GetMediaPool()
            try:
                receipt = rv_append_to_timeline(project, media_pool, items, paths, getattr(self, "timeline_placement", None))
                self._landed(receipt, paths, diagnostic_paths)
            except SecondUnitError as exc:
                self._landed_in_bin(names, exc)
        except SecondUnitError as exc:
            self._landing_failed(exc, paths)
        except Exception as exc:
            self._landing_raised(exc, paths)
        finally:
            self.set_attr("generate", "Enabled", import_succeeded)
        return import_succeeded

    def begin_landing(self, message):
        if message.get("storyboard"):
            if self.finish_environment_storyboard(message):
                self.pending_delivery = None
                if self.job:
                    self.job.mark_consumed("done")
            else:
                self.pending_delivery = dict(message)
            return
        if getattr(self, "landing", None):
            log("landing: already landing; %s waits for the next retry" % (message.get("prompt_id") or "done record"))
            self.pending_delivery = dict(message)
            return
        self.gate_warnings = list(message.get("warnings") or [])
        self.landing = {"message": dict(message), "step": "copy", "started": time.monotonic(),
                        "paths": list(message.get("paths") or []), "diagnostic": list(message.get("paths") or []),
                        "result": None, "error": None, "thread": None, "target_dir": None,
                        "project": None, "names": None, "items": None}
        self.set_attr("generate", "Enabled", False)
        self._clearing_state = True
        try:
            self.state("DELIVERING", text="Rendered %d frames in %s. Copying the render out of ComfyUI/output..."
                       % (message.get("frames", 0), mmss(message.get("render_seconds", 0))), progress=96)
        finally:
            self._clearing_state = False

    def _landing_retry(self, msg):
        self.pending_delivery = dict(msg)
        self.landing = None
        self.set_attr("generate", "Enabled", False)

    def advance_landing(self):
        L = getattr(self, "landing", None)
        if not L:
            return
        msg = L["message"]
        if L["step"] == "copy":
            if L["thread"] is None:
                L["target_dir"] = delivery_dir_for(self.delivery_source_path(msg), self.recovery_cache_root)
                def _copy():
                    try:
                        L["result"] = deliver_outputs(L["diagnostic"], L["target_dir"])
                    except Exception as exc:
                        L["error"] = exc
                L["thread"] = threading.Thread(target=_copy, name="su-delivery-copy", daemon=True)
                L["thread"].start()
                return
            if L["thread"].is_alive():
                done = 0
                for src in L["diagnostic"]:
                    target = os.path.join(L["target_dir"], os.path.basename(src))
                    for candidate in (target, target + ".part"):
                        if os.path.isfile(candidate):
                            done += os.path.getsize(candidate)
                total = sum(os.path.getsize(p) for p in L["diagnostic"] if os.path.isfile(p)) or 1
                self.state("DELIVERING", elapsed=time.monotonic() - L["started"],
                           text="Copying the render to %s: %d of %d MB" % (L["target_dir"], min(done, total) // 1048576, total // 1048576),
                           progress=96)
                return
            if L["error"] is not None:
                if isinstance(L["error"], SecondUnitError):
                    self._landing_failed(L["error"], L["diagnostic"])
                else:
                    self._landing_raised(L["error"], L["diagnostic"])
                return self._landing_retry(msg)
            L["paths"], L["step"] = list(L["result"] or []), "import"
            log("delivery: importing %s (diagnostic originals: %s)" % ("; ".join(L["paths"]), "; ".join(L["diagnostic"])))
            self.state("IMPORTING", text="Importing into '%s'..." % BIN_NAME, progress=97)
            return
        if L["step"] == "import":
            try:
                project = rv_current_project(self.resolve, self.injected_project)
                if project is None:
                    raise SecondUnitError("No project is open in Resolve, so there is nowhere to import to.")
                names, items = rv_import_clips(self.resolve, project, BIN_NAME, L["paths"])
                rv_keyword_items(items, CLIP_KEYWORD)
            except SecondUnitError as exc:
                self._landing_failed(exc, L["paths"])
                return self._landing_retry(msg)
            except Exception as exc:
                self._landing_raised(exc, L["paths"])
                return self._landing_retry(msg)
            L.update(project=project, names=names, items=items, step="append")
            self.set_attr("generate", "Enabled", not getattr(self, "build_stale", False))
            self.status("Imported into '%s'. Placing on the timeline..." % BIN_NAME, 99)
            return
        if L["step"] == "append":
            try:
                receipt = rv_append_to_timeline(L["project"], L["project"].GetMediaPool(), L["items"], L["paths"], getattr(self, "timeline_placement", None))
                self._landed(receipt, L["paths"], L["diagnostic"])
            except SecondUnitError as exc:
                self._landed_in_bin(L["names"], exc)
            except Exception as exc:
                log("timeline append raised:\n%s" % traceback.format_exc())
                self._landed_in_bin(L["names"], exc)
            if self.job and hasattr(self.job, "mark_consumed"):
                self.job.mark_consumed("done")
            self._delivery_retry_at = None
            self.set_attr("generate", "Enabled", not getattr(self, "build_stale", False))
            self.landing = None



    def run(self):
        t0 = time.perf_counter()
        log("=" * 72)
        log("PANEL START  build=%s" % build_id())
        log("  log=%s" % log_path())
        try:
            log("  resolve=%s  page=%s" % (self.resolve.GetVersionString(), self.resolve.GetCurrentPage()))
        except Exception as exc:
            log("  resolve version unavailable: %s" % exc)
        self.build()
        t_build = time.perf_counter()


        self.status("Second Unit is open. Reading the preset library...", 0)


        self.health = HealthProbe(COMFY_URL, self.outbox, self.health_stop,
                                  lambda: bool(self.job and self.job.is_alive()))
        self.health.start()

        self.probe_server_now()

        self.win.Show()
        t_show = time.perf_counter()
        if not getattr(self, "own_loop", False): self.start_timer()
        self.rescan()
        self.check_build_on_disk(force=True)
        self.restore_panel_state()
        t_scan = time.perf_counter()

        if not self.entries:

            note = "Ready. Click LOAD WORKFLOW to import your ComfyUI API JSON. This preview does not bundle presets."
        else:
            _proven = sum(1 for e in self.entries if e.production_ready and e.proven)
            _hidden = sum(1 for e in self.entries if e.production_ready and not e.proven and not e.user_workflow)
            note = (u"Ready Â· %d proven presets" % _proven) + (
                u" (%d unproven hidden - Show unproven reveals them)" % _hidden if _hidden and not self.show_unproven() else "")
            if LAST_UI_SKIPPED > 0:
                note += u" Â· %d UI-format file(s) ignored - see log" % LAST_UI_SKIPPED
        readiness = self.first_run_status("open", server_probed=True)
        if readiness:
            note += u"   " + readiness
        if not getattr(self, "own_loop", False):
            note += "  Live updates are OFF on this Resolve build: renders keep going; press REFRESH to see progress and land a finished clip."
        if getattr(self, "unwired", None):
            note += "  Degraded: " + "; ".join(self.unwired[:2])
        self.status(note, 0, severity=None if self.entries else "info")
        if self.recovered_job and self.job and not self.job.is_consumed():
            self.set_attr("generate", "Enabled", False)
            self.status(
                "Recovered the unfinished external render from the previous panel session. "
                "No new prompt will be submitted; reading its durable status now...",
                severity="warn")
            self.pump(None)
        if not self.entries:
            self.state("REFUSED", detail="no presets")
        log("PANEL VISIBLE  %.0fms from import  (import %.0f + build %.0f + show %.0f)"
            % ((t_show - _T_IMPORT) * 1000.0, (t0 - _T_IMPORT) * 1000.0,
               (t_build - t0) * 1000.0, (t_show - t_build) * 1000.0))
        log("PANEL OPEN  total=%.0fms  ready-to-use  scan=%.0fms  presets=%d  server=%s"
            % ((t_scan - _T_IMPORT) * 1000.0, (t_scan - t_show) * 1000.0,
               len(self.entries), COMFY_URL))
        if getattr(self, "unwired", None):
            log("  DEGRADED: %s" % "; ".join(self.unwired))
        if getattr(self, "own_loop", False):
            self.run_event_loop()
        else:
            self.dispatcher.RunLoop()
        self.stop_event.set()
        self.health_stop.set()
        self.win.Hide()


def _injected(name):
    return globals().get(name, None)


def main():
    fusion_obj = _injected("fusion")
    bmd_obj = _injected("bmd")
    if fusion_obj is None or bmd_obj is None:
        raise SystemExit("SecondUnit.py must run as a Resolve Workflow Integration (no fusion/bmd globals).")
    existing = fusion_obj.UIManager.FindWindow(WIN_ID)
    if existing:
        existing.Show()
        existing.Raise()
        return
    SecondUnitPanel(fusion_obj, bmd_obj, _injected("resolve"), _injected("project")).run()

def _selftest():
    import importlib.util
    path = os.path.join(os.path.dirname(WORKFLOW_DIR), "tools", "check_preview.py")
    spec = importlib.util.spec_from_file_location("second_unit_package_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run(sys.modules.get(__name__), globals())

if _injected("fusion") is not None and _injected("bmd") is not None:
    main()
elif __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--external-worker":

        try:
            sys.exit(external_worker_main(sys.argv[2]))
        except Exception:
            traceback.print_exc()
            sys.exit(2)

    extra = [a for a in sys.argv[1:] if a != "--selftest"]
    if extra:
        print(__doc__)
        print("Unknown argument(s): %s   (no options besides --selftest)" % " ".join(extra))
        sys.exit(2)
    sys.exit(_selftest())
