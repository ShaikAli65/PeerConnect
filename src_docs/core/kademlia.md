# Kademlia Module Documentation (_kademlia.py)

## Overview

Implements a customized Kademlia Distributed Hash Table (DHT) integration for PeerConnect, featuring:

- Custom RPC protocols for peer communication
- Modified routing table implementation
- Peer lifecycle management
- Integration with system storage and transport layers

## Key Components

### 1. Protocol Extensions

#### `KadProtocol`

Core protocol handling Kademlia operations with PeerConnect-specific modifications:

```python
class KadProtocol(RPCCaller, RPCReceiver, protocol.KademliaProtocol):
    # Custom implementations for:
    # - Peer validation
    # - Data storage
    # - List management
    # - Peer search
```

### 2. Routing Enhancements

#### `AnotherRoutingTable`

Custom routing table with peer management integration:

```python
class AnotherRoutingTable(routing.RoutingTable): ...
```

### 3. Server Implementation

#### `PeerServer`

Custom Kademlia server with enhanced peer list management:

```python
class PeerServer(network.Server):
    # Features:
    # - Automatic peer list maintenance
    # - Distributed storage of peer lists
    # - Network crawling capabilities
    # - Bootstrap integration
```

### 4. RPC Handlers

| Method Group        | Key Features                              |
|---------------------|-------------------------------------------|
| `RPCCaller`         | Enhanced peer list operations             |
| `RPCReceiver`       | Storage management integration            |
| `RPCFindResponse`   | Custom peer deserialization               |

## Integration Points

1. **Peer Discovery**

    ```python
    def new_peer(peer):
        Dock.peer_list.add_peer(peer)
        # UI update integration
    ```

2. **Transport Layer**

    ```python
    class KademliaTransport:
        # Bridges Kademlia protocol with system's network transport
    ```

3. **Storage Integration**

    ```python
    class Storage(peerstore.Storage):
        # Custom peer list storage implementation
    ```

## Important Extensions

- **Peer List Management**: Custom RPC methods for storing/fetching peer lists
- **Proximity-based Storage**: Data storage based on network topology
- **Search Integration**: Combined Kademlia/gossip search capabilities

> [back](/src_docs/core)
