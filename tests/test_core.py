#!/usr/bin/env python3
"""
Test core business logic functions.
"""

import pytest
from result import Ok, Err

from otpylib_config import core
from otpylib_config.atoms import config_path_atom

# Apply anyio plugin across this module
pytestmark = pytest.mark.anyio


class TestConfigValueOperations:
    """Test getting and setting configuration values."""
    
    async def test_get_config_value_with_default(self, config_state):
        """Test getting config value returns default when not set."""
        result = await core.get_config_value("app.name", "DefaultApp", config_state)
        
        assert result.is_ok()
        assert result.unwrap() == "DefaultApp"
    
    async def test_ensure_config_value_creates_new(self, config_state):
        """Test setting new config value."""
        result = await core.ensure_config_value("app.name", "MyApp", config_state)
        
        assert result.is_ok()
        change_info = result.unwrap()
        assert change_info["changed"] is True
        assert change_info["old_value"] is None
        assert change_info["new_value"] == "MyApp"
        assert "created" in change_info["message"]
    
    async def test_ensure_config_value_updates_existing(self, config_state):
        """Test updating existing config value."""
        # Set initial value
        await core.ensure_config_value("app.name", "OldApp", config_state)
        
        # Update value
        result = await core.ensure_config_value("app.name", "NewApp", config_state)
        
        assert result.is_ok()
        change_info = result.unwrap()
        assert change_info["changed"] is True
        assert change_info["old_value"] == "OldApp"
        assert change_info["new_value"] == "NewApp"
        assert "updated" in change_info["message"]
    
    async def test_ensure_config_value_idempotent(self, config_state):
        """Test setting same value twice is idempotent."""
        # Set initial value
        await core.ensure_config_value("app.name", "MyApp", config_state)
        
        # Set same value again
        result = await core.ensure_config_value("app.name", "MyApp", config_state)
        
        assert result.is_ok()
        change_info = result.unwrap()
        assert change_info["changed"] is False
        assert change_info["old_value"] == "MyApp"
        assert change_info["new_value"] == "MyApp"
        assert "already set correctly" in change_info["message"]
    
    async def test_runtime_config_overrides_source_config(self, config_state):
        """Test that runtime config takes priority over source config."""
        # Simulate source config
        path_atom = config_path_atom("app.name")
        config_state.config[path_atom] = "SourceApp"
        
        # Set runtime override
        await core.ensure_config_value("app.name", "RuntimeApp", config_state)
        
        # Get should return runtime value
        result = await core.get_config_value("app.name", "Default", config_state)
        assert result.is_ok()
        assert result.unwrap() == "RuntimeApp"
    
    async def test_get_falls_back_to_source_config(self, config_state):
        """Test get falls back to source config when no runtime override."""
        # Set only source config
        path_atom = config_path_atom("app.name")
        config_state.config[path_atom] = "SourceApp"
        
        # Get should return source value
        result = await core.get_config_value("app.name", "Default", config_state)
        assert result.is_ok()
        assert result.unwrap() == "SourceApp"


class TestSubscriptionManagement:
    """Test configuration change subscription functionality."""
    
    async def test_ensure_subscription_creates_new(self, config_state):
        """Test creating new subscription."""
        async def callback(path, old, new):
            pass
        
        result = await core.ensure_subscription("app.*", callback, config_state)
        
        assert result.is_ok()
        sub_info = result.unwrap()
        assert sub_info["new_subscription"] is True
        assert "Subscribed" in sub_info["message"]
    
    async def test_ensure_subscription_idempotent(self, config_state):
        """Test subscribing same callback twice is idempotent."""
        async def callback(path, old, new):
            pass
        
        # Subscribe first time
        await core.ensure_subscription("app.*", callback, config_state)
        
        # Subscribe same callback again
        result = await core.ensure_subscription("app.*", callback, config_state)
        
        assert result.is_ok()
        sub_info = result.unwrap()
        assert sub_info["new_subscription"] is False
        assert "Already subscribed" in sub_info["message"]
    
    async def test_ensure_subscription_absent(self, config_state):
        """Test removing subscription."""
        async def callback(path, old, new):
            pass
        
        # Subscribe first
        await core.ensure_subscription("app.*", callback, config_state)
        
        # Then unsubscribe
        result = await core.ensure_subscription_absent("app.*", callback, config_state)
        
        assert result.is_ok()
        unsub_info = result.unwrap()
        assert unsub_info["was_subscribed"] is True
        assert "Unsubscribed" in unsub_info["message"]
    
    async def test_ensure_subscription_absent_idempotent(self, config_state):
        """Test removing non-existent subscription is idempotent."""
        async def callback(path, old, new):
            pass
        
        result = await core.ensure_subscription_absent("app.*", callback, config_state)
        
        assert result.is_ok()
        unsub_info = result.unwrap()
        assert unsub_info["was_subscribed"] is False
        assert "Was not subscribed" in unsub_info["message"]
    
    async def test_get_matching_subscribers(self, config_state):
        """Test finding subscribers that match a config path."""
        # Create callbacks
        app_callback_called = []
        db_callback_called = []
        
        async def app_callback(path, old, new):
            app_callback_called.append((path, old, new))
        
        async def db_callback(path, old, new):
            db_callback_called.append((path, old, new))
        
        # Subscribe to different patterns
        await core.ensure_subscription("app.*", app_callback, config_state)
        await core.ensure_subscription("database.*", db_callback, config_state)
        
        # Test matching
        app_matches = core.get_matching_subscribers("app.name", config_state)
        assert len(app_matches) == 1
        assert app_callback in app_matches
        
        db_matches = core.get_matching_subscribers("database.url", config_state)
        assert len(db_matches) == 1
        assert db_callback in db_matches
        
        no_matches = core.get_matching_subscribers("logging.level", config_state)
        assert len(no_matches) == 0


class TestConfigurationReconciliation:
    """Test configuration reconciliation from sources."""
    
    async def test_reconcile_configuration_with_no_sources(self, config_state):
        """Test reconciliation with empty sources list."""
        result = await core.reconcile_configuration(config_state)
        
        assert result.is_ok()
        reload_result = result.unwrap()
        assert reload_result.success is True
        assert reload_result.sources_loaded == 0
        assert reload_result.sources_failed == 0
        assert reload_result.config_changes == 0
    
    async def test_reconcile_preserves_runtime_config(self, config_state, file_source):
        """Test that reconciliation preserves runtime configuration."""
        # Set up state with source
        config_state.sources = [file_source]
        
        # Set runtime config
        await core.ensure_config_value("app.runtime_setting", "RuntimeValue", config_state)
        
        # Reconcile configuration (loads from file)
        result = await core.reconcile_configuration(config_state)
        assert result.is_ok()
        
        # Runtime config should still be accessible
        runtime_result = await core.get_config_value("app.runtime_setting", None, config_state)
        assert runtime_result.is_ok()
        assert runtime_result.unwrap() == "RuntimeValue"
        
        # File config should also be accessible
        file_result = await core.get_config_value("app.name", None, config_state)
        assert file_result.is_ok()
        assert file_result.unwrap() == "TestApp"  # From temp config file


class TestStatusAndMetrics:
    """Test status and metrics functionality."""
    
    async def test_get_manager_status(self, config_state):
        """Test getting manager status returns expected fields."""
        result = await core.get_manager_status(config_state)
        
        assert result.is_ok()
        status = result.unwrap()
        
        # Check expected fields exist
        assert "config_keys" in status
        assert "subscribers" in status
        assert "sources" in status
        assert "total_reloads" in status
        assert "failed_reloads" in status
        assert "started_at" in status
        
        # Check initial values
        assert status["config_keys"] == 0
        assert status["subscribers"] == 0
        assert status["total_reloads"] == 0
        assert status["failed_reloads"] == 0
