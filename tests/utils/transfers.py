class AsyncByteStream:
    def __init__(self, data=b''):
        self.data = bytearray(data)
        self.sent = []

    async def send(self, data):
        self.data.extend(bytes(data))
        self.sent.append(bytes(data))
        return len(data)

    async def recv(self, size):
        chunk = bytes(self.data[:size])
        del self.data[:size]
        return chunk


class DummyStatus:
    def __init__(self):
        self.setups = []
        self.updates = []
        self.closed = 0

    def status_setup(self, *args, **kwargs):
        self.setups.append((args, kwargs))

    async def update_status(self, status):
        self.updates.append(status)

    async def write_update(self, update):
        self.updates.append(update)

    async def close(self):
        self.closed += 1

