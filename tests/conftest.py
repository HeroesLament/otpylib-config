#!/usr/bin/env python3
"""
Test fixtures for otpylib-config tests.
"""

import pytest
import tempfile
import os
from pathlib import Path

from otpylib_config.data import ConfigManagerState, ConfigSpec
from otpylib_config.sources import FileSource, EnvironmentSource


@pytest.fixture
def anyio_backend():
    """Force anyio to only use asyncio backend, not trio."""
    return 'asyncio'


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write("""
[app]
name = "TestApp"
debug = true
workers = 2

[database]
url = "sqlite:///test.db"
pool_size = 5

[logging]
level = "INFO"
""")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def temp_json_config():
    """Create a temporary JSON config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("""{
    "api": {
        "host": "localhost",
        "port": 8080
    },
    "features": {
        "new_ui": false,
        "metrics": true
    }
}""")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def config_state():
    """Create a fresh ConfigManagerState for testing."""
    return ConfigManagerState()


@pytest.fixture
def file_source(temp_config_file):
    """Create a FileSource pointing to temp config."""
    return FileSource(temp_config_file, format="toml")


@pytest.fixture
def env_source():
    """Create an EnvironmentSource for testing."""
    return EnvironmentSource(prefix="TEST_")


@pytest.fixture
def config_spec(file_source, env_source):
    """Create a basic ConfigSpec for testing."""
    return ConfigSpec(
        id="test_config",
        sources=[file_source, env_source],
        reload_interval=1.0
    )


@pytest.fixture
def clean_env():
    """Clean up TEST_ environment variables before and after test."""
    # Store original env
    original_env = {}
    for key in list(os.environ.keys()):
        if key.startswith("TEST_"):
            original_env[key] = os.environ[key]
            del os.environ[key]
    
    yield
    
    # Restore original env
    for key in list(os.environ.keys()):
        if key.startswith("TEST_"):
            del os.environ[key]
    
    for key, value in original_env.items():
        os.environ[key] = value


@pytest.fixture
def sample_env_vars(clean_env):
    """Set up sample environment variables for testing."""
    os.environ["TEST_APP_NAME"] = "EnvApp"
    os.environ["TEST_APP_DEBUG"] = "false"
    os.environ["TEST_DATABASE_MAX_CONNECTIONS"] = "20"
    os.environ["TEST_FEATURE_FLAGS"] = '{"experimental": true}'
    
    yield
    
    # Cleanup happens in clean_env fixture
