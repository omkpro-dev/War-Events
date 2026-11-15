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


def passes_strict_rule(names):
    return len(distinct_outlets(names)) >= 3
