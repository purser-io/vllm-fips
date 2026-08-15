# custom-wheels

Locally built wheels that the container images consume via `UV_FIND_LINKS`.
The `.whl` files are **not** committed (see `.gitignore`) -- they are
reproducible build outputs, not source.

## `opencv-python-headless` (FIPS)

### Why

The published `opencv-python*` manylinux wheels bundle their own OpenSSL
(1.1.1w) inside a vendored FFmpeg, shipped in `opencv_python_headless.libs/`.
On a FIPS-enabled host that non-validated OpenSSL fails its self-test while the
extension module is being `dlopen`'d and aborts the process:

```text
crypto/fips/fips.c:154: OpenSSL internal error: FATAL FIPS SELFTEST FAILURE
Aborted (core dumped)
```

Exit code 134, during `import cv2`. It is a process abort, not a Python
exception, so it cannot be caught or worked around at runtime.

Upstream reports: [opencv-python#1184][1184], [#1191][1191].
Upstream fixes: [#1190][1190] and [#1224][1224] -- **both still open**
(#1224 is `CONFLICTING`), so no released PyPI wheel contains the fix.

[1184]: https://github.com/opencv/opencv-python/issues/1184
[1191]: https://github.com/opencv/opencv-python/issues/1191
[1190]: https://github.com/opencv/opencv-python/pull/1190
[1224]: https://github.com/opencv/opencv-python/pull/1224

### Build

```bash
docker buildx build -f docker/Dockerfile.opencv-fips --platform linux/amd64 \
    --target export --output type=local,dest=custom-wheels .
```

This produces `opencv_python_headless-4.13.0.92+fips-*.whl`.

> **Bumping the version:** `opencv-python` tags are only the trailing component
> and do **not** imply the OpenCV minor version — tag `92` is 4.13.0.92 but tag
> `94` is 4.14.0**.94**. The build asserts its own output against
> `EXPECT_VERSION`, so a mismatch fails there; if you bump `OPENCV_PYTHON_REF`,
> update `EXPECT_VERSION`, `requirements/common.txt`, and both `UV_OVERRIDE`
> entries plus both `--expect-version` gates in `docker/Dockerfile`.

**Always pass `--platform` explicitly.** The wheel is architecture-specific and
buildx defaults to the host architecture, so running this on an arm64 machine
(Apple Silicon) silently yields an `aarch64` wheel that cannot satisfy the pin
in an x86_64 image — the build then fails at dependency resolution rather than
producing a broken image, but the error is easy to misread. Build on a native
runner; emulated cross-builds of OpenCV + FFmpeg are extremely slow. To support
both vLLM architectures, build once per platform and leave both wheels in this
directory — uv picks the one matching the target.

The `+fips` local version segment is deliberate: no PyPI release can satisfy
`opencv-python-headless == 4.13.0.92+fips`, so the `UV_OVERRIDE` entry in
`docker/Dockerfile` fails closed. A missing or stale wheel is a hard resolution
error rather than a silent fallback to the crashing upstream build.

Enforcement is in the Dockerfile, **not** in `requirements/common.txt`. That
file is shared with the CPU/ROCm/TPU/XPU requirement sets, which have no such
wheel, and `setup.py` derives the published wheel's `install_requires` from it —
pinning a local version there would break every non-CUDA image and make the
published vLLM wheel uninstallable from any index. `common.txt` keeps a plain
`>= 4.13.0` floor.

### What the build does differently

Upstream's fix relinks the vendored FFmpeg against the *system* OpenSSL. This
build goes further and configures FFmpeg with `--disable-openssl`
(plus `--disable-gnutls --disable-mbedtls` so configure cannot substitute
another TLS backend). FFmpeg only needs OpenSSL for TLS transports, and vLLM
never asks it to open a URL -- `vllm/multimodal/video.py` passes an in-memory
buffer to `cv2.VideoCapture(BytesIO(data), backend, [])`. So the FIPS trigger
is removed outright instead of being relocated to the host.

FFmpeg itself is **kept**. An OpenCV built without it reports `FFMPEG: NO` and
exposes no *stream-buffered* videoio backend, which is precisely what
`vllm/multimodal/video.py` requires -- that "fix" would resolve FIPS by
deleting video support. `tools/check_opencv_fips.py --require-ffmpeg` guards
against exactly that regression and runs in both the `vllm-base` and `test`
stages.

The wheel is built on the same Ubuntu release as `FINAL_BASE_IMAGE` and then
`auditwheel repair`ed, so it is self-contained and does not depend on the
runtime image shipping matching `libjpeg`/`libtiff` sonames.

### Verifying an existing wheel

```bash
python tools/check_opencv_fips.py --require-ffmpeg \
    --expect-version 4.13.0.92+fips
```

### Getting the wheels from CI (preferred)

`.github/workflows/opencv-fips-wheel.yml` builds both architectures on **native
GitHub runners** (`ubuntu-24.04` for x86_64, `ubuntu-24.04-arm` for aarch64) --
no QEMU, which would otherwise push an OpenCV + FFmpeg build into the
multi-hour range. Each job asserts the wheel targets the expected architecture,
re-runs the FIPS gate against the exported artifact in a clean interpreter, and
records a SHA256.

To populate this directory from a workflow run:

```bash
gh run download --repo purser-io/vllm-fips \
    --name opencv-fips-wheels --dir custom-wheels
sha256sum -c custom-wheels/SHA256SUMS
```

On a published release of `purser-io/vllm-fips` the wheels and `SHA256SUMS` are
attached as release assets.

Do not reintroduce the wheel as a committed binary -- the reproducible build
recipe plus a recorded digest is the auditable path.

## Attribution and reporting

The FIPS abort was diagnosed and reported by the OpenCV community; the analysis
and both candidate fixes are theirs ([#1184][1184], [#1191][1191], [#1190][1190],
[#1224][1224]). vLLM is developed by the [vLLM project][vllm]. What is
maintained here is narrower: a packaging variant that drops FFmpeg's TLS backend
instead of relinking it, plus the build, pinning, and verification around it.

This wheel and its tooling are maintained by **Purser** in
[`purser-io/vllm-fips`][fork].

| Issue | Where |
| --- | --- |
| This wheel, the recipe, the pinning, or the gate | Issues on [`purser-io/vllm-fips`][fork] |
| A vulnerability in any of the above | **Not a public issue** — GitHub → Security → *Report a vulnerability*, or <security@purser-io.io> |
| A genuine vLLM bug | [vllm-project/vllm][vllm-issues] |
| A genuine OpenCV / `opencv-python` bug | [opencv/opencv-python][cv-issues] |

Please do not file FIPS-packaging issues upstream — the wheel is not theirs to
fix, and duplicates add noise to the open PRs we want merged.

[fork]: https://github.com/purser-io/vllm-fips
[vllm]: https://github.com/vllm-project/vllm
[vllm-issues]: https://github.com/vllm-project/vllm/issues
[cv-issues]: https://github.com/opencv/opencv-python/issues
