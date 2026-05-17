from src.net.connection_pool import ConnectionPool


class BandwidthWatcher:
    def __init__(
          self,
          connection_pool: ConnectionPool,
          max_combined_mbps=None,
    ):
        self.connection_pool = connection_pool
        self.max_combined_mbps = max_combined_mbps
