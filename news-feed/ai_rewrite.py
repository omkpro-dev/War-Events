"""Original-wording summaries for the Feed and the WIRE ticker.

Outlets' headlines and snippets are never published as written: each item is rewritten by Claude into one short
sentence of our own, and anything that still echoes the source (a long run of identical words) is dropped.
Standard library only.
"""
import json, os, re, urllib.request

KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_RUN = 5   # a summary may not share more than this many consecutive words with its source

SYSTEM = """You rewrite news items for a news aggregator so that no outlet's own wording is reproduced.

You get numbered items: the outlet, its headline and the opening words of the article. For each, write ONE original summary in your own words: a single plain, factual sentence of at most {words} words saying what happened.
Rules:
- Do not copy the headline's wording, and never reuse a run of more than four consecutive words from the input (names and numbers excepted).
- No direct quotes, no outlet names, no questions, no clickbait.
- Do not add any fact that is not in the input. Keep names, places and numbers accurate.
- Neutral tone, present or past tense as fits.

Return ONLY JSON: {{"0": "summary", "1": "summary", ...}} with one entry per item number."""


def _words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def echoes(summary, source):
    """True when the summary shares a run of more than MAX_RUN consecutive words with the source text."""
    s, src = _words(summary), _words(source)
    if len(s) <= MAX_RUN:
        return False
    grams = {tuple(src[i:i + MAX_RUN + 1]) for i in range(len(src) - MAX_RUN)}
    return any(tuple(s[i:i + MAX_RUN + 1]) in grams for i in range(len(s) - MAX_RUN))


def rewrite(entries, max_words=32):
    """entries: [{"outlet","headline","snippet"}] -> list of rewritten strings, None where it failed or still echoed the source."""
    out = [None] * len(entries)
    if not KEY or not entries:
        return out
    for start in range(0, len(entries), 25):
        chunk = entries[start:start + 25]
        lines = "\n".join("%d. [%s] %s | %s" % (i, e.get("outlet", ""), e["headline"][:240], (e.get("snippet") or "")[:300]) for i, e in enumerate(chunk))
        try:
            body = json.dumps({
                "model": MODEL, "max_tokens": 3000,
                "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
                "system": [{"type": "text", "text": SYSTEM.format(words=max_words), "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
                "messages": [{"role": "user", "content": lines}],
            }).encode()
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                res = json.loads(r.read())
            txt = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
            got = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception as ex:
            print("rewrite batch failed:", str(ex)[:120])
            continue
        for i, e in enumerate(chunk):
            t = str(got.get(str(i), "")).strip()
            if not t or len(t.split()) > max_words + 12:
                continue
            if echoes(t, e["headline"] + " " + (e.get("snippet") or "")):
                print("dropped (too close to the source):", t[:70])
                continue
            out[start + i] = t
    return out
