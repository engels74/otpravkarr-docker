# AGENTS.md

This file provides guidance to AI coding agents when working with code in this
repository.

## Scope

Packaging-only repository for the `otpravkarr` Docker image. No application source lives here —
both Dockerfiles fetch `https://github.com/engels74/otpravkarr/archive/${VERSION}.tar.gz` at build
time. Application behaviour belongs in `engels74/otpravkarr`; this repo owns only the image layout,
its s6 services, and its build metadata.

## Branches are release channels

`release` is the default branch; `nightly` is a second channel with its own `meta.json`. There is
no `main`. The branch name becomes the published tag (`ghcr.io/engels74/otpravkarr-docker:<branch>`).

| Branch    | `version` resolves to                | `renovate.json` |
|-----------|--------------------------------------|-----------------|
| `release` | newest tag of `engels74/otpravkarr`  | yes             |
| `nightly` | HEAD commit SHA of upstream `main`   | no              |

`git diff release origin/nightly` is exactly `meta.json` + `renovate.json`. Everything else —
Dockerfiles, `root/`, `build.sh`, workflows — is meant to be identical, so a fix to a shared file
must be committed to both branches or the two published tags drift. Do not merge branches wholesale.

`workflows` is a reserved branch name: `call-build.yml` ignores it and `update-on-call.yml` filters
it out of its branch matrix.

## Commands

No package manifest, test suite, linter, or formatter exists here. Validation is a Docker build.

```sh
./build.sh amd64     # -> local image "otpravkarr-docker-amd64"; needs docker + jq + a git checkout
./build.sh arm64
eval "$(jq -r '.version__command' < meta.json)"   # re-run a version probe the way CI does
```

`build.sh` names the image from the repo directory (`git rev-parse --show-toplevel`) and turns every
`meta.json` key into an uppercase `--build-arg`, including the `__COMMAND` keys that CI filters out
(harmless warnings). It does not pass `IMAGE_STATS` or `PACKAGE_VERSION`, which CI does.

**`./build.sh` cannot succeed on `release`.** `engels74/otpravkarr` has zero git tags, so
`version__command` resolves to the literal string `"null"` and the builder curls
`archive/null.tar.gz` → 404. Build from `nightly` (its `version` is a live commit SHA), or put a real
ref in `meta.json` `version` locally — do not commit that edit; the hourly bot overwrites it anyway.

## meta.json is the build contract

- Every key becomes an uppercase `--build-arg`. Only `VERSION`, `UPSTREAM_IMAGE`,
  `UPSTREAM_TAG_SHA`, and `IMAGE_STATS` are consumed by the Dockerfiles; CI reads the rest itself.
- `*__command` values are shell snippets `eval`'d hourly, with the result written back to the same
  key minus the suffix. To change how a value is discovered, edit the `__command` string — editing
  the resolved value is silently reverted within the hour. Keep keys sorted; the bot writes with
  `jq --sort-keys`.
- `version` and `upstream_tag_sha` are bot-maintained. `packages_hash` is inert — nothing in the
  build or update workflow reads it.
- `test_amd64` and `test_arm64` are `false` here, so CI runs **no** smoke test and `test_url` is
  inert. A container that fails to start still publishes. Verify by hand:
  `docker run --rm -p 3000:3000 -e OTPRAVKARR_SECRET="$(openssl rand -base64 48)" otpravkarr-docker-amd64`
  then `curl -fsSL http://localhost:3000`.
- `latest: false` on both branches, so no `:latest` tag is published.
- `description` is published verbatim to the public tag table on `engels74/website`.

`packages.txt` is bot-generated and empty by design — CI removes every package already present in
the base image's `packages.txt`. Never hand-edit it.

## CI lives in another repository

`.github/workflows/{call-build,call-update}.yml` are thin callers into
`engels74/base-image/.github/workflows/{build-on-call,update-on-call}.yml@workflows`. All build,
publish, manifest, tagging, and notification logic is there — change that repo, not this one.

Any push to any branch except `workflows` triggers a full build and publish. The `packages.txt`
commit CI makes carries `[skip ci]`; the hourly `meta.json` commit does not, so an upstream version
bump auto-triggers a rebuild.

## Container runtime contract

`APP_DIR=/app`, `CONFIG_DIR=/config`, the `XDG_*` vars, `UMASK=002`, `VOLUME ["/config"]`, and the
`hotio` user (uid/gid 1000) come from `ghcr.io/engels74/base-image:alpinevpn`. Use the variables; do
not redefine them or hardcode `/app` / `/config`.

- Shared bash helpers: `source /etc/s6-overlay/scripts/bash-functions` (`log_inf`, `mask`, ...).
- `init-setup` and `init-wireguard` are base-image units this image orders itself against.
- Services drop privileges: `exec s6-setuidgid hotio bun start`.
- Persistence is a symlink, not a mount: the Dockerfile replaces `${APP_DIR}/data` with a symlink to
  `${CONFIG_DIR}/data`. The app opens `./data/otpravkarr.sqlite` relative to its cwd (`${APP_DIR}`)
  and only `${CONFIG_DIR}` is a declared volume — drop the symlink and the database is lost on every
  container recreate.

## Adding or changing an s6 service

1. `root/etc/s6-overlay/s6-rc.d/<name>/type` containing `oneshot` or `longrun`.
2. `run` starting with `#!/command/with-contenv bash`; for `oneshot` also add `up` holding the
   absolute in-container path of that `run` (see `init-setup-app/up`).
3. Ordering: an empty marker file at `<name>/dependencies.d/<dependency>`.
4. Enable it with an empty marker at `root/etc/s6-overlay/user-bundles.d/user/contents.d/<name>` —
   not `s6-rc.d/user/contents.d/`, which stopped working at s6-overlay 3.2.3.1 and makes the service
   silently never start (commit `fe82957`).
5. No `chmod` needed; both Dockerfiles end with
   `find /etc/s6-overlay/s6-rc.d -name "run*" -execdir chmod +x {} +`.

Marker files under `dependencies.d/` and `contents.d/` are empty on purpose — create them with
`touch`; content is not how s6 reads them.

## Gotchas

- **Edit both Dockerfiles together.** `linux-amd64.Dockerfile` and `linux-arm64.Dockerfile` are
  identical except that arm64's builder also installs `build-base python3`. CI builds each on its
  own runner, so a divergence ships one broken architecture. Keep the
  `# check=skip=InvalidDefaultArgInFrom` header too — it silences the BuildKit check that
  `FROM ${UPSTREAM_IMAGE}:${UPSTREAM_TAG_SHA}` (ARGs with no default) otherwise flags every build.
- **`OTPRAVKARR_SECRET` is a data-destroying knob.** `init-setup-app/run` hard-fails when it is unset
  or under 32 characters. It derives the AES-GCM keys for encrypted config rows and per-user Xtream
  passwords, so never add a fallback or auto-generation path — a changed value orphans that data
  permanently.
- **Changing the port touches four places:** `ENV PORT=`/`WEBUI_PORTS=` in both Dockerfiles, the
  `!= "3000"` guard in `init-setup-app/run` that rewrites `WEBUI_PORTS` into
  `/var/run/s6/container_environment/`, `test_url` in `meta.json`, and `README.md`.
- **`README.md` and `meta.json` `description` on `release` both describe the nightly image**
  ("Otpravkarr Docker Image (Nightly)", "Every commit to main"), and `description` is published to
  the public tag table. Known stale content — correct it deliberately rather than concluding that
  `release` is the nightly branch.
- Human commits use Conventional Commits. `Modified: <files>` commits are the bot's — don't imitate
  that format.

## Reference

- `README.md` — user-facing docs, branch-specific. Update whenever the exposed port, volume layout,
  or environment variables change.
- `engels74/base-image` branch `alpinevpn` — env vars, users, and s6 units the base already
  provides. Read before adding something that may already exist.
- `engels74/base-image` branch `workflows` — read before changing how the image is built, tagged, or
  published.
