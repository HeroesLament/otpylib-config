#!/usr/bin/env python3
"""
Base Configuration Source

Abstract base class for all configuration sources.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ConfigSource(ABC):
    """Abstract base class for configuration sources."""
    
    @abstractmethod
    async def load(self) -> Optional[Dict[str, Any]]:
        """
        Load configuration from this source.
        
        Returns:
            Dict with configuration data, or None if no changes since last load
        """
        pass
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """Source priority (higher number = higher priority)."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this source."""
        pass
