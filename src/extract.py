"""Find v2ray configs in text, and read configs out of subscription links."""
import re
from urllib.parse import urlsplit

import requests

from convert import b64

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

URI_RE = re.compile(r"(?<![A-Za-z0-9])(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic)://[^\s<>\"'`]+", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)
TRAILING = ".,;:!?)]}»«\u200e\u200f"
SKIP_HOSTS = ("t.me", "telegram.me", "telegram.org", "instagram.com", "youtube.com", "youtu.be",
              "twitter.com", "x.com", "facebook.com", "tiktok.com", "wa.me", "play.google.com", "apps.apple.com")
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".apk", ".zip", ".exe", ".dmg", ".pdf")


def uris_in(text):
    """Every config-looking link in a blob of text."""
    return [u.rstrip(TRAILING) for u in URI_RE.findall(text)]


def sub_links_in(text):
    """http(s) links that might be subscriptions (everything except social sites / media files)."""
    out = []
    for u in URL_RE.findall(text):
        u = u.rstrip(TRAILING)
        try:
            parts = urlsplit(u)
        except ValueError:
            continue
        host = (parts.hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in SKIP_HOSTS):
            continue
        if parts.path.lower().endswith(SKIP_EXT):
            continue
        out.append(u)
    return out


def fetch_text(url, limit=3_000_000):
    try:
        with requests.get(url, headers=UA, timeout=15, stream=True) as r:
            if r.status_code != 200:
                return ""
            buf = b""
            for chunk in r.iter_content(65536):
                buf += chunk
                if len(buf) > limit:
                    return ""
            return buf.decode("utf-8", "ignore")
    except requests.RequestException:
        return ""


def uris_in_body(body):
    """Configs inside a subscription body: plain list first, then whole-body base64."""
    found = uris_in(body)
    if found:
        return found
    try:
        return uris_in(b64(body))
    except Exception:
        return []
