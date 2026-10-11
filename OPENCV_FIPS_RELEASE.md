# FIPS-Safe OpenCV Wheels Release v4.13.0.92+fips

This release provides FIPS-compliant OpenCV Python wheels for x86_64 and ARM64 platforms.

## Changes

- Built OpenCV 4.13.0 from source with FIPS-safe configuration
- FFmpeg compiled without TLS backends (`--disable-openssl --disable-gnutls --disable-mbedtls`)
- No bundled OpenSSL/GnuTLS/MbedTLS libraries
- Static linking for all dependencies

## Platforms Supported

- **x86_64**: `opencv_python_headless-4.13.0.92+fips-cp312-cp312-manylinux_2_28_x86_64.whl`
- **ARM64**: `opencv_python_headless-4.13.0.92+fips-cp312-cp312-manylinux_2_28_aarch64.whl`

## Verification

Both wheels have been tested on FIPS-enabled systems with `OPENSSL_FORCE_FIPS_MODE=1`:
- OpenCV loads successfully in FIPS mode
- vLLM imports successfully with the FIPS-safe OpenCV wheels

## Usage

```bash
pip install opencv_python_headless-4.13.0.92+fips-cp312-cp312-manylinux_2_28_x86_64.whl
# or for ARM64:
pip install opencv_python_headless-4.13.0.92+fips-cp312-cp312-manylinux_2_28_aarch64.whl
```

To run in FIPS mode:
```bash
OPENSSL_FORCE_FIPS_MODE=1 python your_script.py
```

## Build Details

- Python: 3.12.15
- OpenCV: 4.13.0
- FFmpeg: 6.1.1 (custom build, no TLS)
- dav1d: 1.5.4
