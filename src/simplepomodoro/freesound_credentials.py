"""Private, local Freesound API-key configuration; never timer preferences."""
import json
import os
from pathlib import Path
import re
import tempfile


def credentials_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "simplepomodoro/freesound.json"


def validate_api_key(value):
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,256}", value):
        raise ValueError("Enter the API key from your Freesound application credentials (letters and digits).")
    return value


def load_api_key():
    environment = os.environ.get("FREESOUND_API_KEY", "").strip()
    if environment:
        return environment
    try:
        data = json.loads(credentials_path().read_text())
        return validate_api_key(data.get("api_key", "")) if isinstance(data, dict) else ""
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def save_api_key(value):
    value = validate_api_key(value)
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".freesound-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"api_key": value}, output)
            output.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def clear_api_key():
    credentials_path().unlink(missing_ok=True)
