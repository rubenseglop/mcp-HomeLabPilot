"""Small unit tests for StackARR path validation."""
import pytest

from stackarr.server import _safe_path


@pytest.mark.parametrize("path", ["/api/v3/movie", "/api/v2/torrents/info"])
def test_safe_path_accepts_api_paths(path):
    assert _safe_path(path) == path


@pytest.mark.parametrize(
    "path",
    ["", "api/v3/movie", "//evil.example/path", "https://evil.example", "/\\evil", "/api/v3/../admin"],
)
def test_safe_path_rejects_non_api_paths(path):
    with pytest.raises(ValueError):
        _safe_path(path)
