import asyncio


class Multicast(asyncio.DatagramProtocol):
    def __init__(self):
        self.all_peers = set()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.all_peers.add(addr)
        for peer in self.all_peers:
            self.transport.sendto(data, peer)


async def main():
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        Multicast,
    )


if __name__ == "__main__":
    asyncio.run(main=main())
