import asyncio
import struct
import sys

import pytest

from src.avails import WireData
from src.avails.exceptions import FailedToSend, InvalidPacket
from src.core.requests import RequestsService
from src.net.connect import IPAddress
from src.net.requests import RequestsEndPoint
from src.net.transports import REQUESTS_FLAG, RequestsTransport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class RecordingUDPTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def get_extra_info(self, key, default=None):
        return default


def make_wire_payload(wire: WireData) -> bytes:
    """Build the bytes that follow the flag byte in a requests datagram."""
    raw = bytes(wire)
    return struct.pack("!I", len(raw)) + raw


def make_packet(flag: REQUESTS_FLAG, wire: WireData) -> bytes:
    return flag.flag_to_bytes + make_wire_payload(wire)


def make_ack_packet(msg_id: bytes) -> bytes:
    return REQUESTS_FLAG.ACK.flag_to_bytes + msg_id


_INTERFACE = IPAddress(ip="127.0.0.1", scope_id=0)
_ADDR = ("127.0.0.1", 9000)


def make_endpoint(dispatcher=None):
    if dispatcher is None:
        dispatcher = lambda event: None  # noqa: E731
    finalizing = asyncio.Event()
    ep = RequestsEndPoint(dispatcher, finalizing, _INTERFACE)
    transport = RecordingUDPTransport()
    ep.connection_made(transport)
    return ep, transport


# ---------------------------------------------------------------------------
# REQUESTS_FLAG enum
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flag", [
    REQUESTS_FLAG.KADEMLIA,
    REQUESTS_FLAG.DISCOVERY,
    REQUESTS_FLAG.GOSSIP,
    REQUESTS_FLAG.REQUEST,
    REQUESTS_FLAG.ACK,
    REQUESTS_FLAG.REQUIRE_ACK,
])
def test_flag_round_trip(flag):
    assert REQUESTS_FLAG.bytes_to_flag(flag.flag_to_bytes) == flag


def test_flag_combined_round_trip():
    combined = REQUESTS_FLAG.REQUEST | REQUESTS_FLAG.REQUIRE_ACK
    assert REQUESTS_FLAG.bytes_to_flag(combined.flag_to_bytes) == combined


def test_flag_base_vs_extra_separation():
    combined = REQUESTS_FLAG.REQUEST | REQUESTS_FLAG.REQUIRE_ACK
    base = REQUESTS_FLAG(combined & (REQUESTS_FLAG.EXTRA - 1))
    extra = REQUESTS_FLAG(combined & ~(REQUESTS_FLAG.EXTRA - 1))
    assert base == REQUESTS_FLAG.REQUEST
    assert extra & REQUESTS_FLAG.REQUIRE_ACK


# ---------------------------------------------------------------------------
# RequestsTransport.sendto — byte layout
# ---------------------------------------------------------------------------

def test_requests_transport_sendto_default_format():
    udp = RecordingUDPTransport()
    rt = RequestsTransport(udp)
    payload = b"hello"

    rt.sendto(payload, _ADDR)

    assert len(udp.sent) == 1
    raw, addr = udp.sent[0]
    assert addr == _ADDR

    flag_byte = raw[0:1]
    size_bytes = raw[1:5]
    body = raw[5:]

    flag = REQUESTS_FLAG.bytes_to_flag(flag_byte)
    assert flag & REQUESTS_FLAG.REQUEST        # routing_header present
    assert flag & REQUESTS_FLAG.EXTRA          # default extra ORed in
    assert struct.unpack("!I", size_bytes)[0] == len(payload)
    assert body == payload


def test_requests_transport_sendto_custom_extra_flag():
    udp = RecordingUDPTransport()
    rt = RequestsTransport(udp)

    rt.sendto(b"data", _ADDR, extra=REQUESTS_FLAG.REQUIRE_ACK)

    flag = REQUESTS_FLAG.bytes_to_flag(udp.sent[0][0][0:1])
    assert flag & REQUESTS_FLAG.REQUIRE_ACK


# ---------------------------------------------------------------------------
# RequestsEndPoint._decode_packet
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decode_ack_resolves_waiting_future():
    ep, _ = make_endpoint()
    msg_id = b"msg-001"
    fut = asyncio.get_running_loop().create_future()
    ep._ack_futs[msg_id] = fut

    ack_packet = make_ack_packet(msg_id)
    code, data = ep._decode_packet(ack_packet, _ADDR)

    assert code is None and data is None
    assert fut.done()
    assert fut.result() is None


@pytest.mark.asyncio
async def test_decode_ack_unknown_msg_id_returns_none():
    ep, _ = make_endpoint()

    ack_packet = make_ack_packet(b"unknown-id")
    code, data = ep._decode_packet(ack_packet, _ADDR)

    assert code is None and data is None


@pytest.mark.asyncio
async def test_decode_require_ack_sends_ack_back():
    ep, udp_transport = make_endpoint()
    wire = WireData(header="ping", msg_id="req-42")
    flag = REQUESTS_FLAG.REQUEST | REQUESTS_FLAG.REQUIRE_ACK
    packet = flag.flag_to_bytes + make_wire_payload(wire)

    code, req_data = ep._decode_packet(packet, _ADDR)

    assert code == REQUESTS_FLAG.REQUEST
    assert req_data.msg_id == "req-42"
    assert len(udp_transport.sent) == 1
    sent_raw, sent_addr = udp_transport.sent[0]
    sent_flag = REQUESTS_FLAG.bytes_to_flag(sent_raw[0:1])
    assert sent_flag & REQUESTS_FLAG.ACK
    assert sent_addr == _ADDR


@pytest.mark.asyncio
async def test_decode_normal_request_packet():
    ep, udp_transport = make_endpoint()
    wire = WireData(header="greet", msg_id="msg-77")
    packet = make_packet(REQUESTS_FLAG.REQUEST, wire)

    code, req_data = ep._decode_packet(packet, _ADDR)

    assert code == REQUESTS_FLAG.REQUEST
    assert req_data.msg_id == "msg-77"
    assert len(udp_transport.sent) == 0   # no ACK sent


# ---------------------------------------------------------------------------
# RequestsEndPoint.wait_for_ack
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wait_for_ack_times_out():
    ep, _ = make_endpoint()

    with pytest.raises(asyncio.TimeoutError):
        await ep.wait_for_ack(b"no-one-acks", timeout=0.01)


@pytest.mark.asyncio
async def test_wait_for_ack_resolved_by_ack_packet():
    ep, _ = make_endpoint()
    msg_id = b"will-ack"

    async def send_ack_after_delay():
        await asyncio.sleep(0.01)
        ack_packet = make_ack_packet(msg_id)
        ep._decode_packet(ack_packet, _ADDR)

    asyncio.create_task(send_ack_after_delay())
    result = await asyncio.wait_for(ep.wait_for_ack(msg_id, timeout=1.0), timeout=1.0)
    assert result is None


# ---------------------------------------------------------------------------
# RequestsService.send_request
# ---------------------------------------------------------------------------

class FakeDispatcher:
    def __init__(self):
        self._replies = {}

    async def register_reply(self, msg_id):
        fut = asyncio.get_running_loop().create_future()
        self._replies[msg_id] = fut
        return await fut

    def resolve_reply(self, msg_id, value):
        self._replies[msg_id].set_result(value)


class FakeRequestsTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr, *, extra=REQUESTS_FLAG.EXTRA):
        self.sent.append((data, addr, extra))


class FakePeer:
    req_uri = _ADDR


@pytest.mark.asyncio
async def test_send_request_expect_reply_waits_for_dispatcher():
    ep, _ = make_endpoint()
    dispatcher = FakeDispatcher()
    service = RequestsService(dispatcher, FakeRequestsTransport(), ep)
    wire = WireData(header="req", msg_id="reply-key")
    reply_value = WireData(header="resp", msg_id="reply-key")

    async def resolve():
        await asyncio.sleep(0.01)
        dispatcher.resolve_reply("reply-key", reply_value)

    asyncio.create_task(resolve())
    result = await asyncio.wait_for(
        service.send_request(wire, FakePeer(), expect_reply=True),
        timeout=1.0,
    )
    assert result is reply_value


@pytest.mark.asyncio
async def test_send_request_confirm_delivery_succeeds_on_ack():
    ep, _ = make_endpoint()
    transport = FakeRequestsTransport()
    service = RequestsService(FakeDispatcher(), transport, ep)
    wire = WireData(header="deliver", msg_id="ack-me")

    async def deliver_ack():
        await asyncio.sleep(0.003)
        ack_packet = make_ack_packet("ack-me".encode())
        ep.datagram_received(ack_packet, _ADDR)

    asyncio.create_task(deliver_ack())
    await asyncio.wait_for(
        service.send_request(wire, FakePeer(), confirm_delivery=True, retries=3),
        timeout=2.0,
    )
    assert len(transport.sent) == 3
    assert transport.sent[0][2] == REQUESTS_FLAG.REQUIRE_ACK


@pytest.mark.asyncio
async def test_send_request_confirm_delivery_raises_after_retries(monkeypatch):
    ep, _ = make_endpoint()
    service = RequestsService(FakeDispatcher(), FakeRequestsTransport(), ep)
    wire = WireData(header="deliver", msg_id="no-ack")

    with pytest.raises(FailedToSend):
        await service.send_request(wire, FakePeer(), confirm_delivery=True, retries=2)
