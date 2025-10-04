#!/usr/bin/env python3
"""
Configuration Manager Lifecycle

OTP supervision for the configuration manager with reload ticker.
"""

import asyncio
from otpylib import gen_server, supervisor, process
from otpylib.supervisor import PERMANENT, ONE_FOR_ONE

from otpylib_config.boundaries import callbacks
from otpylib_config.data import CONFIG_MANAGER, ConfigSpec
from otpylib_config.atoms import RELOAD_TICK


async def reload_ticker(config_spec: ConfigSpec):
    """Factory that spawns a reload ticker process."""
    async def ticker():
        """Send periodic reload ticks to the configuration manager."""
        while True:
            try:
                await asyncio.sleep(config_spec.reload_interval)
                await process.send(CONFIG_MANAGER, RELOAD_TICK)
            except Exception:
                break
    
    return await process.spawn(ticker, mailbox=True)


async def start(config_spec: ConfigSpec):
    """
    Factory that spawns the Configuration Manager supervisor process.
    
    Returns the PID of the spawned supervisor process that manages both
    the GenServer and reload ticker under OTP supervision.
    """
    async def config_supervisor():
        """Run the config manager supervisor."""
        genserver_spec = supervisor.child_spec(
            id=CONFIG_MANAGER,
            func=gen_server.start,
            args=[callbacks, config_spec, CONFIG_MANAGER],
            restart=PERMANENT,
            name=CONFIG_MANAGER,
        )
        
        ticker_spec = supervisor.child_spec(
            id="config_reload_ticker",
            func=reload_ticker,
            args=[config_spec],
            restart=PERMANENT,
        )
        
        children = [genserver_spec, ticker_spec]
        
        supervisor_opts = supervisor.options(
            strategy=ONE_FOR_ONE,
            max_restarts=3,
            max_seconds=60
        )
        
        await supervisor.start(
            child_specs=children,
            opts=supervisor_opts
        )

        try:
            while True:
                await process.receive()
        except asyncio.CancelledError:
            pass
    
    return await process.spawn(config_supervisor, mailbox=True)


async def stop():
    """Stop the Configuration Manager GenServer gracefully."""
    try:
        await gen_server.cast(CONFIG_MANAGER, "stop")
    except Exception:
        pass
