"""Is a headline geopolitical? Shared by the Wire ticker (fetch_rss_feeds.py) and the Feed
(news-feed/fetch_latest_reports.py) so both drop local crime, courts, accidents, sport and
celebrity stories.

A headline is kept when it mentions war / security / diplomacy terms (GEO) and is not a
domestic story (LOCAL) -- unless it also has a strong international signal (STRONG), e.g.
"Russia charges Swedish man with sabotage" stays, "Man charged after house fire" goes.
Standard library only.
"""
import re

# Plurals and -ed/-ing forms count too ("drones", "attacks", "sanctioned").
GEO = re.compile(
    r"\b(war|military|army|troop|missile|drone|strike|attack|sanction|diplomat|minister|president|"
    r"summit|treaty|talk|border|election|coup|protest|ceasefire|truce|nato|security|defen[cs]e|navy|naval|nuclear|"
    r"tariff|alliance|rebel|conflict|envoy|kill|force|invasion|invade|hostage|airstrike|shelling|bomb|"
    r"refiner(?:y|ies)|airspace|incursion|militant|insurgent|kremlin|pentagon|hamas|hezbollah|houthi|gaza|"
    r"sovereignty|annex|occupation|blockade|embargo|frigate|warship|fighter jet|interceptor|weapon|arms|"
    r"spy|espionage|sabotage|un security council|united nations|genocide|refugee|famine|junta|regime|oil|gas pipeline)"
    r"(?:s|es|ed|ing|ic)?\b", re.I)

# Domestic / non-geopolitical: crime, courts, accidents, weather, sport, entertainment.
LOCAL = re.compile(
    r"\b(charged|sentenced|jailed|convicted|acquitted|pleads?|guilty|trial|court|murder(?:ed|er)?|manslaughter|"
    r"stabb(?:ed|ing)|shooting|shooter|gunman|assault(?:ed)?|robbery|burglary|arson|criminal damage|house fire|"
    r"blaze|fire at|car crash|road crash|collision|drown(?:ed|ing)?|missing (?:man|woman|teen|girl|boy|child)|"
    r"police (?:say|said|hunt|seek|appeal)|inquest|coroner|execution|death row|"
    r"football|soccer|cricket|tennis|golf|olympic|world cup|premier league|nba|nfl|match|"
    r"celebrity|actor|actress|singer|album|film|movie|festival|royal baby|wedding|"
    r"weather|heatwave|storm|flood(?:s|ing)?|earthquake|recipe|lottery|school|playground|parents|teachers|nurses|junior doctors|strike action)\b", re.I)

# International signals that keep a story even if it trips LOCAL (spy trials, war-crimes courts...).
STRONG = re.compile(
    r"\b(spy|espionage|sabotage|treason|war crime|icc|international court|icj|terror(?:ism|ist)?|"
    r"russia|ukraine|china|taiwan|iran|israel|gaza|north korea|nato|kremlin|pentagon|hamas|hezbollah|houthi|"
    r"sanction|missile|drone|military|troops|army|navy)", re.I)


def is_geopolitical(title, trusted=False):
    """trusted=True for defence/security-only outlets: only the LOCAL check applies."""
    t = title or ""
    if LOCAL.search(t) and not STRONG.search(t):
        return False
    return trusted or bool(GEO.search(t))
