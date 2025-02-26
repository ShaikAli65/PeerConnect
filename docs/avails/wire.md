# Wire Protocol Module Documentation

## Overview

The `wire.py` module provides core networking primitives for structured data transmission in PeerConnect. It handles:

- Data serialization/deserialization
- Stream (TCP) and datagram (UDP) communication
- Protocol versioning
- Structured message formats

## Key Components

### 1. Wire Class
Core I/O operations for network communication

**Methods**:
```python
# Stream communication
Wire.send(sock: Socket, data: bytes)
Wire.receive(sock: Socket, timeout=None)
Wire.send_async(sock: Socket, data: bytes)
Wire.receive_async(sock: Socket)

# Datagram communication
Wire.send_datagram(sock, address, data: bytes)
Wire.recv_datagram(sock)
Wire.load_datagram(data_payload)
```

**Features**:
- Automatic size framing (4-byte header)
- Async/sync variants
- Maximum datagram size enforcement (64KB)

### 2. WireData Class
Structured message container for network operations

**Structure**:
```python
WireData(
    header: str,        # Message type identifier
    msg_id: str,        # Unique message ID
    peer_id: str,       # Sender peer ID
    version: str,       # Protocol version
    **body              # Payload data
)
```

**Serialization**:
```python
bytes_data = bytes(wire_data_instance)
restored = WireData.load_from(bytes_data)
```

### 3. Protocol Messages

#### Gossip Protocol
```python
class GossipMessage:
    message: str    # Content payload
    ttl: int        # Time-to-live counter
    created: float  # Creation timestamp
```

#### Palm Tree Protocol
```python
@dataclass
class PalmTreeInformResponse:
    peer_id: str
    passive_addr: tuple[str, int]
    active_addr: tuple[str, int]
    session_key: str

@dataclass 
class PalmTreeSession:
    originate_id: str
    session_id: int
    key: str
    fanout: int
    link_wait_timeout: int
    adjacent_peers: list[str]
    chunk_size: int
```

### 4. DataWeaver Class
Web handler message wrapper

**Structure**:
```json
{
    "header": "MESSAGE_TYPE",
    "content": {}, 
    "peerId": "PEER_ID",
    "msgId": "MESSAGE_ID",
    "type": "signal|data"
}
```

## Usage Examples

### Sending a Structured Message
```python
# Create message
data = WireData(
    header="FILE_TRANSFER",
    msg_id="UNIQUE_ID_123",
    peer_id="MY_PEER_ID",
    filename="large_file.zip",
    size=1024000
)

# Send over stream
with create_socket() as sock:
    Wire.send(sock, bytes(data))

# Send via datagram
transport.sendto(bytes(data), address)
```

### Receiving Messages
```python
# Stream receiver
def handle_stream(sock):
    while True:
        data = Wire.receive(sock)
        message = WireData.load_from(data)
        print(f"Received {message.header}: {message.body}")

# Datagram handler
def datagram_received(data, addr):
    try:
        message = unpack_datagram(data)
        print(f"From {addr}: {message}")
    except InvalidPacket:
        print("Malformed packet received")
```

## Serialization Formats

1. **WireData**:
   - Uses MessagePack (umsgpack)
   - Structure: `[header, msg_id, version, body, peer_id]`

2. **DataWeaver**:
   - Uses JSON
   - Schema enforced with required fields check

## Protocol Details

### Versioning
```python
WIRE_VERSION = "0.1" # ? TBD # Defined in constants
```

### Error Handling
- `InvalidPacket` exception for malformed data
- Automatic connection health checks
- Size validation for datagrams

### Performance Characteristics
- Zero-copy buffer management
- Async-ready architecture
- Batch message processing
