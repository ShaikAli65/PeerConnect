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


def serverlog(statustring: str, status: int):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'serverlogs.txt')
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
        logging.debug(statustring)
    elif status == 2:
        logging.info(statustring)
    elif status == 3:
        logging.warning(statustring)
    elif status == 4:
        logging.error(statustring)
    elif status == 5:
        logging.critical(statustring)


def activitylog(statustring: str):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'activitylogs.txt')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger('')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    logging.info(statustring)
    pass


def errorlog(statustring: str):
    os.makedirs(constants.LOG_DIR, exist_ok=True)
    file_path = os.path.join(constants.LOG_DIR, 'errorlogs.txt')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger('')
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    logging.info(statustring)
    pass
