#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Verify the image's OpenSSL works, and is restricted, in FIPS mode.

Run with FIPS mode on (a fips=1 kernel, or OPENSSL_FORCE_FIPS_MODE=1, which
Ubuntu's OpenSSL treats the same way), after
docker/entrypoints/vllm-fips-entrypoint.sh has configured OpenSSL. Without
the FIPS provider, Ubuntu's OpenSSL cannot create a TLS context in FIPS mode,
so vLLM fails while importing aiohttp.

Maintained by Purser in https://github.com/purser-io/vllm-fips.

Usage:
    vllm-fips-entrypoint python3 tools/check_fips_runtime.py [--expect-provider V]
    python3 tools/check_fips_runtime.py   # e.g. via `docker exec`, after startup
"""

from __future__ import annotations

import argparse
import hashlib
import os
import ssl
import subprocess
import sys


def _fail(msg: str) -> None:
    sys.stdout.flush()
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_provider(expect_version: str) -> None:
    out = subprocess.run(
        ["openssl", "list", "-providers"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # "  <name>" starts a provider; "    <key>: <value>" lines describe it.
    providers: dict[str, dict[str, str]] = {}
    for line in out.splitlines():
        if line.startswith("    ") and providers:
            key, _, value = line.strip().partition(": ")
            providers[next(reversed(providers))][key] = value
        elif line.startswith("  "):
            providers[line.strip()] = {}
    fips = providers.get("fips", {})
    if fips.get("status") != "active":
        _fail(f"OpenSSL FIPS provider is not active:\n{out}")
    if fips.get("version") != expect_version:
        _fail(f"expected FIPS provider {expect_version}:\n{out}")
    conf = os.environ.get("OPENSSL_CONF", "system openssl.cnf")
    print(f"OK   FIPS provider {expect_version} active ({conf})")


def check_tls() -> None:
    ctx = ssl.create_default_context()
    print(f"OK   TLS context created with {ssl.OPENSSL_VERSION}")
    try:
        ctx.set_ciphers("CHACHA20")
    except ssl.SSLError:
        print("OK   non-approved TLS cipher (ChaCha20) rejected")
    else:
        _fail("ChaCha20 accepted: TLS is not restricted to the FIPS provider")


def check_hashlib() -> None:
    try:
        hashlib.md5(b"x")
    except ValueError:
        print("OK   md5 refused for security use")
    else:
        _fail("md5 allowed: hashlib is not FIPS-enforcing")
    hashlib.md5(b"x", usedforsecurity=False)
    hashlib.sha256(b"x")
    print("OK   md5(usedforsecurity=False) and sha256 work")


def check_vllm_imports() -> None:
    import vllm
    from vllm.entrypoints.openai import api_server  # noqa: F401  (aiohttp, ssl)

    print(f"OK   vllm {vllm.__version__} and its API server import")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-provider", default="3.1.2")
    parser.add_argument(
        "--skip-vllm", action="store_true", help="skip the vLLM import check"
    )
    args = parser.parse_args()

    check_provider(args.expect_provider)
    check_tls()
    check_hashlib()
    if not args.skip_vllm:
        check_vllm_imports()
    print("PASS OpenSSL is FIPS-mode capable")


if __name__ == "__main__":
    main()
