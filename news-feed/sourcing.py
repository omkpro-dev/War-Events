"""Outlet-count rules: how many different outlets reported a story.

Sister brands count as one outlet (Politico + Politico Europe, France 24 + its editions).
"""
import outlets

FAMILY = {"Politico Europe": "Politico", "SCMP": "South China Morning Post"}


def outlet_family(name):
    if name.startswith("France 24"):
        return "France 24"
    return FAMILY.get(name, name)


def distinct_outlets(names):
    seen = []
    for n in names:
        f = outlet_family(n)
        if f not in seen:
            seen.append(f)
    return seen


def passes_war_rule(names):
    fams = distinct_outlets(names)
    return len(fams) >= 3 or (len(fams) == 2 and all(f in outlets.TIER1 for f in fams))


# Outlets run by one government. For the stricter sections they count as one outlet, so a story carried only by
# one state's media never passes. (War keeps its own rule unchanged.)
STATE_MEDIA = {
    "Xinhua": "Chinese state media", "China Daily": "Chinese state media", "CGTN": "Chinese state media",
    "Global Times": "Chinese state media", "People's Daily": "Chinese state media",
    "TASS": "Russian state media", "RIA Novosti": "Russian state media", "RT": "Russian state media",
}


def passes_strict_rule(names):
    return len({STATE_MEDIA.get(f, f) for f in distinct_outlets(names)}) >= 3


def passes_economy_rule(names):
    """Economy: the strict rule, and at least one top-tier international newsroom among the outlets, so a story
    that only one country's business press carries (an IPO calendar, a local fund) stays out."""
    return passes_strict_rule(names) and any(outlet_family(n) in outlets.TIER1 for n in names)
