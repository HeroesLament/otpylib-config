import asyncio

from otpylib import atom, supervisor, process
from otpylib.runtime import set_runtime
from otpylib.runtime.backends.asyncio_backend.backend import AsyncIOBackend
from otpylib.supervisor import PERMANENT, ONE_FOR_ONE

import otpylib_config
import otpylib_logger as logger
from otpylib_config import CONFIG_MANAGER
from otpylib_config.sources import ConfigSource
from otpylib_logger import LOGGER_SUP
from otpylib_logger.data import LoggerSpec, HandlerSpec, LogLevel


DEMO_WORKER = atom.ensure("demo_worker")
ROOT_SUPERVISOR = atom.ensure("root_supervisor")


# =============================================================================
# Config Change Handler (Module-level)
# =============================================================================

async def config_change_handler(subscriber_pid, path: str, old_value, new_value):
    """Handle configuration changes - gets called when config updates."""
    await logger.info(
        f"Config changed: {path}",
        {"old_value": old_value, "new_value": new_value, "subscriber": subscriber_pid}
    )


# =============================================================================
# Demo Worker
# =============================================================================

async def worker_main():
    """Demo worker that uses configuration and demonstrates dynamic updates."""
    await logger.info("Demo worker started")
    
    # Give the GenServer time to fully initialize
    await asyncio.sleep(0.5)
    
    # Query this process's PID
    my_pid = process.self()
    
    # Subscribe to configuration changes
    await otpylib_config.Config.subscribe("app.*", config_change_handler, my_pid)
    await otpylib_config.Config.subscribe("database.*", config_change_handler, my_pid)
    
    await logger.info("Subscriptions complete, entering main loop")
    
    counter = 0
    while True:
        await asyncio.sleep(1.0)
        counter += 1
        
        # Read configuration values
        app_name = await otpylib_config.Config.get("app.name", "DefaultApp")
        log_level = await otpylib_config.Config.get("app.log_level", "INFO")
        db_url = await otpylib_config.Config.get("database.url", "sqlite:///app.db")
        worker_count = await otpylib_config.Config.get("app.workers", 2)
        
        await logger.info(
            "Config status check",
            {
                "counter": counter,
                "app_name": app_name,
                "log_level": log_level,
                "worker_count": worker_count,
                "db_url": db_url,
            }
        )
        
        # Update configuration at different intervals to show dynamic changes
        if counter == 3:
            await logger.warn("Enabling debug mode")
            await otpylib_config.Config.put("app.log_level", "DEBUG")
            
        elif counter == 6:
            await logger.warn("Scaling up workers")
            await otpylib_config.Config.put("app.workers", 8)
            
        elif counter == 9:
            await logger.warn("Changing database")
            await otpylib_config.Config.put("database.url", "postgresql://localhost/myapp")
            
        elif counter == 12:
            await logger.warn("Optimizing for production")
            await otpylib_config.Config.put("app.log_level", "WARN")
            await otpylib_config.Config.put("app.workers", 8)
            await otpylib_config.Config.put("app.name", "ProductionApp")


async def demo_worker():
    """Factory that spawns a demo worker process."""
    return await process.spawn(worker_main, mailbox=True)


# =============================================================================
# Supervisor Setup
# =============================================================================

async def start():
    """Entrypoint into the Config+Logger Demo Root Supervisor."""
    
    # Configure logger
    logger_spec = LoggerSpec(
        level=LogLevel.DEBUG,
        handlers=[
            HandlerSpec(
                name="console",
                handler_module="otpylib_logger.handlers.console",
                config={"use_stderr": False, "colorize": True},
                level=LogLevel.DEBUG,
            ),
            HandlerSpec(
                name="file",
                handler_module="otpylib_logger.handlers.file",
                config={"path": "/tmp/otpylib_config_demo.log", "mode": "a"},
                level=LogLevel.INFO,
            ),
        ]
    )
    
    # Configure config manager
    sources: list[ConfigSource] = [
        otpylib_config.FileSource("config.json", format="json"),
        otpylib_config.EnvironmentSource(prefix="DEMO_"),
    ]
    
    config_spec = otpylib_config.ConfigSpec(
        id="demo_config",
        sources=sources,
        reload_interval=1.0
    )

    children = [
        supervisor.child_spec(
            id=LOGGER_SUP,
            func=logger.start_link,
            args=[logger_spec],
            restart=PERMANENT,
        ),
        supervisor.child_spec(
            id=CONFIG_MANAGER,
            func=otpylib_config.start,
            args=[config_spec],
            restart=PERMANENT,
        ),
        supervisor.child_spec(
            id=DEMO_WORKER,
            func=demo_worker,
            restart=PERMANENT
        )
    ]
    
    opts = supervisor.options(strategy=ONE_FOR_ONE)

    await supervisor.start(
        child_specs=children,
        opts=opts,
        name=ROOT_SUPERVISOR,
    )
    
    try:
        while True:
            await process.receive()
    except asyncio.CancelledError:
        pass


async def main():
    """Main demo application."""
    backend = AsyncIOBackend()
    await backend.initialize()
    set_runtime(backend)
    
    await process.spawn(start, mailbox=True)
    
    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await backend.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
