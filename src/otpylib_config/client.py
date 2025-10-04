#!/usr/bin/env python3
"""
Configuration Client API

Simple client interface for configuration access.
"""

from otpylib import gen_server, process
from otpylib_config.atoms import GET_CONFIG, PUT_CONFIG, SUBSCRIBE, RELOAD
from otpylib_config.data import CONFIG_MANAGER


class Config:
    """Simple client API for configuration access."""
    @staticmethod
    async def get(path: str, default=None):
        """Get configuration value by path."""
        result = await gen_server.call(CONFIG_MANAGER, (GET_CONFIG, path, default), timeout=5.0)
        return result
    
    @staticmethod  
    async def put(path: str, value):
        """Set configuration value at path."""
        result = await gen_server.call(CONFIG_MANAGER, (PUT_CONFIG, path, value), timeout=5.0)
        return result
    
    @staticmethod
    async def subscribe(pattern: str, callback, subscriber_pid):
        """
        Subscribe to configuration changes matching pattern.
        
        Args:
            pattern: Glob pattern for config paths (e.g., "app.*")
            callback: Function called as callback(subscriber_pid, path, old_value, new_value)
            subscriber_pid: PID of the subscribing process (use process.self())
        """
        if subscriber_pid is None:
            raise TypeError("subscriber_pid is required - pass process.self() from your worker")
        
        result = await gen_server.call(CONFIG_MANAGER, (SUBSCRIBE, pattern, callback, subscriber_pid), timeout=5.0)
        return result
    
    @staticmethod
    async def reload():
        """Force reload from all sources."""
        return await gen_server.cast(CONFIG_MANAGER, (RELOAD,))