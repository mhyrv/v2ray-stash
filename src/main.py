"""Telegram → extract v2ray configs → keep the ones that really work → write the subscription files."""
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import check
import convert
import extract
import sources

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def chat_name(raw):
    """'https://t.me/s/foo', '@foo' and 'foo' all become 'foo'; numeric ids pass through."""
    s = str(raw).strip()
    for prefix in ("https://", "http://", "t.me/s/", "t.me/", "telegram.me/"):
        s = s.removeprefix(prefix)
    return s.lstrip("@").split("/")[0].split("?")[0]


def main():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    hours = cfg.get("window_hours", 12)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    test, out = cfg.get("test", {}), cfg.get("output", {})

    # 1 ── read Telegram
    posts = []
    web = [chat_name(s["name"]) for s in cfg["sources"] if s.get("mode", "web") == "web"]
    api = [chat_name(s["name"]) for s in cfg["sources"] if s.get("mode") == "api"]
    for name in web:
        got = sources.scrape_web(name, cutoff)
        print(f"{name}: {len(got)} posts in the last {hours}h")
        posts += got
    if api:
        got = sources.scrape_api(api, cutoff)
        print(f"api sources: {len(got)} posts in the last {hours}h")
        posts += got
    posts.sort(key=lambda p: p[0], reverse=True)          # newest first

    # 2 ── pull configs out of the posts, and out of any subscription links in them
    uris, links = [], []
    for _, text in posts:
        uris += extract.uris_in(text)
        links += extract.sub_links_in(text)
    direct = len(uris)
    if cfg.get("follow_subscription_links", True):
        links = list(dict.fromkeys(links))[:100]
        with ThreadPoolExecutor(8) as ex:
            for body in ex.map(extract.fetch_text, links):
                uris += extract.uris_in_body(body)
    print(f"found {direct} configs in posts + {len(uris) - direct} via {len(links)} links")

    # 3 ── last run's winners get re-tested too (they go first, so they survive the candidate cap)
    sub_file = OUT / "sub.txt"
    prev = []
    if out.get("keep_previous", True) and sub_file.exists():
        prev = [l.strip() for l in sub_file.read_text(encoding="utf-8").splitlines() if l.strip()]

    # 4 ── translate to Xray outbounds; de-duplicate on the settings (the remark/name is ignored)
    cand, skipped = {}, 0
    for uri in prev + uris:
        outbound = convert.to_outbound(uri)
        if outbound is None:
            skipped += 1
            continue
        cand.setdefault(json.dumps(outbound, sort_keys=True), (uri, outbound))
    cand = dict(list(cand.items())[: test.get("max_candidates", 2500)])
    print(f"{len(cand)} unique candidates ({skipped} skipped: unsupported protocol or malformed)")

    # 5 ── real-delay test
    delays = check.run({k: ob for k, (_, ob) in cand.items()},
                       test.get("url", "http://www.gstatic.com/generate_204"),
                       test.get("timeout", 8), test.get("workers", 30))
    fast = {k: ms for k, ms in delays.items() if ms <= out.get("max_delay_ms", 300)}
    ranked = sorted(fast, key=fast.get)[: out.get("max_configs", 300)]
    print(f"{len(delays)} alive, publishing {len(ranked)}")
    if not ranked:
        sys.exit("nothing passed the delay test - leaving the previous output untouched")

    # 6 ── write
    lines = [cand[k][0] for k in ranked]
    OUT.mkdir(exist_ok=True)
    text = "\n".join(lines) + "\n"
    (OUT / "sub.txt").write_text(text, encoding="utf-8")
    (OUT / "sub_base64.txt").write_text(base64.b64encode(text.encode()).decode(), encoding="utf-8")
    (OUT / "last_run.json").write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_hours": hours,
        "posts_scanned": len(posts),
        "candidates_tested": len(cand),
        "alive": len(delays),
        "published": len(lines),
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
