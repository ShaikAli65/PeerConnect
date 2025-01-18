import json
import logging.config
import queue
from contextlib import contextmanager
from pathlib import Path

from src.avails import const

log_queue = queue.SimpleQueue()


@contextmanager
def initiate():
    with open(const.PATH_LOG_CONFIG) as fp:
        log_config = json.load(fp)
    log_file_name = log_config["log_file_name"]
    log_file_path = Path(const.PATH_LOG, log_file_name)
    log_config["handlers"]["rfile_handler"]["filename"] = log_file_path

    log_config["handlers"]["file"]["filename"] = log_file_path

    logging.config.dictConfig(log_config)
    q_handler = logging.getHandlerByName("queue_handler")

    if q_handler is None:
        yield
        return

    queue_listener = getattr(q_handler, 'listener')
    queue_listener.start()
    yield
    queue_listener.stop()
    for handler in queue_listener.handlers:
        handler.close()
    print("closing logging")
