#!/usr/bin/env python3
"""
File Configuration Source

Load configuration from TOML or JSON files with change detection.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
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
    _last_modified: float = 0
    
    @property
    def priority(self) -> int:
        return self._priority
    
    @property
    def name(self) -> str:
        return f"file:{self.path}"
    
    async def load(self) -> Optional[Dict[str, Any]]:
        """Load configuration from file."""
        path = Path(self.path)
        
        if not path.exists():
            return {}
        
        try:
            stat = path.stat()
            if stat.st_mtime <= self._last_modified:
                return None  # No changes
            
            self._last_modified = stat.st_mtime
            
            with open(path, 'rb') as f:
                if self.format.lower() == "toml":
                    if tomllib is None:
                        raise ImportError("TOML support requires 'tomli' package")
                    return tomllib.load(f)
                elif self.format.lower() == "json":
                    return json.load(f)
                else:
                    raise ValueError(f"Unsupported format: {self.format}")
                    
        except Exception as e:
            return {}
