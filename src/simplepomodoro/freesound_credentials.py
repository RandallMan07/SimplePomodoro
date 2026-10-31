"""Freesound credentials in the desktop keyring, or explicitly in memory."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import threading

_session_key = ""
ATTRIBUTES = {"application": "simplepomodoro", "service": "freesound"}


class CredentialError(Exception):
    pass


def credentials_path():
    """Legacy private file, read for compatibility; never newly written."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "simplepomodoro/freesound.json"


def validate_api_key(value):
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,256}", value):
        raise ValueError("Enter your Freesound application API key (letters and digits).")
    return value


def _secret():
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Gio, Secret
    except (ImportError, ValueError):
        raise CredentialError("Desktop keyring unavailable. Use this key for the current session instead.") from None
    schema = Secret.Schema.new("io.github.simplepomodoro.Freesound", Secret.SchemaFlags.NONE,
                               {name: Secret.SchemaAttributeType.STRING for name in ATTRIBUTES})
    return Secret, Gio, schema


@contextmanager
def _bounded(cancellable=None):
    Secret, Gio, schema = _secret()
    cancellable = cancellable or Gio.Cancellable()
    timeout = threading.Timer(8, cancellable.cancel)
    timeout.daemon = True
    timeout.start()
    try:
        yield Secret, schema, cancellable
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("Desktop keyring unavailable or locked. Unlock it or use a key for this session.") from None
    finally:
        timeout.cancel()


def credential_state(cancellable=None):
    """Find matching item metadata, without loading any secret into the form."""
    if os.environ.get("FREESOUND_API_KEY", "").strip():
        return "environment"
    if _session_key:
        return "session"
    try:
        with _bounded(cancellable) as (Secret, schema, cancel):
            service = Secret.Service.get_sync(Secret.ServiceFlags.NONE, cancel)
            items = service.search_sync(schema, ATTRIBUTES, Secret.SearchFlags.NONE, cancel)
            if items:
                return "locked" if items[0].get_locked() else "keyring"
    except CredentialError:
        return "legacy" if credentials_path().is_file() else "unavailable"
    return "legacy" if credentials_path().is_file() else "none"


def _legacy_key():
    try:
        data = json.loads(credentials_path().read_text())
        return validate_api_key(data.get("api_key", "")) if isinstance(data, dict) else ""
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def load_api_key():
    environment = os.environ.get("FREESOUND_API_KEY", "").strip()
    if environment:
        return environment
    if _session_key:
        return _session_key
    try:
        with _bounded() as (Secret, schema, cancel):
            key = Secret.password_lookup_sync(schema, ATTRIBUTES, cancel)
            if key:
                return key
    except CredentialError:
        legacy = _legacy_key()
        if legacy:
            return legacy
        raise
    return _legacy_key()


def save_api_key(value, cancellable=None):
    """Store persistently; only a successful store may remove a legacy file."""
    global _session_key
    value = validate_api_key(value)
    with _bounded(cancellable) as (Secret, schema, cancel):
        if not Secret.password_store_sync(schema, ATTRIBUTES, Secret.COLLECTION_DEFAULT,
                                           "SimplePomodoro · Freesound API key", value, cancel):
            raise CredentialError("The key was not saved. Unlock the desktop keyring or use session-only storage.")
    _session_key = ""
    try:
        credentials_path().unlink(missing_ok=True)
    except OSError:
        raise CredentialError("Saved in desktop keyring; the legacy file could not be removed.") from None


def migrate_api_key(cancellable=None):
    value = _legacy_key()
    if not value:
        raise CredentialError("No readable legacy key. Enter the key to save it in your desktop keyring.")
    save_api_key(value, cancellable)


def use_session_key(value):
    global _session_key
    _session_key = validate_api_key(value)


def clear_api_key(cancellable=None):
    global _session_key
    _session_key = ""
    # A failed keyring removal must not be presented as a fully cleared key.
    with _bounded(cancellable) as (Secret, schema, cancel):
        Secret.password_clear_sync(schema, ATTRIBUTES, cancel)
    try:
        credentials_path().unlink(missing_ok=True)
    except OSError:
        raise CredentialError("Keyring key removed; the legacy local file could not be removed.") from None
