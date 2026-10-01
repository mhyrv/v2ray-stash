"""Real-delay test: run each config in its own Xray process and fetch a URL *through* it."""
import json
import os
import queue
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import requests

XRAY = os.environ.get("XRAY_BIN") or shutil.which("xray")
BASE_PORT = 20000


def _wait_port(port, proc, wait=4.0):
    """True once Xray's local SOCKS port accepts connections; False if Xray died or timed out."""
    end = time.time() + wait
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def _delay(port, url, timeout):
    """ms for a request through the proxy, or None. 1st request warms the tunnel up, 2nd is the number we report."""
    proxy = f"socks5h://127.0.0.1:{port}"          # socks5h: the proxy server resolves the hostname
    times = []
    with requests.Session() as s:
        s.proxies = {"http": proxy, "https": proxy}
        for _ in range(2):
            t0 = time.perf_counter()
            try:
                r = s.get(url, timeout=timeout, allow_redirects=False)
            except requests.RequestException:
                break
            if r.status_code not in (200, 204):
                break
            times.append(int((time.perf_counter() - t0) * 1000))
    return times[-1] if times else None


def run(outbounds, url, timeout, workers):
    """outbounds: {key: xray_outbound}. Returns {key: delay_ms} for the ones that really pass traffic."""
    if not XRAY:
        raise SystemExit("xray binary not found (put it on PATH or set XRAY_BIN)")
    ports = queue.Queue()
    for i in range(workers):
        ports.put(BASE_PORT + i)
    tmp = tempfile.mkdtemp()

    def one(item):
        key, outbound = item
        port = ports.get()
        try:
            cfg = os.path.join(tmp, f"{port}.json")
            with open(cfg, "w") as f:
                json.dump({"log": {"loglevel": "none"},
                           "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks",
                                         "settings": {"auth": "noauth", "udp": False}}],
                           "outbounds": [outbound]}, f)
            proc = subprocess.Popen([XRAY, "run", "-c", cfg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                return key, (_delay(port, url, timeout) if _wait_port(port, proc) else None)
            finally:
                proc.kill()
                proc.wait()
        except Exception:
            return key, None
        finally:
            ports.put(port)

    good = {}
    with ThreadPoolExecutor(workers) as ex:
        for i, (key, ms) in enumerate(ex.map(one, outbounds.items()), 1):
            if ms is not None:
                good[key] = ms
            if i % 100 == 0:
                print(f"  tested {i}/{len(outbounds)}, alive so far {len(good)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return good
