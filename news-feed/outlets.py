"""Outlet ranking shared by the Events (fetch_news.py) and Feed (fetch_latest_reports.py) scripts.

Bigger, more established newsrooms get more weight; smaller or very high-volume
outlets get less, and are capped so they can't flood a list.
Edit the tiers below to move an outlet up or down. Anything not listed counts as tier 3.
Standard library only.
"""

TIER1 = {   # major international newsrooms and wire services
    "Reuters", "AP", "BBC News", "Financial Times", "Bloomberg", "The Guardian",
    "The New York Times", "The Washington Post", "The Wall Street Journal", "The Economist",
    "Al Jazeera", "NPR", "DW", "France 24", "Le Monde", "Sky News", "Politico Europe", "Politico",
}
TIER2 = {   # respected regional / specialist outlets
    "CNN", "Kyiv Independent", "Times of Israel", "SCMP", "South China Morning Post", "Nikkei Asia",
    "Japan Times", "Yonhap", "The National", "Arab News", "Asharq Al-Awsat", "Al-Monitor",
    "Middle East Eye", "The Diplomat", "Defense News", "NK News", "RFI Africa", "France 24 Africa",
    "Africanews", "Meduza", "The Moscow Times", "Ukrainska Pravda", "The New Arab", "Radio Dabanga",
    "Premium Times", "Daily Maverick", "CNA", "The Irrawaddy", "Rappler", "El País", "Balkan Insight",
    "OC Media", "Euronews",
}
# Tier 3: everything else, e.g. The Hindu, Dawn, Daily Sabah, DefenceTalk, and the more partisan or
# single-country outlets: Iran International, Jerusalem Post, Taipei Times, Mexico News Daily,
# Buenos Aires Times, Notes from Poland.

WEIGHT = {1: 4.0, 2: 3.0, 3: 1.5}   # credit an outlet adds to a story's score
CAP = {1: None, 2: 5, 3: 2}         # max items per outlet in one list (None = no limit)


def tier(outlet):
    if outlet in TIER1:
        return 1
    if outlet in TIER2:
        return 2
    return 3


def weight(outlet):
    return WEIGHT[tier(outlet)]


def cap(outlet):
    return CAP[tier(outlet)]


def apply_caps(items, outlet_of):
    """Keep items in order, dropping any beyond their outlet's per-list cap."""
    seen, out = {}, []
    for it in items:
        o = outlet_of(it)
        c = cap(o)
        if c is not None and seen.get(o, 0) >= c:
            continue
        seen[o] = seen.get(o, 0) + 1
        out.append(it)
    return out
