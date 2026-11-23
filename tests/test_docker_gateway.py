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
