"""Token usage + estimated cost for the Claude calls a bot makes in one run.

Call record(out) with each parsed /v1/messages response; when the script exits, one line per model
is printed to the run log, e.g.

  [usage] enrich_stories claude-haiku-5-5 calls=3 in=2,410 cache_read=2,700 cache_write=900 out=1,260 searches=0 cost=$0.0012

Prices are list prices per million tokens (cache reads 0.1x input, cache writes 1.25x for 5 min /
2x for 1 hour, web search $10 per 1,000). Haiku 5.5 prompts over 100K tokens cost more; none of
ours come close.
"""
import atexit, os, sys

PRICES = {   # model -> (input, output) $ per million tokens
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
SEARCH = 0.01
_runs = {}


def record(out):
    """Add one API response's usage to this run's totals; never raises."""
    try:
        u = out.get("usage") or {}
        t = _runs.setdefault(out.get("model") or "?", dict(calls=0, inp=0, read=0, w5=0, w1=0, out=0, searches=0))
        t["calls"] += 1
        t["inp"] += u.get("input_tokens") or 0
        t["read"] += u.get("cache_read_input_tokens") or 0
        cc = u.get("cache_creation") or {}
        if cc:
            t["w5"] += cc.get("ephemeral_5m_input_tokens") or 0
            t["w1"] += cc.get("ephemeral_1h_input_tokens") or 0
        else:
            t["w5"] += u.get("cache_creation_input_tokens") or 0
        t["out"] += u.get("output_tokens") or 0
        t["searches"] += (u.get("server_tool_use") or {}).get("web_search_requests") or 0
    except Exception:
        pass


def cost(model, t):
    p_in, p_out = next((v for k, v in PRICES.items() if model.startswith(k)), (0, 0))
    return (t["inp"] * p_in + t["read"] * p_in * 0.1 + t["w5"] * p_in * 1.25 + t["w1"] * p_in * 2
            + t["out"] * p_out) / 1e6 + t["searches"] * SEARCH


@atexit.register
def _report():
    name = os.path.splitext(os.path.basename(sys.argv[0] or "bot"))[0]
    for model, t in _runs.items():
        print(f"[usage] {name} {model} calls={t['calls']} in={t['inp']:,} cache_read={t['read']:,} "
              f"cache_write={t['w5'] + t['w1']:,} out={t['out']:,} searches={t['searches']} cost=${cost(model, t):.4f}")
