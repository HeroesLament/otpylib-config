#!/usr/bin/env python3
"""
Runtime Configuration Source

In-memory configuration source for runtime updates.
Highest priority source for dynamic configuration changes.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from .base import ConfigSource


@dataclass
class RuntimeSource(ConfigSource):
    """In-memory configuration source for runtime updates."""
    
    _priority: int = 100  # Highest priority
    _config: Dict[str, Any] = field(default_factory=dict)
    _version: int = 0
    _last_version: int = -1
    
    @property
    def priority(self) -> int:
        return self._priority
    
    @property
    def name(self) -> str:
        return "runtime"
    
    async def load(self) -> Optional[Dict[str, Any]]:
        """Return runtime configuration if it has changed."""
        if self._last_version == self._version:
            return None  # No changes
        
        self._last_version = self._version
        # Only return config if we actually have values
        return self._config.copy() if self._config else None
    
    def set(self, key: str, value: Any):
        """Set a runtime configuration value."""
        self._set_nested_value(self._config, key, value)
        self._version += 1
    
    def delete(self, key: str):
        """Delete a runtime configuration value."""
        self._delete_nested_value(self._config, key)
        self._version += 1
    
    def clear(self):
        """Clear all runtime configuration."""
        self._config.clear()
        self._version += 1
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any):
        """Set a nested value using dot notation."""
        parts = key.split('.')
        current = config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    def _delete_nested_value(self, config: Dict[str, Any], key: str):
        """Delete a nested value using dot notation."""
        parts = key.split('.')
        current = config
        
        try:
            for part in parts[:-1]:
                current = current[part]
            del current[parts[-1]]
        except (KeyError, TypeError):
            pass  # Key doesn't exist, ignore
