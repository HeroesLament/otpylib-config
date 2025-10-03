#!/usr/bin/env python3
"""
Configuration Manager Core Business Logic

Pure business logic functions with idempotent API.
All functions here are pure - they take state and return new state.
No side effects, no GenServer knowledge, just business logic.

API Design: Idempotent operations that declare desired state rather than imperative CRUD.
"""

import time
import fnmatch
from typing import Dict, Any, List, Callable, Optional, Set
from result import Ok, Err, Result

from otpylib_config.data import ConfigManagerState, ReloadResult, ConfigResult
from otpylib_config.atoms import config_path_atom, path_from_atom


async def ensure_config_value(path: str, value: Any, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """
    Ensure configuration value is set to given value.
    Runtime values are stored separately and overlay source config.
    Idempotent: safe to call multiple times with same data.
    """
    try:
        path_atom = config_path_atom(path)
        
        # Check current effective value (runtime overlay + source config)
        existing_value = state.runtime_config.get(path_atom)
        if existing_value is None:
            existing_value = state.config.get(path_atom)
        
        match existing_value:
            case None:
                # New runtime configuration value
                state.runtime_config[path_atom] = value
                return Ok({
                    "path": path,
                    "old_value": None,
                    "new_value": value,
                    "changed": True,
                    "message": f"Runtime configuration key '{path}' created"
                })
            
            case existing if existing == value:
                # Value already correct
                return Ok({
                    "path": path,
                    "old_value": existing,
                    "new_value": value,
                    "changed": False,
                    "message": f"Runtime configuration key '{path}' already set correctly"
                })
            
            case existing:
                # Value needs updating
                state.runtime_config[path_atom] = value
                return Ok({
                    "path": path,
                    "old_value": existing,
                    "new_value": value,
                    "changed": True,
                    "message": f"Runtime configuration key '{path}' updated"
                })
                
    except Exception as e:
        return Err(f"Failed to ensure config value for '{path}': {str(e)}")


async def get_config_value(path: str, default: Any, state: ConfigManagerState) -> Result[Any, str]:
    """
    Get configuration value by path.
    Runtime values override source values.
    Idempotent: safe to call multiple times.
    """
    try:
        path_atom = config_path_atom(path)
        
        # Check runtime config first (highest priority)
        value = state.runtime_config.get(path_atom)
        if value is not None:
            return Ok(value)
        
        # Fall back to source config
        value = state.config.get(path_atom, default)
        return Ok(value)
        
    except Exception as e:
        return Err(f"Failed to get config value for '{path}': {str(e)}")


async def ensure_subscription(pattern: str, callback: Callable, subscriber_pid, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """
    Ensure subscription exists for pattern and callback.
    Idempotent: safe to call multiple times with same callback.
    """
    try:
        pattern_atom = config_path_atom(pattern)
        
        if pattern_atom not in state.subscribers:
            state.subscribers[pattern_atom] = []
        
        # Store (pid, callback) tuple
        subscription = (subscriber_pid, callback)
        
        # Check if subscription already exists
        if subscription in state.subscribers[pattern_atom]:
            return Ok({
                "pattern": pattern,
                "new_subscription": False,
                "message": f"Already subscribed to pattern '{pattern}'"
            })
        else:
            state.subscribers[pattern_atom].append(subscription)
            return Ok({
                "pattern": pattern,
                "new_subscription": True,
                "message": f"Subscribed to pattern '{pattern}'"
            })
            
    except Exception as e:
        return Err(f"Failed to ensure subscription for pattern '{pattern}': {str(e)}")


async def ensure_subscription_absent(pattern: str, callback: Callable, subscriber_pid, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """
    Ensure subscription does not exist for pattern and callback.
    Idempotent: safe to call multiple times.
    """
    try:
        pattern_atom = config_path_atom(pattern)
        
        if pattern_atom not in state.subscribers:
            return Ok({
                "pattern": pattern,
                "was_subscribed": False,
                "message": f"Was not subscribed to pattern '{pattern}'"
            })
        
        subscription = (subscriber_pid, callback)
        
        if subscription in state.subscribers[pattern_atom]:
            state.subscribers[pattern_atom].remove(subscription)
            # Clean up empty subscriber lists
            if not state.subscribers[pattern_atom]:
                del state.subscribers[pattern_atom]
            return Ok({
                "pattern": pattern,
                "was_subscribed": True,
                "message": f"Unsubscribed from pattern '{pattern}'"
            })
        else:
            return Ok({
                "pattern": pattern,
                "was_subscribed": False,
                "message": f"Was not subscribed to pattern '{pattern}'"
            })
            
    except Exception as e:
        return Err(f"Failed to ensure subscription absent for pattern '{pattern}': {str(e)}")


async def reconcile_configuration(state: ConfigManagerState) -> Result[ReloadResult, str]:
    """
    Reconcile configuration from all sources.
    Merges by priority and detects changes for subscriber notification.
    
    This is the core reconciliation operation - idempotent and safe to call repeatedly.
    """
    start_time = time.time()
    state.total_reloads += 1
    
    try:
        # Collect configurations from all sources by priority
        source_configs = []
        sources_failed = 0
        errors = []
        
        for source in state.sources:
            try:
                config = await source.load()
                if config is not None and config:  # Skip None and empty dicts
                    source_configs.append((source.priority, source.name, config))
            except Exception as e:
                sources_failed += 1
                error_msg = f"Failed to load from source {source.name}: {e}"
                errors.append(error_msg)
        
        # Sort by priority (lowest first, so higher priority overwrites)
        source_configs.sort(key=lambda x: x[0])
        
        # Merge configurations
        merged_config = {}
        for priority, source_name, config in source_configs:
            _deep_merge_config(merged_config, config)
        
        # Convert to atom-keyed config and detect changes
        old_atom_config = state.config.copy()
        new_atom_config = {}
        
        # Convert new source config to atom keys
        _flatten_config_to_atoms(merged_config, new_atom_config)
        
        # Update source config (but preserve runtime overrides)
        state.config = new_atom_config
        
        # Count changes in effective configuration (source + runtime overlay)
        old_effective_config = old_atom_config.copy()
        old_effective_config.update(state.runtime_config)  # Apply runtime overlay to old
        
        new_effective_config = new_atom_config.copy()
        new_effective_config.update(state.runtime_config)  # Apply runtime overlay to new
        
        config_changes = _count_config_differences(old_effective_config, new_effective_config)
        state.last_reload = time.time()
        
        # Calculate duration
        duration = time.time() - start_time
        state.last_reload_duration = duration
        
        # Clear any previous error if this reload succeeded
        if sources_failed == 0:
            state.last_error = None
        else:
            state.last_error = errors[-1] if errors else None
        
        result = ReloadResult(
            success=True,
            sources_loaded=len(source_configs),
            sources_failed=sources_failed,
            config_changes=config_changes,
            duration_seconds=duration,
            errors=errors
        )
        
        return Ok(result)
        
    except Exception as e:
        duration = time.time() - start_time
        state.failed_reloads += 1
        state.last_error = str(e)
        state.last_reload_duration = duration
        
        result = ReloadResult(
            success=False,
            sources_loaded=0,
            sources_failed=len(state.sources),
            config_changes=0,
            duration_seconds=duration,
            errors=[str(e)]
        )
        
        return Err(f"Configuration reconciliation failed: {str(e)}")


async def get_manager_status(state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """Get current manager status and statistics."""
    try:
        status = {
            "config_keys": len(state.config),
            "subscribers": len(state.subscribers),
            "sources": len(state.sources),
            "last_reload": state.last_reload,
            "reload_interval": state.reload_interval,
            "total_reloads": state.total_reloads,
            "failed_reloads": state.failed_reloads,
            "last_reload_duration": state.last_reload_duration,
            "last_error": state.last_error,
            "started_at": state.started_at.isoformat()
        }
        return Ok(status)
    except Exception as e:
        return Err(f"Failed to get status: {str(e)}")


def get_config_differences(old_config: Dict, new_config: Dict) -> List[Dict[str, Any]]:
    """
    Get list of configuration differences between old and new config.
    Returns list of change records for subscriber notification.
    """
    changes = []
    all_keys = set(old_config.keys()) | set(new_config.keys())
    
    for path_atom in all_keys:
        old_value = old_config.get(path_atom)
        new_value = new_config.get(path_atom)
        
        if old_value != new_value:
            path_str = path_from_atom(path_atom)
            changes.append({
                "path": path_str,
                "old_value": old_value,
                "new_value": new_value
            })
    
    return changes


def get_matching_subscribers(path: str, state: ConfigManagerState) -> List[tuple]:
    """
    Get all subscriber (pid, callback) tuples that match the given configuration path.
    Uses pattern matching to find relevant subscribers.
    """
    matching_subscriptions = []
    
    for pattern_atom, subscriptions_list in state.subscribers.items():
        pattern_str = path_from_atom(pattern_atom)
        
        if _path_matches_pattern(path, pattern_str):
            matching_subscriptions.extend(subscriptions_list)
    
    return matching_subscriptions


# =============================================================================
# Internal Helper Functions
# =============================================================================

def _deep_merge_config(target: Dict[str, Any], source: Dict[str, Any]):
    """
    Deep merge source dict into target dict.
    Higher priority sources overwrite lower priority ones.
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge_config(target[key], value)
        else:
            target[key] = value


def _flatten_config_to_atoms(config: Dict[str, Any], atom_config: Dict, prefix: str = ""):
    """
    Convert nested dict to flat atom-keyed dict.
    Handles deep nesting with dot notation paths.
    """
    for key, value in config.items():
        path = f"{prefix}.{key}" if prefix else key
        
        if isinstance(value, dict):
            # Recurse for nested dicts
            _flatten_config_to_atoms(value, atom_config, path)
        else:
            # Store with atom key
            path_atom = config_path_atom(path)
            atom_config[path_atom] = value


def _count_config_differences(old_config: Dict, new_config: Dict) -> int:
    """Count the number of configuration differences between old and new config."""
    changes = 0
    all_keys = set(old_config.keys()) | set(new_config.keys())
    
    for path_atom in all_keys:
        old_value = old_config.get(path_atom)
        new_value = new_config.get(path_atom)
        
        if old_value != new_value:
            changes += 1
    
    return changes


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """
    Check if a configuration path matches a pattern (supports wildcards).
    Uses fnmatch for Unix shell-style wildcards.
    """
    return fnmatch.fnmatch(path, pattern)
