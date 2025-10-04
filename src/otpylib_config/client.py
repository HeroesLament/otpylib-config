#!/usr/bin/env python3
"""
Configuration Manager GenServer

The core GenServer that manages configuration state, sources, and subscriptions.
Uses atom-based message dispatch for high performance.
"""

from typing import Any
from otpylib import atom, gen_server, process
from otpylib.gen_server import CallbackNS

from result import Result

from otpylib_config.atoms import (
    GET_CONFIG, PUT_CONFIG, SUBSCRIBE, UNSUBSCRIBE, RELOAD,
    PING, STOP, STATUS, RELOAD_TICK,
    time_atom_comparison,
)
from otpylib_config.data import ConfigManagerState, CONFIG_MANAGER, ConfigSpec
from otpylib_config import core


OK = atom.ensure("ok")
STOP = atom.ensure("stop")


# =============================================================================
# GenServer Callbacks
# =============================================================================

callbacks = CallbackNS("ConfigManager")


async def init(config_spec: ConfigSpec):
    """Initialize configuration manager with sources."""
    print("[TRACE:config_mgr.init] ENTER")

    state = ConfigManagerState(
        sources=config_spec.sources if hasattr(config_spec, "sources") else [],
        reload_interval=getattr(config_spec, "reload_interval", 30.0),
    )

    # Load initial configuration from all sources
    result: Result = await core.reconcile_configuration(state)
    if result.is_err():
        err = result.unwrap_err()
        print(f"[TRACE:config_mgr.init] reconcile_configuration failed: {err}")
        raise Exception(err)  # let supervisor treat this as init crash
    else:
        print("[TRACE:config_mgr.init] reconcile_configuration succeeded")
        return state


async def handle_call(message, from_, state: ConfigManagerState):
    """Handle synchronous configuration requests using atom dispatch."""
    match message:
        case msg_type, path_str, default if time_atom_comparison(msg_type, GET_CONFIG):
            result = await core.get_config_value(path_str, default, state)
            if result.is_ok():
                return (gen_server.Reply(payload=result.unwrap()), state)
            else:
                return (gen_server.Reply(payload=Exception(result.unwrap_err())), state)

        case msg_type, path_str, value if time_atom_comparison(msg_type, PUT_CONFIG):
            result = await core.ensure_config_value(path_str, value, state)
            if result.is_ok():
                change_info = result.unwrap()
                if change_info["changed"]:
                    await _notify_subscribers(
                        state,
                        change_info["path"],
                        change_info["old_value"],
                        change_info["new_value"],
                    )
                return (gen_server.Reply(payload=True), state)
            else:
                return (gen_server.Reply(payload=Exception(result.unwrap_err())), state)

        case msg_type, pattern_str, callback, subscriber_pid if time_atom_comparison(msg_type, SUBSCRIBE):
            result = await core.ensure_subscription(pattern_str, callback, subscriber_pid, state)
            return (
                gen_server.Reply(payload=True if result.is_ok() else Exception(result.unwrap_err())),
                state,
            )

        case msg_type, pattern_str, callback, subscriber_pid if time_atom_comparison(msg_type, UNSUBSCRIBE):
            result = await core.ensure_subscription_absent(pattern_str, callback, subscriber_pid, state)
            return (
                gen_server.Reply(payload=True if result.is_ok() else Exception(result.unwrap_err())),
                state,
            )

        case msg_type if time_atom_comparison(msg_type, PING):
            return (gen_server.Reply(payload="pong"), state)

        case msg_type if time_atom_comparison(msg_type, STATUS):
            result = await core.get_manager_status(state)
            return (
                gen_server.Reply(payload=result.unwrap() if result.is_ok() else Exception(result.unwrap_err())),
                state,
            )

        case _:
            return (gen_server.Reply(payload=NotImplementedError(f"Unknown call: {message}")), state)


async def handle_cast(message, state: ConfigManagerState):
    """Handle asynchronous configuration updates."""
    match message:
        case msg_type if time_atom_comparison(msg_type, RELOAD):
            result = await core.reconcile_configuration(state)
            if result.is_ok():
                await _notify_reload_changes(state, result)
            return (gen_server.NoReply(), state)

        case msg_type if time_atom_comparison(msg_type, STOP):
            return (gen_server.Stop(reason=None), state)

        case ("source_update", source_name, new_config):
            result = await core.reconcile_configuration(state)
            if result.is_ok():
                await _notify_reload_changes(state, result)
            return (gen_server.NoReply(), state)

        case _:
            return (gen_server.NoReply(), state)


async def handle_info(message, state: ConfigManagerState):
    """Handle info messages (direct mailbox sends)."""
    match message:
        case msg_type if time_atom_comparison(msg_type, RELOAD_TICK):
            old_config = state.config.copy()
            result = await core.reconcile_configuration(state)
            if result.is_ok():
                reload_result = result.unwrap()
                if reload_result.config_changes > 0:
                    await _notify_config_changes(state, old_config, state.config)
            return (gen_server.NoReply(), state)

        case _:
            return (gen_server.NoReply(), state)


async def terminate(reason, state: ConfigManagerState):
    """Cleanup on termination."""
    pass


# Wire up callbacks
callbacks.init = init
callbacks.handle_call = handle_call
callbacks.handle_cast = handle_cast
callbacks.handle_info = handle_info
callbacks.terminate = terminate


# =============================================================================
# Internal Helper Functions
# =============================================================================

async def _notify_subscribers(state, path: str, old_value: Any, new_value: Any):
    """Notify pattern-matched subscribers of a configuration change."""
    matching_subscriptions = core.get_matching_subscribers(path, state)

    for subscriber_pid, callback in matching_subscriptions:
        try:
            await callback(subscriber_pid, path, old_value, new_value)
        except Exception:
            pass


async def _notify_reload_changes(state, reload_result):
    """Notify subscribers of configuration changes detected during reload."""
    pass


async def _notify_config_changes(state, old_config: dict, new_config: dict):
    """Notify subscribers of specific configuration changes."""
    changes = core.get_config_differences(old_config, new_config)

    for change in changes:
        await _notify_subscribers(
            state, change["path"], change["old_value"], change["new_value"]
        )
