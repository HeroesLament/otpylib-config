#!/usr/bin/env python3
"""
Configuration Data Structures

Data structures and types for otpylib-config.
Pure data - no business logic here.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Literal, Union
from datetime import datetime

from otpylib import atom
from otpylib_config.sources import ConfigSource


# =============================================================================
# State Structures
# =============================================================================

@dataclass
class ConfigManagerState:
    """
    State container for the Configuration Manager GenServer.
    
    Tracks configuration sources, current values, subscriptions, and reload metrics.
    """
    started_at: datetime = field(default_factory=datetime.now)
    
    # Configuration state
    config: Dict[Any, Any] = field(default_factory=dict)  # Maps path atoms to final values
    runtime_config: Dict[Any, Any] = field(default_factory=dict)  # Maps path atoms to runtime overrides
    subscribers: Dict[Any, List[Callable]] = field(default_factory=dict)  # Maps pattern atoms to callbacks
    
    # Source management (excludes runtime - that's in runtime_config above)
    sources: List[ConfigSource] = field(default_factory=list)  # ConfigSource objects
    last_reload: float = 0
    reload_interval: float = 30.0
    
    # Performance metrics
    total_reloads: int = 0
    failed_reloads: int = 0
    last_reload_duration: float = 0
    last_error: Optional[str] = None


@dataclass
class ConfigSpec:
    """Configuration specification for a configuration manager."""
    
    id: str
    sources: List[ConfigSource]  # List of ConfigSource objects
    reload_interval: float = 30.0  # Seconds between automatic reloads
    
    def __post_init__(self):
        """Validate the configuration spec."""
        if not self.id:
            raise ValueError("Configuration spec must have an ID")
        
        if not self.sources:
            raise ValueError("Configuration spec must have at least one source")
        
        if self.reload_interval <= 0:
            raise ValueError("Reload interval must be positive")


# =============================================================================
# GenServer Constants
# =============================================================================

CONFIG_MANAGER = atom.ensure("config_manager")
CONFIG_SUP = atom.ensure("config_sup")


# =============================================================================
# RPC Call Definitions
# =============================================================================

class ConfigRPC:
    """RPC call definitions for Configuration Manager GenServer."""
    
    # Primary operations
    GET_CONFIG = "get_config"
    PUT_CONFIG = "put_config"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    RELOAD = "reload"
    
    # Query operations
    STATUS = "status"
    PING = "ping"
    
    # Self-messaging info messages
    RELOAD_TICK = "reload_tick"
    CONFIG_CHANGED = "config_changed"


# =============================================================================
# Result Data Structures
# =============================================================================

@dataclass
class ConfigResult:
    """Result of a configuration operation."""
    success: bool
    operation: str
    duration_seconds: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    errors: List[str] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None


@dataclass
class ReloadResult:
    """Result of a configuration reload operation."""
    success: bool
    sources_loaded: int
    sources_failed: int
    config_changes: int
    duration_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    errors: List[str] = field(default_factory=list)
