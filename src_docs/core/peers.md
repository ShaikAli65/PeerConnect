# Peer Management Module Documentation (peers.py)

## Overview

Handles peer discovery, search, and lifecycle management through:

- Kademlia-based network crawling
- Gossip protocol integration
- Distributed peer list management
- Connectivity verification

## Strategy

- PeerConnect uses 20 evenly spaced node ids in [0, 2**160] id space.
- Peers closest to these ids store peer details that are close to these ids
- This effectively creates a database that is scattered across and accessed through kademlia's routing
- These data points are referred as `LISTS` across the code (a better name TBD).

> ex:
> PERIODIC_TIMEOUT_TO_ADD_THIS_REMOTE_PEER_TO_LISTS = 10

## Core Components

### 1. Search Mechanisms

#### `SearchCrawler`

```python
class SearchCrawler:
    # Combines Kademlia and gossip protocols for:
    # - Keyword-based peer discovery
    # - Distributed search coordination
```

#### `GossipSearch`

```python
class GossipSearch:
    # Implements gossip-based search with:
    # - Time-bound async iterators
    # - Request/response management
    # - Result caching
```

### 2. Peer List Management

#### `PeerListGetter`

```python
class PeerListGetter(crawling.ValueSpiderCrawl):
    # Features:
    # - Distributed peer list retrieval
    # - Cache management
    # - Pagination support
```

### 3. Peer Lifecycle

```python
def new_peer(peer):
    # Handles new peer discovery
    # Integrates with UI system

def remove_peer(peer):
    # Implements verification-based removal
    # Uses connectivity checks
```

## Key Features

### Peer Discovery Strategies

1. **Direct ID Lookup**

    ```python
    async def get_remote_peer(peer_id)
    ```

2. **Keyword Search**

    ```python
    async def search_for_nodes(node_server, search_string)
    ```

3. **Gossip-based Search**

    ```python
    async def gossip_search(search_string)
    ```

### Connectivity Management

```python
async def check_and_remove_if_needed(peer: RemotePeer):
    # Verification workflow:
    # 1. Initiate connectivity check
    # 2. Evaluate result
    # 3. Update status or remove
```

## Architecture Notes

1. **Hybrid Search**  
Combines Kademlia's structured network crawling with gossip's epidemic protocol

2. **Cache Management**  
Implements time-based caching with manual invalidation

3. **UI Integration**  
Automatic peer list updates through webpage integration

## Performance Considerations

- **Search Timeouts**: Configurable timeout periods
- **Network Queries**: Limited through Kademlia's α parameter
- **Result Streaming**: Async iterator pattern for progressive results

> [back](/src_docs/core)
