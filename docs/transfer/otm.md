# Palm Tree Protocol Documentation

> Note: this module is not finalized and needs many improvements before going live

## Overview

The Palm Tree Protocol is a gossip-based protocol designed for efficient file distribution in peer-to-peer networks. It combines UDP for lightweight control plane communication and TCP for reliable bulk data transfer. The protocol dynamically builds a spanning tree to propagate files across participating nodes, minimizing redundant data transmission.

## Key Components

1. **Relay (PalmTreeRelay/OTMFilesRelay)**
   - Manages peer connections and protocol state
   - Handles gossip messages and connection upgrades
   - Coordinates tree formation and data forwarding
   - Maintains both active (TCP) and passive (UDP) links

2. **Sender (FilesSender)**
   - Initiates file transfer sessions
   - Manages file chunking and metadata distribution
   - Coordinates with relays for data propagation

3. **Receiver (FilesReceiver)** 
   - Handles file assembly from received chunks
   - Manages disk writing and storage
   - Tracks transfer progress and completeness

4. **Tree Links (PalmTreeLink)**
   - Abstract representation of peer connections
   - Two types:
     - *Passive*: UDP-based, for control messages
     - *Active*: TCP-based, for bulk data transfer

## Protocol Phases

### 1. Session Initialization
```python
# Sender creates protocol instance
sender = FilesSender(file_list, peers, timeout)
await sender.start()
```
- Initiator creates OTMSession with unique ID
- Establishes passive UDP endpoint for control messages
- Broadcasts session metadata to participating peers

### 2. Topology Formation (Hypercube)
```python
# Hypercube topology creation
def create_hypercube(self):
    dimensions = math.ceil(math.log2(n_peers))
    for i in range(n_peers):
        for j in range(dimensions):
            neighbor = i ^ (1 << j)
            # Create adjacency list
```
- Builds logical hypercube structure for efficient message propagation
- Each peer maintains connections to log2(N) neighbors
- Enables O(log N) diameter for message dissemination

### 3. Spanning Tree Construction
```python
# Tree check propagation
async def gossip_tree_check(self, packet, addr):
    if validate(packet):
        forward_to(sampled_peers)
    else:
        send_rejection()
```
- Initiated by root node (original sender)
- Validation checks:
  - Peer exists in adjacency list
  - Active links under fanout limit
  - No existing parent connection
- Successful validation triggers connection upgrade

### 4. Data Transfer
```python
# File chunk forwarding
async def _forward_chunk(self, chunk):
    for link in active_links:
        await link.send(chunk)
```
- File divided into fixed-size chunks (default 64KB)
- Metadata sent first using msgpack serialization
- Chunks flow through spanning tree using active links
- Relays buffer and forward chunks to downstream peers

## Connection Lifecycle

1. **Passive Link Establishment**
   - UDP control channel initialized
   - Handles tree check/update messages
   - Bookkeeping for potential upgrades

2. **Active Link Upgrade**
   ```python
   async def _send_upgrade_packet(self):
       send(UPGRADE_REQUEST)
       await connection_confirmation()
   ```
   - Initiated via UDP control message
   - TCP connection established on upgrade acceptance
   - Bidirectional communication channel

3. **Failure Handling**
   - Timeout detection (configurable timeout)
   - Automatic downgrade to passive mode
   - Missing chunk tracking and retransmission

## Performance Considerations

1. **Fanout Control**
   ```python
   session = OTMSession(fanout=4)  # Default 4 connections
   ```
   - Balances between tree width and connection overhead
   - Configurable based on network capacity

2. **Flow Control**
   - Semaphore-based forwarding limiter
   ```python
   self._forward_limiter = Semaphore(fanout)
   ```
   - Prevents overwhelming slow receivers
   - Automatic backpressure through TCP congestion control

3. **Buffer Management**
   - Ring buffer for chunk storage (default 64 chunks)
   ```python
   recv_buffer_queue = deque(maxlen=MAX_OTM_BUFFERING)
   ```
   - Enables retransmission without disk access

## Failure Modes Handling

1. **Link Degradation**
   - Automatic downgrade to passive mode
   - Periodic health checks
   - Buffer retention for retransmission

2. **Parent Failure**
   ```python
   async def _parent_link_broken(self):
       await self._parent_link_fut  # Reconnect
   ```
   - Re-initiate tree check protocol
   - Select new parent from active links

3. **Partial Chunk Recovery**
   ```python
   async def fill_partial_chunks(self):
       request_missing(missing_chunks)
   ```
   - Bitmap tracking of received chunks
   - End-of-transfer missing chunk request

## Usage Example

### Sender Side
```python
async def send_files():
    sender = FilesSender(
        file_list=["large_file.iso"],
        peers=[peer1, peer2, peer3],
        timeout=30
    )
    async for step in sender.start():
        handle_progress(step)
```

### Receiver Side
```python
def on_transfer_start(receiver):
    print(f"Receiving {len(receiver.file_items)} files")
    
async def data_handler():
    async for chunk in receiver.data_receiver():
        update_progress(chunk)
```

## Protocol Limitations
1. Dynamic Topology
   - Static peer list assumption

## Future Improvements

1. Chunk Prioritization
   - Rarest-first chunk selection
   - Tit-for-tat bandwidth allocation

2. Adaptive Topology
   - Dynamic peer sampling
   - Link quality metrics

3. Enhanced Reliability
   - Forward Error Correction
   - Merkle-tree chunk verification