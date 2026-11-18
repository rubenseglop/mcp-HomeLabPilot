# HomeLabPilot

A unified media-stack application combining a browser dashboard and an MCP server. Use the web interface directly, or connect an MCP client such as ChatGPT to the same backend.

It connects to the native APIs of Radarr, Sonarr, Prowlarr, Bazarr, Lidarr, Scryer and qBittorrent. HomeLabPilot is designed to be installed by different users on different Docker hosts; it does not require any particular folder layout, IP address, container name, Docker network or storage system.

## Web dashboard

HomeLabPilot serves its browser dashboard and MCP endpoint from the same application and port. Open `http://YOUR_DOCKER_HOST:8765/` and sign in with `HOMELABPILOT_WEB_USERNAME` and `HOMELABPILOT_WEB_PASSWORD`. These dashboard credentials are separate from `MCP_AUTH_TOKEN`; the MCP bearer token is only for MCP clients. The browser receives a random, HttpOnly session cookie and does not store either credential in browser local storage.

The dashboard includes a searchable Apps catalogue grouped by category. It distinguishes native dashboard integrations, generic API integrations, status-only checks and planned integrations, and shows the latest connectivity state without exposing credentials. Unconfigured native services are reported separately from configured services whose health check fails. Native integrations with existing dashboard workflows provide a direct shortcut from their catalogue card. Each card also exposes a connection form for allowlisted settings. Values are saved to `/data/app-config.enc` on the existing persistent volume using Fernet encryption and restrictive file permissions. The browser receives non-secret values and secret-presence flags only; secret values are never returned. Blank secret fields preserve existing credentials, while an explicit checkbox clears them. Saved settings override bootstrap environment values and are applied to the running process without a container restart. Set a stable `HOMELABPILOT_CONFIG_ENCRYPTION_KEY` in the private `.env` (recommended); if omitted, `MCP_AUTH_TOKEN` is used as the key source, so rotating that token makes the encrypted settings unreadable. Only known application fields are accepted, and service URLs cannot contain embedded credentials, query strings or fragments. Entries marked as planned can store connection details, but they do not gain API functionality or health checks until their integration is implemented. The catalogue is an inventory/status view; integrations marked as planned are not yet manageable from the dashboard. The dashboard currently includes live service status, Radarr movie, Sonarr series and Lidarr artist/album browsing, queue/history views, qBittorrent controls, Scryer library/requests/audit/recycle-bin views, and HomeLabPilot operation history. Configuration includes a curated Bazarr subtitle settings form, ARR profiles and integrations, Prowlarr configuration, and selected qBittorrent preferences. Destructive deletions display a current snapshot, require a typed confirmation, and reject stale previews. The optional Docker view is available only through the restricted Docker profile. Secret fields are redacted when configurations are read and restored server-side when records are updated.

By default, Compose publishes the port on loopback only. To open the dashboard from another device on your LAN, set `HOMELABPILOT_BIND_ADDRESS=0.0.0.0` in your private `.env` and recreate the container. This also makes the authenticated MCP endpoint reachable on the LAN. Do not forward this port from your router to the public internet. For remote access, use a private VPN such as Tailscale or a trusted HTTPS access layer.

## Current implementation

- `arr_api_request`: full REST API bridge for Radarr, Sonarr, Prowlarr, Bazarr and Lidarr.
- `scryer_graphql`: GraphQL query/mutation bridge for Scryer.
- `qbittorrent_api_request`: qBittorrent Web API bridge, including queue/download controls.
- `stack_status`: connectivity and version checks for the existing ARR services plus configured integrations.
- `integration_catalog`: list additional integrations and configuration state without returning credentials.
- `integration_api_request`: read native APIs for configured HTTP apps using fixed server-side URLs and credentials.
- `integration_preview_api_write` / `integration_confirm_api_write`: admin-only API write preview and exact typed confirmation.
- Postgres and Redis status use TCP reachability only; Recyclarr is listed as container/CLI integration.
- `scryer_introspect`: discover the live Scryer GraphQL query/mutation schema.
- `scryer_list_recycled_items`: read Scryer's recycle-bin settings and paged recycled-file details, including scheduled purge dates.
- `scryer_list_titles`, `scryer_list_media_requests`, `scryer_list_audit_events`: dedicated read-only Scryer catalog, request and audit workflows.
- `scryer_preview_delete_title` / `scryer_delete_title`: deletion preview, fingerprint check and typed confirmation. Destructive fields are blocked in the generic GraphQL tool.
- `homelabpilot_get_operation_history`: read HomeLabPilot's metadata-only local audit trail.
- `bazarr_get_settings` / `bazarr_update_settings`: curated native Bazarr settings form and admin-only updates.
- `arr_preview_delete_configuration` / `arr_delete_configuration`: preview and confirm configuration deletion; generic ARR DELETE is blocked.
- `qbittorrent_preview_delete_torrents` / `qbittorrent_delete_torrents`: snapshot and typed confirmation before torrent removal or data deletion.
- `docker_list_allowlisted_containers` / `docker_control_allowlisted_container`: optional allowlisted start/stop/restart via the restricted gateway.
- `qbittorrent_list_torrents`: list and filter torrents.
- `qbittorrent_list_categories`: inspect qBittorrent categories and their save paths.
- `qbittorrent_control_torrents`: pause, resume, recheck or reannounce.
- `qbittorrent_delete_torrents`: remove torrents, optionally including their data files, after a fresh preview and exact confirmation.
- `qbittorrent_set_category`: change torrent categories.
- `qbittorrent_preview_update_category_path` / `qbittorrent_update_category_path`: preview and confirm a category save-path change. Updating the category path does not move existing torrent data; use the torrent-location workflow for that.
- `qbittorrent_preview_move_torrents` / `qbittorrent_move_torrents`: snapshot and typed confirmation before moving selected torrent data to another absolute path on the qBittorrent host.
- `arr_list_library`: list Radarr movies, Sonarr series or Lidarr artists.
- `arr_update_library_item`: update monitoring and profiles for an existing movie, series or artist while preserving all other fields.
- `arr_add_artist`, `lidarr_list_albums`, `lidarr_update_album`, `lidarr_get_history` and `lidarr_get_missing_albums`: dedicated Lidarr music-library workflows.
- `arr_search_catalog`: find movies/series by title.
- `arr_get_queue`: inspect download/import queues.
- `arr_get_history` / `arr_get_missing_items`: consult recent activity and missing monitored items across Radarr, Sonarr and Lidarr.
- `tdarr_get_status`, `tdarr_get_nodes`, `tdarr_search_files`, `tdarr_list_job_reports` and `tdarr_get_job_report`: inspect Tdarr status, connected nodes, media records and FFmpeg/HandBrake job reports.
- `tdarr_preview_requeue_files` / `tdarr_confirm_requeue_files`: requeue up to 50 specifically selected files through the existing Tdarr flow/stack; exact file IDs are signed into the preview and require typed confirmation.
- `tdarr_preview_rescan_file` / `tdarr_confirm_rescan_file`: refresh metadata and queue state for one selected file.
- `plex_get_library_sections`, `plex_get_recently_added`, `plex_get_recently_added_all`, `plex_get_on_deck`, `plex_get_active_sessions`: inspect Plex libraries, recent additions, continue-watching and active playback.
- `jellyfin_get_libraries`, `jellyfin_search_items`, `jellyfin_get_active_sessions`, `jellyfin_get_server_info`: inspect Jellyfin libraries, search titles, playback sessions and server details.
- `seerr_get_status`, `seerr_get_application_data_status`, `seerr_get_requests`, `seerr_search_media`: inspect Seerr health, request queues by media type/status and media search.
- `immich_get_albums`, `immich_get_server_statistics`, `immich_search_assets`: inspect photo albums, server statistics and metadata search.
- `romm_get_platforms`, `romm_list_roms`, `romm_search_roms`, `romm_get_rom`, `romm_list_collections`: inspect platforms, game library, search results, game details and collections.
- `transmission_get_session`, `transmission_get_statistics`, `transmission_list_torrents`: inspect daemon settings, transfer totals/speeds and torrent status.
- `cloudflare_list_zones`, `cloudflare_list_dns_records`: inspect zones and DNS records using a scoped Cloudflare API token.
- `arr_get_setup_options`: retrieve valid root folders and quality profiles.
- `arr_add_movie` / `arr_add_series`: add titles by TMDB/TVDB ID.
- `arr_search_releases` / `arr_grab_release`: search and send a selected release to the download client. The browser library screen exposes this workflow per movie or series.

The wider integration catalog adds native HTTP API access for Plex, Jellyfin, Seerr, Transmission, Pulsarr, Cleanuparr, Maintainerr, Agregarr, Tracearr, Immich, RomM, BookOrbit, TinyMediaManager, Tidarr, FlareSolverr and Cloudflare. Postgres and Redis receive TCP reachability checks; Recyclarr is identified as a container/CLI integration. Native API reads are direct; writes require admin permission, a signed request preview and exact typed confirmation.

## MCP permission levels

Set `HOMELABPILOT_MCP_PERMISSION_LEVEL` in the private `.env` file to control what an authenticated MCP client may do:

- `read`: inspect service status, libraries, queues, releases, torrents and configuration. All writes are blocked.
- `operations`: the default. Includes ordinary media operations such as adding titles, grabbing releases, changing monitoring, categorizing torrents and pausing/resuming/rechecking downloads.
- `admin`: also permits sensitive configuration changes and qBittorrent preference changes. Deletions require their preview/confirmation workflows.

The generic ARR REST bridge applies the same checks: GET is read-only, ordinary writes require operations, and configuration/system endpoints require admin. Additional integration API writes require admin and an exact typed confirmation bound to the request snapshot. Direct ARR DELETE requests are refused; configuration deletion uses a preview token and exact typed confirmation. Scryer mutations require admin, and destructive mutations are available only through dedicated preview/confirmation tools.

The level is enforced server-side for shared write operations from both MCP tools and the browser dashboard; the dashboard still has its own separate login. Changing the level requires recreating the HomeLabPilot container. Invalid values fail closed. Use `read` when connecting an unfamiliar MCP client; raise it to `operations` or `admin` only when those capabilities are needed. Permission is not a per-action approval prompt: an MCP client should still obtain the user's explicit confirmation before invoking sensitive admin operations.

## Configuration coverage

The dashboard exposes an Advanced API explorer for the native REST APIs of Radarr, Sonarr, Prowlarr, Bazarr and Lidarr. It supports GET, POST, PUT and PATCH with JSON query parameters and request bodies; direct DELETE is refused in favor of preview workflows. API keys remain server-side and permission checks apply to every request. Dedicated forms cover ARR configuration records, selected Bazarr system/subtitle settings, and qBittorrent preferences. Bazarr writes use its native form-encoded settings endpoint and an explicit allowlist; provider credentials and restart-sensitive settings are excluded.

The Scryer dashboard includes a schema-driven control center plus dedicated library search, media request, audit log and recycle-bin views. The schema view is generated from the installed instance. Deleting a title requires a preview fingerprint and the exact confirmation prompt returned by Scryer. The generic GraphQL console remains useful for other operations, but destructive delete fields are blocked there.

HomeLabPilot records successful and failed writes initiated through its API in a local SQLite audit database. It stores timestamp, source, service, operation, target and outcome; request bodies, API keys and tokens are excluded. Compose persists the database in the `homelabpilot_state` named volume. The dashboard and `homelabpilot_get_operation_history` show recent events; the log is capped at 10,000 entries.

## Security model

- The caller cannot supply a hostname: requests are restricted to the base URLs configured by the operator.
- API keys and passwords are read from environment variables and must never be committed.
- The server does not expose a generic internet HTTP proxy.
- Write operations are available because this project is designed for full control. Treat the MCP endpoint and its credentials as administrator-level access to your media stack.
- The web API requires an authenticated browser session and rejects cross-origin browser POSTs. Destructive actions show a current preview and require exact typed confirmation; snapshot fingerprints reject stale previews. Library updates fetch the current ARR object and change only requested fields.
- Radarr, Sonarr, Prowlarr and Lidarr configuration records can be listed, edited, created from native JSON payloads and deleted. These configuration mutations require `admin`; secret fields are redacted from responses and existing secrets are preserved when editing records.
- The assistant should ask before irreversible actions such as deleting library files, removing titles with files, deleting torrents and data, or changing global settings.
- Optional Docker controls are disabled by default. Only a separate gateway mounts the Docker socket; HomeLabPilot can list and start/stop/restart exact allowlisted containers. It does not expose create, delete, exec, image, volume or arbitrary Engine API routes. The Docker socket remains host-powerful if the gateway itself is compromised, so enable the profile only on a trusted host and keep its network private.

## Configure

Copy `.env.example` to `.env` and fill in the URLs and credentials for the applications you have installed. Set `HOMELABPILOT_WEB_USERNAME` and `HOMELABPILOT_WEB_PASSWORD` to your dashboard login and a long, unique password. Keep `.env` outside Git.

Every URL must be reachable **from inside the HomeLabPilot container**. The correct address depends on your deployment:
- If HomeLabPilot and an application share a Docker network, use that application's Docker DNS name and internal port.
- If the application is reachable through a host-published port, use a host address reachable from the container.
- If it is on another machine, use that machine's reachable LAN/VPN address.

You do not need to configure services you do not use. Leave their variables empty.

Scryer uses its GraphQL API at `/graphql` and a bearer API key. Create an API key in Scryer's security settings and give it the permissions needed for the operations you want HomeLabPilot to perform.

Operation previews are signed with `HOMELABPILOT_PREVIEW_SECRET`; if it is unset, HomeLabPilot uses `MCP_AUTH_TOKEN`. Keep the signing secret stable between preview and confirmation calls.

## Install locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env, then export its variables before launching:
set -a && source .env && set +a
homelabpilot-mcp
```

The server supports MCP over stdio and authenticated Streamable HTTP. HTTP mode requires a bearer token of at least 32 characters and rejects unauthenticated requests.

Run the unit tests with `pip install -e ".[test]"` followed by `pytest`.

## Docker deployment

1. Clone this repository on the Docker host.
2. Create your local configuration:
   ```bash
   cp .env.example .env
   openssl rand -hex 32
   ```
   Put the generated value in `MCP_AUTH_TOKEN`. Set `HOMELABPILOT_WEB_USERNAME` and `HOMELABPILOT_WEB_PASSWORD` for browser login, then fill in the URLs and credentials for the applications you use. Do not publish or share the `.env` file.
3. Ensure HomeLabPilot can reach the configured application URLs from its container. The supplied Compose file creates an isolated HomeLabPilot network by default. If your applications are on other Docker networks, attach HomeLabPilot to those existing networks in `compose.yaml`. For each network, add it to the service's `networks` list and declare it at the bottom as external, using your own network name. For example:
   ```yaml
   services:
     homelabpilot:
       networks:
         - default
         - media_apps
   networks:
     media_apps:
       external: true
       name: YOUR_EXISTING_DOCKER_NETWORK
   ```
   Repeat this for additional networks if your applications are split across them. Alternatively, configure URLs that are reachable from the HomeLabPilot container without joining their Docker networks.
4. Start HomeLabPilot:
   ```bash
   docker compose up -d --build
   ```
5. Check startup:
   ```bash
   docker compose logs -f homelabpilot
   ```

The MCP endpoint is `http://YOUR_DOCKER_HOST:8765/mcp` and requires `Authorization: Bearer <MCP_AUTH_TOKEN>`. The dashboard is at the same host and port, at `/`. By default both are bound to loopback; set `HOMELABPILOT_BIND_ADDRESS=0.0.0.0` for LAN access. Never expose the port directly to the public internet.

Docker management is opt-in. Set `HOMELABPILOT_DOCKER_ENABLED=true`, `HOMELABPILOT_DOCKER_PERMISSION_LEVEL=operations`, a unique 32-character-or-longer `HOMELABPILOT_DOCKER_GATEWAY_TOKEN`, and a comma-separated exact container name/ID allowlist in `.env`. Then start the optional gateway with `docker compose --profile docker up -d --build`. The gateway is not published on a host port and accepts only list/start/stop/restart for allowlisted containers. The Docker socket is host-powerful; enabling the module means trusting the gateway and its host.

The MCP HTTP transport validates the incoming `Host` header to prevent DNS-rebinding attacks. Set `HOMELABPILOT_MCP_ALLOWED_HOSTS` to a comma-separated allowlist matching the host and published port used by your MCP client (for example, `localhost:*,127.0.0.1:*,[::1]:*,192.168.1.61:8765`). Entries are exact patterns; `host:*` allows any port for that hostname. Add each LAN, Tailscale, or reverse-proxy hostname that clients actually use.

The container runs as a non-root user, drops Linux capabilities, and uses a read-only filesystem.

## API references

- Radarr: `/api/v3`
- Sonarr: `/api/v3`
- Prowlarr: `/api/v1`
- Bazarr: native API under `/api`
- Lidarr: `/api/v1`
- Scryer: GraphQL at `/graphql`
- qBittorrent: Web API under `/api/v2`
- Home Assistant: REST API under `/api` (long-lived access token; read tools plus admin-only preview/confirmation for service calls)

## Completed development roadmap

- Added dedicated Scryer library, request, audit and deletion-preview workflows, plus curated native Bazarr settings forms.
- Added a persistent operation audit log and snapshot-bound, typed confirmations for destructive deletion flows.
- Added an opt-in Docker gateway with its own permission level, container allowlist and restricted start/stop/restart API.


## Additional app integrations

Configure only the services you run. Tdarr uses TDARR_URL (normally http://tdarr:8266) and optional TDARR_API_KEY created in Tdarr Tools → API Keys. Its dedicated MCP workflows search files, inspect nodes/status and job reports, and requeue/rescan only selected files after a signed preview and typed confirmation. Requeueing uses the existing library flow/stack; Tdarr controls the actual encode and whether the source is replaced. No library-wide requeue or file deletion tool is exposed. Keep worker counts conservative on low-power hardware. The API bridge accepts a service name and native API path; it never accepts a caller-provided host. Plex uses `PLEX_TOKEN`, Jellyfin uses `JELLYFIN_API_KEY`, Seerr uses `SEERR_API_KEY`, Immich uses `IMMICH_API_KEY`, RomM uses its bearer API token, and Cloudflare uses a scoped API token. Transmission uses its configured RPC URL and optional basic-auth credentials. Other HTTP apps use the configured API key header.

Home Assistant exposes MCP tools for core configuration, entity states (optionally filtered by domain), individual entity lookup, historical state changes, and the service catalogue. Device/service execution is available only through an admin-only signed preview followed by exact typed confirmation; the selected service must currently exist in Home Assistant, and entity targets are explicitly enumerated. This can operate physical devices, locks, covers, scripts or automations, so use the preview carefully. Pulsarr exposes health, approval-queue and content-router-rule queries. Agregarr exposes dedicated read-only MCP tools for version/status, collection configurations, default Plex hubs, pre-existing collections, scheduled jobs, filtered logs, missing-item queues and statistics, plus dashboard activity. TinyMediaManager exposes dedicated MCP tools for system status (version, busy state and task queue), its live OpenAPI description, and metadata task batches for movies, TV shows and movie sets. Tasks such as updating data sources, scraping, writing NFOs, downloading artwork/subtitles, renaming and refreshing metadata are limited to documented actions; each batch requires admin permission, a signed preview and exact typed confirmation before it is queued. Configure `TINYMEDIAMANAGER_URL` (the HTTP API base URL, commonly port 7878) and `TINYMEDIAMANAGER_API_KEY` (sent in the `api-key` header); enable the HTTP API in tinyMediaManager settings.\n\nCloudflare exposes read-only zone/DNS-record discovery plus admin-only DNS record creation, update and deletion. DNS mutations require a signed preview and exact typed confirmation; update/delete previews capture the current record so stale previews are rejected. Configure a scoped `CLOUDFLARE_API_TOKEN` with Zone:Read and DNS:Edit permissions, and `CLOUDFLARE_API_URL` (defaults to the official API base URL). DNS edits can interrupt websites, remote access or mail; review the preview carefully.\n\nFlareSolverr exposes MCP tools to list active browser sessions and fetch a public HTTP(S) page through its challenge-solving browser. The fetch tool requires `operations` permission, limits the timeout and response size, and rejects local/internal hostnames and non-public IP literals. FlareSolverr has no authentication, so keep it on a trusted private network and never expose it to the internet. Configure `FLARESOLVERR_URL`.\n\nCleanuparr exposes read-only liveness/readiness probes, system and *arr/download-client status, scheduled jobs, paginated event and strike history, event timelines, aggregate statistics and manual-event statistics. Configure `CLEANUPARR_URL` and an API key created in Cleanuparr Settings → Account → API Key; HomeLabPilot sends it in the `X-Api-Key` header. Mutating endpoints (job triggers, configuration changes, strike deletion and event resolution) are not exposed. The liveness and readiness probes are public by design; keep Cleanuparr on a trusted private network.\n\nMaintainerr exposes read-only MCP tools for app version/update status, process timezone, liveness/readiness (including database availability) and the running state of its scheduled tasks. Its API has no authentication at all: configure `MAINTAINERR_URL` only on a trusted private Docker network and never publish it to the internet. HomeLabPilot deliberately does not expose Maintainerr settings, media deletion, or other mutation endpoints.\n\nTidarr exposes read-only tools for authentication mode, paginated download queue, queue pause/batch status, download history and synchronized playlists/mixes. Download submission, queue pause/resume, retrying failed items and triggering playlist synchronization use a signed preview followed by exact typed confirmation. Download URLs are restricted to HTTPS Tidal links and supported media types; API keys use the `X-Api-Key` header. Configure `TIDARR_URL` and `TIDARR_API_KEY` (the key is available in Tidarr Settings → Authentication → API Key or in `/shared/.tidarr-api-key`).\n\nBookOrbit exposes read-only tools for API/database health, server version, effective API-key identity and permissions, accessible libraries, per-library statistics, book search/details and library-wide statistics/format distribution. Create a read-only API key in BookOrbit under Settings → You → API keys, then configure `BOOKORBIT_URL` and `BOOKORBIT_API_KEY`. Tracearr provides dedicated read-only tools for live streams (including direct-play/transcode and codec details), cursor-paginated watch history, server health, user identities and per-user history/statistics, title resolution across servers, per-title stats/watchers/season-episode hierarchy, library rollups, recently added media, playback activity trends and top titles. It uses the Public API v2 for cursor-paginated history and library data, plus v1 public health/activity endpoints; generate an owner API key in Tracearr Settings → Data & API → API. Cleanuparr exposes authenticated operational monitoring tools and Maintainerr exposes read-only health and task-status tools; Maintainerr's API has no built-in authentication, so keep its endpoint on a trusted private network. Configure `HOMEASSISTANT_URL` and a long-lived access token in `HOMEASSISTANT_TOKEN`; HomeLabPilot does not invoke Home Assistant services through these tools.

`integration_catalog` reports configuration without showing credentials. `stack_status` checks configured API endpoints and Postgres/Redis TCP reachability. Postgres and Redis are currently connectivity checks only; Recyclarr is listed as a container/CLI integration. App-specific SQL and CLI workflows are not exposed by the generic HTTP API tool.

`integration_api_request` is read-only, except Transmission's read RPC methods. For a native API write, call `integration_preview_api_write` and then `integration_confirm_api_write` with the same request, returned token and exact phrase. Writes require server permission level `admin`. Maintainerr and FlareSolverr have no API authentication in this integration configuration; keep their URLs on a trusted private network.
