# Core State Management Module (src/core/public.py)

## Overview

Central registry for global application state and service access points. Provides controlled access through accessor
functions rather than direct global variable access.

## Key Components

### 1. Dock Class (Singleton Pattern)

Global state container with essential system references:

#### Abstract

| Attribute              | Type                   | Description                 |
|------------------------|------------------------|-----------------------------|
| `peer_list`            | `_PeerDict`            | Active peer directory       |
| `state_manager_handle` | `StateManager`         | State machine controller    |
| `global_gossip`        | `RumorMongerProtocol`  | Gossip protocol instance    |
| `in_network`           | `asyncio.Event`        | Network connectivity status |
| `requests_transport`   | `RequestsTransport`    | Network transport layer     |
| `dispatchers`          | `dict[DISPATCHS, ...]` | Protocol handler registry   |

#### Detailed

A centralized container for global references:

- **Attributes:**
  - `peer_list`: A collection of remote peers.
  - `state_manager_handle`: Reference to the state manager.
  - `global_gossip`: Global gossip protocol instance.
  - `_this_object`: The current remote peer object.
  - `kademlia_network_server`: Kademlia network server instance.
  - `in_network`: An asyncio event indicating network connectivity.
  - `finalizing`: An asyncio event indicating application shutdown.
  - `requests_transport`: The transport object used for sending requests.
  - `dispatchers`: A mapping of `DISPATCHS` keys to their corresponding dispatchers.
  - `exit_stack`: An `AsyncExitStack` for managing asynchronous cleanup.
  - `current_config`: A `ConfigParser` instance for application configuration.

### 2. DISPATCHS Enum

Protocol handler types:

| Value | Constant    | Description              |
|-------|-------------|--------------------------|
| 1     | REQUESTS    | Network request handling |
| 2     | DISCOVER    | Peer discovery           |
| 3     | GOSSIP      | Gossip propagation       |
| 4     | CONNECTIONS | Connection management    |
| 5     | MESSAGES    | Message routing          |

### 3. Core Accessors & Utility Functions

- **Address and Peer Management:**
  - `addr_tuple(ip, port)`: Returns an address tuple using application constants.
  - `get_this_remote_peer()`: Retrieves the current remote peer from `Dock`.
  - `set_current_remote_peer_object(remote_peer)`: Sets the current remote peer.

- **Dispatcher Accessors:**
  - `get_dispatcher(dispatcher_id)`: Returns the dispatcher for the given ID.
  - Specific functions:
    - `requests_dispatcher()`
    - `discover_dispatcher()`
    - `gossip_dispatcher()`
    - `connections_dispatcher()`
    - `msg_dispatcher()`

### 4. Network Operations

```python
async def send_msg_to_requests_endpoint(
        msg: WireData,
        peer: RemotePeer,
        *, expect_reply: bool = False
) -> Optional[Response]:
    """Managed message sending with reply tracking"""
```

## Architectural Notes

1. **State Isolation**

    - All global references contained in `Dock` class
    - Access only through accessor functions
    - Type hints enforced via TYPE_CHECKING guards

2. **Dispatcher System**

    - Unified interface for protocol handlers
    - Enum-based registry (DISPATCHS)
    - Lazy loading via getter functions

3. **Network Integration**

    - Abstracts transport layer details
    - Provides async-aware network status tracking
    - Coordinates with Kademlia DHT implementation

## Usage Example

```python
# Send message with reply expectation
response = await send_msg_to_requests_endpoint(
    WireData(header="PEER_SEARCH", ...),
    target_peer,
    expect_reply=True
)

# Access current peer
local_peer = get_this_remote_peer()
```

---

**Architectural Judgment**: While global state is generally discouraged, this implementation shows:

✅ **Controlled Access** through accessor methods rather than direct global access  
✅ **Type Safety** via rigorous type hinting  
✅ **Modularity** through dispatcher registry pattern  
⚠️ **Tradeoff** - Balances practicality of state sharing against ideal isolation for distributed system needs  
⚠️ **Caution** - Requires strict discipline to maintain read-only access except through owner modules  

**[WIP](/src_docs/README.md#legend)**:  A refactor needs to be considered on applying context pattern which passes Dock as a context object around application

> [back](/src_docs/core)
