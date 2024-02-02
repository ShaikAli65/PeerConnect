import logging
import os
from avails import constants

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
"""
    status : 1 for DEBUG
    status : 2 for INFO
    status : 3 for WARNING
    status : 4 for ERROR
    status : 5 for CRITICAL
"""


def server_log(status_string: str, status: int):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'server.logs')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger('')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)

    if status == 1:
        logging.debug(status_string)
    elif status == 2:
        logging.info(status_string)
    elif status == 3:
        logging.warning(status_string)
    elif status == 4:
        logging.error(status_string)
    elif status == 5:
        logging.critical(status_string)


def activity_log(status_string: str):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'activity.logs')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger('')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    logging.info(status_string)
    pass


def error_log(status_string: str):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'error.logs')
    # with open(file_path, 'w') as f:
    #     f.write('')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger('')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    logging.info(status_string)
    pass
