import logging
import os
import constants

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

"""
    status : 1 for DEBUG
    status : 2 for INFO
    status : 3 for WARNING
    status : 4 for ERROR
    status : 5 for CRITICAL
"""


def serverlog(statustring: str, status: int):
    os.makedirs(constants.LOGDIR, exist_ok=True)
    file_path = os.path.join(constants.LOGDIR, 'serverlogs.txt')
    file_handler = logging.FileHandler(file_path)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logging.getLogger('').addHandler(file_handler)
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
    return


def activitylog(statustring: str, status: int):
    pass


def errorlog(statustring: str):
    pass
