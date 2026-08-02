# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

Packaging-only repository that builds the multi-arch Docker image for the
[`engels74/otpravkarr`](https://github.com/engels74/otpravkarr) Bun/SvelteKit application. No
application source lives here — the builder stage downloads a tarball from that repo. Application
behaviour changes belong upstream; only image layout, s6-overlay service wiring, and build metadata
belong here.

The image extends `ghcr.io/engels74/base-image:alpinevpn`, which supplies s6-overlay, the `hotio`
user (uid 1000), `APP_DIR=/app`, `CONFIG_DIR=/config`, `UMASK`, `VOLUME ["/config"]`,
`/etc/s6-overlay/scripts/bash-functions`, and the `init-setup` / `init-wireguard` units this repo
depends on.

## Branch Model

There is no `main`. Two long-lived build branches exist, and the branch name becomes the image tag
(`ghcr.io/engels74/otpravkarr-docker:<branch>`):

| Branch | Default | `meta.json` `version__command` resolves to | Notes |
| --- | --- | --- | --- |
| `release` | yes | latest tag of `engels74/otpravkarr`, leading `v` stripped | has `renovate.json` |
| `nightly` | no | `commits/main` SHA of `engels74/otpravkarr` | no `renovate.json` |

`git diff origin/release origin/nightly` is exactly `meta.json` + `renovate.json`. Everything else —
Dockerfiles, `root/`, `build.sh`, workflows — is meant to be identical, so **any change to those
shared files must be applied to both branches** or the two published tags drift.

`workflows` is a reserved branch name: `call-build.yml` ignores it and the update workflow filters
it out of its branch matrix.

## Essential Commands

There is no package manifest, test suite, linter, or formatter in this repository. Validation is a
Docker build.

```sh
./build.sh amd64      # build linux/amd64 from linux-amd64.Dockerfile
./build.sh arm64      # build linux/arm64 from linux-arm64.Dockerfile
```

Run from the repository root; requires `docker` and `jq`. The script uppercases every `meta.json`
key into a `--build-arg` and tags the result `otpravkarr-docker-<arch>` (derived from the repo
directory name via `git rev-parse --show-toplevel`).

## CI and Automation

Both workflows are thin callers into reusable workflows on `engels74/base-image@workflows`. Read
that repo's `build-on-call.yml` / `update-on-call.yml` when you need to know what a `meta.json`
field actually controls — nothing in this repository documents them.

* `call-build.yml` — on push to any branch except `workflows`. Builds both platforms, pushes
  manifests to ghcr.io, regenerates `packages.txt`, updates the website tag table, notifies Discord.
* `call-update.yml` — hourly cron. Per branch, evaluates every `<key>__command` in `meta.json`,
  writes the result back to `<key>` with `jq --sort-keys`, refreshes `packages.txt`, and commits as
  `Modified: meta.json` under `github-actions[bot]`.

### Bot-owned values — do not hand-edit

`packages.txt` and the `version` / `upstream_tag_sha` values in `meta.json` are overwritten hourly.
To change how a value is derived, edit the matching `*__command` string; editing the resolved value
is silently reverted within the hour. Keep `meta.json` keys alphabetically sorted so the next bot
commit produces a clean diff.

## s6-overlay Service Wiring

`root/` is copied verbatim to `/` in the final stage. Two units are defined here; everything else
comes from the base image.

* `init-setup-app` — `oneshot`, depends on base `init-setup`. Validates `OTPRAVKARR_SECRET`,
  rewrites `WEBUI_PORTS` when `PORT` differs from 3000, and chowns `${CONFIG_DIR}/data` to `hotio`.
* `service-otpravkarr` — `longrun`, depends on base `init-wireguard`. Runs
  `s6-setuidgid hotio bun start` from `${APP_DIR}`.

To add a unit:

1. Create `root/etc/s6-overlay/s6-rc.d/<name>/type` containing `oneshot` or `longrun`.
2. Add `run` with shebang `#!/command/with-contenv bash`. For a `oneshot`, also add `up` containing
   the absolute path to that `run` script.
3. Add empty marker files under `<name>/dependencies.d/` naming each prerequisite unit.
4. Add an empty marker at `root/etc/s6-overlay/user-bundles.d/user/contents.d/<name>`.

Step 4 is the easy one to get wrong. Markers must live under `user-bundles.d/user/contents.d/`, not
`s6-rc.d/user/contents.d/` — s6-overlay >= 3.2.3.1 ignores the old location and the service never
starts (see commit `fe82957`). The Dockerfile's
`find /etc/s6-overlay/s6-rc.d -name "run*" -execdir chmod +x {} +` sets the executable bit, so `run`
scripts need no committed mode change.

## Dockerfile Conventions

`linux-amd64.Dockerfile` and `linux-arm64.Dockerfile` differ on exactly one line: the arm64 builder
additionally installs `build-base python3` for native module compilation. Mirror every other change
across both files.

Both use a two-stage build — an `oven/bun:alpine` builder that fetches
`https://github.com/engels74/otpravkarr/archive/${VERSION}.tar.gz`, runs
`bun install --frozen-lockfile && bun run build`, then reinstalls production-only dependencies; and
a runtime stage on the base image that installs Bun from `bun.sh/install` and copies only `build/`,
`node_modules/`, and `package.json` into `${APP_DIR}`.

Persistence relies on a symlink, not on mounting `/app`:

```dockerfile
RUN mkdir -p "${CONFIG_DIR}/data" && \
    rm -rf "${APP_DIR}/data" && ln -s "${CONFIG_DIR}/data" "${APP_DIR}/data" && \
    chmod -R u=rwX,go=rX "${APP_DIR}"
```

The app opens `./data/otpravkarr.sqlite` relative to its working directory (`${APP_DIR}`), and only
`${CONFIG_DIR}` is a declared volume — removing the symlink loses the database on every container
recreate.

## Critical Gotchas

* **`version` is the literal string `"null"` on `release`.** `engels74/otpravkarr` has no git tags,
  so `version__command` resolves to `null` and both `./build.sh` and CI try to fetch
  `archive/null.tar.gz`. To build from `release` locally, put a real ref in `meta.json` `version`
  first; otherwise work from `nightly`, whose `version` is a live commit SHA.
* **`OTPRAVKARR_SECRET` is a data-destroying knob.** `init-setup-app/run` hard-fails when it is unset
  or under 32 characters. It derives the AES-GCM keys for encrypted config rows, so do not add a
  fallback or auto-generation path — a changed value permanently orphans encrypted data.
* **`meta.json` `description` and `README.md` on `release` both describe the nightly image**
  ("Every commit to `main`", "Otpravkarr Docker Image (Nightly)"), and `description` is published to
  the public tag table by the build workflow. Known inconsistency: correct it deliberately rather
  than concluding that `release` is the nightly branch.
