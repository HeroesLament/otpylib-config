#!/usr/bin/env python3
"""
File Configuration Source

Load configuration from TOML or JSON files. Always re-read on every load.
"""

import json
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

from .base import ConfigSource

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class FileSource(ConfigSource):
    """Load configuration from a file (TOML or JSON)."""
    
    path: str
    format: str = "toml"
    _priority: int = 1
    
    @property
    def priority(self) -> int:
        return self._priority
    
    @property
    def name(self) -> str:
        return f"file:{self.path}"
    
    async def load(self) -> Dict[str, Any]:
        """Always read configuration fresh from disk."""
        path = Path(self.path)
        if not path.exists():
            return {}
        
        try:
            with open(path, "rb") as f:
                if self.format.lower() == "toml":
                    if tomllib is None:
                        raise ImportError("TOML support requires 'tomli' package")
                    data = tomllib.load(f)
                elif self.format.lower() == "json":
                    data = json.load(f)
                else:
                    raise ValueError(f"Unsupported format: {self.format}")
            
            return data if isinstance(data, dict) else {}
        
        except Exception:
            return {}
