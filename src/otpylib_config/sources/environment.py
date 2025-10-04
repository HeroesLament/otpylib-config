#!/usr/bin/env python3
"""
Environment Configuration Source

Load configuration from environment variables with prefix support.
"""

import os
import json
from typing import Dict, Any
from dataclasses import dataclass

from .base import ConfigSource


@dataclass
class EnvironmentSource(ConfigSource):
    """Load configuration from environment variables."""
    
    prefix: str = ""
    _priority: int = 2
    
    @property
    def priority(self) -> int:
        return self._priority
    
    @property
    def name(self) -> str:
        return f"env:{self.prefix or 'all'}"
    
    async def load(self) -> Dict[str, Any]:
        """Load configuration from environment variables.
        Always returns a dict (may be empty).
        """
        config: Dict[str, Any] = {}

        for key, value in os.environ.items():
            if self.prefix and not key.startswith(self.prefix):
                continue
            
            # Convert MYAPP_DATABASE_URL -> database.url
            if self.prefix:
                config_key = key[len(self.prefix):].lower().replace('_', '.')
            else:
                config_key = key.lower().replace('_', '.')

            if not config_key:
                continue
            
            parsed_value = self._parse_value(value)
            self._set_nested_value(config, config_key, parsed_value)

        return config
    
    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate Python type."""
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        if value.lower() in ('none', 'null', ''):
            return None
        
        try:
            if '.' not in value:
                return int(value)
            return float(value)
        except ValueError:
            pass
        
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
        
        return value
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any):
        """Set a nested value in config dict using dot notation."""
        parts = key.split('.')
        current = config
        
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
