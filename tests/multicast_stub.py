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
        print('new multicast arrived', addr)
        strings = ["forwarding to"]
        for peer in (self.all_peers - {addr}):
            strings.append(f"{peer} ")
            self.transport.sendto(data, peer)

        strings.append('\n')
        print("".join(strings))

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
