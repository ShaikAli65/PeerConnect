# Peer Discovery Module (core/discover.py)

## Overview

Implements network discovery mechanisms using a state machine pattern. Integrates with `core/requests.py` for network
I/O operations.

Key Features:

- Kademlia-based bootstrapping
- Multicast discovery requests
- Passive/active mode transitions
- User fallback interaction

## Key Components

### 1. Discovery State Machine

```text
Initiate → Register Handlers → Send Requests → Bootstrap Check → [Passive Mode]
```

- Exponential backoff retries (up to `DISCOVERY_RETRIES`)
- Periodic passive mode requests (`DISCOVERY_TIMEOUT`)

### 2. Core Handlers

| Handler                   | Responsibility                      |
|---------------------------|-------------------------------------|
| `DiscoveryReplyHandler`   | Processes bootstrap responses       |
| `DiscoveryRequestHandler` | Handles incoming discovery requests |

### 3. Discovery Dispatcher

- Inherits `QueueMixIn` and `ReplyRegistryMixIn`
- Routes discovery-related messages
- Manages async request processing

## Discovery Workflow

1. Send multicast discovery packets
2. Handle replies to bootstrap Kademlia
3. Enter passive mode if bootstrapping fails
4. Optional user interaction fallback:

```python
async def _try_asking_user():
    if peer_name := await webpage.ask_user_peer_name_for_discovery():
# Attempt direct connection
```

## Integration Notes

- **Network I/O Foundation**: Relies on `core/requests.py` for actual network operations
- **Transport Layer**: Uses `DiscoveryTransport` wrapper for message sending
- **State Management**: Integrates with `Dock` for system status tracking
- **Kademlia Integration**: Directly interacts with DHT server for bootstrapping

> [back](/src_docs/core)
