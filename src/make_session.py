"""Run this ONCE on your own machine to log in to Telegram and print a session string.

    pip install telethon
    python src/make_session.py

Put the printed string in the GitHub secret TG_SESSION. Treat it like a password: anyone who has it
can act as that Telegram account. Use a spare account, not your main one.
"""
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("api_id (from https://my.telegram.org): "))
api_hash = input("api_hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:   # asks for phone number + login code
    print("\nTG_SESSION =\n" + client.session.save())
