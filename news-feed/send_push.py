"""Send a push notification to the War Events iPhone app for major new stories.

Runs in the "Update news stories" GitHub workflow after fetch_news.py.
Uses Firebase Cloud Messaging (HTTP v1), topic "breaking" -- every app that
turned alerts on is subscribed to it, so no device list is stored anywhere.

Rules (tune with env vars):
  PUSH_MIN_SCORE   only stories with score >= this (default 20, i.e. roughly
                   3+ independent outlets or 2 top-tier ones)
  PUSH_MAX_AGE_H   story must be newer than this many hours (default 3)
  PUSH_MAX_PER_DAY at most this many pushes in 24h (default 5)
  PUSH_GAP_MIN     at least this many minutes between pushes (default 60)
One push per run at most. Sent story ids are kept in news-feed/push_sent.json.

Needs the secret FIREBASE_SERVICE_ACCOUNT (the service-account JSON from
Firebase console > Project settings > Service accounts). Without it the
script does nothing.
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / os.environ.get("FEED_PATH", "key_developments.json")
STATE = ROOT / "news-feed" / "push_sent.json"
TOPIC = os.environ.get("PUSH_TOPIC", "breaking")
MIN_SCORE = int(os.environ.get("PUSH_MIN_SCORE", "20"))
MAX_AGE_H = float(os.environ.get("PUSH_MAX_AGE_H", "3"))
MAX_PER_DAY = int(os.environ.get("PUSH_MAX_PER_DAY", "5"))
GAP_MIN = float(os.environ.get("PUSH_GAP_MIN", "60"))
DRY_RUN = os.environ.get("PUSH_DRY_RUN") == "1"


def parse_time(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def load_state():
    try:
        st = json.loads(STATE.read_text())
    except Exception:
        st = {}
    st.setdefault("sent", [])      # [{id, at}]
    st.setdefault("seen", [])      # story ids already considered (never re-sent)
    return st


def access_token(sa_info):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    creds.refresh(Request())
    return creds.token


def send(sa_info, story):
    import requests
    place = clean(story.get("place", "")).title()
    title = place or "War Events"
    body = clean(story.get("headline", ""))
    msg = {
        "message": {
            "topic": TOPIC,
            "notification": {"title": title, "body": body},
            "data": {"story": str(story.get("id", ""))},
            "apns": {
                "headers": {"apns-priority": "10", "apns-collapse-id": str(story.get("id", ""))[:64]},
                "payload": {"aps": {"sound": "default", "thread-id": "breaking"}},
            },
        }
    }
    if DRY_RUN:
        print("DRY RUN, would send:", json.dumps(msg, ensure_ascii=False))
        return True
    url = f"https://fcm.googleapis.com/v1/projects/{sa_info['project_id']}/messages:send"
    r = requests.post(url, json=msg, timeout=20,
                      headers={"Authorization": f"Bearer {access_token(sa_info)}"})
    print("FCM", r.status_code, r.text[:300])
    return r.ok


def main():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
    if not raw and not DRY_RUN:
        print("FIREBASE_SERVICE_ACCOUNT not set - push disabled")
        return 0
    sa_info = json.loads(raw) if raw else {}

    stories = json.loads(FEED.read_text())
    st = load_state()
    now = time.time()
    first_run = not st["seen"]
    seen = set(st["seen"])
    recent = [s for s in st["sent"] if now - s["at"] < 24 * 3600]

    candidates = [
        s for s in stories
        if s.get("id") and s["id"] not in seen
        and s.get("score", 0) >= MIN_SCORE
        and now - parse_time(s.get("time", "")) < MAX_AGE_H * 3600
    ]
    candidates.sort(key=lambda s: (s.get("score", 0), s.get("time", "")), reverse=True)

    sent_one = None
    if first_run:
        print("first run: marking current stories as seen, nothing sent")
    elif not candidates:
        print("no new major stories")
    elif len(recent) >= MAX_PER_DAY:
        print(f"daily limit reached ({len(recent)}/{MAX_PER_DAY})")
    elif recent and now - max(s["at"] for s in recent) < GAP_MIN * 60:
        print("too soon since the last push")
    else:
        top = candidates[0]
        if send(sa_info, top):
            sent_one = top
            recent.append({"id": top["id"], "at": now})
            print("sent:", top.get("headline"))

    # Remember every major story we've now looked at, so a story that missed
    # its slot (limits) isn't pushed hours later when it's stale. Others stay
    # eligible in case their score rises as more outlets report it.
    for s in stories:
        if s.get("id") and (first_run or s.get("score", 0) >= MIN_SCORE):
            if first_run or s is sent_one or now - parse_time(s.get("time", "")) >= MAX_AGE_H * 3600:
                seen.add(s["id"])
    if sent_one:
        seen.add(sent_one["id"])
    st["seen"] = sorted(seen)[-2000:]
    st["sent"] = recent
    if not DRY_RUN:
        STATE.write_text(json.dumps(st, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
