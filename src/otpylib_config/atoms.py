#!/usr/bin/env python3
"""
Configuration Management Atoms

Pre-defined atoms for high-performance configuration operations.
These atoms are created once at module import time for optimal performance.
"""

import time
from otpylib import atom

# =============================================================================
# Core Configuration Operation Atoms
# =============================================================================

# Primary operations
GET_CONFIG = atom.ensure("get_config")
PUT_CONFIG = atom.ensure("put_config")
SUBSCRIBE = atom.ensure("subscribe")
UNSUBSCRIBE = atom.ensure("unsubscribe")
RELOAD = atom.ensure("reload")
CONFIG_CHANGED = atom.ensure("config_changed")

# Source operations
SOURCE_UPDATE = atom.ensure("source_update")
SOURCE_ERROR = atom.ensure("source_error")
SOURCE_RELOAD = atom.ensure("source_reload")

# Internal management
HEALTH_CHECK = atom.ensure("health_check")
PING = atom.ensure("ping")
STOP = atom.ensure("stop")
STATUS = atom.ensure("status")

# Self-messaging ticker
RELOAD_TICK = atom.ensure("reload_tick")

# =============================================================================
# Performance Tracking
# =============================================================================

# Performance measurement collections
lookup_times = []
comparison_times = []

def time_atom_comparison(atom1, atom2):
    """Time atom comparison for performance tracking."""
    start = time.monotonic_ns()
    result = atom1 == atom2
    end = time.monotonic_ns()
    comparison_times.append(end - start)
    return result

def time_atom_lookup(name: str):
    """Time atom lookup via ensure (cached lookup)."""
    start = time.monotonic_ns()
    atom_obj = atom.ensure(name)
    end = time.monotonic_ns()
    lookup_times.append(end - start)
    return atom_obj

# =============================================================================
# Configuration Path Atoms
# =============================================================================

_path_atom_cache = {}

def config_path_atom(path: str):
    """
    Convert a config path string to an atom for fast lookup.
    Uses caching to avoid repeated atom creation for the same paths.
    
    Examples:
        config_path_atom("database.url") -> Atom("config.database.url")
        config_path_atom("app.debug") -> Atom("config.app.debug")
    """
    if path not in _path_atom_cache:
        _path_atom_cache[path] = atom.ensure(f"config.{path}")
    return _path_atom_cache[path]

def path_from_atom(atom_obj):
    """
    Extract config path from atom.
    
    Examples:
        path_from_atom(Atom("config.database.url")) -> "database.url"
        path_from_atom(Atom("config.app.debug")) -> "app.debug"
    """
    name = atom_obj.name
    if name.startswith("config."):
        return name[7:]  # Remove "config." prefix
    return name

def clear_path_cache():
    """Clear the path atom cache (useful for testing)."""
    global _path_atom_cache
    _path_atom_cache.clear()

# =============================================================================
# Performance Statistics
# =============================================================================

def get_performance_stats():
    """Get current atom performance statistics."""
    from statistics import mean, median
    
    stats = {
        "total_lookups": len(lookup_times),
        "total_comparisons": len(comparison_times),
        "cached_paths": len(_path_atom_cache),
        "total_atoms": atom.atom_count()
    }
    
    if lookup_times:
        stats.update({
            "lookup_mean_ns": mean(lookup_times),
            "lookup_median_ns": median(lookup_times),
            "lookup_min_ns": min(lookup_times),
            "lookup_max_ns": max(lookup_times)
        })
    
    if comparison_times:
        stats.update({
            "comparison_mean_ns": mean(comparison_times),
            "comparison_median_ns": median(comparison_times),
            "comparison_min_ns": min(comparison_times),
            "comparison_max_ns": max(comparison_times)
        })
    
    return stats

def reset_performance_stats():
    """Reset performance tracking collections."""
    global lookup_times, comparison_times
    lookup_times.clear()
    comparison_times.clear()
