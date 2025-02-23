from src.avails import const


def mock_timeouts():
    const.DISCOVER_TIMEOUT = 1  # quick and reponsive in testing
    const.PING_TIME_CHECK_WINDOW = 1

    const.TIMEOUT_TO_WAIT_FOR_MSG_PROCESSING_TASK = 100
    const.PING_TIMEOUT = 100
    const.DEFAULT_TRANSFER_TIMEOUT = 100
