# Bandwidth Management

Responsible for monitoring and managing connection bandwidth in PeerConnect. It currently implements a `Watcher` class that tracks active connections and their underlying sockets, and is designed to be extended with additional features in the near future.

---

## Overview

- **Purpose:**  
  To monitor connection objects and manage the underlying raw sockets, playing a critical role in the acceptance and maintenance of connections within the application.

- **Current Functionality:**  
  - Maintains a mapping from `RemotePeer` to a set of connection–socket pairs.
  - Provides methods to register new connections for monitoring.
  - Offers functionality to refresh and prune inactive or disconnected sockets.
  - Integrates with the global application exit stack for proper resource cleanup.

---

## Current configured parameters

- CONNECTION_RETRIES = 3
- MAX_RETIRES = 7
- MAX_CONNECTIONS_BETWEEN_PEERS = 6
- MAX_TOTAL_CONNECTIONS = 40
- MAX_CONCURRENT_MSG_PROCESSING = 6
- BYTES_PER_KB = 1024.0
- RATE_WINDOW = .0001

> *refer [constants](/src/avails/constants.py) module for more*

## Incoming and Outgoing Connections

In PeerConnect, connections are treated uniformly regardless of whether they are incoming or outgoing. However, to avoid race conditions, these connections are managed in separate pools. Each connection object contains a lock that indicates whether the connection is in use.

### Typical Connection Flow

Consider a typical connection from peer **p1** to peer **p2**:

> **s** -(requests)-> **p1 connector** -(arrives)-> **p2 acceptor** -(delegates)-> **s**

- **Step 1:** A service (**s**) on **p1** initiates a connection request.
- **Step 2:** The request is handled by **p1's connector**.
- **Step 3:** The connection arrives at **p2's acceptor**.
- **Step 4:** The acceptor delegates the connection to the service (**s**).

After the service completes its task, the connection is returned back to the acceptor. At this point, the acceptor attaches a watcher to the connection to monitor for any further activity.

### Potential Race Condition

If the connector were to incorporate incoming connections into its pool, the following scenario might occur:

1. **Service Request Reuse:**  
   When a service **s** on **p1** later requests a connection, the connector might pick the connection provided by the acceptor from the pool.

2. **Watcher Interference:**  
   At the same time, **p2's acceptor** is still monitoring that connection through its watcher. This can result in:
   - The connection becoming corrupted.
   - A race condition where both the acceptor and connector attempt to manage or use the same connection concurrently.

### Resolution Strategy

To prevent such race conditions:

- **Incoming connections** are kept **separate** from outgoing connections.
- They are pooled **independently**, ensuring that the acceptor’s watcher can monitor the connection without interference from the connector.
  
Separation guarantees that when a service (**s**) on **p1** requests a connection, it only receives an outgoing connection from the connector's pool, which is not subject to the acceptor's monitoring.

---

**Legend:**

- **p**: Peer  
- **s**: Some functionality or service

## Key Components

### `Watcher` Class

- **Description:**  
  A singleton class (using a mixin) that extends `AExitStackMixIn` to manage connection lifetimes via context management. It is responsible for tracking active connections and ensuring that inactive or misbehaving connections are pruned.

- **Attributes:**  
  - `sockets`: A dictionary mapping each `RemotePeer` to another dictionary that maps `Connection` objects to their associated `Socket` objects.

- **Methods:**
  - **`watch(socket: Socket, connection: Connection)`**  
    Registers a new connection by storing its raw socket. It also enters the socket into the exit stack, ensuring automatic cleanup when the context is exited.
  
  - **`refresh(peer, *connections: Connection)`**  
    Iterates over the connections for a given peer, checks their status using `is_socket_connected()`, and:
    - Adds active connections to an "active" set.
    - Removes and closes inactive sockets, collecting them into a "not active" set.
    Returns both sets for further handling.
  
  - **`refresh_all(peer)`**  
    A helper that checks all connections related to the specified peer by calling `refresh()` with all registered connections.

### `start_watcher` Function

- **Description:**  
  An asynchronous function that instantiates the `Watcher` (via the global exit stack in `Dock`) and begins monitoring connections. Ensures that the `Watcher` is active within the application's lifecycle.

---

## Future Enhancements

While the current code focuses on tracking and pruning connection sockets, the module is planned to be extended with additional mechanisms:

- **Throughput Throttling:**  
  Future versions will leverage the `pause` and `resume` methods on connection objects to dynamically throttle data throughput based on network conditions.

- **Connection Lifetime Management:**  
  Enhancements will include sophisticated lifetime management, allowing the system to more aggressively prune long-accessed or misbehaved connections.

- **Decision-Making Support:**  
  The `Watcher` will play a critical role in the acceptance process by providing real-time metrics and connection health, influencing whether new connections should be accepted.

---

In summary, the current implementation provides a solid foundation for bandwidth and connection management. With planned enhancements for throughput throttling and dynamic connection lifetime control, this module is set to become a key component in PeerConnect’s overall network management strategy.

> [back](/src_docs/core)
