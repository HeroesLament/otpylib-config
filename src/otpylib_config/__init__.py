#!/usr/bin/env python3
"""
otpylib-config: Runtime Configuration Management Worker-bee

A configuration management system for otpylib applications that supports
hot reloading, change notifications, and multiple configuration sources.

This is the main entry point - import this module to use the Configuration Manager.
"""

from .lifecycle import start, stop
from .data import CONFIG_MANAGER, ConfigRPC, ConfigSpec
from .sources import FileSource, EnvironmentSource, RuntimeSource
from .client import Config

__all__ = [
    "start", 
    "stop",
    "Config",
    "ConfigSpec",
    "FileSource",
    "EnvironmentSource", 
    "RuntimeSource",
    "CONFIG_MANAGER",
    "ConfigRPC"
]
