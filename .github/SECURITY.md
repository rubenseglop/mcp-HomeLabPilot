# Security Policy

HomeLabPilot can interact with homelab infrastructure and may hold API credentials. Please do not disclose vulnerabilities publicly before a fix is available.

## Reporting a vulnerability

Please use **Private vulnerability reporting** / **Report a vulnerability** in the repository's GitHub Security tab when that option is available. Include:

- A concise description of the issue and its impact.
- The affected version, commit, component, and configuration.
- Reproduction steps or a minimal proof of concept.
- Any suggested mitigation, if known.

Do not include real tokens, passwords, API keys, session cookies, personal data, or other secrets in the report.

If private vulnerability reporting is unavailable, contact the repository maintainer privately through GitHub rather than opening a public issue.

## Security documentation

The project's security model, MCP permission levels, preview and confirmation requirements, credential handling, network exposure, agent proxy, and optional Docker gateway are documented in [docs/SECURITY.md](../docs/SECURITY.md).

Please also review the deployment guidance in the README before exposing the service to a LAN or remote network.
