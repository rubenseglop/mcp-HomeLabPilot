# StackARR MCP

A unified MCP server to **control your media stack from an MCP client such as ChatGPT**.

It connects directly to the native APIs of Radarr, Sonarr, Prowlarr, Bazarr, Scryer and qBittorrent. The goal is not to build another dashboard: it is to expose the applications' capabilities as tools the assistant can call.

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
- `arr_list_library`: list Radarr movies or Sonarr series.
- `arr_search_catalog`: find movies/series by title.
- `arr_get_queue`: inspect download/import queues.
- `arr_get_setup_options`: retrieve valid root folders and quality profiles.
- `arr_add_movie` / `arr_add_series`: add titles by TMDB/TVDB ID.
- `arr_search_releases` / `arr_grab_release`: search and send a selected release to the download client.

The API bridge supports the native operations exposed by each application, rather than hard-coding a small set of workflows. This lets us add higher-level, easy-to-use tools without losing access to less common features.

## Security model

- The caller cannot supply a hostname: requests are restricted to the base URLs configured in environment variables.
- API keys and passwords are read from environment variables and must never be committed.
- The server does not expose a generic internet HTTP proxy.
- Write operations are available because this project is designed for full control. Treat the MCP endpoint and its credentials as administrator-level access to your media stack.
- The assistant should ask before irreversible actions such as deleting library files, removing titles with files, deleting torrents and data, or changing global settings.

## Configure

Copy `.env.example` to `.env` and fill in the URLs and credentials. Keep `.env` outside Git.

Use Docker service names when StackARR shares a Docker network with the applications; otherwise use reachable LAN URLs. The default examples are placeholders and may need changing for your Compose network.

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

The server uses MCP over stdio. Configure the MCP client to launch `stackarr-mcp` with the environment variables.

Run the unit tests with `pip install -e ".[test]"` followed by `pytest`.

## API references

- Radarr: `/api/v3`
- Sonarr: `/api/v3`
- Prowlarr: `/api/v1`
- Bazarr: native API under `/api`
- Scryer: GraphQL at `/graphql`
- qBittorrent: Web API under `/api/v2`

## Next development steps

1. Expand the typed tools with monitoring, quality-profile changes, commands, and safe delete/preview workflows.
2. Use `scryer_introspect` against the installed Scryer version, then build safe typed workflows for title discovery, library management, requests, releases and subtitles.
3. Add qBittorrent file-upload support for adding .torrent files.
4. Add qBittorrent torrent-file uploads and a Docker Compose deployment example.
