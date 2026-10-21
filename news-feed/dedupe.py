"""Shared "is this the same story?" check, used by every feed script so one event
reported by several outlets (BBC, RT, Xinhua...) shows once, not once per source.

Standard library only. Import with:
    import sys, os; sys.path.insert(0, os.path.join(<repo root>, "news-feed"))
    from dedupe import same_story, dedupe
"""
import re

STOP = set("""a an the and or but of to in on at for from by with as is are was were be been
has have had will would could should may might can into over after before about amid says said
say new news live latest update updates report reports reported video watch how why what who
its it this that these those their they them he she his her we our you your not no than more
most also just still very up down out off two three one first last week day days year years
amid against between under during while""".split())

# Same thing, different wording across outlets.
SYN = {
    "kyiv": "ukraine", "kiev": "ukraine", "ukrainian": "ukraine", "kremlin": "russia", "moscow": "russia",
    "russian": "russia", "putin": "russia", "beijing": "china", "chinese": "china", "xi": "china",
    "washington": "us", "american": "us", "usa": "us", "pentagon": "us", "trump": "us",
    "tehran": "iran", "iranian": "iran", "israeli": "israel", "idf": "israel", "netanyahu": "israel",
    "gazan": "gaza", "palestinian": "gaza", "hamas": "gaza", "taipei": "taiwan", "pyongyang": "nkorea",
    "british": "uk", "britain": "uk", "london": "uk", "drones": "drone", "uav": "drone", "uavs": "drone",
    "missiles": "missile", "rockets": "missile", "rocket": "missile", "strikes": "strike", "airstrike": "strike",
    "airstrikes": "strike", "struck": "strike", "attacks": "attack", "attacked": "attack", "killed": "kill",
    "kills": "kill", "dead": "kill", "deaths": "kill", "truce": "ceasefire", "talks": "talk", "troops": "troop",
    "soldiers": "troop", "forces": "troop", "sanctions": "sanction", "tariffs": "tariff",
}


def _stem(w):
    w = SYN.get(w, w)
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    return SYN.get(w, w)


def tokens(title):
    words = re.findall(r"[a-z0-9]+", (title or "").lower().replace("'", ""))
    return {_stem(w) for w in words if (len(w) > 2 or w.isdigit() or w in ("us", "uk", "un", "eu")) and w not in STOP}


def same_story(a, b, same_place=False):
    """a, b: headline strings or token sets."""
    ta = a if isinstance(a, set) else tokens(a)
    tb = b if isinstance(b, set) else tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    n = len(inter)
    jac = n / len(ta | tb)
    ovl = n / min(len(ta), len(tb))
    nums = {t for t in inter if t.isdigit()}
    if jac >= 0.45:
        return True
    if n >= 3 and ovl >= 0.6:
        return True
    if nums and n >= 3:                     # "360 drones" in both = same event
        return True
    if same_place and (jac >= 0.25 or (n >= 2 and ovl >= 0.5)):
        return True
    return False


def dedupe(items, title=lambda x: x["title"], limit=None):
    """Keep the first of each story (sort best/newest first before calling)."""
    out, seen = [], []
    for it in items:
        tk = tokens(title(it))
        if any(same_story(tk, s) for s in seen):
            continue
        seen.append(tk)
        out.append(it)
        if limit and len(out) >= limit:
            break
    return out
