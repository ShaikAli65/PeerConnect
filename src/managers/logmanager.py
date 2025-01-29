import json
import logging.config
import queue
import traceback
from contextlib import contextmanager
from pathlib import Path

from src.avails import const

log_queue = queue.SimpleQueue()


@contextmanager
def initiate():
    with open(const.PATH_LOG_CONFIG) as fp:
        log_config = json.load(fp)

    for handler in log_config["handlers"]:
        if "filename" in log_config["handlers"][handler]:
            log_config["handlers"][handler]["filename"] = str(
                Path(const.PATH_LOG, log_config["handlers"][handler]["filename"]))
    #
    # log_config["handlers"]["rfile_handler"]["filename"] = log_file_path
    # log_config["handlers"]["file"]["filename"] = log_file_path

    logging.config.dictConfig(log_config)

    queue_handlers = []

    for q_handler in log_config["queue_handlers"]:
        queue_handlers.append(logging.getHandlerByName(q_handler))

    if not any(queue_handlers):
        yield
        return

    for q_handler in queue_handlers:
        queue_listener = getattr(q_handler, 'listener')
        queue_listener.start()
    try:
        yield
    finally:
        print("*"*80)
        try:
            for q_handler in queue_handlers:
                queue_listener = getattr(q_handler, 'listener')
                queue_listener.stop()
                for handler in queue_listener.handlers:
                    handler.close()
        except Exception:
            print("*"*80)
            traceback.print_exc()
        print("closing logging")
