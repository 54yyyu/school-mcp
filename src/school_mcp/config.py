"""Configuration management for the School MCP server."""

import os
import json
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_config() -> Dict[str, str]:
    """
    Get configuration from environment variables first,
    then fall back to config.json if it exists.
    """
    config = {}
    
    # Try to get configuration from environment variables
    env_vars = {
        "CANVAS_ACCESS_TOKEN": os.getenv("CANVAS_ACCESS_TOKEN"),
        "CANVAS_DOMAIN": os.getenv("CANVAS_DOMAIN"),
        "GRADESCOPE_EMAIL": os.getenv("GRADESCOPE_EMAIL"),
        "GRADESCOPE_PASSWORD": os.getenv("GRADESCOPE_PASSWORD"),
    }
    
    # Remove None values
    env_config = {k: v for k, v in env_vars.items() if v is not None}
    
    if all(k in env_config for k in ["CANVAS_ACCESS_TOKEN", "CANVAS_DOMAIN", 
                                     "GRADESCOPE_EMAIL", "GRADESCOPE_PASSWORD"]):
        return {
            "canvas_access_token": env_config["CANVAS_ACCESS_TOKEN"],
            "canvas_domain": env_config["CANVAS_DOMAIN"],
            "gradescope_email": env_config["GRADESCOPE_EMAIL"],
            "gradescope_password": env_config["GRADESCOPE_PASSWORD"],
        }
    
    # Fall back to config.json if it exists
    try:
        config_path = Path(os.path.expanduser("~")) / "Documents" / "projects" / "homie" / "config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config
    except Exception as e:
        raise ValueError(f"Error loading config: {str(e)}")
    
    # If we get here, we couldn't find a valid configuration
    raise ValueError(
        "No valid configuration found. Please set environment variables or create a config.json file."
    )

def save_download_path(path: str) -> None:
    """Save the download path to a settings file."""
    settings_path = Path.home() / ".school_mcp_settings.json"
    
    settings = {}
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
    
    settings["download_path"] = path
    
    with open(settings_path, 'w') as f:
        json.dump(settings, f)

def get_download_path() -> str:
    """Get the saved download path or return a default path."""
    settings_path = Path.home() / ".school_mcp_settings.json"
    
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            settings = json.load(f)
            if "download_path" in settings:
                return settings["download_path"]
    
    # Default path
    return str(Path.home() / "Canvas_Downloads")
