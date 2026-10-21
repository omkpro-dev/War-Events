"""Writes the "Geopolitical overview" for every country in data/country_stats.json with Claude.

Each overview names the country's real, longstanding geopolitical issues: territorial
disputes and claims (e.g. China and Taiwan), rivalries, separatist or frozen conflicts,
key alliances and dependencies. Grounded with the partners / adversaries / conflicts /
blocs already in the data file.

Runs from .github/workflows/update-profiles.yml (needs the ANTHROPIC_API_KEY secret).
Only countries without a current overview are written, MAX_NEW per run, so it costs
almost nothing after the first pass. Bump OVERVIEW_V to rewrite them all.
Standard library only.
"""
import json, os, re, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS = os.path.join(ROOT, "data", "country_stats.json")
NAMES = json.load(open(os.path.join(ROOT, "news-feed", "country_names.json"), encoding="utf-8"))
ISO2 = json.load(open(os.path.join(ROOT, "news-feed", "country_iso2.json"), encoding="utf-8"))  # name -> ISO2
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_NEW = int(os.environ.get("OVERVIEW_MAX", "250"))
OVERVIEW_V = 1

CODE2NAME = {}
for _n, _c in ISO2.items():   # first entry per code is the proper country name (later ones are aliases)
    CODE2NAME.setdefault(_c.lower(), _n)

PROMPT = """You write the "Geopolitical overview" box on a world-affairs map site.

Country: {name}
From our data (may be incomplete): adversaries: {adv}; armed conflicts with: {conf}; key partners: {part}; blocs: {blocs}; note: {tag}

Write 2-3 sentences, 45-70 words, plain English, neutral and factual, about this country's LONGSTANDING geopolitical issues:
- territorial disputes, claims and contested borders, naming both sides (e.g. "China claims Taiwan and has not ruled out force", "India and Pakistan both claim Kashmir");
- core rivalries and security threats, separatist or frozen conflicts, occupied or breakaway territory;
- the alliances or powers it relies on, and key resource or trade leverage (oil, gas, straits, rare minerals).
Lead with the single most important issue. Be specific (name the places and countries). No history lessons, no statistics, no dates of recent events, no opinion, no "In conclusion". If the country has few disputes, say what actually shapes its position (neighbours, aid, migration, climate, a big power's influence).

Style examples:
- China: "China claims Taiwan as its territory and has not ruled out force to take it, making the Taiwan Strait its central flashpoint. It contests most of the South China Sea with Vietnam, the Philippines and others, and has an unresolved Himalayan border with India, all amid strategic rivalry with the United States."
- Japan: "The Taiwan Strait and an assertive China in the East China Sea, including the disputed Senkaku Islands, are Japan's central security concerns. North Korean missiles and a territorial dispute with Russia over the Kuril Islands add pressure, and Japan relies on its alliance with the United States."

Return ONLY the overview text."""


def names(codes):
    out = [CODE2NAME.get(str(c).lower(), str(c).upper()) for c in (codes or [])][:6]
    return ", ".join(out) or "none listed"


def ask(name, c):
    body = json.dumps({
        "model": MODEL, "max_tokens": 300,
        "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": PROMPT.format(
            name=name, adv=names(c.get("adversaries")), conf=names(c.get("conflicts")),
            part=names(c.get("partners")), blocs=", ".join(c.get("blocs", [])[:6]) or "none listed",
            tag=c.get("specialTag") or "none")}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    txt = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()
    txt = re.sub(r"\s+", " ", txt.strip('"\' \n'))
    return txt if 120 <= len(txt) <= 700 else ""


def main():
    if not KEY:
        print("ANTHROPIC_API_KEY not set; skipping overviews")
        return
    data = json.load(open(STATS, encoding="utf-8"))
    C = data["countries"]
    new = 0
    for cid, name in NAMES.items():
        c = C.setdefault(cid, {})
        if c.get("overviewV") == OVERVIEW_V and c.get("overview"):
            continue
        if new >= MAX_NEW:
            break
        try:
            t = ask(name, c)
        except Exception as e:
            print("failed", name, e)
            time.sleep(2)
            continue
        if t:
            c["overview"], c["overviewV"] = t, OVERVIEW_V
            new += 1
        time.sleep(0.3)
    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("overviews written:", new)


if __name__ == "__main__":
    main()
