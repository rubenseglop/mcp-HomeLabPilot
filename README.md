# StackARR

A unified media-stack application combining a browser dashboard and an MCP server. Use the web interface directly, or connect an MCP client such as ChatGPT to the same backend.

It connects to the native APIs of Radarr, Sonarr, Prowlarr, Bazarr, Scryer and qBittorrent. StackARR is designed to be installed by different users on different Docker hosts; it does not require any particular folder layout, IP address, container name, Docker network or storage system.

## Web dashboard

StackARR serves its browser dashboard and MCP endpoint from the same application and port. Open `http://YOUR_DOCKER_HOST:8765/` and sign in with `STACKARR_WEB_USERNAME` and `STACKARR_WEB_PASSWORD`. These dashboard credentials are separate from `MCP_AUTH_TOKEN`; the MCP bearer token is only for MCP clients. The browser receives a random, HttpOnly session cookie and does not store either credential in browser local storage.

The dashboard currently includes live service status, Radarr movie and Sonarr series library browsing, Radarr/Sonarr queue inspection, qBittorrent torrent listing with pause/resume controls, and metadata catalogue search with workflows to add movies or series using the configured root folders and quality profiles. Settings can edit existing Radarr/Sonarr quality profiles, delay profiles, indexers, download clients and notifications; Prowlarr indexers, download clients and notifications; and an allowlist of qBittorrent preferences. Secret fields are redacted when configurations are read and restored server-side when records are updated. Browser requests use the same configured service API layer as MCP; they are not a separate integration. The overview refreshes automatically every 30 seconds.

By default, Compose publishes the port on loopback only. To open the dashboard from another device on your LAN, set `STACKARR_BIND_ADDRESS=0.0.0.0` in your private `.env` and recreate the container. This also makes the authenticated MCP endpoint reachable on the LAN. Do not forward this port from your router to the public internet. For remote access, use a private VPN such as Tailscale or a trusted HTTPS access layer.

## Current implementation

- `arr_api_request`: full REST API bridge for Radarr, Sonarr, Prowlarr and Bazarr.
- `scryer_graphql`: GraphQL query/mutation bridge for Scryer.
- `qbittorrent_api_request`: qBittorrent Web API bridge, including queue/download controls.
- `stack_status`: connectivity and version checks.
- `scryer_introspect`: discover the live Scryer GraphQL query/mutation schema.
- `qbittorrent_list_torrents`: list and filter torrents.
- `qbittorrent_control_torrents`: pause, resume, recheck or reannounce.
- `qbittorrent_delete_torrents`: remove torrents, optionally including their data files.
- `qbittorrent_set_category`: change torrent categories.
- `arr_list_library`: list Radarr movies or Sonarr series.\n- `arr_update_library_item`: update monitoring and/or quality profile for an existing movie or series while preserving all other fields.
- `arr_search_catalog`: find movies/series by title.
- `arr_get_queue`: inspect download/import queues.
- `arr_get_setup_options`: retrieve valid root folders and quality profiles.
- `arr_add_movie` / `arr_add_series`: add titles by TMDB/TVDB ID.
- `arr_search_releases` / `arr_grab_release`: search and send a selected release to the download client. The browser library screen exposes this workflow per movie or series.

The API bridge supports the native operations exposed by each application, rather than hard-coding a small set of workflows. This lets us add higher-level, easy-to-use tools without losing access to less common features.

## MCP permission levels

Set `STACKARR_MCP_PERMISSION_LEVEL` in the private `.env` file to control what an authenticated MCP client may do:

- `read`: inspect service status, libraries, queues, releases, torrents and configuration. All writes are blocked.
- `operations`: the default. Includes ordinary media operations such as adding titles, grabbing releases, changing monitoring, categorizing torrents and pausing/resuming/rechecking downloads.
- `admin`: also permits sensitive configuration changes, qBittorrent preference changes, torrent deletion and generic ARR API DELETE requests.

The generic Radarr/Sonarr/Prowlarr REST bridge applies the same checks: GET is read-only, ordinary writes require operations, and deletes or configuration/system endpoints require admin. Scryer GraphQL queries are read-only; GraphQL mutations require admin in this first version.

The level is enforced server-side for shared write operations from both MCP tools and the browser dashboard; the dashboard still has its own separate login. Changing the level requires recreating the StackARR container. Invalid values fail closed. Use `read` when connecting an unfamiliar MCP client; raise it to `operations` or `admin` only when those capabilities are needed. Permission is not a per-action approval prompt: an MCP client should still obtain the user's explicit confirmation before invoking sensitive admin operations.

## Configuration coverage

The dashboard exposes an Advanced API explorer for the native REST APIs of Radarr, Sonarr, Prowlarr and Bazarr. It supports GET, POST, PUT, PATCH and DELETE with JSON query parameters and request bodies; API keys remain server-side and the same server-side permission checks used by MCP are applied to every request. This provides access to endpoints that do not yet have dedicated forms. The dashboard also exposes native Radarr and Sonarr configuration records through their APIs: quality and delay profiles, indexers, download clients, notifications, quality definitions, custom formats, import lists, metadata records and tags. Sonarr additionally exposes language and release profiles. Availability varies by application version and API schema; unsupported endpoints are reported by the application rather than silently emulated. Singleton application settings (for example host, UI and media-management settings) and options that require a service restart are not yet exposed as editable forms.

The Scryer dashboard includes a schema-driven control center: it reads the installed GraphQL schema, separates query and mutation fields, shows descriptions, argument types and return types, and supports filtering. A GraphQL console with JSON variables is included for operations not yet represented by dedicated workflows. The schema view is generated from the live Scryer instance rather than assuming a fixed API version. Read-only queries are available at every permission level; GraphQL mutations require admin. The same scryer_graphql MCP tool exposes the native API.

## Security model

- The caller cannot supply a hostname: requests are restricted to the base URLs configured by the operator.
- API keys and passwords are read from environment variables and must never be committed.
- The server does not expose a generic internet HTTP proxy.
- Write operations are available because this project is designed for full control. Treat the MCP endpoint and its credentials as administrator-level access to your media stack.
- The web API requires an authenticated browser session. Torrent pause/resume and library edits require confirmation in the UI. Library updates fetch the current Radarr/Sonarr object and change only the requested monitoring/profile fields, preserving the remaining metadata.
- The assistant should ask before irreversible actions such as deleting library files, removing titles with files, deleting torrents and data, or changing global settings.
- Docker management is a planned optional module. It will use separate permissions and a restricted control layer; no unrestricted Docker socket access is enabled.

## Configure

Copy `.env.example` to `.env` and fill in the URLs and credentials for the applications you have installed. Set `STACKARR_WEB_USERNAME` and `STACKARR_WEB_PASSWORD` to your dashboard login and a long, unique password. Keep `.env` outside Git.

Every URL must be reachable **from inside the StackARR container**. The correct address depends on your deployment:
- If StackARR and an application share a Docker network, use that application's Docker DNS name and internal port.
- If the application is reachable through a host-published port, use a host address reachable from the container.
- If it is on another machine, use that machine's reachable LAN/VPN address.

You do not need to configure services you do not use. Leave their variables empty.

Scryer uses its GraphQL API at `/graphql` and a bearer API key. Create an API key in Scryer's security settings and give it the permissions needed for the operations you want StackARR to perform.

## Install locally

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env, then export its variables before launching:
set -a && source .env && set +a
stackarr-mcp
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
   Put the generated value in `MCP_AUTH_TOKEN`. Set `STACKARR_WEB_USERNAME` and `STACKARR_WEB_PASSWORD` for browser login, then fill in the URLs and credentials for the applications you use. Do not publish or share the `.env` file.
3. Ensure StackARR can reach the configured application URLs from its container. The supplied Compose file creates an isolated StackARR network by default. If your applications are on other Docker networks, attach StackARR to those existing networks in `compose.yaml`. For each network, add it to the service's `networks` list and declare it at the bottom as external, using your own network name. For example:
   ```yaml
   services:
     stackarr:
       networks:
         - default
         - media_apps
   networks:
     media_apps:
       external: true
       name: YOUR_EXISTING_DOCKER_NETWORK
   ```
   Repeat this for additional networks if your applications are split across them. Alternatively, configure URLs that are reachable from the StackARR container without joining their Docker networks.
4. Start StackARR:
   ```bash
   docker compose up -d --build
   ```
5. Check startup:
   ```bash
   docker compose logs -f stackarr
   ```

The MCP endpoint is `http://YOUR_DOCKER_HOST:8765/mcp` and requires `Authorization: Bearer <MCP_AUTH_TOKEN>`. The dashboard is at the same host and port, at `/`. By default both are bound to loopback; set `STACKARR_BIND_ADDRESS=0.0.0.0` for LAN access. Never expose the port directly to the public internet.

The container runs as a non-root user, drops Linux capabilities, and uses a read-only filesystem.

## API references

- Radarr: `/api/v3`
- Sonarr: `/api/v3`
- Prowlarr: `/api/v1`
- Bazarr: native API under `/api`
- Scryer: GraphQL at `/graphql`
- qBittorrent: Web API under `/api/v2`

## Next development steps

1. Add richer library details (monitoring, quality-profile editing and release search/grabbing are now available).
2. Add dedicated Scryer workflows on top of the live schema browser, plus Bazarr management and operation history/auditing.
3. Add fine-grained permissions and safer previews for destructive operations.
4. Add optional Docker management behind a separate restricted permission boundary.
