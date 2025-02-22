import asyncio

from _socket import gethostbyname, gethostname


class Multicast(asyncio.DatagramProtocol):
    def __init__(self):
        self.all_peers = set()
        self.transport = None

    def connection_made(self, transport):
        print("multicast up and running", transport.get_extra_info('socket'))
        self.transport = transport

    def datagram_received(self, data, addr):
        print('new message arrived', addr)
        print("forwarding to", end=' ')
        for peer in (self.all_peers - {addr}):
            print(peer, end=' ')
            self.transport.sendto(data, peer)
        print('')
        self.all_peers.add(addr)


async def main(config):
    if config.test_mode == "host":
        multicast_ip = '127.0.0.1'
    else:
        multicast_ip = gethostbyname(gethostname())

    multicast_port = 4000

    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        Multicast,
        local_addr=(multicast_ip, multicast_port)
    )
    await asyncio.Event().wait()
