from src.avails import const


def mock_multicast_addr(config):
    if config.test_mode == 'host':
        if const.USING_IP_V4:
            const.MULTICAST_IP_v4 = '127.0.0.1'
            const.PORT_NETWORK = 4000
