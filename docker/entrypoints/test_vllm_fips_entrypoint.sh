#!/bin/sh
# Shell-level unit test for vllm-fips-entrypoint.sh.
#
# Runs on the host (no Docker, no FIPS kernel) with a stub `openssl` that
# records its arguments. FIPS mode is driven through the same variables
# Ubuntu's OpenSSL reads: OPENSSL_FORCE_FIPS_MODE and
# OPENSSL_FIPS_MODE_SWITCH_PATH.
#
# Usage:
#   bash docker/entrypoints/test_vllm_fips_entrypoint.sh
# Exits non-zero on the first failed assertion.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="${SCRIPT_DIR}/vllm-fips-entrypoint.sh"

if [ ! -x "$WRAPPER" ]; then
    echo "FAIL: wrapper not found or not executable: $WRAPPER" >&2
    exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'chmod -R u+w "$WORKDIR"; rm -rf "$WORKDIR"' EXIT

# Stub provider tree: `openssl fipsinstall` writes a marker module config, and
# then fails when STUB_FIPSINSTALL_FAIL is set.
PROVIDER="$WORKDIR/openssl-fips"
mkdir -p "$PROVIDER/bin" "$PROVIDER/lib/ossl-modules"
cat > "$PROVIDER/bin/openssl" <<'EOF'
#!/bin/sh
echo "$*" > "${STUB_LOG:?}"
while [ $# -gt 0 ]; do
    if [ "$1" = "-out" ]; then printf '[fips_sect]\nactivate = 1\n' > "$2"; fi
    shift
done
# Fails after writing output, so only the wrapper's exit status check stops it.
if [ -n "${STUB_FIPSINSTALL_FAIL:-}" ]; then
    echo "SELF TEST FAILED" >&2
    exit 1
fi
EOF
chmod +x "$PROVIDER/bin/openssl"

CONF="$WORKDIR/vllm-fips.d"
mkdir -p "$CONF" "$WORKDIR/tmp"
printf '1\n' > "$WORKDIR/fips_on"
printf '0\n' > "$WORKDIR/fips_off"

fail() { echo "FAIL: $*" >&2; exit 1; }

# Runs the wrapper with a clean FIPS environment plus the given assignments,
# and prints OPENSSL_CONF as seen by the wrapped command.
run() {
    # shellcheck disable=SC2016  # expanded by the wrapped shell, not here
    env -u OPENSSL_FORCE_FIPS_MODE -u OPENSSL_CONF \
        FIPS_OPENSSL_PROVIDER_DIR="$PROVIDER" FIPS_OPENSSL_CONF_DIR="$CONF" \
        TMPDIR="$WORKDIR/tmp" STUB_LOG="$WORKDIR/stub.log" \
        OPENSSL_FIPS_MODE_SWITCH_PATH="$WORKDIR/fips_off" \
        "$@" "$WRAPPER" sh -c 'echo "${OPENSSL_CONF:-__unset__}"'
}

assert_fips_conf() {
    _c="$1"
    grep -q '^default_properties = fips=yes$' "$_c" || fail "fips=yes missing"
    grep -q '^fips = fips_sect$' "$_c" || fail "fips provider not configured"
    grep -q '^base = vllm_fips_base_sect$' "$_c" || fail "base not configured"
    grep -q '^default = vllm_fips_default_sect$' "$_c" || fail "default missing"
    _inc="$(sed -n 's/^\.include //p' "$_c")"
    grep -q '^\[fips_sect\]$' "$_inc" || fail "fipsmodule config not generated"
    grep -q -- '-pedantic' "$WORKDIR/stub.log" || fail "fipsinstall not -pedantic"
    grep -q -- "-module $PROVIDER/lib/ossl-modules/fips.so" "$WORKDIR/stub.log" \
        || fail "fipsinstall used the wrong module"
}

# Not FIPS: nothing is configured and fipsinstall never runs.
rm -f "$WORKDIR/stub.log"
[ "$(run)" = "__unset__" ] || fail "configured outside FIPS mode"
[ ! -e "$WORKDIR/stub.log" ] || fail "fipsinstall ran outside FIPS mode"
[ ! -e "$CONF/fips.cnf" ] || fail "config written outside FIPS mode"
[ "$(run OPENSSL_FORCE_FIPS_MODE=0)" = "__unset__" ] \
    || fail "OPENSSL_FORCE_FIPS_MODE=0 must disable FIPS mode"
[ "$(run OPENSSL_FIPS_MODE_SWITCH_PATH=/nonexistent)" = "__unset__" ] \
    || fail "missing switch file must mean FIPS off"

# FIPS via the kernel switch: system-wide config, no env var needed.
[ "$(run OPENSSL_FIPS_MODE_SWITCH_PATH="$WORKDIR/fips_on")" = "__unset__" ] \
    || fail "system mode must not need OPENSSL_CONF"
assert_fips_conf "$CONF/fips.cnf"

# A config left over from a FIPS host is removed on a non-FIPS start.
run > /dev/null
[ ! -e "$CONF/fips.cnf" ] && [ ! -e "$CONF/fipsmodule.inc" ] \
    || fail "stale FIPS config survived a non-FIPS start"

# FIPS forced: any value other than "0", matching Ubuntu's OpenSSL.
for v in 1 yes ""; do
    rm -f "$CONF/fips.cnf"
    run OPENSSL_FORCE_FIPS_MODE="$v" > /dev/null
    [ -f "$CONF/fips.cnf" ] || fail "OPENSSL_FORCE_FIPS_MODE='$v' did not enable"
done

# Read-only config dir: per-process fallback through OPENSSL_CONF. Root
# ignores permission bits, so this case only runs unprivileged.
rm -f "$CONF/fips.cnf" "$CONF/fipsmodule.inc"
if [ "$(id -u)" != 0 ]; then
    chmod a-w "$CONF"
    conf="$(run OPENSSL_FORCE_FIPS_MODE=1 2>/dev/null)"
    chmod u+w "$CONF"
    case "$conf" in
        "$WORKDIR/tmp/"*) ;;
        *) fail "fallback not under TMPDIR: $conf" ;;
    esac
    grep -q '^\.include /etc/ssl/openssl.cnf$' "$conf" || fail "system config dropped"
    assert_fips_conf "$(dirname "$conf")/fips.cnf"
    [ ! -e "$CONF/fips.cnf" ] || fail "wrote to a read-only config dir"
fi

# Fail closed: a failed self-test stops the container with the reason.
if err="$(run OPENSSL_FORCE_FIPS_MODE=1 STUB_FIPSINSTALL_FAIL=1 2>&1)"; then
    fail "wrapper continued after fipsinstall failed"
fi
echo "$err" | grep -q "SELF TEST FAILED" || fail "self-test output not shown"

# Arguments pass through untouched.
out="$(env -u OPENSSL_FORCE_FIPS_MODE OPENSSL_FIPS_MODE_SWITCH_PATH=/nonexistent \
    FIPS_OPENSSL_CONF_DIR="$CONF" "$WRAPPER" printf '%s|' "a b" "--flag=1" "")"
[ "$out" = "a b|--flag=1||" ] || fail "argv not forwarded verbatim: $out"

echo "PASS: vllm-fips-entrypoint.sh"
