#!/bin/bash
set -e
cd "${0%/*}"

APPID=$(sed -n 's/^id[[:space:]]*=[[:space:]]*//p' default/app.conf | head -1)
OUTPUT="${1:-${APPID}.spl}"

rm -rf lib/splunklib
python3.9 -m pip install --upgrade -t lib -r lib/requirements.txt

# pip -t installs console_scripts (idna/normalizer CLIs) into lib/bin; this add-on never
# invokes them, they're dead weight.
rm -rf lib/bin

# grpc is pulled in transitively via google-api-core[grpc], but this add-on only ever
# queries over the BigQuery REST API (client.query().result()), never bqstorage/grpc.
# Its compiled extension has no pure-Python fallback and isn't multi-arch/multi-Python
# safe, so the unused chain is dropped rather than shipped broken.
rm -rf lib/grpc lib/grpc_status lib/grpcio-*.dist-info lib/grpcio_status-*.dist-info

# These native speedups have a pure-Python fallback; deleting the compiled extension
# forces it, avoiding x86_64-only binaries that fail Splunk Cloud AArch64 vetting.
find lib/charset_normalizer -name '*.so' -delete
rm -f lib/*mypyc*.so
find lib/google_crc32c -name '*.so' -delete
rm -rf lib/google_crc32c.libs
rm -rf lib/google/_upb

# cffi's compiled backend has no pure-Python fallback, and cryptography (needed for
# service-account JWT signing) requires it. Unlike cryptography's abi3 wheel, cffi builds
# a separate extension per CPython minor version, so pip's cp39 build alone won't import
# under Python 3.13. Fetch the matching cp313 wheel too and vendor its .so alongside -
# Python's loader picks whichever file matches its own ABI tag.
CFFI_VERSION=$(sed -n 's/^Version: //p' lib/cffi-*.dist-info/METADATA)
CFFI_TMP=$(mktemp -d)
python3.9 -m pip download --no-deps --only-binary=:all: --python-version 3.13 \
    --implementation cp --abi cp313 --platform manylinux2014_x86_64 \
    -d "$CFFI_TMP" "cffi==${CFFI_VERSION}"
unzip -o -q "$CFFI_TMP"/cffi-*.whl -d "$CFFI_TMP/extracted"
cp "$CFFI_TMP"/extracted/_cffi_backend*.so lib/
rm -rf "$CFFI_TMP"

# Drop pip's build metadata (dist-info carries absolute build-host paths and goes stale
# the moment a vendored version changes) and nested bytecode caches.
rm -rf lib/*.dist-info
find lib -type d -name '__pycache__' -prune -exec rm -rf {} +

# Exec bits must be stripped AFTER pip installs, not before: pip sets +x on some
# installed files, so a chmod pass before pip never touches them.
chmod -R u=rwX,go= *
chmod -R u-x+X *
chmod -R u=rwx,go= bin/*

REPODIR=$(basename "$PWD")
cd ..
COPYFILE_DISABLE=1 tar -cpzf "$OUTPUT" --transform "s,^${REPODIR},${APPID}," \
    --exclude='*/.*' --exclude=.* --exclude=package.json --exclude='__pycache__' "$REPODIR"
