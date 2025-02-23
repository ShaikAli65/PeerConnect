import asyncio
import json
import logging
import logging.config
import queue
from pathlib import Path

from src.avails import const
from src.core.public import Dock

log_queue = queue.SimpleQueue()


async def initiate():
    log_config = {}

    def _loader():
        nonlocal log_config
        with open(const.PATH_LOG_CONFIG) as fp:
            log_config = json.load(fp)

    def _log_exit():
        logging.getLogger().info("closing logging")
        for queue_handler in queue_handlers:
            q_listener = getattr(queue_handler, 'listener')
            q_listener.stop()
            for hand in q_listener.handlers:
                hand.close()

    await asyncio.to_thread(_loader)

    for handler in log_config["handlers"]:
        if "filename" in log_config["handlers"][handler]:
            log_config["handlers"][handler]["filename"] = str(
                Path(const.PATH_LOG, log_config["handlers"][handler]["filename"]))

    logging.config.dictConfig(log_config)

    queue_handlers = []

    for q_handler in log_config["queue_handlers"]:
        queue_handlers.append(logging.getHandlerByName(q_handler))

    if not any(queue_handlers):
        return

    for q_handler in queue_handlers:
        queue_listener = getattr(q_handler, 'listener')
        queue_listener.start()

    Dock.exit_stack.callback(_log_exit)
