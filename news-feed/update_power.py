"""Monthly refresh of Power > Core (data/power.json).

1. Purchasing power parity factors for military spending (World Bank, no key needed).
2. Spheres of influence, strategic buffers, leverage points and rivalries: Claude reviews each
   section against the latest reporting (web search) and returns it with only the changes the
   news supports. Every reply is checked (same shape, real country codes, sources as links)
   before it replaces the old section, so a bad reply can never break the page.
Military figures (SIPRI, Global Firepower, FAS) are yearly publications and are left as they are.
"""
import json, os, re, time, urllib.request
from datetime import date
import usage   # prints this run's token use and cost to the log

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(os.path.dirname(HERE), "data", "power.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
UA = {"User-Agent": "Mozilla/5.0 (compatible; WarEvents/1.0; +https://www.warevents.com)"}


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.loads(r.read())
        except Exception:
            if i == 2:
                raise
            time.sleep(5)


def refresh_ppp(d):
    def latest(ind):
        rows = get(f"https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&mrnev=1&per_page=400")
        return {x["country"]["id"]: x["value"] for x in (rows[1] or []) if x["value"]}
    ppp, usd = latest("NY.GDP.MKTP.PP.CD"), latest("NY.GDP.MKTP.CD")
    n = 0
    for c, m in d.get("military", {}).items():
        if ppp.get(c) and usd.get(c):
            m["ppp"] = round(ppp[c] / usd[c], 3); n += 1
    print("ppp factors", n)


def ask(prompt, searches=8):
    messages = [{"role": "user", "content": prompt}]
    for _ in range(5):
        body = json.dumps({"model": MODEL, "max_tokens": 16000, "messages": messages,
                           "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": searches}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.loads(r.read())
            usage.record(out)
        if out.get("stop_reason") == "pause_turn":
            messages.append({"role": "assistant", "content": out["content"]}); continue
        return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    return ""


def first_json(txt):
    for o, c in (("{", "}"), ("[", "]")):
        i, j = txt.find(o), txt.rfind(c)
        if i >= 0 and j > i:
            try:
                return json.loads(txt[i:j + 1])
            except ValueError:
                pass
    return None


CC = re.compile(r"^[A-Z]{2}$")
def codes_ok(v):
    return isinstance(v, list) and all(isinstance(x, str) and CC.match(x) for x in v)
def text_ok(v, n=400):
    return isinstance(v, str) and 0 < len(v) <= n
def src_ok(v):
    return isinstance(v, list) and all(isinstance(u, str) and u.startswith("http") and "wikipedia.org" not in u for u in v)


def valid(name, old, new):
    if type(new) is not type(old):
        return False
    if name == "spheres":
        if set(new) - set(old):           # no new powers invented
            return False
        return all(codes_ok(x.get("core", [])) and codes_ok(x.get("strong", [])) and codes_ok(x.get("contested", []))
                   and text_ok(x.get("note")) and src_ok(x.get("sources", [])) for x in new.values())
    if name == "buffers":
        return len(new) >= len(old) - 3 and all(CC.match(str(b.get("cc", ""))) and codes_ok(b.get("between")) and text_ok(b.get("note")) and src_ok(b.get("sources", [])) for b in new)
    if name == "leverage":
        return len(new) >= len(old) - 4 and all(CC.match(str(v.get("holder", ""))) and codes_ok(v.get("over")) and text_ok(v.get("via"), 90)
                                                 and text_ok(v.get("note")) and v.get("kind") in ("chokepoint", "energy", "minerals", "water", "finance", "technology", "food")
                                                 and src_ok(v.get("sources", [])) for v in new)
    if name == "rivalries":
        return len(new) >= len(old) - 3 and all(CC.match(str(r.get("a", ""))) and CC.match(str(r.get("b", ""))) and text_ok(r.get("note")) for r in new)
    return False


PROMPT = """You maintain the "{title}" section of War Events, a geopolitics website. Today is {today}.
Here is the current data (JSON):
{data}

Search the latest reporting (last few months) from reliable outlets and think tanks (Reuters, AP, BBC, FT, CSIS, IISS, Chatham House, CFR, Carnegie, Crisis Group...). Never use Wikipedia.
Return the SAME JSON structure with only the changes the reporting clearly supports: move a country between lists, add or remove an entry, rewrite a note that is out of date, add the new source links.
Keep everything that is still true unchanged. Notes: plain English, one or two sentences, no capital-letter words. Country codes: ISO 3166-1 alpha-2 uppercase.
Reply with the JSON only."""
TITLES = {"spheres": "Spheres of influence (for each power: core, strong and contested countries)", "buffers": "Strategic buffer states",
          "leverage": "Leverage points (chokepoints, energy, minerals, water, finance, technology, food)", "rivalries": "Great-power and regional rivalries"}


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    try:
        refresh_ppp(d)
    except Exception as e:
        print("ppp failed", e)
    if KEY:
        for name in ("spheres", "buffers", "leverage", "rivalries"):
            old = d.get(name)
            if not old:
                continue
            try:
                new = first_json(ask(PROMPT.format(title=TITLES[name], today=date.today().isoformat(), data=json.dumps(old, ensure_ascii=False))))
            except Exception as e:
                print(name, "failed", e); continue
            if new is not None and valid(name, old, new):
                d[name] = new; print(name, "updated")
            else:
                print(name, "reply rejected, kept as it was")
    else:
        print("ANTHROPIC_API_KEY not set; only PPP refreshed")
    d["updated"] = date.today().isoformat()
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
