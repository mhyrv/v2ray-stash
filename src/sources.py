"""Read recent posts from Telegram. Every function returns [(datetime_utc, text)]."""
import asyncio
import os
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def scrape_web(name, cutoff, max_pages=30):
    """Public channels only. Walks https://t.me/s/<name> backwards until `cutoff`. No login needed."""
    posts, before = [], None
    for page in range(max_pages):
        url = f"https://t.me/s/{name}" + (f"?before={before}" if before else "")
        try:
            r = requests.get(url, headers=UA, timeout=20)
        except requests.RequestException as e:
            print(f"  [{name}] request failed: {e}")
            break
        if r.status_code != 200:
            print(f"  [{name}] HTTP {r.status_code}")
            break

        ids, hit_cutoff = [], False
        for m in BeautifulSoup(r.text, "html.parser").select("div.tgme_widget_message"):
            post, t = m.get("data-post"), m.select_one("a.tgme_widget_message_date time")
            if not post or not t:
                continue
            ids.append(int(post.rsplit("/", 1)[-1]))
            when = datetime.fromisoformat(t["datetime"])
            if when < cutoff:
                hit_cutoff = True
                continue
            parts = []
            for body in m.select("div.tgme_widget_message_text"):
                for br in body.find_all("br"):
                    br.replace_with("\n")
                parts.append(body.get_text())
                parts += [a["href"] for a in body.find_all("a", href=True)]  # hidden hyperlinks
            posts.append((when, "\n".join(parts)))

        if not ids:
            if page == 0:
                print(f"  [{name}] no posts visible (not a public channel, or its web preview is disabled)")
            break
        if hit_cutoff or min(ids) == before:
            break
        before = min(ids)
        time.sleep(1)
    return posts


def scrape_api(names, cutoff):
    """Groups / private chats / anything the logged-in Telegram account can read."""
    if not all(os.environ.get(k) for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION")):
        print("  api sources skipped: TG_API_ID / TG_API_HASH / TG_SESSION are not set")
        return []
    return asyncio.run(_scrape_api(names, cutoff))


async def _scrape_api(names, cutoff):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import MessageEntityTextUrl

    posts = []
    client = TelegramClient(StringSession(os.environ["TG_SESSION"]),
                            int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            print("  api sources skipped: the saved Telegram session is no longer valid, make a new one")
            return []
        numeric = lambda n: str(n).lstrip("-").isdigit()
        if any(numeric(n) for n in names):
            await client.get_dialogs()  # lets Telethon resolve numeric chat ids
        for name in names:
            try:
                async for m in client.iter_messages(int(name) if numeric(name) else name):
                    if m.date < cutoff:
                        break  # newest → oldest, so we're done with this chat
                    parts = [m.raw_text or ""]
                    parts += [e.url for e in (m.entities or []) if isinstance(e, MessageEntityTextUrl)]
                    posts.append((m.date, "\n".join(parts)))
            except Exception as e:
                print(f"  [{name}] failed: {e}")
    finally:
        await client.disconnect()
    return posts
