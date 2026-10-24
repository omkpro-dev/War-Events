"""Push key_developments.json to the Vandict event store.

Runs as the last step of the warevents "Update news stories" workflow. Standard library
only, so the workflow installs nothing. It never fails the workflow: whatever happens
it exits 0 and prints one line. It never prints the key.

Environment:
  VANDICT_INGEST_URL  full ingest URL, e.g. https://<host>/v1/ingest/legacy-key-developments
  VANDICT_INGEST_KEY  the ingest key (a GitHub secret)
  FEED_PATH           file to send (default key_developments.json)
"""
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv: list[str] | None = None) -> int:
    url = os.environ.get("VANDICT_INGEST_URL", "").strip()
    key = os.environ.get("VANDICT_INGEST_KEY", "").strip()
    if not url or not key:
        print("vandict: skipped (no VANDICT_INGEST_URL/KEY)")
        return 0
    try:
        with open(os.environ.get("FEED_PATH", "key_developments.json"), "rb") as f:
            body = f.read()
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "warevents-pipeline/1",
        })
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        print("vandict: " + " ".join(f"{k}={result.get(k)}" for k in ("inserted", "updated", "unchanged", "skipped")))
    except urllib.error.HTTPError as e:
        print(f"vandict: push failed (HTTP {e.code})")
    except Exception as e:  # noqa: BLE001 - must never fail the workflow
        print(f"vandict: push failed ({type(e).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
