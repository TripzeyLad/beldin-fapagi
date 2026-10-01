"""Shared exclusions for project observation and sanitized action backups."""
from pathlib import Path

def denied(path):
    parts = [p.casefold() for p in Path(path).parts]
    return any(p.startswith(".env") or p.startswith("config.") or
               p in {"token.txt", "secrets.json", ".git", "__pycache__"} or
               p.endswith((".pem", ".key", ".pfx")) for p in parts)
