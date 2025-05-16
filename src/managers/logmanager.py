import asyncio
import json
import logging
import logging.config
import queue
import sys
import traceback
from functools import partial
from pathlib import Path

from src.avails import const
from src.core.app import AppType

log_queue = queue.SimpleQueue()


def _loader(file_path):
    with open(file_path) as fp:
        log_config = json.load(fp)
    return log_config


def _log_exit(queue_handlers):
    logging.getLogger().info("closing logging")
    for queue_handler in queue_handlers:
        q_listener = getattr(queue_handler, 'listener')
        q_listener.stop()
        for hand in q_listener.handlers:
            hand.close()


async def _py312_initiate(app: AppType):
    try:
        log_config = await asyncio.to_thread(_loader, const.PATH_LOG_CONFIG)
    except (ValueError, OSError):
        traceback.print_exc()
        print("LOGGING CONFIG ERROR, using basic configuration", file=sys.stderr)
        logging.basicConfig(
            format="%(asctime)s - %(levelname)-8s %(name)-30s %(funcName)-25s - %(message)s",
            level=logging.DEBUG,
        )

        return

    for handler in log_config["handlers"]:
        if "filename" in log_config["handlers"][handler]:
            log_config["handlers"][handler]["filename"] = str(
                Path(const.PATH_LOG, log_config["handlers"][handler]["filename"]))

    logging.config.dictConfig(log_config)

    queue_handlers = []

    for q_handler in log_config["queue_handlers"]:
        queue_handlers.append(logging.getHandlerByName(q_handler))

    if logging.getLogger().getEffectiveLevel() != logging.DEBUG:
        const.debug = False

    if not any(queue_handlers):
        return

    for q_handler in queue_handlers:
        queue_listener = getattr(q_handler, 'listener')
        queue_listener.start()

    app.exit_stack.callback(partial(_log_exit, queue_handlers))


async def _py311_initiate(_: AppType):
    log_file_311 = const.PATH_LOG_CONFIG.with_stem(const.PATH_LOG_CONFIG.stem + "311")

    try:
        log_config = await asyncio.to_thread(_loader, log_file_311)
    except (ValueError, OSError):
        traceback.print_exc()
        print("LOGGING CONFIG ERROR, using basic configuration", file=sys.stderr)
        logging.basicConfig(
            format="%(asctime)s - %(levelname)-8s %(name)-30s %(funcName)-25s - %(message)s",
            level=logging.DEBUG,
        )
        return

    logging.config.dictConfig(log_config)

    if logging.getLogger().getEffectiveLevel() != logging.DEBUG:
        const.debug = False


if sys.version_info >= (3, 12):
    initiate = _py312_initiate
else:
    initiate = _py311_initiate
