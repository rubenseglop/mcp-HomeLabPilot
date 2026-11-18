"""A deliberately small Docker Engine gateway for the optional Docker profile.

The daemon socket is mounted only in this process. The network API exposes only
listing and start/stop/restart for explicitly allowlisted container names/IDs.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlsplit

SOCKET_PATH = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
TOKEN = os.getenv("HOMELABPILOT_DOCKER_GATEWAY_TOKEN", "").strip()
ALLOWED = {
    item.strip().lstrip("/")
    for item in os.getenv("HOMELABPILOT_DOCKER_ALLOWED_CONTAINERS", "").split(",")
    if item.strip()
}


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(SOCKET_PATH)


def daemon_request(method: str, path: str) -> tuple[int, object]:
    connection = UnixHTTPConnection("localhost", timeout=10)
    connection.request(method, path, headers={"Host": "docker"})
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    try:
        body: object = json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError):
        body = {"message": raw.decode("utf-8", "replace")[:1000]}
    return response.status, body


def visible_containers() -> list[dict[str, str]]:
    if not ALLOWED:
        return []
    status, body = daemon_request("GET", "/containers/json?all=1")
    if status != 200 or not isinstance(body, list):
        raise RuntimeError("Docker Engine refused the container list request")
    result = []
    for item in body:
        if not isinstance(item, dict):
            continue
        names = [str(name).lstrip("/") for name in item.get("Names", [])]
        identifier = str(item.get("Id", ""))
        if not any(name in ALLOWED for name in names) and identifier not in ALLOWED:
            continue
        result.append({
            "id": identifier,
            "name": names[0] if names else identifier[:12],
            "image": str(item.get("Image", "")),
            "state": str(item.get("State", "unknown")),
            "status": str(item.get("Status", "")),
        })
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeLabPilotDockerGateway"
    sys_version = ""

    def log_message(self, _format: str, *args: object) -> None:
        print("docker-gateway: " + (_format % args))

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + TOKEN
        return bool(TOKEN) and hmac.compare_digest(supplied.encode(), expected.encode())

    def _handle(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "unauthorized"})
            return
        route = urlsplit(self.path).path
        if self.command == "GET" and route == "/health":
            self._send(200, {"ok": True})
            return
        if self.command == "GET" and route == "/v1/containers":
            try:
                self._send(200, visible_containers())
            except Exception as exc:
                self._send(502, {"error": str(exc)[:500]})
            return
        match = re.fullmatch(r"/v1/containers/([^/]+)/(start|stop|restart)", route)
        if self.command == "POST" and match:
            requested, action = map(unquote, match.groups())
            try:
                item = next(
                    (x for x in visible_containers() if x["name"] == requested or x["id"] == requested),
                    None,
                )
                if item is None:
                    self._send(404, {"error": "container is not allowlisted or does not exist"})
                    return
                status, result = daemon_request(
                    "POST", f"/containers/{quote(item['id'], safe='')}/{action}"
                )
                if status not in {204, 304}:
                    self._send(502, {"error": "Docker Engine rejected the action", "status": status, "detail": result})
                    return
                self._send(200, {"ok": True, "container": item["name"], "action": action})
            except Exception as exc:
                self._send(502, {"error": str(exc)[:500]})
            return
        self._send(404, {"error": "route not available"})

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()


def main() -> None:
    if len(TOKEN) < 32:
        raise RuntimeError("HOMELABPILOT_DOCKER_GATEWAY_TOKEN must contain at least 32 characters")
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("DOCKER_GATEWAY_PORT", "2375"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
