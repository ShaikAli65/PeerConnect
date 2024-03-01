from collections import deque
import threading
import socket


class RecentsCacheQueue(deque):
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.max_cache_size = 5

    def append(self, x):
        with self._lock:
            if len(self) >= self.max_cache_size:
                xt = self.popleft()
                if isinstance(xt, socket.socket):
                    self.remove_socket(xt)
            super().append(x)
        return

    def remove_socket(self, x):
        with self._lock:
            try:
                x.close()
                self.remove(x)
            except socket.error as e:
                print(f"::Error while closing socket : {e}")
        return

    def pop(self):
        with self._lock:
            return super().pop()

    def __repr__(self):
        return f"RecentsQueue({list(self)})"

    def __len__(self):
        return len(self)

    def __getitem__(self, item):
        with self._lock:
            return super().__getitem__(item)

    def __contains__(self, item):
        with self._lock:
            return super().__contains__(item)