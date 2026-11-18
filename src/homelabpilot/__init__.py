"""HomeLabPilot package and legacy environment compatibility."""

import os

# Keep existing installations working while operators migrate STACKARR_* keys.
for _legacy_key, _legacy_value in tuple(os.environ.items()):
    if _legacy_key.startswith("STACKARR_"):
        os.environ.setdefault("HOMELABPILOT_" + _legacy_key[len("STACKARR_"):], _legacy_value)

del _legacy_key, _legacy_value

__version__ = "0.1.0"
