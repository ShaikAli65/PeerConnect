import logging.config
import json
from pathlib import Path

from src.avails import const


def initiate():
    with open(const.PATH_LOG_CONFIG) as fp:
        log_config = json.load(fp)

    log_config["handlers"]["file"]["filename"] = Path(const.PATH_LOG, 'new.log')

    logging.config.dictConfig(log_config)
