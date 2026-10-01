"""Turn vmess / vless / trojan / ss share links into Xray outbound objects.

Anything we can't translate (hysteria2, tuic, ss plugins, quic transport ...) returns None
and is simply skipped. `allowInsecure` is deliberately NOT passed on: current Xray removed it,
so links that depend on it fail the test, the same way they would in an up-to-date client.
"""
import base64
import json
from urllib.parse import parse_qs, unquote, urlsplit


def b64(s):
    """Lenient base64 / base64url decode to text."""
    s = "".join(s.split()).replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")


def _opts(q):
    """Normalise the many query-param spellings into one dict."""
    g = lambda k: q.get(k, "")
    return {
        "host": g("host"), "path": g("path"), "sni": g("sni") or g("peer"), "fp": g("fp"),
        "alpn": g("alpn"), "pbk": g("pbk"), "sid": g("sid"), "spx": g("spx"),
        "service": g("serviceName"), "mode": g("mode"), "htype": g("headerType") or "none",
        "seed": g("seed"), "extra": g("extra"),
    }


def _stream(net, sec, o):
    net = {"http": "h2", "splithttp": "xhttp", "mkcp": "kcp", "": "tcp"}.get(net, net)
    if sec not in ("", "none", "tls", "reality"):
        raise ValueError(f"unsupported security {sec}")
    s = {"network": net, "security": sec or "none"}
    if sec == "tls":
        t = {"serverName": o["sni"] or o["host"], "fingerprint": o["fp"] or "chrome"}
        if o["alpn"]:
            t["alpn"] = o["alpn"].split(",")
        s["tlsSettings"] = t
    elif sec == "reality":
        s["realitySettings"] = {"serverName": o["sni"], "fingerprint": o["fp"] or "chrome",
                                "publicKey": o["pbk"], "shortId": o["sid"], "spiderX": o["spx"]}

    path = o["path"] or "/"
    hosts = [h for h in o["host"].split(",") if h]
    if net == "ws":
        s["wsSettings"] = {"path": path, "headers": {"Host": o["host"]} if o["host"] else {}}
    elif net == "grpc":
        s["grpcSettings"] = {"serviceName": o["service"], "multiMode": o["mode"] == "multi"}
    elif net == "httpupgrade":
        s["httpupgradeSettings"] = {"path": path, "host": o["host"]}
    elif net == "xhttp":
        x = {"path": path, "host": o["host"], "mode": o["mode"] or "auto"}
        if o["extra"]:
            x["extra"] = json.loads(o["extra"])
        s["xhttpSettings"] = x
    elif net == "h2":
        s["httpSettings"] = {"path": path, "host": hosts}
    elif net == "kcp":
        k = {"header": {"type": o["htype"]}}
        if o["seed"]:
            k["seed"] = o["seed"]
        s["kcpSettings"] = k
    elif net == "tcp":
        if o["htype"] == "http":
            s["tcpSettings"] = {"header": {"type": "http", "request": {"path": [path], "headers": {"Host": hosts}}}}
    else:
        raise ValueError(f"unsupported transport {net}")
    return s


def _split(uri):
    """vless/trojan style: scheme://userinfo@host:port?query#name"""
    u = urlsplit(uri)
    if "@" not in u.netloc or not u.hostname or not u.port:
        raise ValueError("bad link")
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    return unquote(u.netloc.rsplit("@", 1)[0]), u.hostname, u.port, q


def _vless(uri):
    uid, host, port, q = _split(uri)
    user = {"id": uid, "encryption": q.get("encryption") or "none"}
    if q.get("flow"):
        user["flow"] = q["flow"]
    return {"protocol": "vless",
            "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
            "streamSettings": _stream(q.get("type", "tcp"), q.get("security", "none"), _opts(q))}


def _trojan(uri):
    password, host, port, q = _split(uri)
    return {"protocol": "trojan",
            "settings": {"servers": [{"address": host, "port": port, "password": password}]},
            "streamSettings": _stream(q.get("type", "tcp"), q.get("security", "tls"), _opts(q))}


def _vmess(uri):
    d = json.loads(b64(unquote(uri.split("://", 1)[1].split("#")[0])))
    net = d.get("net") or "tcp"
    q = {"host": d.get("host", ""), "path": d.get("path", ""), "sni": d.get("sni", ""),
         "fp": d.get("fp", ""), "alpn": d.get("alpn", ""), "headerType": d.get("type", "")}
    if net == "grpc":                      # vmess-json reuses its fields for grpc / kcp
        q["serviceName"], q["mode"] = d.get("path", ""), d.get("type", "")
    elif net == "kcp":
        q["seed"] = d.get("path", "")
    user = {"id": d["id"], "security": d.get("scy") or "auto"}
    return {"protocol": "vmess",
            "settings": {"vnext": [{"address": d["add"], "port": int(d["port"]), "users": [user]}]},
            "streamSettings": _stream(net, d.get("tls", ""), _opts(q))}


def _ss(uri):
    body = uri.split("://", 1)[1].split("#")[0]
    body, _, query = body.partition("?")
    if "plugin" in query:
        raise ValueError("ss plugins not supported")
    body = body.rstrip("/")
    if "@" in body:                        # ss://base64(method:pass)@host:port   or   ss://method:pass@host:port
        info, hostport = body.rsplit("@", 1)
        info = unquote(info)
        if ":" not in info:
            info = b64(info)
    else:                                  # legacy: ss://base64(method:pass@host:port)
        info, hostport = b64(body).rsplit("@", 1)
    method, password = info.split(":", 1)
    host, port = hostport.rsplit(":", 1)
    return {"protocol": "shadowsocks",
            "settings": {"servers": [{"address": host.strip("[]"), "port": int(port),
                                      "method": method, "password": password}]}}


def to_outbound(uri):
    """Xray outbound dict for a share link, or None if we can't (or don't) handle it."""
    fn = {"vmess": _vmess, "vless": _vless, "trojan": _trojan, "ss": _ss}.get(uri.split("://", 1)[0].lower())
    if not fn:
        return None
    try:
        return fn(uri)
    except Exception:
        return None
