# StackARR MCP

MCP server for **read-only diagnosis** of a self-hosted *arr stack.

The goal is to let an MCP client inspect Radarr, Sonarr, Prowlarr, Bazarr and qBittorrent together, correlate their state, and explain where a media workflow is stuck — without changing configuration, queue items, downloads, or library files.

## Principles

- Read-only: this server only calls API endpoints intended for inspection.
- Secrets stay in environment variables; never commit real API keys or passwords.
- Local-first: run it next to the Docker stack, or connect it to services reachable over your LAN.
- Diagnostic output should identify evidence, the likely failing stage, and a safe suggested remedy.

## Current status

Initial scaffold. The first implementation provides connection checks and read-only queue snapshots for Radarr, Sonarr, Prowlarr and qBittorrent. Bazarr is included in configuration and will be added to the diagnostic probes after its API behavior is verified against the deployed version.

## Configuration

Copy `.env.example` to `.env` and fill in the URLs and API keys for the services you use.

Do not publish `.env`, API keys, passwords, or access tokens.

## Run locally

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env, then:
set -a && source .env && set +a
stackarr-mcp
```

The server uses MCP over stdio. Configure your MCP client to launch `stackarr-mcp` with the required environment variables.

## Available tools

- `stack_status`: checks connectivity and reports application versions/status.
- `get_download_queue`: reads the Radarr, Sonarr and qBittorrent queues and returns a compact snapshot.

All tools are observational. No command is provided to add, remove, rename, import, search-and-grab, or modify media.

## Planned

1. Add Bazarr diagnostics and subtitle status.
2. Correlate a title across the request, *arr queue, download client, import history and library.
3. Add a `diagnose_media` tool with evidence, first failing stage, and remedy.
4. Add tests with mocked API responses and deployment examples for Docker/Portainer.
