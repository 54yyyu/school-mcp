"""Configuration management for the School MCP server.

Supports multiple named accounts (e.g. "columbia", "mit"). Each account is
defined in the environment with a prefix, for example:

    COLUMBIA_CANVAS_ACCESS_TOKEN=...
    COLUMBIA_CANVAS_DOMAIN=canvas.instructure.com
    COLUMBIA_GRADESCOPE_EMAIL=...
    COLUMBIA_GRADESCOPE_PASSWORD=...

    MIT_CANVAS_ACCESS_TOKEN=...
    MIT_CANVAS_DOMAIN=canvas.mit.edu

The active account comes from ~/.school_mcp_settings.json, falling back to the
SCHOOL_ACCOUNT environment variable. Unprefixed CANVAS_* / GRADESCOPE_* variables
and config.json are still honored as a legacy "default" account.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN_KEY = "CANVAS_ACCESS_TOKEN"
LEGACY_ACCOUNT = "default"
SETTINGS_PATH = Path.home() / ".school_mcp_settings.json"


def _load_settings() -> Dict:
    """Read the settings file, tolerating a missing or corrupt file."""
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_settings(settings: Dict) -> None:
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2)


def _env_prefix(account: str) -> str:
    """Environment variable prefix for an account name."""
    return account.strip().upper().replace('-', '_').replace(' ', '_')


def _account_env(account: str, key: str) -> Optional[str]:
    return os.getenv(f"{_env_prefix(account)}_{key}")


def _legacy_config() -> Optional[Dict[str, str]]:
    """The pre-multi-account configuration: unprefixed env vars, then config.json."""
    token = os.getenv(TOKEN_KEY)
    domain = os.getenv("CANVAS_DOMAIN")
    if token and domain:
        return {
            "account": LEGACY_ACCOUNT,
            "canvas_access_token": token,
            "canvas_domain": domain,
            "gradescope_email": os.getenv("GRADESCOPE_EMAIL"),
            "gradescope_password": os.getenv("GRADESCOPE_PASSWORD"),
        }

    config_path = Path(os.path.expanduser("~")) / "Documents" / "projects" / "homie" / "config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Error loading config.json: {str(e)}")
        if config.get("canvas_access_token") and config.get("canvas_domain"):
            config.setdefault("gradescope_email", None)
            config.setdefault("gradescope_password", None)
            config["account"] = LEGACY_ACCOUNT
            return config

    return None


def list_accounts() -> List[str]:
    """
    List every configured account name, discovered from <PREFIX>_CANVAS_ACCESS_TOKEN
    environment variables. Includes the legacy "default" account when one exists.
    """
    accounts = []
    suffix = f"_{TOKEN_KEY}"
    for key, value in os.environ.items():
        if key.endswith(suffix) and key != suffix and value:
            accounts.append(key[:-len(suffix)].lower())

    accounts.sort()

    if _legacy_config() is not None:
        accounts.append(LEGACY_ACCOUNT)

    return accounts


def get_active_account() -> str:
    """
    Name of the account currently in use: the saved setting, else SCHOOL_ACCOUNT,
    else the only configured account.
    """
    accounts = list_accounts()
    if not accounts:
        raise ValueError(
            "No accounts configured. Add <NAME>_CANVAS_ACCESS_TOKEN and "
            "<NAME>_CANVAS_DOMAIN to your .env file."
        )

    saved = _load_settings().get("active_account")
    if saved and saved.lower() in accounts:
        return saved.lower()

    from_env = os.getenv("SCHOOL_ACCOUNT")
    if from_env and from_env.lower() in accounts:
        return from_env.lower()

    if len(accounts) == 1:
        return accounts[0]

    raise ValueError(
        f"No active account selected. Configured accounts: {', '.join(accounts)}. "
        "Set SCHOOL_ACCOUNT in .env or call set_active_account()."
    )


def set_active_account(account: str) -> str:
    """Persist the active account. Returns the canonical account name."""
    name = account.strip().lower()
    accounts = list_accounts()
    if name not in accounts:
        raise ValueError(
            f"Unknown account '{account}'. Configured accounts: {', '.join(accounts) or 'none'}."
        )

    settings = _load_settings()
    settings["active_account"] = name
    _save_settings(settings)
    return name


def get_config(account: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Get the configuration for an account (the active one when not specified).

    Returns canvas_access_token, canvas_domain, gradescope_email,
    gradescope_password and account. The Gradescope values are None for accounts
    that do not have Gradescope configured.
    """
    name = (account or get_active_account()).strip().lower()

    if name == LEGACY_ACCOUNT:
        legacy = _legacy_config()
        if legacy is None:
            raise ValueError("No legacy configuration found.")
        return legacy

    token = _account_env(name, TOKEN_KEY)
    domain = _account_env(name, "CANVAS_DOMAIN")

    if not token or not domain:
        accounts = list_accounts()
        raise ValueError(
            f"Account '{name}' is missing {_env_prefix(name)}_{TOKEN_KEY} or "
            f"{_env_prefix(name)}_CANVAS_DOMAIN. Configured accounts: "
            f"{', '.join(accounts) or 'none'}."
        )

    return {
        "account": name,
        "canvas_access_token": token,
        "canvas_domain": domain,
        "gradescope_email": _account_env(name, "GRADESCOPE_EMAIL"),
        "gradescope_password": _account_env(name, "GRADESCOPE_PASSWORD"),
    }


def has_gradescope(config: Dict[str, Optional[str]]) -> bool:
    """Whether an account config carries usable Gradescope credentials."""
    return bool(config.get("gradescope_email") and config.get("gradescope_password"))


def save_download_path(path: str) -> None:
    """Save the download path to a settings file."""
    settings = _load_settings()
    settings["download_path"] = path
    _save_settings(settings)


def get_download_path() -> str:
    """Get the saved download path or return a default path."""
    path = _load_settings().get("download_path")
    if path:
        return path

    # Default path
    return str(Path.home() / "Canvas_Downloads")
