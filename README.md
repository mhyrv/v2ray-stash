# v2ray-sub

A self-updating V2Ray subscription. Every 6 hours GitHub Actions:

1. reads the last 12 hours of the Telegram channels/groups listed in `config.yml`
2. collects `vmess://`, `vless://`, `trojan://` and `ss://` links, both from post text and from subscription links found in posts
3. starts each config in its own [Xray-core](https://github.com/XTLS/Xray-core) process and fetches a `generate_204` URL **through it** (a real-delay test, like "real delay" in v2rayN)
4. commits the ones that work, fastest first, to `output/`

| file | what it is |
|---|---|
| `output/sub.txt` | plain list, one link per line |
| `output/sub_base64.txt` | the same list base64-encoded (the classic subscription format) |
| `output/last_run.json` | counts from the last run |

## Setup

1. Create a **public** GitHub repo and push these files to it (private repos can't be used as a subscription URL without a token).
2. Edit `config.yml` and put your channels in `sources`.
3. Open the **Actions** tab, pick *update-subscription*, press **Run workflow**. Later runs happen on their own.
4. In your client add this as a subscription URL (replace the placeholders):

   ```
   https://raw.githubusercontent.com/<user>/<repo>/main/output/sub.txt
   ```

   If `raw.githubusercontent.com` is blocked for you, try `https://cdn.jsdelivr.net/gh/<user>/<repo>@main/output/sub.txt` (jsDelivr caches for a while).

## Groups and private channels (`mode: api`)

Telegram's public web preview only exists for **channels**. Groups, private chats and channels with preview disabled need a real login:

1. Get an `api_id` and `api_hash` at <https://my.telegram.org> → *API development tools*.
2. On your own computer: `pip install telethon`, then `python src/make_session.py`. Log in, copy the printed string.
3. In the repo: *Settings → Secrets and variables → Actions* → add `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`.
4. Join the group with that account and list it in `config.yml` with `mode: api` (username, or numeric id for private groups).

Use a spare Telegram account. The session string gives full access to the account, and Telegram may restrict accounts that log in from datacenter IPs.

## Run it locally

```
pip install -r requirements.txt
# install xray (https://github.com/XTLS/Xray-core/releases) and put it on PATH, or set XRAY_BIN=/path/to/xray
python src/main.py
```

## Good to know

- **The test runs on a GitHub server (USA), not on your connection.** A config that passes is alive and really forwards traffic, but a server or SNI that is blocked where you live can still pass here and fail for you, and the ms values are not your latency. Let your client re-test the subscription itself.
- **Supported:** vmess, vless (incl. Reality), trojan, shadowsocks, over tcp / ws / grpc / httpupgrade / xhttp / h2 / kcp. **Skipped:** hysteria2, tuic, ss with plugins, quic.
- Current Xray removed `allowInsecure`, so configs that only work with certificate checks off are dropped.
- With `keep_previous: true` last run's winners are re-tested each time, so the list does not shrink when channels are quiet. Dead ones fall out automatically.
- Each run commits, which also keeps GitHub from pausing the schedule after 60 days of repo inactivity. If it ever shows as disabled, re-enable it in the Actions tab.
- If the commit step fails with a 403, enable *Settings → Actions → General → Workflow permissions → Read and write*.
- Free configs from public channels are run by strangers who can see unencrypted traffic and metadata. Alive does not mean safe, so don't use them for anything sensitive.
