# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Vendored `lib/` (google-cloud-bigquery stack)

- `lib/` is built by `.build.sh` from `lib/requirements.txt` (`python3.9 -m pip install -t lib`),
  not hand-edited. Re-run `.build.sh` after any requirements change; it also applies the hygiene
  steps below. `lib/splunklib` and `lib/*.dist-info` are gitignored and regenerated each build.
- **grpc is deliberately dropped.** `google-cloud-bigquery` depends on `google-api-core[grpc]`
  (a hard, non-optional extra as of 3.x), but `bin/bigquery.py` only ever calls the REST query
  path (`client.query().result()`), never bqstorage/grpc - proved by running a real query with
  `grpcio`/`grpcio-status` fully uninstalled. `.build.sh` deletes `lib/grpc*` after install.
- **`cryptography` + `cffi` are the one unavoidable native dependency.** Modern `google-auth`'s
  service-account JWT signing (`Credentials.from_service_account_info`) unconditionally routes
  through `cryptography`'s compiled backend - no pure-Python path exists in that call, and `cffi`'s
  compiled backend has no fallback either (confirmed by deleting each and hitting ImportError).
  Every other native speedup (charset-normalizer, protobuf's upb, google-crc32c) has a working
  pure-Python fallback and is deleted post-install in `.build.sh` to avoid arch-specific `.so` files.
- **Dual-Python (3.9/3.13) trick:** `cryptography`'s compiled extension is abi3 (`_rust.abi3.so`),
  one build serves both interpreters. `cffi`'s is NOT abi3 - it's built per-CPython-minor, so
  `.build.sh` additionally downloads the cp313 wheel and vendors its `_cffi_backend*.so` alongside
  pip's cp39 build; the two coexist under different filenames and Python's loader picks the one
  matching its own ABI tag. Verified end-to-end (import + live query) on both 3.9 and 3.13.
- **Known unresolved gap: AArch64.** `cryptography`'s abi3 `.so` has the *same* filename in the
  x86_64 and aarch64 wheels, so - unlike the cp39/cp313 case - there's no side-by-side vendoring
  trick for architecture; Linux has no fat-binary mechanism. A build on an x86_64 host fails
  `splunk-appinspect`'s `check_aarch64_compatibility` (verified directly, not theoretical) on
  `cffi`'s and `cryptography`'s `.so` files. This blocks a Splunk Cloud/aarch64 AppInspect badge,
  not general Enterprise installability. See PR discussion for the options considered (ship
  x86_64-only vs. a runtime arch-dispatch shim vs. an older pre-cryptography-mandate google-auth).
- `setuptools` is NOT a dependency - nothing in the modern stack imports `pkg_resources`/
  `setuptools` (verified by grep + a clean import with both entirely absent). Adding it back
  drags in setuptools's own vendored test suite and Windows launcher `.exe` files, which is most
  of the AppInspect warning noise seen historically - don't re-add it without re-verifying need.
- `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` in `bin/bigquery.py` forces protobuf's
  pure-Python implementation because `google/_upb`'s compiled accelerator is deleted in
  `.build.sh` (same arch-specific-`.so` reasoning as above), not because of old generated code.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
