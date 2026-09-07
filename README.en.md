# AnyTube

[Français](README.md) · **English**

A personal, self-hosted video platform: bring your sources together, search for videos, watch them and keep your media in a private library.

**Status: development preview · 0.4.1-preview.** Capabilities depend on each source and validation remains partial. An installed extractor does not guarantee search, playback or downloading.

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Support on Ko-fi](https://img.shields.io/badge/Support-Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/nthstudio)

This project is developed in my spare time. If you would like to support it, you can buy me a [Ko-fi](https://ko-fi.com/nthstudio). Thank you!

**Source discovery assistant:** integrated discovery, PeerTube reuse, JSON inference,
configurable SearXNG/JSON search and optional Ollama/OpenAI-compatible AI. Sources are
added after search checks; playback is not certified. See the [configuration guide](docs/SOURCE-ASSISTANT.md)
(French). The optional Chromium service still requires Docker validation.

## Features

- **Explore your sources**: a home feed per source, federated search, multiple source selection, rankings and additional results where supported. Errors from one source do not hide other results.
- **Configure connectors**: a yt-dlp catalogue, search templates, JSON GET/POST APIs, URL-only sources, configuration copying and testing before saving.
- **Watch videos**: a locally served player, media resolution, a private HLS/DASH relay and selection of available qualities and tracks. These paths remain experimental depending on the platform and browser.
- **Keep your media**: MP4 H.264/AAC video or M4A audio preparation, progress, cancellation, retry, a persistent library and configurable quotas.
- **Resume your activity**: private favourites, history, playback progress and preferences per account; collection browsing and a playback queue.
- **Share your installation**: a first administrator created using a one-time token, invitation-based accounts, revocable sessions and data separation between users.
- **Manage source credentials**: an encrypted vault for API keys, bearer tokens and imported cookies, with allowed domains and separate references for search and media access.
- **Adjust the interface**: mobile and desktop layouts, light/dark themes, integrated confirmation dialogs and optional SponsorBlock for YouTube. The application interface is currently in French.

AnyTube does not load embedded platform players or third-party advertising scripts. The browser requests thumbnails directly from platforms. SponsorBlock relies on community contributions and does not guarantee removal of all advertising.

## Install with Docker

Requirements: Git, Docker Engine with Linux containers and Docker Compose v2. The kernel must support `iptables` and owner matching; see the [Unraid guide](docs/UNRAID.md), currently in French.

```sh
git clone https://github.com/Nicthien/AnyTube.git
cd AnyTube
cp .env.example .env
docker compose -f compose.unraid.yaml up -d --build
docker compose -f compose.unraid.yaml logs --tail=100 anytube
```

In PowerShell, replace `cp .env.example .env` with `Copy-Item .env.example .env`.

Open [localhost:8088](http://localhost:8088), then create the first administrator using the one-time token printed in the logs. Additional accounts are created through invitations from **Mon compte** (My account).

The `anytube:family` image is built locally; no published AnyTube registry image is required. One container runs the application, outbound proxy and daily backups. Python, yt-dlp, FFmpeg, ffprobe and Node are included.

### Configuration

Copying `.env.example` is required to use the quick start's local paths. Without this file, Compose uses its default Unraid paths.

| Variable | Value in `.env.example` | Purpose |
| --- | --- | --- |
| `ANYTUBE_BIND` | `127.0.0.1` | Listening address; `0.0.0.0` for LAN access. |
| `ANYTUBE_PORT` | `8088` | HTTP port. |
| `ANYTUBE_APPDATA` | `./data/docker` | SQLite database and backups. |
| `ANYTUBE_STORAGE` | `./data/media` | Media cache and library. |
| `ANYTUBE_SECRETS` | `./secrets/docker` | Vault key, separate from the database. |
| `ANYTUBE_PUBLIC_URL` | empty | Canonical HTTPS URL, after configuring your reverse proxy. |

For Unraid, adjust the paths to `/mnt/user/appdata/anytube`, `/mnt/user/anytube` and `/mnt/user/appdata/anytube-secrets`. For LAN access, open `http://SERVER_IP:8088` after changing `ANYTUBE_BIND`.

When an HTTPS URL is configured, cookies become secure and other addresses redirect to that URL. Sign-in must then use HTTPS.

The container prepares its volumes and firewall on startup, then runs application services under dedicated users without capabilities. The outbound proxy and firewall restrict access to public addresses. The legacy `compose.yaml` file is for development and does not provide this network isolation.

### Backups and updates

SQLite stores accounts, sources, preferences, tasks and settings. Daily backups retain seven database copies and a configuration archive. Also back up the media library and **a separate private copy of the vault key**: the database alone cannot restore encrypted credentials.

Before updating, retain the code, image and a consistent backup. Restoration procedures are detailed in [docs/UNRAID.md](docs/UNRAID.md).

## Sources and compatibility

AnyTube distinguishes three capabilities: **extracting a URL**, **searching a platform** and **playing media in the browser**. Each requires its own verification.

The September 6, 2026 inventory lists 1,750 extractors, automatically grouped into 927 families, and 31 search templates. These counts describe the catalogue, not certified compatible platforms.

In **Mes sources** (My sources), add a template or create a connector, test its configuration, then save it. JSON APIs use JSON Pointer paths (`/data/videos`, `/title`, `/owner/name`); pagination and rankings depend on the API. URL-only sources do not provide search.

All **31 search templates** have been reviewed in batches, platform by platform, by reading the official interfaces and the installed extractor code, then probing each template with three suitable queries over two pages: [batch 01](docs/sources-lot-01.md) (20 templates) and [batch 02](docs/sources-lot-02.md) (11 templates). Both reports are in French. A reviewed template does not make its platform verified: **1,719 installed extractors still have no search template**, and playback, audio, live, subtitles and downloading remain unverified for those 31 templates.

Three templates are unusable for a cause identified at the provider or in the upstream extractor (Google Video, Yahoo Video, Rokfin) and five need an account stored in the vault (the four PRX templates and Vimeo). The catalogue shows these limits next to each template.

Self-hosted software is instantiable: one PeerTube template, as many sources as instances. Give the domain when adding the source; the installed extractor recognises 1,292 instances. An instance it does not know can still be added, with search but **without playback**, and the interface says so.

Dated evidence is recorded in the [source progress report](docs/SOURCES-PROGRESS.md). Documented checks include Dailymotion search, HLS playback of Big Buck Bunny in Chrome and video/audio preparation of that film. They do not validate every platform or every later code revision.

### Current limitations

- Real DASH playback, live streams, language/subtitle switching, Firefox, Safari and playback authenticated with an external platform remain unverified.
- No DRM circumvention; OAuth and platform-specific login forms are not implemented.
- Some connectors reload a growing result prefix, capped at 100 per source, instead of using native pagination. A platform whose ordering shifts between two calls can then repeat results on the next page; the interface drops them, it does not invent them.
- Duration and date filters are available on Dailymotion only. Search and home rankings depend on each template.
- Support for formats, large segments, network recovery and persistent queues remains incomplete. Sites may reject extraction or require authentication.
- Not all new media and source credential capabilities have been validated on Unraid. Consult the reports before treating them as available on an existing installation.

## Development

The Dockerfile uses Python 3.14 and Node 24. For media processing outside Docker, also install FFmpeg/ffprobe and Node on the host.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8088
```

To enable the vault during development, create its key once before starting the server:

```powershell
.\.venv\Scripts\python scripts/init_vault.py secrets/vault.key
$env:ANYTUBE_VAULT_KEY_FILE = (Resolve-Path secrets/vault.key).Path
```

Reuse this key on subsequent starts. Never replace a key required by existing credentials.

Shaka Player is already included in `app/static/vendor/`. To regenerate the files after updating the dependency:

```sh
npm ci
npm run vendor
```

API: `/api/health`, `/api/sources`, `/api/catalog` and the `/openapi.json` schema. Mutation and search POST requests require `X-AnyTube: 1`; private routes also require a session.

Run a single Uvicorn process: some tasks, playback sessions and quota reservations are coordinated in memory.

## Contributing

[Issues](https://github.com/Nicthien/AnyTube/issues) and pull requests are welcome. For a source problem, include the capability, versions and a reproducible public example, without sharing cookies, tokens or account data.

Before proposing a change, run `python -m unittest discover -s tests` in the project environment and `git diff --check`. The suite includes a guard against native JavaScript dialogs. Connector or playback changes also require a real check of the claimed capability.

## Documentation

- [Unraid installation, operation and restoration](docs/UNRAID.md) — French.
- [Source status, evidence and remaining work](docs/SOURCES-PROGRESS.md) — French.
- [Search template batch 01](docs/sources-lot-01.md) and [batch 02](docs/sources-lot-02.md) — French; corrections, dated evidence and remaining blockers.
- `python scripts/triage_families.py` — ranks the families without a search template by likely cost; output in [docs/family-triage.json](docs/family-triage.json).
- [Family foundation validation history](docs/FAMILY-DELIVERY.md) — French; some findings predate the source expansion.

## License

Original AnyTube code is distributed under the [MIT License](LICENSE), © 2026 Nicolas Thiennet.

Third-party dependencies and data retain their respective licenses, including [Shaka Player under Apache-2.0](app/static/vendor/shaka-player.LICENSE). SponsorBlock data is attributed in the interface under CC BY-NC-SA 4.0. The project license grants no rights to platform media.
