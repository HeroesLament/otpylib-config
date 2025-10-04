"""
Configuration Manager Core Business Logic

Pure business logic functions with idempotent API.
All functions here are pure - they take state and return new state.
No side effects, no GenServer knowledge, just business logic.

API Design: Idempotent operations that declare desired state rather than imperative CRUD.
"""

import time
import fnmatch
from typing import Dict, Any, List, Callable
from result import Ok, Err, Result

from otpylib import atom, process
from otpylib_config.data import ConfigManagerState, ReloadResult
from otpylib_config.atoms import config_path_atom, path_from_atom

# Logger target
LOGGER = atom.ensure("logger")


async def ensure_config_value(path: str, value: Any, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """
    Ensure configuration value is set to given value.
    Runtime values are stored separately and overlay source config.
    Idempotent: safe to call multiple times with same data.
    """
    try:
        path_atom = config_path_atom(path)
        
        # Check current effective value
        existing_value = state.runtime_config.get(path_atom)
        if existing_value is None:
            existing_value = state.config.get(path_atom)
        
        match existing_value:
            case None:
                state.runtime_config[path_atom] = value
                return Ok({
                    "path": path,
                    "old_value": None,
                    "new_value": value,
                    "changed": True,
                    "message": f"Runtime configuration key '{path}' created"
                })
            case existing if existing == value:
                return Ok({
                    "path": path,
                    "old_value": existing,
                    "new_value": value,
                    "changed": False,
                    "message": f"Runtime configuration key '{path}' already set correctly"
                })
            case existing:
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
    """
    try:
        path_atom = config_path_atom(path)
        value = state.runtime_config.get(path_atom)
        if value is not None:
            return Ok(value)
        return Ok(state.config.get(path_atom, default))
    except Exception as e:
        return Err(f"Failed to get config value for '{path}': {str(e)}")


async def ensure_subscription(pattern: str, callback: Callable, subscriber_pid, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """Ensure subscription exists for pattern and callback."""
    try:
        pattern_atom = config_path_atom(pattern)
        if pattern_atom not in state.subscribers:
            state.subscribers[pattern_atom] = []
        
        subscription = (subscriber_pid, callback)
        if subscription in state.subscribers[pattern_atom]:
            return Ok({
                "pattern": pattern,
                "new_subscription": False,
                "message": f"Already subscribed to pattern '{pattern}'"
            })
        state.subscribers[pattern_atom].append(subscription)
        return Ok({
            "pattern": pattern,
            "new_subscription": True,
            "message": f"Subscribed to pattern '{pattern}'"
        })
    except Exception as e:
        return Err(f"Failed to ensure subscription for pattern '{pattern}': {str(e)}")


async def ensure_subscription_absent(pattern: str, callback: Callable, subscriber_pid, state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """Ensure subscription does not exist for pattern and callback."""
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
            if not state.subscribers[pattern_atom]:
                del state.subscribers[pattern_atom]
            return Ok({
                "pattern": pattern,
                "was_subscribed": True,
                "message": f"Unsubscribed from pattern '{pattern}'"
            })
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
    Merge by priority and detect changes.
    """
    start_time = time.time()
    state.total_reloads += 1
    
    try:
        source_configs = []
        sources_failed = 0
        errors: List[str] = []
        
        for source in state.sources:
            try:
                config = await source.load()
                if config:
                    source_configs.append((source.priority, source.name, config))
            except Exception as e:
                sources_failed += 1
                error_msg = f"Failed to load from source {source.name}: {e}"
                errors.append(error_msg)
                await process.send(LOGGER, ("log", "ERROR", f"[CONFIG] {error_msg}", {}))
        
        source_configs.sort(key=lambda x: x[0])
        merged_config: Dict[str, Any] = {}
        for _, _, config in source_configs:
            _deep_merge_config(merged_config, config)
        
        if not merged_config:
            merged_config = {path_from_atom(k): v for k, v in state.config.items()}
        
        old_atom_config = state.config.copy()
        new_atom_config: Dict[Any, Any] = {}
        _flatten_config_to_atoms(merged_config, new_atom_config)
        state.config = new_atom_config
        
        old_effective = old_atom_config.copy()
        old_effective.update(state.runtime_config)
        new_effective = new_atom_config.copy()
        new_effective.update(state.runtime_config)
        
        config_changes = _count_config_differences(old_effective, new_effective)
        state.last_reload = time.time()
        state.last_reload_duration = state.last_reload - start_time
        
        state.last_error = None if sources_failed == 0 else (errors[-1] if errors else None)
        
        result = ReloadResult(
            success=True,
            sources_loaded=len(source_configs),
            sources_failed=sources_failed,
            config_changes=config_changes,
            duration_seconds=state.last_reload_duration,
            errors=errors
        )
        return Ok(result)
    except Exception as e:
        state.failed_reloads += 1
        state.last_error = str(e)
        state.last_reload_duration = time.time() - start_time
        result = ReloadResult(
            success=False,
            sources_loaded=0,
            sources_failed=len(state.sources),
            config_changes=0,
            duration_seconds=state.last_reload_duration,
            errors=[str(e)]
        )
        return Err(f"Configuration reconciliation failed: {str(e)}")


async def get_manager_status(state: ConfigManagerState) -> Result[Dict[str, Any], str]:
    """Get current manager status and statistics."""
    try:
        return Ok({
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
        })
    except Exception as e:
        return Err(f"Failed to get status: {str(e)}")


def get_config_differences(old_config: Dict, new_config: Dict) -> List[Dict[str, Any]]:
    """Return list of differences between old and new config dicts."""
    changes: List[Dict[str, Any]] = []
    for path_atom in set(old_config) | set(new_config):
        old_value = old_config.get(path_atom)
        new_value = new_config.get(path_atom)
        if old_value != new_value:
            changes.append({
                "path": path_from_atom(path_atom),
                "old_value": old_value,
                "new_value": new_value
            })
    return changes


def get_matching_subscribers(path: str, state: ConfigManagerState) -> List[tuple]:
    """Get all subscribers matching a config path."""
    matches: List[tuple] = []
    for pattern_atom, subs in state.subscribers.items():
        if _path_matches_pattern(path, path_from_atom(pattern_atom)):
            matches.extend(subs)
    return matches


# =============================================================================
# Internal Helpers
# =============================================================================

def _deep_merge_config(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Deep merge dicts (source into target)."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_merge_config(target[key], value)
        else:
            target[key] = value


def _flatten_config_to_atoms(config: Dict[str, Any], atom_config: Dict[Any, Any], prefix: str = "") -> None:
    """Flatten nested dicts into atom-keyed flat dict."""
    for key, value in config.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten_config_to_atoms(value, atom_config, path)
        else:
            atom_config[config_path_atom(path)] = value


def _count_config_differences(old_config: Dict, new_config: Dict) -> int:
    """Count the number of differing keys."""
    count = 0
    for key in set(old_config) | set(new_config):
        if old_config.get(key) != new_config.get(key):
            count += 1
    return count


def _path_matches_pattern(path: str, pattern: str) -> bool:
    """Check if config path matches a pattern (wildcards supported)."""
    return fnmatch.fnmatch(path, pattern)