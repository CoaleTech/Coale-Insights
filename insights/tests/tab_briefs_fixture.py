import json
import pathlib

_DIR = pathlib.Path(__file__).parent / "fixtures" / "tab_briefs"


def load(module: str) -> dict:
    """The payload a dashboard module's ``briefs()`` receives (envelope removed)."""
    raw = json.loads((_DIR / f"{module}.json").read_text())
    return raw["data"] if isinstance(raw.get("data"), dict) else raw
