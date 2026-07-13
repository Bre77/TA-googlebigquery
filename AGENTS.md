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
- **`lib/` is pure Python - no `cryptography`/`cffi`, by deliberate choice.** Modern
  `google-auth` (>=2.48) made `cryptography` a hard, unconditional dependency for
  service-account JWT signing, and `cryptography` needs `cffi`'s compiled backend too -
  neither has a pure-Python fallback in that line. `google-auth` 2.46.0/2.47.0 are the last
  versions where `crypt/rsa.py` still guards the `cryptography` import in a try/except and
  falls back to the pure-Python `rsa`/`pyasn1`/`pyasn1_modules` signer
  (`google.auth.crypt._python_rsa`) with **no code changes needed** in `bin/bigquery.py` -
  `Credentials.from_service_account_info()` picks it up automatically once `cryptography`
  isn't installed. `lib/requirements.txt` pins `google-auth>=2.46.0,<2.48` for exactly this
  reason - do not let it float to 2.48+ without re-deciding this trade-off. Verified: the
  signer really is `google.auth.crypt._python_rsa.RSASigner` at runtime, and a real
  service-account-signed request reaches BigQuery successfully.
- **Why not native multi-arch (tried first).** The captain's first instinct was to keep
  `cryptography`+`cffi` and ship both x86_64 and aarch64 builds side by side in
  arch-specific directories (avoiding the identical-filename collision that blocks putting
  both in the same directory). Built a real test package this way and ran
  `splunk-appinspect`'s `check_aarch64_compatibility` against it: **it still fails**, because
  that check scans every file in the package independently and flags any non-ARM binary
  regardless of directory or whether an ARM sibling exists elsewhere - there is no
  Splunk-recognized directory convention that exempts one architecture's binary because
  another one is also present. Splunk's own `linux_x86_64`/`darwin_x86_64`/etc. per-arch
  `bin/` directory convention (`splunk_appinspect/app.py`'s `arch_bin_dirs`) predates ARM
  and has no aarch64 bucket either. Confirmed empirically with a throwaway test package run
  through `splunk-appinspect`, not just inferred from reading the check's source. Native
  multi-arch is only genuinely achievable via separate per-architecture Splunkbase package
  uploads, a materially larger change (doubled CI/release surface) than this task's scope.
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
