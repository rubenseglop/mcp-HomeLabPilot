"""Unit tests for the restricted Docker Engine gateway."""

from homelabpilot import docker_gateway


def test_visible_containers_returns_the_allowlisted_alias(monkeypatch):
    monkeypatch.setattr(docker_gateway, "ALLOWED", {"allowed-alias"})
    monkeypatch.setattr(
        docker_gateway,
        "daemon_request",
        lambda method, path: (
            200,
            [{
                "Id": "a" * 64,
                "Names": ["/unlisted-primary-name", "/allowed-alias"],
                "Image": "example/image:latest",
                "State": "running",
                "Status": "Up 2 hours",
            }],
        ),
    )

    result = docker_gateway.visible_containers()

    assert len(result) == 1
    assert result[0]["name"] == "allowed-alias"
    assert result[0]["id"] == "a" * 64


def test_visible_containers_hides_non_allowlisted_containers(monkeypatch):
    monkeypatch.setattr(docker_gateway, "ALLOWED", {"only-this"})
    monkeypatch.setattr(
        docker_gateway,
        "daemon_request",
        lambda method, path: (
            200,
            [{
                "Id": "b" * 64,
                "Names": ["/not-allowed"],
                "Image": "example/image:latest",
                "State": "running",
                "Status": "Up 2 hours",
            }],
        ),
    )

    assert docker_gateway.visible_containers() == []


def test_recyclarr_sync_executes_only_fixed_command_in_configured_allowlisted_container(monkeypatch):
    calls = []
    monkeypatch.setenv("HOMELABPILOT_RECYCLARR_CONTAINER", "recyclarr")
    monkeypatch.setattr(docker_gateway, "visible_containers", lambda: [{
        "id": "c" * 64, "name": "recyclarr", "state": "running", "status": "Up",
    }])

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if path.endswith("/exec"):
            return 201, {"Id": "exec-123"}
        if path.endswith("/start"):
            return 200, {"message": "sync output"}
        if path.endswith("/json"):
            return 200, {"ExitCode": 0}
        raise AssertionError(path)

    monkeypatch.setattr(docker_gateway, "daemon_request", fake_request)
    result = docker_gateway.run_recyclarr_sync()

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert calls[0][2]["Cmd"] == ["recyclarr", "sync"]
    assert calls[0][2]["Cmd"] != ["sh", "-c", "recyclarr sync"]
    assert calls[1][1] == "/exec/exec-123/start"
    assert calls[2][1] == "/exec/exec-123/json"


def test_recyclarr_sync_refuses_non_allowlisted_container(monkeypatch):
    monkeypatch.setenv("HOMELABPILOT_RECYCLARR_CONTAINER", "recyclarr")
    monkeypatch.setattr(docker_gateway, "visible_containers", lambda: [])
    with pytest.raises(PermissionError, match="allowlist"):
        docker_gateway.run_recyclarr_sync()
