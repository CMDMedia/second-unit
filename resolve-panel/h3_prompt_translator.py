
import difflib
import json
import os
import re
import ssl
import threading
import urllib.request
import urllib.error
import math
import time
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
def _guide_dir_candidates(here=None, env=None):
    here = here or HERE
    env = os.environ if env is None else env
    out = [os.path.join(here, "official_prompt_guides")]
    try:
        with open(os.path.join(here, "second-unit-home.json"), "r", encoding="utf-8-sig") as h:
            repo = (json.load(h) or {}).get("repo") or ""
        if repo:
            out.append(os.path.join(repo, "resolve-panel", "official_prompt_guides"))
    except Exception:
        pass
    if env.get("SECOND_UNIT_REPO"):
        out.append(os.path.join(env["SECOND_UNIT_REPO"], "resolve-panel", "official_prompt_guides"))
    return out

def resolve_guide_dir(here=None, env=None):
    cands = _guide_dir_candidates(here, env)
    for c in cands:
        if os.path.isfile(os.path.join(c, "SKILL.md")) and os.path.isfile(os.path.join(c, "references", "ref-en.txt")):
            return c
    return cands[0]

GUIDE_DIR = resolve_guide_dir()
GUIDE_BASE = os.path.join(GUIDE_DIR, "references", "base-en.txt")
GUIDE_REF = os.path.join(GUIDE_DIR, "references", "ref-en.txt")
GUIDE_SKILL = os.path.join(GUIDE_DIR, "SKILL.md")

BASE_MODES = ("t2va", "i2va", "fl2va", "l2va")
REF_MODE = "ref2va"
MODES = BASE_MODES + (REF_MODE,)
GENERATION_NODES = ("MiniMaxH3ReferenceToVideo", "MiniMaxH3ImageToVideo",
                    "MiniMaxH3TextToVideo", "MiniMaxH3FirstLastFrameToVideo")

VISIBLE_MARKERS = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
AUDIO_MARKERS = ("fully_copy", "partially_copy", "reference", "weak_reference")
REF_SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
                "overall_soundscape", "non_diegetic_music")
BASE_SECTIONS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")
TASK_TYPES = ("keyframe completion", "reference generation", "video editing", "video continuation",
              "audio reuse", "audio reference")

NEGATION_PATTERNS = (" no ", " not ", "never", "without", "rather than", "instead of", "does not", "nothing", " none", "avoid")
TRANSITION_WORDS = ("cut", "cuts", "dissolve", "dissolving", "dissolves", "transition", "transitions", "wipe", "fade")
EXPANDER_DEFAULT_TIMEOUT = 60.0
HEALTH_TIMEOUT = 3.0
OPENAI_MAX_TOKENS = 4096
ECHO_RATIO_MAX = 0.80
DESC_MIN_WORDS = 220
DESC_MAX_WORDS = 400
ANCHOR_STOPWORDS = ("toward", "towards", "with", "from", "into", "onto", "over", "under", "their", "there", "then", "than", "this",
                    "that", "these", "those", "while", "after", "before", "slowly", "very", "across", "around", "through", "about",
                    "each", "every", "where", "when")
PERSON_WORDS = ("woman", "women", "girl", "girls", "boy", "boys", "she", "her", "hers", "herself", "crowd", "people", "person",
                "persons", "individuals", "figures", "crew", "team", "colleague", "colleagues", "assistant", "stranger",
                "strangers", "others")
KNOWN_PROVIDERS = ("openai", "anthropic", "template")
CAMERA_WORDS = ("camera moves", "camera pushes", "camera pulls", "camera tracks", "camera follows", "camera orbits", "camera pans",
    "camera tilts", "camera cranes", "camera rises", "camera drops", "camera holds", "camera circles", "camera may", "camera is",
    "camera will", "camera repositions", "repositioned", "reframe", "reframes", "dolly", "push-in", "push in", "pull-out", "pull back",
    "pan", "pans", "tilt", "tilts", "crane shot", "handheld", "hand-held", "steadicam", "gimbal", "tracking shot", "zoom", "zooms",
    "close-up", "closeup", "wide shot", "medium shot", "over-the-shoulder", "over the shoulder", "low-angle", "low angle",
    "high-angle", "high angle", "dutch angle", "lens", "focal length", "35mm", "50mm", "85mm", "shot scale")
SOUND_WORDS = ("sound", "sounds", "audio", "hear", "hears", "heard", "noise", "noises", "silence", "echo", "echoes", "echoing",
    "drip", "drips", "dripping", "rumble", "rumbles", "hum", "hums", "humming", "footsteps", "breathing", "thunder", "roar", "roars",
    "crackle", "crackles", "crackling", "ambience", "ambient", "room tone", "wind", "howls", "hiss", "hisses", "birdsong",
    "music", "soundtrack", "song", "melody", "drums", "piano", "choir", "orchestra", "orchestral")
MUSIC_WORDS = ("music", "soundtrack", "song", "melody", "drums", "piano", "choir", "orchestra", "orchestral")
LIGHTING_WORDS = ("light", "lights", "lit", "lighting", "sunlight", "moonlight", "moonlit", "daylight", "candlelight", "torchlight",
    "firelight", "lamplight", "backlit", "backlight", "rim light", "key light", "glow", "glows", "glowing", "shadow", "shadows",
    "silhouette", "silhouetted", "haze", "hazy", "fog", "foggy", "mist", "misty", "dawn", "sunrise", "morning", "midday", "noon",
    "afternoon", "golden hour", "sunset", "dusk", "twilight", "blue hour", "night", "nighttime", "midnight", "overcast", "exposure",
    "contrast", "colour grade", "color grade", "neon")
ACTION_WORDS = ("walks", "walk", "walking", "runs", "running", "stands", "standing", "sits", "sitting", "turns", "turning", "looks",
    "stares", "gazes", "raises", "lifts", "reaches", "holds", "grips", "kneels", "kneeling", "steps", "breathes", "smiles", "speaks",
    "says", "whispers", "shouts", "nods", "gestures", "points", "opens", "closes", "moves", "leans", "rises", "falls", "crouches",
    "enters", "exits", "approaches", "performs", "delivers")
WARDROBE_WORDS = ("wear", "wears", "wearing", "worn", "dressed", "costume", "outfit", "wardrobe", "robe", "robes", "cloak", "hood",
    "hooded", "coat", "jacket", "shirt", "trousers", "pants", "boots", "shoes", "gloves", "scarf", "hat", "cuff", "armor", "armour",
    "fabric", "cloth", "garment", "garments", "sleeve", "sleeves", "belt", "necklace", "jewelry", "jewellery")
ENVIRONMENT_WORDS = ("cave", "cavern", "chamber", "tunnel", "grotto", "room", "hall", "corridor", "street", "alley", "forest", "woods",
    "desert", "dunes", "beach", "shore", "ocean", "sea", "river", "lake", "pool", "water", "waterfall", "mountain", "cliff", "valley",
    "rock", "rocks", "stone", "limestone", "wall", "walls", "floor", "ceiling", "ground", "sky", "horizon", "city", "building",
    "interior", "exterior", "location", "backdrop", "background", "landscape", "ruins", "temple", "sanctuary", "ledge", "puddle",
    "puddles", "stalactite", "stalactites", "moss", "sand", "snow", "rain", "trees", "vegetation", "mouth of the cave", "cave mouth")

BUCKET_PRECEDENCE = (("camera", CAMERA_WORDS), ("sound", SOUND_WORDS), ("lighting", LIGHTING_WORDS),
                     ("action", ACTION_WORDS), ("wardrobe", WARDROBE_WORDS), ("environment", ENVIRONMENT_WORDS))
STYLE_OPENINGS = (
    "Live-action, cinematic, photographed on a large-format digital cinema camera with a shallow depth of field",
    "Live-action and photographic, with the texture, grain and dynamic range of a large-format digital cinema camera",
    "Live-action, hyper-real and cinematic, captured as a real location on a large-format digital cinema camera")
LIGHT_OPENINGS = ("Live-action, cinematic, photographed as a real location", "Live-action and photographic, lit exactly as the shot describes",
                  "Live-action, hyper-real and cinematic, photographed as a real place")
CLOSINGS = (" The take runs unbroken from the first frame to the last frame.",
            " One uninterrupted take holds from the first frame to the last frame.",
            " A single unbroken take runs from the opening frame to the final frame.")



PICTURE_ROLE_WORDS = (
    ("continuity", "continuity"), ("previous window", "continuity"),
    ("first frame", "first_frame"), ("last frame", "last_frame"), ("keyframe", "first_frame"),
    ("storyboard", "storyboard"),
    ("environment material", "environment_material"), ("environment beauty", "environment"), ("environment", "environment"), ("backdrop", "environment"), ("cave look", "environment"),
    ("wardrobe", "wardrobe"), ("costume", "wardrobe"), ("outfit", "wardrobe"),
    ("replacement", "replacement"), ("character", "replacement"),
    ("identity", "identity"), ("performer", "identity"),
)


def picture_role_from_title(title):
    t = (title or "").strip().lower()
    for word, role in PICTURE_ROLE_WORDS:
        if word in t:
            return role
    return "reference"


def refs_from_graph(graph, node_id=None):
    node = graph.get(str(node_id)) if node_id is not None else None
    if node is None:
        for nid, n in graph.items():
            if isinstance(n, dict) and n.get("class_type") in GENERATION_NODES:
                node = n
                break
    if node is None:
        return None, {"pictures": [], "videos": [], "audios": []}
    ct = str(node.get("class_type", ""))
    inputs = node.get("inputs") or {}

    def is_link(v):
        return isinstance(v, list) and len(v) == 2

    def title_of(link):
        src = graph.get(str(link[0])) or {}
        return str((src.get("_meta") or {}).get("title") or "")

    def upstream_mentions(link, words, hops=4):
        seen, frontier = set(), [str(link[0])]
        for _ in range(hops):
            nxt = []
            for nid in frontier:
                if nid in seen:
                    continue
                seen.add(nid)
                n = graph.get(nid) or {}
                text = (str((n.get("_meta") or {}).get("title") or "") + " " + str(n.get("class_type") or "")).lower()
                if any(w in text for w in words):
                    return True
                for v in (n.get("inputs") or {}).values():
                    if is_link(v):
                        nxt.append(str(v[0]))
            frontier = nxt
        return False

    refs = {"pictures": [], "videos": [], "audios": []}
    if "ReferenceToVideo" in ct:
        mode = REF_MODE
        pics = sorted((k for k in inputs if k.startswith("ref_images.ref_image_") and is_link(inputs[k])),
                      key=lambda k: int(k.rsplit("_", 1)[1]))
        for i, k in enumerate(pics, start=1):
            title = title_of(inputs[k])
            src = graph.get(str(inputs[k][0])) or {}
            image = str((src.get("inputs") or {}).get("image") or "")
            refs["pictures"].append({"index": i, "role": picture_role_from_title(title), "title": title, "image": image})
        vids = sorted((k for k in inputs if k.startswith("ref_videos.ref_video_") and is_link(inputs[k])),
                      key=lambda k: int(k.rsplit("_", 1)[1]))
        for i, k in enumerate(vids, start=1):
            title = title_of(inputs[k]).lower()
            if upstream_mentions(inputs[k], ("depth",)):
                role = "depth"
            else:
                role = "source_edit" if i == 1 else "structure"
            refs["videos"].append({"index": i, "role": role, "title": title})
        auds = sorted((k for k in inputs if k.startswith("ref_video_audios.ref_video_audio_") and is_link(inputs[k])),
                      key=lambda k: int(k.rsplit("_", 1)[1]))
        for i, k in enumerate(auds, start=1):
            refs["audios"].append({"index": i, "role": "copy", "of_video": int(k.rsplit("_", 1)[1]) + 1})
        extra = sorted((k for k in inputs if k.startswith("ref_audios.ref_audio_") and is_link(inputs[k])),
                       key=lambda k: int(k.rsplit("_", 1)[1]))
        for k in extra:
            refs["audios"].append({"index": len(refs["audios"]) + 1, "role": "reference"})
    elif "ImageToVideo" in ct or "FirstLast" in ct:
        first = is_link(inputs.get("first_frame")) or is_link(inputs.get("start_image")) or is_link(inputs.get("image"))
        last = is_link(inputs.get("last_frame")) or is_link(inputs.get("end_image"))
        if first and last:
            mode = "fl2va"
            refs["pictures"] = [{"index": 1, "role": "first_frame", "title": "first frame"},
                                {"index": 2, "role": "last_frame", "title": "last frame"}]
        elif last:
            mode = "l2va"
            refs["pictures"] = [{"index": 1, "role": "last_frame", "title": "last frame"}]
        elif first:
            mode = "i2va"
            refs["pictures"] = [{"index": 1, "role": "first_frame", "title": "first frame"}]
        else:
            mode = "t2va"
    else:
        mode = "t2va"
    return mode, refs


def duration_seconds(graph, fps=24.0):
    for n in graph.values():
        if isinstance(n, dict) and n.get("class_type") in GENERATION_NODES:
            length = (n.get("inputs") or {}).get("length")
            if isinstance(length, (int, float)):
                return float(length) / float(fps or 24.0)
    return None



def _label(kind, i):
    return "<%s %d>" % (kind, i)


def _instruction_line(mode, refs, duration_s):
    pics = refs.get("pictures") or []
    if mode == "i2va":
        return "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    if mode == "fl2va":
        end = "%.2f" % (duration_s or 0.0)
        return ("How the reference pictures align with the target video \u2014 Picture 1 (from Shot 1) aligns with the "
                "0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the %s-second mark of the "
                "target video." % end)
    if mode == "l2va":
        end = "%.2f" % (duration_s or 0.0)
        return ("How the reference pictures align with the target video \u2014 <Picture 1> (from [Shot 1]) aligns with "
                "the %s-second mark of the target video." % end)
    return ""


def _style_line(opts):
    return (opts.get("style") or
            "Live-action, cinematic, photographed on a large-format digital cinema camera with a shallow depth of field")


def _camera_sentence(opts):
    cam = (opts.get("camera") or "").lower()
    if not cam:
        return ""
    if cam == "static":
        return "The camera holds a static shot for the entire duration."
    return "The camera %s for the entire duration." % opts["camera"]


def _closing(opts):
    if opts.get("continuous_take", True):
        return " The take runs unbroken from the first frame to the last frame."
    return ""
_DIALOGUE_RE = re.compile(r"<d>.*?</d>", re.S)

def split_sentences(text):
    text = (text or "").strip()
    if not text:
        return []
    held = []
    def _hold(m):
        held.append(m.group(0))
        return "\x00%d\x00" % (len(held) - 1)
    masked = _DIALOGUE_RE.sub(_hold, text)
    out = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", masked):
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], part)
        if part[-1] not in ".!?\"'>":
            part += "."
        out.append(part)
    return out

def _has_word(low, word):
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", low) is not None

def classify_sentence(sentence):
    if "<d>" in sentence:
        return "action"
    low = sentence.lower()
    for bucket, words in BUCKET_PRECEDENCE:
        if any(_has_word(low, w) for w in words):
            return bucket
    return "action"

def _forbidden_reason(sentence, continuous_take=True):
    low = " " + sentence.lower() + " "
    if any(p in low for p in NEGATION_PATTERNS):
        return "negation"
    if continuous_take and set(re.findall(r"[a-z]+", low)) & set(TRANSITION_WORDS):
        return "transition word"
    return ""

def classify_request(request, mode, refs, opts):
    source = [v for v in (refs.get("videos") or []) if v.get("role") in ("source_edit", "continuation")]
    locked = mode == REF_MODE and bool(source) and not opts.get("reframe")
    report = {"kept": [], "held_back": [], "buckets": {"camera": [], "sound": [], "music": [], "lighting": [], "action": [],
              "wardrobe": [], "environment": []}, "camera_locked": locked}
    for s in split_sentences(request):
        why = _forbidden_reason(s, opts.get("continuous_take", True))
        bucket = classify_sentence(s)
        if not why and bucket == "camera" and locked:
            why = "camera locked to <Video %d>" % source[0]["index"]
        if why:
            report["held_back"].append((s, why))
            continue
        if bucket == "sound" and any(_has_word(s.lower(), w) for w in MUSIC_WORDS):
            bucket = "music"
        report["kept"].append(s)
        report["buckets"][bucket].append(s)
    return report

def _digest(report):
    picked = [s for s in report["kept"] if s in report["buckets"]["action"] + report["buckets"]["environment"]
              + report["buckets"]["wardrobe"] + report["buckets"]["lighting"]][:3]
    return " ".join(picked)


def translate_with_report(mode, refs, request, duration_s=None, opts=None):
    opts = dict(opts or {})
    request = (request or "").strip()
    mode = (mode or "t2va").lower()
    if mode not in MODES:
        raise ValueError("unknown H3 mode %r" % mode)
    v = int(opts.get("variant") or 0) % 3
    report = classify_request(request, mode, refs, opts)
    b = report["buckets"]
    auds = refs.get("audios") or []
    audio_copy = any(a["role"] == "copy" for a in auds)
    opening = opts.get("style") or (LIGHT_OPENINGS[v] if b["lighting"] else STYLE_OPENINGS[v])
    light_text = " ".join(b["lighting"])
    closing = CLOSINGS[v] if opts.get("continuous_take", True) else ""
    dur = duration_s
    sound = opts.get("soundscape") or " ".join(b["sound"] + (b["music"] if audio_copy else [])) or "Quiet room tone continues throughout, with the soft physical sounds of the subject's movement."
    music = opts.get("music") or (" ".join(b["music"]) if (b["music"] and not audio_copy) else "N/A")
    if mode in BASE_MODES:
        head = _instruction_line(mode, refs, dur)
        anchor = ""
        if mode == "i2va":
            anchor = ("The shot begins from <Picture 1>, preserving its subjects, composition, clothing, colours and scene "
                      "anchors, then develops forward. ")
        elif mode == "fl2va":
            anchor = ("The shot begins in the position and framing established by Picture 1 and ends in the pose, spacing "
                      "and composition established by Picture 2. ")
        elif mode == "l2va":
            anchor = ("The shot begins from a plausible earlier state and converges on the arrangement, camera angle, "
                      "lighting and composition established by <Picture 1> at the end. ")
        body = "[Shot 1] %s. %s%s %s%s" % (opening, anchor, " ".join(report["kept"]), _camera_sentence(opts), closing)
        parts = []
        if head:
            parts.append(head)
            parts.append("")
        parts.append("integrated_multimodal_description: " + " ".join(body.split()))
        parts.append("")
        parts.append("overall_soundscape: " + sound)
        parts.append("")
        parts.append("non_diegetic_music: " + music)
        return "\n".join(parts), report


    pics = refs.get("pictures") or []
    vids = refs.get("videos") or []
    subj, ret, tasks = [], [], []
    subj_n = 0
    identity = [p for p in pics if p["role"] in ("identity", "replacement")]
    wardrobe = [p for p in pics if p["role"] == "wardrobe"]
    env = [p for p in pics if p["role"] in ("environment", "environment_material")]
    cont = [p for p in pics if p["role"] in ("continuity", "first_frame")]
    last = [p for p in pics if p["role"] == "last_frame"]
    others = [p for p in pics if p["role"] in ("storyboard", "reference")]
    source = [v for v in vids if v["role"] in ("source_edit", "continuation")]
    depth = [v for v in vids if v["role"] == "depth"]
    if depth and source and env and not opts.get("reframe"):

        env = [dict(p, role="environment_material") for p in env]
    env_subject = None
    performer_subject = None
    if identity or source:
        subj_n += 1
        performer_subject = subj_n
        srcs = []
        if source:
            srcs.append("the performer of %s" % _label("Video", source[0]["index"]))
        if identity:

            srcs.append("the same person shown in %s" % ", ".join(
                _label("Picture", p["index"]) + ((" (%s)" % p["note"]) if p.get("note") else "") for p in identity))
        subj.append("<Subject %d> is %s%s" % (subj_n, " and ".join(srcs) if srcs else "the performer",
                    (": every one of these pictures shows this one person and they are fused as complementary evidence of "
                     "one identity. He keeps a complete body exactly where the footage places it." if identity else ".")))
        aspects = "identity, face, skin, build, pose sequence, gesture timing, head turns, eye-line, expression timing and mouth movement"
        ret.append("<Subject %d> (appears in [Shot 1]): fully_preserved - the performer's %s are retained%s." % (
            subj_n, aspects, "; the pictures' framing, head size, angle and lighting are left behind" if identity else ""))
        if identity:
            tasks.append("reference generation")
    if wardrobe:
        subj_n += 1
        subj.append("<Subject %d> is the costume shown in %s: the garments exactly as pictured, their tailoring, layering, colour, "
                    "weave, wear and fastenings." % (subj_n, " and ".join(_label("Picture", p["index"]) for p in wardrobe)))
        if b["wardrobe"]: subj[-1] = subj[-1] + " " + " ".join(b["wardrobe"])
        ret.append("<Subject %d> (appears in [Shot 1]): attribute_transfer - the costume is transferred onto <Subject %d> "
                   "for the whole shot, fitted to the target performer's proportions; the costume pictures' faces, "
                   "body proportions, shoulder width, torso bulk, poses, framing and lighting are left behind." % (
                       subj_n, performer_subject or 1))
        tasks.append("reference generation")
    if env:
        subj_n += 1
        e = env[0]
        env_subject = subj_n
        if e["role"] == "environment_material":
            subj.append("<Subject %d> is the material reference for the location in %s: its surfaces, textures, moisture, "
                        "atmosphere and light quality." % (subj_n, _label("Picture", e["index"])))
            geometry = (", and the location's geometry comes from %s" % _label("Video", depth[0]["index"])) if depth else ""
            ret.append("<Subject %d> (appears in [Shot 1]): attribute_transfer - its surfaces, textures, moisture, atmosphere and "
                       "light quality are transferred to the location; its layout and framing are left behind%s." % (subj_n, geometry))
        else:
            subj.append("<Subject %d> is the location shown in %s: its geometry, props and materials." % (subj_n, _label("Picture", e["index"])))
            ret.append("<Subject %d> (appears in [Shot 1]): fully_preserved - the location's geometry, props and materials are "
                       "retained; its lighting is the lighting described below." % subj_n)
        if b["environment"]: subj[-1] = subj[-1] + " " + " ".join(b["environment"])
        tasks.append("reference generation")
    for p in others:
        subj.append("%s is a %s reference for [Shot 1], providing composition and placement." % (_label("Picture", p["index"]), p["role"]))
        ret.append("%s ([Shot 1] composition): weak_reference - only its composition and placement are followed." % _label("Picture", p["index"]))
        tasks.append("reference generation")
    for v in source:
        if v["role"] == "continuation":
            subj.append("%s is the source video that the target video continues from." % _label("Video", v["index"]))
            ret.append("%s (continuation point): fully_preserved - the target video continues from its final state." % _label("Video", v["index"]))
            tasks.append("video continuation")
        else:
            subj.append(("%s is the performance and timing reference for a shot with the newly requested camera."
                         if opts.get("reframe") else
                         "%s is the source video for the target video edit: the performance, the camera, the framing and the timing.")
                        % _label("Video", v["index"]))
            if opts.get("reframe"):

                ret.append("%s (performance: pose sequence, body language, gesture timing, head turns, eye-line, expression "
                           "timing, mouth movement): fully_preserved - reproduced from the source performance." % _label("Video", v["index"]))
                ret.append("%s (framing and camera): weak_reference - the source camera position, framing and shot scale are "
                           "left behind; the shot is re-staged from the camera described below, with the timing and performance kept." % _label("Video", v["index"]))
            else:
                ret.append("%s (performance, camera position, motion, lens, framing, shot scale, timing): fully_preserved - reproduced from the source." % _label("Video", v["index"]))
            ret.append("%s (action timing): fully_preserved - each footfall, head turn, gesture and change of body "
                       "orientation occurs at its original source timestamp and speed. The recorded acting remains "
                       "the motion authority when the camera moves." % _label("Video", v["index"]))
            if env:

                ret.append("%s (environment): weak_reference - the source location is replaced by <Subject %d>." % (
                    _label("Video", v["index"]), subj_n))
            if env and not wardrobe and not opts.get("reframe"):
                ret.append("%s (clothing): fully_preserved - every garment is reproduced exactly from the source footage in its "
                           "tailoring, colour, weave and fastening." % _label("Video", v["index"]))
            tasks.append("video editing")
    for v in depth:
        subj.append("%s is the measured depth of the same footage and provides the camera, the framing and the position of everything in the frame." % _label("Video", v["index"]))
        if opts.get("reframe"):
            ret.append("%s (depth and pose timing): partially_preserved - scene depth and performance timing inform the requested camera angle." % _label("Video", v["index"]))
        else:
            ret.append("%s (camera and depth): fully_preserved - it locks camera, framing, pose timing and the position of everything in the frame." % _label("Video", v["index"]))
    for v in vids:
        if v["role"] == "structure":
            subj.append("%s provides the shot flow and pacing reference." % _label("Video", v["index"]))
            ret.append("%s (shot structure and pacing): weak_reference - only its pacing is followed." % _label("Video", v["index"]))
            tasks.append("reference generation")
    for p in cont:
        subj.append("%s is the first frame of [Shot 1]." % _label("Picture", p["index"]))
        ret.append("%s ([Shot 1] first frame): fully_preserved - the shot begins from %s and continues its set dressing, props, "
                   "lighting and framing exactly." % (_label("Picture", p["index"]), _label("Picture", p["index"])))
        tasks.append("keyframe completion")
    for p in last:
        subj.append("%s is the last frame of [Shot 1]." % _label("Picture", p["index"]))
        ret.append("%s ([Shot 1] last frame): fully_preserved - the shot ends on %s." % (_label("Picture", p["index"]), _label("Picture", p["index"])))
        tasks.append("keyframe completion")
    for a in auds:
        if a["role"] == "copy":
            of = a.get("of_video")
            subj.append("%s is the synchronized audio track of %s and is reused in the target video." % (
                _label("Audio", a["index"]), _label("Video", of or 1)))
            ret.append("%s: fully_copy - %s is reused 1:1 as the target video's complete final audio track." % (
                _label("Audio", a["index"]), _label("Audio", a["index"])))
            tasks.append("audio reuse")
        else:
            subj.append("%s is an audio reference for the target video's sound." % _label("Audio", a["index"]))
            ret.append("%s: reference - only its timbre, rhythm and texture are referenced." % _label("Audio", a["index"]))
            tasks.append("audio reference")
    if source and opts.get("continuous_take", True):
        ret.append("%s (shot structure and pacing): weak_reference - the target video is one single continuous take, a single "
                   "uninterrupted run of the camera from the first frame to the last frame; whatever the source contains, the "
                   "target is one shot." % _label("Video", source[0]["index"]))
    ordered = [t for t in TASK_TYPES if t in tasks] or ["reference generation"]
    who = "<Subject %d>" % performer_subject if performer_subject else "the subject"
    if wardrobe:
        who += " wearing <Subject %d>" % (2 if performer_subject else 1)
    summary = "[%s] " % " + ".join(ordered)
    if source and source[0]["role"] == "source_edit":
        summary += "The target video is an edited version of %s. " % _label("Video", source[0]["index"])
    digest = _digest(report)
    if source and source[0]["role"] == "source_edit":
        summary += "%s performs exactly as in %s, %s%s. " % (who, _label("Video", source[0]["index"]),
            "at the same timing, seen from the requested camera angle" if opts.get("reframe") else "at the same camera, framing and timing",
            (", relocated into <Subject %d>" % env_subject) if (env and env_subject) else "")
        if digest:
            summary += digest + " "
    else:
        summary += "%s: %s " % (who, digest or "performs the described action.")
    if opts.get("continuous_take", True):
        summary += "The target video is one single continuous shot from its first frame to its last frame. "
    if any(a["role"] == "copy" for a in auds):
        summary += "<Audio 1> is reused 1:1."
    if b["lighting"]:
        style = "The target video is %s. %s" % (opening.lower(), light_text)
    elif opts.get("continuous_take", True):
        style = "The target video is %s, a single continuous take." % opening.lower()
    else:
        style = "The target video is %s." % opening.lower()
    begins = ""
    if cont:
        begins = " The shot begins from %s." % _label("Picture", cont[0]["index"])
    env_hold = ""
    camera_text = _camera_sentence(opts)
    if env and source and depth and not opts.get("reframe"):
        env_hold = " <Subject %d> is fully present from the first frame to the last frame." % env_subject
        if not camera_text:
            camera_text = ("The camera holds exactly the position, height, angle and focal length that %s and %s give it for "
                           "the entire duration." % (_label("Video", source[0]["index"]), _label("Video", depth[0]["index"])))
    body = "[Shot 1] %s frame %s.%s%s %s %s%s" % (
        "The framing, shot scale and lens of %s" % _label("Video", source[0]["index"]) if source and not opts.get("reframe") else "The requested camera angle and composition",
        who, begins, env_hold, " ".join(report["kept"]), camera_text, closing)
    if audio_copy:
        sound = opts.get("soundscape") or ("The copied track from <Audio 1> continues throughout the target video, with the "
                                           "original synchronized sound preserved."
                                           + ((" " + " ".join(b["sound"] + b["music"])) if (b["sound"] or b["music"]) else ""))
    lines = ["subject_definitions:"] + subj + ["", "summary:", summary.strip(), "", "retention_analysis:"] + ret + \
            ["", "detailed_description:", style, " ".join(body.split()), "", "overall_soundscape:", sound, "",
             "non_diegetic_music:", music]
    return "\n".join(lines), report


def translate(mode, refs, request, duration_s=None, opts=None):
    return translate_with_report(mode, refs, request, duration_s, opts)[0]



def validate(prompt, mode, opts=None, refs=None):
    opts = dict(opts or {})
    mode = (mode or "t2va").lower()
    issues = []
    p = prompt or ""
    sections = REF_SECTIONS if mode == REF_MODE else BASE_SECTIONS
    pos = [p.find(s + ":") for s in sections]
    if any(x < 0 for x in pos):
        issues.append("missing section(s): %s" % ", ".join(s for s, x in zip(sections, pos) if x < 0))
    elif pos != sorted(pos):
        issues.append("sections out of the guide's order")
    if mode in ("i2va", "fl2va", "l2va"):
        first = p.strip().split("\n", 1)[0]
        if mode == "i2va" and not first.startswith("For the target video, at 0.00 seconds"):
            issues.append("I2VA instruction line missing or not first")
        if mode in ("fl2va", "l2va") and not first.startswith("How the reference pictures align with the target video"):
            issues.append("%s alignment line missing or not first" % mode.upper())
    for m in re.finditer(r"^<(Subject|Picture|Video|Audio) (\d+)>[^:\n]*:\s*([a-z_]+)", p, re.M):
        kind, marker = m.group(1), m.group(3)
        if p.find("retention_analysis:") >= 0 and m.start() > p.find("retention_analysis:") and \
                (p.find("detailed_description:") < 0 or m.start() < p.find("detailed_description:")):
            legal = AUDIO_MARKERS if kind == "Audio" else VISIBLE_MARKERS
            if marker not in legal:
                issues.append("illegal marker %r on %s" % (marker, m.group(0)[:40]))
    used = set(re.findall(r"<(Subject|Picture|Video|Audio) (\d+)>", p))
    if refs is not None:
        available = {(kind, str(item["index"])) for kind, key in
                     (("Picture", "pictures"), ("Video", "videos"), ("Audio", "audios"))
                     for item in refs.get(key, [])}
        invented = sorted(label for label in used if label[0] != "Subject" and label not in available)
        if invented:
            issues.append("references are not wired: %s" % ", ".join("<%s %s>" % x for x in invented))
    if mode == REF_MODE:

        sd_start = p.find("subject_definitions:")
        sd_end = p.find("summary:") if p.find("summary:") > sd_start else len(p)
        section = p[sd_start:sd_end] if sd_start >= 0 else ""
        defined = set(re.findall(r"<(Subject|Picture|Video|Audio) (\d+)>", section))
        undefined = sorted(used - defined)
        if undefined:
            issues.append("labels used but never defined: %s" % ", ".join("<%s %s>" % u for u in undefined))
    shots = re.findall(r"\[Shot (\d+)\]", p)
    if "1" not in shots:
        issues.append("no [Shot 1] marker")
    later = sorted(set(s for s in shots if s != "1"), key=int)
    if later and opts.get("continuous_take", True):
        issues.append("later shot markers present (%s) in a continuous-take prompt" % ", ".join("[Shot %s]" % s for s in later))
    for s in later:
        if not re.search(r"\[Shot %s\] At \d\d:\d\d\.\d\d\d" % s, p):
            issues.append("[Shot %s] lacks the 'At MM:SS.mmm' cut time" % s)
    low = " " + p.lower() + " "
    negs = [w.strip() for w in NEGATION_PATTERNS if w in low]
    if negs:
        issues.append("negative phrasing (CFG-distilled model renders it): %s" % ", ".join(negs))
    if opts.get("continuous_take", True):
        words = set(re.findall(r"[a-z]+", low))
        hits = sorted(w for w in TRANSITION_WORDS if w in words)
        if hits:
            issues.append("transition words in a continuous-take prompt: %s" % ", ".join(hits))
    for m in re.finditer(r"<d>(.*?)</d>", p, re.S):
        if not re.match(r"\[[A-Za-z]+\]", m.group(1).strip()):
            issues.append("dialogue block without a [Language] tag: %s" % m.group(1)[:30])
    return issues



def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as h:
            return h.read()
    except Exception:
        return ""


def expander_config(env=None):
    env = env if env is not None else os.environ
    provider = (env.get("SECOND_UNIT_EXPANDER_PROVIDER") or "").lower()
    if not provider:
        provider = "anthropic" if (env.get("ANTHROPIC_API_KEY") and not env.get("SECOND_UNIT_EXPANDER_URL")) else "openai"
    url = env.get("SECOND_UNIT_EXPANDER_URL") or ("https://api.anthropic.com" if provider == "anthropic" else "")
    model = env.get("SECOND_UNIT_EXPANDER_MODEL") or ""

    host = urlparse(url).hostname
    key = env.get("SECOND_UNIT_EXPANDER_KEY") or ""
    if not key and provider == "anthropic" and host == "api.anthropic.com":
        key = env.get("ANTHROPIC_API_KEY") or ""
    if not key and provider == "openai" and host == "api.openai.com":
        key = env.get("OPENAI_API_KEY") or ""
    try:
        timeout = float(env.get("SECOND_UNIT_EXPANDER_TIMEOUT") or 0) or None
    except ValueError:
        timeout = None
    chain_raw = (env.get("SECOND_UNIT_EXPANDER_CHAIN") or "").lower()
    chain = [p.strip() for p in chain_raw.split(",") if p.strip() in KNOWN_PROVIDERS] if chain_raw else [provider, "template"]
    if "template" not in chain:
        chain.append("template")
    usable = {"openai": bool(provider == "openai" and url and model),
              "anthropic": bool(provider == "anthropic" and url and model and key), "template": True}
    return {"provider": provider, "url": url.rstrip("/"), "model": model, "key": key, "timeout": timeout,
            "effort": (env.get("SECOND_UNIT_EXPANDER_EFFORT") or "").lower() or None,
            "chain": chain, "usable": usable, "configured": any(usable.get(p) for p in chain if p != "template")}


SYSTEM_RULES = """You are the MiniMax H3 prompt rewriter for a film crew's DaVinci Resolve panel. Rewrite the operator's request into the EXACT MiniMax H3 prompt format for the given mode, following the official guide text supplied below to the letter: exact field names, section order, labels, markers and timing notation.

House rules that override style preferences:
- The checkpoints are CFG-distilled: every word is positive conditioning. Describe what exists. Never write what to avoid, never use "no", "not", "never", "without", "rather than", "instead of".
- Unless the operator explicitly asks for cuts, the target video is ONE continuous take: exactly one [Shot 1], the camera described as holding or moving for the entire duration, and the words cut, dissolve, transition, wipe and fade absent from the text. In full-reference mode add the line "<Video 1> (shot structure and pacing): weak_reference - the target video is one single continuous take from the first frame to the last frame" when a source video is present.
- Use only the reference labels in the inventory, with their exact numbers and roles. Define every label you use in subject_definitions (full-reference mode). Never invent references.
- Keep the operator's concrete facts (wardrobe, lighting, setting, action, dialogue) and expand them into specific visible and audible detail; keep dialogue verbatim inside <d>[Language] ...</d>.
- Match the description to the requested duration. Aim for 350-600 words in total unless dialogue-dense.
- Every sentence listed under OPERATOR SENTENCES appears word for word inside the [Shot 1] description; add specific visible and audible detail around them. Sentences listed under HELD BACK stay out of the prompt.
- When CAMERA says locked, the camera, framing and shot scale are exactly those of <Video 1> (and <Video 2> when it is a depth video); describe them as held by the source.
- An environment picture with a depth video supplies materials, textures and atmosphere; geometry, horizon and scale come from <Video 1>/<Video 2>.
- Output ONLY the finished prompt text. No preamble, no code fences, no commentary."""


def _guide_text(mode):
    skill = _read(GUIDE_SKILL)
    guide = _read(GUIDE_REF if mode == REF_MODE else GUIDE_BASE)
    return (skill + "\n\n" + guide).strip()


def _user_message(mode, refs, request, duration_s, skeleton, opts, report=None, previous=None):
    shown = " ".join(report["kept"]) if report is not None else (request or "")
    inv = []
    for p in refs.get("pictures") or []:
        inv.append("<Picture %d>: role=%s%s%s" % (p["index"], p["role"], (" title=%r" % p["title"]) if p.get("title") else "",
                                                  (" note=%s" % p["note"]) if p.get("note") else ""))
    for v in refs.get("videos") or []:
        inv.append("<Video %d>: role=%s%s" % (v["index"], v["role"], (" note=%s" % v["note"]) if v.get("note") else ""))
    for a in refs.get("audios") or []:
        inv.append("<Audio %d>: role=%s%s" % (a["index"], a["role"], (" (soundtrack of <Video %d>)" % a["of_video"]) if a.get("of_video") else ""))
    dur = ("%.2f seconds" % duration_s) if duration_s else "unspecified"
    analysis = ""
    if report is not None:
        analysis = ("OPERATOR SENTENCES:\n%s\n\nHELD BACK:\n%s\n\nCAMERA: %s\n\n" % (
            "\n".join("- %s" % s for s in report["kept"]) or "(none)",
            "\n".join("- %s (%s)" % (s, why) for s, why in report["held_back"]) or "(none)",
            "locked" if report["camera_locked"] else "free"))
    message = ("MODE: %s\nDURATION: %s\nCONTINUOUS TAKE: %s\nREFERENCE INVENTORY:\n%s\n\nOPERATOR REQUEST:\n%s\n\n%s"
               "DETERMINISTIC SKELETON (keep its section headers, labels, markers and operator sentences; its detailed_description is only a placeholder: replace it with 180-400 words of new concrete visual detail built on the operator's sentences; a copied skeleton fails the text check):\n%s\n" % (
                   mode.upper(), dur, "yes" if opts.get("continuous_take", True) else "no",
                   "\n".join(inv) or "(none)", shown.strip() or "(empty)", analysis, skeleton))
    if previous:
        message += ("\nPREVIOUS EXPANSION OF THIS SAME REQUEST - write a new version: elaborate further with different specific detail "
                    "(textures, light behaviour, micro-actions, sound) while keeping every operator sentence, label and marker:\n"
                    + previous)
    return message


class BackendOffline(RuntimeError):
    pass

def _http_body(exc):
    try:
        return exc.read()[:200].decode("utf-8", "replace").strip()
    except Exception:
        return ""

def _post_json(url, body, headers, timeout):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=dict({"Content-Type": "application/json"}, **headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP %d from %s: %s" % (exc.code, urlparse(url).netloc, _http_body(exc)))

def _get_json(url, headers, timeout):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def gateway_name(cfg):
    host = urlparse(cfg.get("url") or "").netloc or "?"
    local_gateway = host.split(":")[0] in ("127.0.0.1", "localhost")
    return ("Local gateway" if local_gateway else "OpenAI-compatible gateway"), host

def backend_label(cfg, provider=None):
    provider = provider or (cfg.get("chain") or [cfg.get("provider")])[0] or ""
    if provider == "openai":
        name, host = gateway_name(cfg)
        return "%s (%s) %s" % (name, host, cfg.get("model") or "")
    if provider == "anthropic":
        return "Anthropic API %s" % (cfg.get("model") or "")
    return "guide template"

def gateway_health(cfg, timeout=HEALTH_TIMEOUT):
    name, host = gateway_name(cfg)
    headers = {"Authorization": "Bearer " + cfg["key"]} if cfg.get("key") else {}
    try:
        out = _get_json(cfg["url"] + "/models", headers, timeout)
    except urllib.error.HTTPError as exc:
        raise BackendOffline("%s (%s) rejected the request (HTTP %d: %s)" % (name, host, exc.code, _http_body(exc)))
    except Exception:
        raise BackendOffline("%s offline (%s)" % (name, host))
    ids = [m.get("id") for m in (out.get("data") or []) if isinstance(m, dict)]
    if cfg.get("model") and ids and cfg["model"] not in ids:
        raise BackendOffline("%s (%s) does not serve %s (serves %s)" % (name, host, cfg["model"], ", ".join(ids[:5])))
    return ids

def budget_seconds(cfg):
    try:
        return max(1, int(math.ceil(float((cfg or {}).get("timeout") or EXPANDER_DEFAULT_TIMEOUT))))
    except (TypeError, ValueError):
        return int(EXPANDER_DEFAULT_TIMEOUT)


def call_llm(system, user, cfg, timeout=20, temperature=0.4):
    if cfg["provider"] == "anthropic":

        body = {"model": cfg["model"], "max_tokens": 4096, "system": system,
                "messages": [{"role": "user", "content": user}],
                "output_config": {"effort": cfg.get("effort") or "medium"},
                "fallbacks": "default"}
        out = _post_json(cfg["url"] + "/v1/messages", body,
                         {"x-api-key": cfg["key"], "anthropic-version": "2023-06-01",
                          "anthropic-beta": "server-side-fallback-2026-07-01"}, timeout)
        if out.get("stop_reason") == "refusal":
            raise RuntimeError("The model declined the rewrite (%s)" % ((out.get("stop_details") or {}).get("category") or "refusal"))
        return "".join(part.get("text", "") for part in out.get("content", []) if part.get("type") == "text")
    body = {"model": cfg["model"], "temperature": temperature, "max_tokens": OPENAI_MAX_TOKENS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    headers = {"Authorization": "Bearer " + cfg["key"]} if cfg.get("key") else {}
    out = _post_json(cfg["url"] + "/chat/completions", body, headers, timeout)
    choice = out["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("reply truncated at max_tokens=%d" % OPENAI_MAX_TOKENS)
    return choice["message"]["content"]


def _strip_fences(text):
    t = (text or "").strip()
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
    t = re.sub(r"^```[a-zA-Z]*\n", "", t)
    t = re.sub(r"\n```$", "", t)
    return t.strip()


def _norm(s):
    return " ".join((s or "").split())

def _match_key(s):
    return re.sub(r"[.!?]+$", "", _norm(s)).lower()
def _section_text(text, name, names):
    heads = "|".join(re.escape(n) for n in names)
    m = re.search(r"^" + re.escape(name) + r":[ \t]*\n?(.*?)(?=^(?:" + heads + r"):|\Z)", text or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def _splice_section(text, name, body, names):
    heads = "|".join(re.escape(n) for n in names)
    pattern = re.compile(r"(^" + re.escape(name) + r":[ \t]*\n?)(.*?)(?=^(?:" + heads + r"):|\Z)", re.M | re.S)
    if not pattern.search(text or ""):
        raise RuntimeError("skeleton has no %s section" % name)
    return pattern.sub(lambda m: m.group(1).rstrip(" \t\n") + "\n" + body.strip() + "\n\n", text, count=1)


def _anchor_stems(sentences):
    stems = []
    for s in sentences or []:
        for word in re.findall(r"[a-z]+", (s or "").lower()):
            if len(word) < 4 or word in ANCHOR_STOPWORDS:
                continue
            stem = word[:5] if len(word) >= 6 else word
            if stem not in stems:
                stems.append(stem)
    return stems


def _clean_body(reply, name, kept, allowed, context=None, skeleton=None):
    body = _strip_fences(reply)
    body = re.sub(r"^\s*" + re.escape(name) + r":[ \t]*", "", body)
    keep = set(_match_key(s) for s in (kept or []))
    allowed = set(allowed or [])
    context_words = set(re.findall(r"[a-z]+", (context or "").lower()))
    objects = []
    for sd_line in _section_text(skeleton or "", "subject_definitions", REF_SECTIONS).splitlines():
        m = re.match(r"\s*(<Subject \d+>)(.*)", sd_line)
        if m and re.search(r"costume|location|setting|material reference", m.group(2).lower()):
            objects.append(m.group(1))
    lines = []
    for line in body.splitlines():
        parts = [s for s in re.split(r"(?<=[.!?])\s+", line.strip()) if s]
        good = []
        for s in parts:
            low = " " + s.lower() + " "
            words = set(re.findall(r"[a-z]+", low))
            bad = any(p in low for p in NEGATION_PATTERNS) or bool(words & set(TRANSITION_WORDS))
            if not set(re.findall(r"<(?:Subject|Picture|Video|Audio) \d+>", s)) <= allowed:
                bad = True
            if any(w in words and w not in context_words for w in PERSON_WORDS):
                bad = True
            if re.search(r"<(?:Picture|Video|Audio) \d+>(?:\W+[\w'-]+)?\W+(?:displays|shows|appears|plays|loops|projects)\b", s) or \
                    (re.search(r"<(?:Picture|Video|Audio) \d+>", s) and
                     re.search(r"\b(?:screen|monitor|display|projector|television)s?\b", s.lower())):
                bad = True
            for subject in objects:
                if re.search(re.escape(subject) + r"(?:\W+[\w'-]+){0,2}\W+(?:enters|walks|nods|gestures|adjusts|taps|steps|"
                             r"turns|looks|speaks|smiles|stands|sits)\b", s):
                    bad = True
            if _match_key(s) in keep or not bad:
                good.append(s)
        if good:
            lines.append(" ".join(good))
    return "\n".join(lines).strip()


def _provider_prompt(provider, mode, refs, base, duration_s, skeleton, opts, cfg, deadline, budget, report, previous):
    pcfg = dict(cfg, provider=provider)
    if provider == "openai" and pcfg.get("url"):
        gateway_health(pcfg, timeout=min(HEALTH_TIMEOUT, max(0.5, deadline - time.monotonic())))
    temp = 0.8 if previous else 0.4
    user = _user_message(mode, refs, base, duration_s, skeleton, opts, report, previous)
    names = REF_SECTIONS if mode == REF_MODE else BASE_SECTIONS
    desc_name = "detailed_description" if mode == REF_MODE else "integrated_multimodal_description"
    shown = _splice_section(skeleton, desc_name, "<<SECTION BODY>>", names)
    user = user.replace(skeleton, shown, 1)
    labels = sorted(set(re.findall(r"<(?:Subject|Picture|Video|Audio) \d+>", skeleton)))
    user += ("\nTASK: write ONLY the body of the %s section of the prompt above, where it says <<SECTION BODY>>. Every other "
             "section is final. Write 250-400 words of concrete visual description built on the operator's sentences, keep "
             "every operator sentence word for word, and include exactly one [Shot 1] marker where the shot description "
             "starts. Use only these labels: %s. Use positive phrasing only. These words are forbidden: %s. Return the body "
             "text only: no section header, no other section, no code fence." % (
                 desc_name, ", ".join(labels) or "(none)",
                 ", ".join(sorted(set([w.strip() for w in NEGATION_PATTERNS] + list(TRANSITION_WORDS))))))
    system = SYSTEM_RULES + "\n\n===== OFFICIAL GUIDE =====\n" + _guide_text(mode)
    sk_body = _section_text(skeleton, desc_name, names)
    required = [s for s in report["kept"] if _match_key(s) in _norm(sk_body).lower()]
    allowed = set(labels)
    context = ((base or "") + "\n" + skeleton).lower()
    stitched = [0]
    def stitch(b):
        add = [s for s in required if _match_key(s) not in _norm(b).lower()]
        stitched[0] = len(add)
        if not add:
            return b
        i = b.find("[Shot 1]")
        if i < 0:
            return " ".join(add) + " " + b
        j = i + len("[Shot 1]")
        return b[:j] + " " + " ".join(add) + " " + b[j:].lstrip(" \t")
    body = stitch(_clean_body(call_llm(system, user, pcfg, max(1.0, deadline - time.monotonic()), temp), desc_name, report["kept"], allowed,
                              context, skeleton))
    text = _splice_section(skeleton, desc_name, body, names)
    def problems(t):
        issues = validate(t, mode, opts, refs)
        low = _norm(t).lower()
        missing = [s for s in report["kept"] if _match_key(s) not in low]
        if missing:
            issues.append("operator sentence missing: %s" % missing[0][:60])
        names = REF_SECTIONS if mode == REF_MODE else BASE_SECTIONS
        desc_name = "detailed_description" if mode == REF_MODE else "integrated_multimodal_description"
        body_missing = [s for s in required if _match_key(s) not in _norm(_section_text(t, desc_name, names)).lower()]
        if body_missing:
            issues.append("%s lost operator sentence: %s" % (desc_name, body_missing[0][:60]))
        rest = _norm(_section_text(t, desc_name, names)).lower()
        for s in required:
            rest = rest.replace(_norm(s).lower(), " ")
        stems = _anchor_stems(required)
        anchored = sum(1 for stem in stems if re.search(r"\b" + re.escape(stem), rest))
        if stems and anchored < min(2, len(stems)):
            issues.append("%s drifts from the request (uses %d of its key words outside the operator sentences)" % (desc_name, anchored))
        if _norm(t) == _norm(skeleton):
            issues.append("returned the deterministic skeleton unchanged")
        else:
            sk_desc = _norm(_section_text(skeleton, desc_name, names))
            t_desc = _norm(_section_text(t, desc_name, names))
            if sk_desc and t_desc and difflib.SequenceMatcher(None, sk_desc, t_desc).ratio() >= ECHO_RATIO_MAX:
                issues.append("%s copies the skeleton (similarity %.2f); rewrite it with new concrete detail" % (desc_name, difflib.SequenceMatcher(None, sk_desc, t_desc).ratio()))
            if len(t_desc.split()) < DESC_MIN_WORDS:
                issues.append("%s too short (%d words); write 250-400 words" % (desc_name, len(t_desc.split())))
        if previous and _norm(t) == _norm(previous):
            issues.append("returned the previous expansion unchanged")
        return issues
    issues = problems(text)
    if issues and (deadline - time.monotonic()) >= 0.4 * budget:
        repair = (user + "\nYOUR BODY:\n" + body + "\nTEXT CHECK FAILURES:\n" + "\n".join(issues)
                  + "\nReturn the corrected section body only.")
        body = stitch(_clean_body(call_llm(system, repair, pcfg, max(1.0, deadline - time.monotonic()), temp), desc_name, report["kept"],
                                  allowed, context, skeleton))
        text = _splice_section(skeleton, desc_name, body, names)
        issues = problems(text)
    if issues:
        raise RuntimeError("output failed text checks: " + "; ".join(issues)[:240])
    return text, stitched[0]

def expand(mode, refs, request, duration_s=None, opts=None, cfg=None, timeout=None, original=None, previous=None, variant=0):
    opts = dict(opts or {})
    mode = (mode or "t2va").lower()
    cfg = expander_config() if cfg is None else cfg
    budget = float(timeout or cfg.get("timeout") or EXPANDER_DEFAULT_TIMEOUT)
    deadline = time.monotonic() + (budget - 2.0 if budget > 4.0 else budget)
    sections = REF_SECTIONS if mode == REF_MODE else BASE_SECTIONS
    base = (original if original else request) or ""
    if all(re.search(r"^" + name + r":", base, re.M) for name in sections):
        return base.strip(), {"source": "passthrough", "fallback": False, "backend": "none", "attempts": [], "held_back": [],
                              "issues": validate(base, mode, opts, refs),
                              "detail": "SHOT is already in MiniMax's format; REVERT or type a plain shot description to expand"}
    skeleton, report = translate_with_report(mode, refs, base, duration_s, dict(opts, variant=variant))
    chain = cfg.get("chain") or [cfg.get("provider") or "template", "template"]
    attempts = []
    if cfg.get("configured"):
        for provider in chain:
            if provider == "template":
                break
            if deadline - time.monotonic() < 1.0:
                attempts.append("%s: skipped, %.0fs budget spent" % (backend_label(cfg, provider), budget))
                continue
            try:
                text, stitched = _provider_prompt(provider, mode, refs, base, duration_s, skeleton, opts, cfg, deadline, budget, report, previous)
                attempts.append("%s: llm stitched=%d" % (backend_label(cfg, provider), stitched))
                return text, {"source": "llm", "fallback": False, "backend": backend_label(cfg, provider), "attempts": attempts,
                              "held_back": report["held_back"], "issues": [], "detail": backend_label(cfg, provider)}
            except BackendOffline as exc:
                attempts.append(str(exc))
            except Exception as exc:
                attempts.append("%s: %s" % (backend_label(cfg, provider), str(exc)[:200]))
        detail = "; ".join(attempts) + " - template used"
    else:
        detail = "no expander backend configured - guide-shaped template"
    return skeleton, {"source": "template", "fallback": bool(cfg.get("configured")), "backend": "template", "attempts": attempts,
                      "held_back": report["held_back"], "issues": validate(skeleton, mode, opts, refs), "detail": detail}


def expand_async(callback, *args, **kwargs):

    cfg = kwargs.get("cfg") or {}
    deadline = max(0.01, float(kwargs.get("timeout") or cfg.get("timeout") or EXPANDER_DEFAULT_TIMEOUT))
    kwargs["timeout"] = deadline
    lock = threading.Lock()
    completed = [False]
    def deliver(prompt, info):
        with lock:
            if completed[0]:
                return
            completed[0] = True
        timer.cancel()
        callback(prompt, info)
    def fallback():
        local = dict(kwargs)
        local["cfg"] = {"configured": False}
        prompt, info = expand(*args, **local)
        info["detail"] = "%s exceeded %.0fs - template used" % (backend_label(cfg) if cfg.get("configured") else "expander", deadline)
        info["fallback"] = bool(cfg.get("configured"))
        deliver(prompt, info)
    timer = threading.Timer(deadline, fallback)
    timer.daemon = True
    def _run():
        try:
            prompt, info = expand(*args, **kwargs)
        except Exception as exc:
            prompt, info = "", {"source": "error", "issues": [str(exc)], "detail": str(exc)}
        deliver(prompt, info)
    t = threading.Thread(target=_run, name="h3-prompt-expander")
    t.daemon = True
    timer.start()
    t.start()
    return t


LTX25_EXPANSION_RULES = """You expand a dictated shot request for LTX 2.5 environment video generation.
The operator's original words will be retained as the beginning of the final prompt, including all camera instructions. Supply ONLY 2-4 supplementary sentences of natural present-tense prose; no headings, tags, JSON, explanations, or repeated operator text.
Expand concrete environment detail already specified by the operator. You have NOT seen the reference image; do not invent its contents, weather, terrain, lighting, colors or objects. For image-to-video, you may describe continuity of existing surfaces, lighting and spatial relationships, except where the operator explicitly requests a change.
Do not add people, actors, animals, dialogue, speech or music. Do not invent camera motion or framing. Do not mention camera, pan, tilt, dolly, orbit, zoom, push, pull, track, crane, stationary, left, right, up, down, forward or backward: the original request already controls these. Do not change any requested movement, speed, duration, focus or composition. Do not invent cuts. Keep the setting physically coherent and the existing material textures photographic. Audio may only elaborate sounds explicitly requested. Keep additions under 90 words. Return only the supplementary prose."""

_LTX_CAMERA_WORDS = re.compile(r"\b(?:camera|pan(?:s|ning)?|tilt(?:s|ing)?|doll(?:y|ies|ying)|orbit\w*|zoom\w*|push\w*|pull\w*|track\w*|cran(?:e|ing)|stationary|static|locked|handheld|left|right|up|down|forward|backward|backwards|reverse|rotate\w*|rotation|refram\w*|close[- ]?up|wide[- ]?shot|angle|cut|cuts|cutting|transition\w*|shot|framing|composition|lens|focal|focus|speed|accelerat\w*|decelerat\w*|movement|motion)\b", re.I)
_LTX_PEOPLE_WORDS = re.compile(r"\b(?:person|people|actor\w*|human\w*|man|men|woman|women|child\w*|figure\w*|face\w*|skin|body|bodies|walk\w*|character\w*|animal\w*|dialogue|speech|voice\w*|music)\b", re.I)


def expand_ltx25(request, graph, cfg=None, timeout=None):
    """Preserve operator intent verbatim; add only environment continuity prose."""
    base = (request or "").strip()
    if not base:
        raise ValueError("Describe the shot before expanding it.")
    cfg = expander_config() if cfg is None else cfg
    referenced = any(isinstance(n, dict) and n.get("class_type") in ("LoadImage", "LoadImageMask") for n in (graph or {}).values())
    continuity = ("The reference environment remains spatially coherent as the requested changes unfold."
                  if referenced else "The environment keeps coherent spatial relationships and consistent lighting throughout the take.")
    fallback = base + (" " if base[-1:] in ".!?" else ". ") + continuity + " Fine surface detail remains natural and photographic."
    attempts = []
    if cfg.get("configured"):
        try:
            additions = _strip_fences(call_llm(LTX25_EXPANSION_RULES,
                "Mode: %s. Operator request: %s" % ("image-to-video with an environment reference" if referenced else "text-to-video", base),
                cfg, timeout=float(timeout or cfg.get("timeout") or EXPANDER_DEFAULT_TIMEOUT), temperature=0.2))
            if not additions or len(additions.split()) > 120 or _LTX_CAMERA_WORDS.search(additions) or _LTX_PEOPLE_WORDS.search(additions):
                raise ValueError("Expansion added camera/subject instructions or exceeded its scope; original intent retained")
            if re.search(r"(?:<[^>]+>|^\s*[#{\[]|subject_definitions:|detailed_description:)", additions, re.M):
                raise ValueError("Expansion returned another model's formatting")
            text = base + (" " if base[-1:] in ".!?" else ". ") + " ".join(additions.split())
            return text, {"source": "llm", "fallback": False, "issues": [], "detail": backend_label(cfg), "family": "LTX25"}
        except Exception as exc:
            attempts.append(str(exc)[:200])
    return fallback, {"source": "template", "fallback": bool(cfg.get("configured")), "issues": [],
                      "attempts": attempts, "family": "LTX25", "detail": "LTX 2.5 continuity prose; operator camera request retained"}


JUGGERNAUT_EXPANSION_RULES = """You expand a film crew's dictated environment request for Juggernaut XL v9, an SDXL still-image workflow.
The original request is kept verbatim at the start of the final positive prompt. Return ONLY 2-4 supplementary natural-language sentences for ONE photographic still, under 60 words. Do not return a prompt heading, tags, JSON, weighting syntax or a negative prompt.
Elaborate material texture, physical scale and detail already justified by the request. Preserve every constraint: the setting, camera position, viewing direction, framing, lens, depth of field, lighting, weather, color and exclusions. Do not add or restate camera choices or lighting choices in your supplement; those are already controlled by the original request. Do not invent terrain, props, people, actors, animals, vehicles or structures. If something was not specified, keep the description neutral rather than choose it for the operator.
This is NOT video. Do not introduce camera movement, animation, action sequences, durations, transitions, chronological beats, dialogue, audio or soundtracks. Never use H3 reference sections or LTX video phrasing. A requested drop of water or mist may be described as visible in a single instant. Keep the result physically plausible and photographic. Return only the supplementary still-image prose."""

_JUGGERNAUT_VIDEO_WORDS = re.compile(r"\b(?:video|animation|animat\w*|sequence|timeline|duration|second|seconds|minute|minutes|throughout|then|eventually|begins?|ends?|unfold\w*|audio|sound\w*|soundtrack|music|dialogue|speech|footsteps|continu(?:ous|ity)|take)\b", re.I)
_JUGGERNAUT_LIGHT_WORDS = re.compile(r"\b(?:sunlight|daylight|moonlight|neon|spotlight|sunrise|sunset|golden|warm|cool|blue|red|orange|green|purple|pink|yellow|white|black|night|day|bright|dark)\b", re.I)


def expand_juggernaut(request, cfg=None, timeout=None):
    """Expand environment still detail without altering the operator's constraints."""
    base = (request or "").strip()
    if not base:
        raise ValueError("Describe the environment before expanding it.")
    cfg = expander_config() if cfg is None else cfg
    joiner = " " if base[-1:] in ".!?" else ". "
    fallback = base + joiner + "Photographic material detail and physically coherent scale define the environment. Surface textures are natural and believable."
    attempts = []
    if cfg.get("configured"):
        try:
            additions = _strip_fences(call_llm(JUGGERNAUT_EXPANSION_RULES,
                "Operator's still-image request: " + base, cfg,
                timeout=float(timeout or cfg.get("timeout") or EXPANDER_DEFAULT_TIMEOUT), temperature=0.2))
            light_words = set(re.findall(r"\w+", base.lower()))
            if "night" in light_words:
                light_words.add("dark")
            if "blue" in light_words:
                light_words.add("cool")
            changed_light = any(word.lower() not in light_words
                                for word in _JUGGERNAUT_LIGHT_WORDS.findall(additions))
            if (not additions or len(additions.split()) > 80 or _LTX_CAMERA_WORDS.search(additions)
                    or _LTX_PEOPLE_WORDS.search(additions) or _JUGGERNAUT_VIDEO_WORDS.search(additions) or changed_light):
                raise ValueError("Still expansion added camera, lighting, subject or video instructions; original intent retained")
            if re.search(r"(?:<[^>]+>|^\s*[#{\[]|subject_definitions:|detailed_description:)", additions, re.M):
                raise ValueError("Still expansion returned incompatible model formatting")
            return base + joiner + " ".join(additions.split()), {
                "source": "llm", "fallback": False, "issues": [], "detail": backend_label(cfg), "family": "JUGGERNAUT"}
        except Exception as exc:
            attempts.append(str(exc)[:200])
    return fallback, {"source": "template", "fallback": bool(cfg.get("configured")), "issues": [],
                      "attempts": attempts, "family": "JUGGERNAUT", "detail": "Juggernaut environment still prose; operator constraints retained"}


def expand_for_family(family, graph, request, cfg=None, opts=None, **kwargs):
    """Select generation-model instructions independently of the configured LLM provider."""
    context = (opts or {}).get("camera_context") or ""
    if context and context not in request:
        request = request.rstrip() + "\n" + context
    if family == "MINIMAXH3":
        mode, refs = refs_from_graph(graph)
        if mode is None:
            raise ValueError("The selected H3 workflow has no supported reference mode.")
        return expand(mode, refs, request, duration_seconds(graph), opts or {}, cfg=cfg, **kwargs)
    if family == "LTX25":
        return expand_ltx25(request, graph, cfg=cfg, timeout=kwargs.get("timeout"))
    if family == "JUGGERNAUT":
        return expand_juggernaut(request, cfg=cfg, timeout=kwargs.get("timeout"))
    raise ValueError("Prompt expansion supports Juggernaut XL v9, MiniMax H3 and LTX 2.5 for this panel.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8-sig") as h:
            g = json.load(h)
        m, r = refs_from_graph(g)
        d = duration_seconds(g)
        req = sys.argv[2] if len(sys.argv) > 2 else "He turns and speaks."
    else:
        m, d, req = "ref2va", 5.17, sys.argv[1] if len(sys.argv) > 1 else "He turns and speaks."
        r = {"pictures": [{"index": 1, "role": "identity", "title": "IDENTITY CARD 1"}, {"index": 2, "role": "wardrobe", "title": "WARDROBE"}],
             "videos": [{"index": 1, "role": "source_edit"}, {"index": 2, "role": "depth"}], "audios": [{"index": 1, "role": "copy", "of_video": 1}]}
    out = translate(m, r, req, d)
    print(out)
    print("---- issues:", validate(out, m) or "none")
