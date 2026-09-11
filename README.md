# Otpravkarr Docker Image (Nightly)

Nightly images use a reviewed, pinned application revision and pass native amd64/arm64 runtime validation before manual publication.

Documentation: [web.edb.fi](https://web.edb.fi/containers/otpravkarr/). The inactive release branch is preserved; no stable source tag has been selected.

## Environment Variables

### `OTPRAVKARR_SECRET` (required)

A stable secret of at least **32 characters** that persists across container restarts. The container will refuse to start if this variable is unset or too short.

> **Warning:** This value must remain stable. It derives the AES-GCM keys used to encrypt configuration (e.g. Plex admin token, Dispatcharr API key) and per-user Xtream passwords. If it changes, all previously-encrypted rows become permanently unreadable.

Generate one with:

```sh
openssl rand -base64 48
```

Then provide it via your compose file or an env file kept outside version control:

```yaml
environment:
  - OTPRAVKARR_SECRET=<paste value here>
```

## Validation and publication

Both architectures use pinned Bun and native base-image digests, a checksummed application source archive, the existing Hotio/s6 layout and persistent `/config` data. CI checks secret rejection, setup/health, exact SQL migration bytes, encrypted persistence across restart/replacement, a missing configured database, and clean shutdown. Live Plex/Dispatcharr connections are not exercised.

Publication is manual from the matching nightly revision after full final CI. It publishes only tested archives and rejects stale workflow/branch revisions or failed runtime evidence. Legacy release/update workflows remain disabled.
