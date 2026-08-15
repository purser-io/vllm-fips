#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Verify the installed OpenCV is FIPS-safe and still able to decode video.

Published `opencv-python*` manylinux wheels bundle their own OpenSSL inside a
vendored FFmpeg. On a FIPS-enabled host that non-validated OpenSSL fails its
self-test while the module is being dlopen'd and calls ``abort()``::

    crypto/fips/fips.c:154: OpenSSL internal error: FATAL FIPS SELFTEST FAILURE
    Aborted (core dumped)

That is a process abort during ``import cv2``, not a catchable exception, so it
cannot be guarded at runtime -- it has to be kept out of the image. See
opencv/opencv-python#1184, #1191 and the (still unmerged) fixes in #1190/#1224.

The obvious workaround -- building OpenCV without FFmpeg -- removes the abort by
removing the feature: ``vllm/multimodal/video.py`` needs a *stream-buffered*
videoio backend for ``cv2.VideoCapture(BytesIO(data), backend, [])``, and
FFmpeg is the only one that provides it on Linux. So this script checks both
halves: no bundled OpenSSL, and video decoding still works.

The abort was diagnosed and reported by the OpenCV community; the upstream
issues and fixes referenced above are their work. This checker and the
accompanying wheel build are maintained by Purser in
https://github.com/purser-io/vllm-fips -- report problems with them there
rather than to the upstream vLLM or OpenCV projects.

Usage:
    python tools/check_opencv_fips.py [--require-ffmpeg] [--expect-version V]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

_CRYPTO_SO = re.compile(r"lib(ssl|crypto)(\.so|-[0-9a-f]{8,}\.so)", re.IGNORECASE)


def _fail(msg: str) -> None:
    sys.stdout.flush()
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_no_bundled_openssl(cv2_module) -> pathlib.Path:
    """No libssl/libcrypto shipped inside the installed OpenCV package tree.

    auditwheel places vendored shared objects in a sibling ``*.libs`` directory,
    so both the package dir and its parent are searched.
    """
    pkg_dir = pathlib.Path(cv2_module.__file__).resolve().parent
    roots = [pkg_dir]
    for sibling in pkg_dir.parent.glob("opencv_python*.libs"):
        roots.append(sibling)

    bundled = [
        p for root in roots for p in root.rglob("*") if _CRYPTO_SO.search(p.name)
    ]
    if bundled:
        _fail(
            "OpenCV ships a bundled OpenSSL, which aborts `import cv2` on a "
            "FIPS-enabled host:\n  " + "\n  ".join(str(p) for p in bundled)
        )
    print(f"OK   no bundled OpenSSL under {', '.join(str(r) for r in roots)}")
    return pkg_dir


def check_no_openssl_loaded_from_package(pkg_dir: pathlib.Path) -> None:
    """No OpenSSL mapped into this process *from within* the OpenCV package.

    A system OpenSSL loaded by `ssl`/`urllib3`/`cryptography` is fine and
    expected -- on a FIPS host that one is the validated module. Only a copy
    loaded out of the OpenCV install is a problem.
    """
    maps = pathlib.Path("/proc/self/maps")
    if not maps.exists():
        print("SKIP /proc/self/maps unavailable (non-Linux); static check only")
        return

    offenders = set()
    for line in maps.read_text().splitlines():
        path = line.split(" ", 5)[-1].strip()
        if not path.startswith("/") or not _CRYPTO_SO.search(pathlib.Path(path).name):
            continue
        # Anything under the OpenCV install (package dir or its *.libs sibling).
        if str(pkg_dir) in path or (".libs" in path and "opencv" in path):
            offenders.add(path)

    if offenders:
        _fail(
            "OpenSSL loaded from inside the OpenCV install:\n  "
            + "\n  ".join(sorted(offenders))
        )
    print("OK   no OpenSSL mapped from the OpenCV install")


def check_ffmpeg_and_stream_backend(cv2_module) -> None:
    """FFmpeg present *and* a usable stream-buffered backend.

    Mirrors OpenCVVideoBackendMixin.get_cv2_video_api() in
    vllm/multimodal/video.py so this gate fails for exactly the cases that
    would break video loading at runtime.
    """
    import cv2.videoio_registry as vr

    build_info = cv2_module.getBuildInformation()
    ffmpeg_line = next(
        (
            ln.strip()
            for ln in build_info.splitlines()
            if ln.strip().startswith("FFMPEG:")
        ),
        "FFMPEG: <not reported>",
    )
    if not re.search(r"FFMPEG:\s*YES", ffmpeg_line):
        _fail(
            f"OpenCV was built without FFmpeg ({ffmpeg_line}). vLLM's OpenCV "
            "video backend cannot decode without it -- this fixes FIPS by "
            "deleting video support."
        )
    print(f"OK   {ffmpeg_line}")

    api_pref = None
    for backend in vr.getStreamBufferedBackends():
        if not vr.hasBackend(backend):
            continue
        if not vr.isBackendBuiltIn(backend):
            _, abi, api = vr.getStreamBufferedBackendPluginVersion(backend)
            if abi < 1 or (abi == 1 and api < 2):
                continue
        api_pref = backend
        break

    if api_pref is None:
        _fail(
            "no usable stream-buffered videoio backend; "
            "cv2.VideoCapture(BytesIO(...), backend, []) in "
            "vllm/multimodal/video.py would fail"
        )
    print(f"OK   stream-buffered backend available: {vr.getBackendName(api_pref)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-ffmpeg",
        action="store_true",
        help="also assert FFmpeg and a stream-buffered backend are available",
    )
    parser.add_argument(
        "--expect-version",
        default=None,
        help="assert the installed opencv-python-headless distribution version",
    )
    args = parser.parse_args()

    # If a bundled non-FIPS OpenSSL is present on a FIPS host, this import is
    # where the process aborts (exit 134) -- the check is the import itself.
    import cv2

    if args.expect_version:
        from importlib.metadata import version

        actual = version("opencv-python-headless")
        if actual != args.expect_version:
            _fail(
                f"expected opencv-python-headless=={args.expect_version}, "
                f"got {actual} (a PyPI wheel may have won resolution)"
            )
        print(f"OK   distribution version {actual}")

    pkg_dir = check_no_bundled_openssl(cv2)
    check_no_openssl_loaded_from_package(pkg_dir)
    if args.require_ffmpeg:
        check_ffmpeg_and_stream_backend(cv2)

    print(f"PASS OpenCV {cv2.__version__} is FIPS-safe")


if __name__ == "__main__":
    main()
