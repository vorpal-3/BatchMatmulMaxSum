#!/usr/bin/env python3
"""Probe outbound HTTPS reachability using Python's OpenSSL stack.

Windows' schannel TLS stack is failing in this environment
(`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS` for git,
"基础连接已经关闭" for Invoke-WebRequest), while Python's OpenSSL stack works.
This tells us which hosts are genuinely reachable, independent of that bug.
"""
import ssl
import sys
import urllib.error
import urllib.request

HOSTS = [
    "https://gitcode.com",
    "https://gitcode.com/api/v5/repos/cann/asc-devkit",
    "https://cannjudge.cn",
    "https://github.com",
    "https://www.hiascend.com",
]

for url in HOSTS:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dsh-probe/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"OK   {resp.status:>4}  {url}")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code:>4}  {url}   (reachable, server said {exc.reason})")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL       {url}   {type(exc).__name__}: {exc}")

print(f"\npython ssl: {ssl.OPENSSL_VERSION}")
