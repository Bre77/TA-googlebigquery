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

# All remaining native speedups have a pure-Python fallback; deleting the compiled
# extension forces it. google-auth is capped below the version where `cryptography`
# became a hard dependency (see lib/requirements.txt), so service-account JWT signing
# uses google-auth's pure-Python rsa/pyasn1 signer instead - no cryptography/cffi
# anywhere in this tree, and therefore nothing left that's arch- or CPython-specific.
find lib/charset_normalizer -name '*.so' -delete
rm -f lib/*mypyc*.so
find lib/google_crc32c -name '*.so' -delete
rm -rf lib/google_crc32c.libs
rm -rf lib/google/_upb

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
