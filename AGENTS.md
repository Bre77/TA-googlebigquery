# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Vendored `lib/` (google-cloud-bigquery stack)

- `lib/` is built by `.build.sh` from `lib/requirements.txt` (`python3.9 -m pip install -t lib`),
  not hand-edited. Re-run `.build.sh` after any requirements change; it also applies the hygiene
  steps below. Everything under `lib/` except `lib/requirements.txt` is gitignored build output;
  CI vendors `lib/` from scratch on every build.
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

## Modular-input runtime and credential handling

- This app runs on `splunk_input_runtime` (https://github.com/Bre77/splunk-input-runtime), not
  `splunklib`/`splunk-sdk`. `lib/requirements.txt` pins it to an exact commit archive URL with a
  `sha256:` comment above it (no PyPI release exists yet, so there is no `==version` line to pin
  against). Bump both the commit and the recorded hash together when the runtime releases a new
  version; never point at a branch.
- Credential handling goes through `self.context.credentials.protect_input_fields(...)` in
  `bin/bigquery.py`, not manual `storage_passwords` list/delete/create calls. This preserves the
  credential identity `(owner=nobody, app=TA-googlebigquery, realm=<stanza name>,
  username=service_account)` that existing installs already have - do not change that tuple
  without a captain-level decision; it strands users' stored service account credentials.
- The runner (`Script.run_script`) owns `EventWriter.close()`; app code must not call it
  explicitly. `splunk_input_runtime`'s `close()` is idempotent by design as a defense.
- `Bre77/SplunkUI-devcontainer`'s `test-harness/credential-continuity-gate.sh` is parameterised
  (`--app-id`, `--kind`, `--field`, `--old-app`/`--new-app`) - run it with `--app-id
  TA-googlebigquery --kind bigquery --field service_account` to prove credential continuity
  across a change to this app's credential handling. Two gate quirks to know before trusting a
  raw run:
  - `--field NAME=FWD:REV` splits on the *first* literal colon in the combined string, so the
    forward-direction (upgrade) test value cannot itself contain a colon; a real GCP
    service-account JSON blob does (both as `"key": "value"` syntax and inside its `https://`
    URLs). Put the colon-bearing, fully realistic secret in the reverse leg only.
  - The gate's `scan_for_secret_leak` passes the whole secret to `grep -rlE` as one PATTERN
    argument. GNU grep treats a PATTERN containing embedded newline *bytes* as one alternative
    regex per line (confirmed against grep 3.1 in the harness container) - a genuinely
    multi-line test secret degenerates into trivial alternatives like a bare `{`, producing a
    FAIL against nearly every log in the container (verified false: none contained the actual
    secret). `bin/bigquery.py`'s own scheme documents `service_account` as "a single line of
    JSON" anyway (real installs paste the key file compacted to one line, PEM newlines as
    literal `\n` escapes) - so build test secrets as one physical line with no raw newline byte
    and this doesn't come up. Still use real quotes, backslash-`\n` escapes, base64 body
    characters, and (reverse leg) colons to exercise the actual hazard.
- `bin/bigquery.py` only writes an indexed event after a real, successful call to the Google
  BigQuery REST API (`client.query().result()`) - the gate cannot prove `decrypt_proof` for this
  app without live GCP credentials reachable from the container; run it with
  `--no-runtime-decrypt-proof <reason>` and disclose that gap rather than hiding it.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
