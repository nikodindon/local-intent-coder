"""
Configuration loader.
Reads config.json and applies sensible defaults.
"""

import json
import os

DEFAULTS = {
    "base_url": "http://localhost:8080/v1",
    "api_key": "sk-placeholder",
    "model": "qwen2.5-coder-7b",
    "context_size": 32768,
    "max_out_tokens": 3000,
    "snapshot_limit": 2000,
    "temperature": 0.1,
}


def load_config(path: str = "config.json") -> dict:
    config = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            overrides = json.load(f)
        config.update(overrides)
    else:
        print(f"  [config] {path} not found, using defaults.")
    return config
