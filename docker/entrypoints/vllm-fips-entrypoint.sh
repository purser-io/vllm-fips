#!/bin/sh
# FIPS-mode OpenSSL setup for the vLLM images, run before the real entrypoint.
#
# Ubuntu's OpenSSL switches itself into FIPS mode when the kernel boots with
# fips=1: it makes `fips=yes` the default property and expects a `fips`
# provider. Stock Ubuntu ships none, so on a FIPS host every algorithm fetch
# fails, `ssl.create_default_context()` raises, and vLLM cannot even import
# aiohttp.
#
# The image carries the OpenSSL 3.1.2 FIPS provider (CMVP certificate #4985),
# built from the validated source per its Security Policy. That policy
# requires `openssl fipsinstall` to run on each machine where the module is
# used, and its output must not be copied between machines, so it cannot be
# baked into the image. This wrapper runs it at container start and activates
# the fips, base and default providers with `fips=yes` as the default
# property. Approved algorithms are the default, and callers that opt out
# explicitly (Python's `usedforsecurity=False`) still reach the default
# provider.
#
# The image's /etc/ssl/openssl.cnf includes the (normally empty) directory
# /etc/ssl/vllm-fips.d. Writing the config there applies it to every process
# in the container, `docker exec` and exec probes included. If that directory
# is not writable (read-only root filesystem, or a UID outside group 0), the
# config goes to $TMPDIR and is exported as OPENSSL_CONF, which only covers
# this process tree.
#
# FIPS mode is detected exactly as Ubuntu's OpenSSL does: OPENSSL_FORCE_FIPS_MODE
# when set (any value but "0" enables), otherwise the first byte of
# OPENSSL_FIPS_MODE_SWITCH_PATH or /proc/sys/crypto/fips_enabled. Outside FIPS
# mode the wrapper only removes a stale config left in the image.

set -eu

_provider_dir="${FIPS_OPENSSL_PROVIDER_DIR:-/opt/openssl-fips}"
_conf_dir="${FIPS_OPENSSL_CONF_DIR:-/etc/ssl/vllm-fips.d}"

_fips_mode() {
    if [ -n "${OPENSSL_FORCE_FIPS_MODE+set}" ]; then
        [ "$OPENSSL_FORCE_FIPS_MODE" != 0 ]
        return
    fi
    _switch="${OPENSSL_FIPS_MODE_SWITCH_PATH:-/proc/sys/crypto/fips_enabled}"
    [ "$(head -c 1 "$_switch" 2>/dev/null)" = 1 ]
}

if ! _fips_mode; then
    # A config from a FIPS host must never apply elsewhere.
    if [ -w "$_conf_dir" ]; then
        rm -f "$_conf_dir/fips.cnf" "$_conf_dir/fipsmodule.inc" \
            "$_conf_dir/fipsinstall.log"
    fi
    exec "$@"
fi

if [ -w "$_conf_dir" ]; then
    _dir="$_conf_dir"
    _system=1
else
    _dir="$(mktemp -d "${TMPDIR:-/tmp}/vllm-fips.XXXXXX")"
    _system=0
fi

# The 3.1.2 tool and libraries perform the install, isolated from any
# caller-supplied OpenSSL config. Files are renamed into place so a process
# reading the config never sees a partial write.
if ! OPENSSL_CONF=/dev/null LD_LIBRARY_PATH="$_provider_dir/lib" \
        "$_provider_dir/bin/openssl" fipsinstall \
        -pedantic \
        -module "$_provider_dir/lib/ossl-modules/fips.so" \
        -out "$_dir/fipsmodule.inc.tmp" > "$_dir/fipsinstall.log" 2>&1; then
    echo "vllm-fips-entrypoint: FIPS mode is on but the FIPS provider" \
         "failed its install self-tests:" >&2
    cat "$_dir/fipsinstall.log" >&2
    exit 1
fi
mv -f "$_dir/fipsmodule.inc.tmp" "$_dir/fipsmodule.inc"

# Extends the sections of Ubuntu's openssl.cnf; OpenSSL merges a re-declared
# section into the existing one.
cat > "$_dir/fips.cnf.tmp" <<EOF
.include $_dir/fipsmodule.inc

[openssl_init]
alg_section = vllm_fips_algorithm_sect

[provider_sect]
fips = fips_sect
base = vllm_fips_base_sect
default = vllm_fips_default_sect

[vllm_fips_base_sect]
activate = 1

[vllm_fips_default_sect]
activate = 1

[vllm_fips_algorithm_sect]
default_properties = fips=yes
EOF
mv -f "$_dir/fips.cnf.tmp" "$_dir/fips.cnf"

if [ "$_system" = 0 ]; then
    printf '.include /etc/ssl/openssl.cnf\n.include %s/fips.cnf\n' "$_dir" \
        > "$_dir/openssl.cnf"
    export OPENSSL_CONF="$_dir/openssl.cnf"
    echo "vllm-fips-entrypoint: $_conf_dir is not writable; the FIPS" \
         "config applies to this process tree only (OPENSSL_CONF)." >&2
fi
unset _provider_dir _conf_dir _dir _system

exec "$@"
