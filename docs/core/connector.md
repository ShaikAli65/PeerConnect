# Documentation for PeerConnect Core Module:  Connector

The two modules work together to form the backbone of PeerConnect’s peer-to-peer networking architecture. The [acceptor](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/acceptor.md) handles incoming connections, while the **Connector** manages outbound connections and connection pooling.

---
## Table of Contents

- [src/core/connector.py](#srccoreconnectorpy)
  - [Overview](#overview-2)
  - [Key Components](#key-components)
    - [_create_conn(peer)](#_create_connpeer)
    - [Connector](#connector)

---

### Overview

- This module is *closely coupled* with `core.acceptor` and provides functionality for connecting to remote peers.
- It encapsulates both the logic for creating outbound connections and the management of connection pools (active and passive connections).

### Key Components

#### _create_conn(peer)

- **Purpose:**  
  An asynchronous helper function that attempts to create a connection to a given peer using `connect.connect_to_peer`.
  
- **Functionality:**  
  - Applies a timeout using a retry count defined in `const.CONNECTION_RETRIES`.
  - Raises a `CannotConnect` exception if the connection attempt fails.

#### Connector

- **Description:**  
  A singleton mixin class (that also mixes in `AExitStackMixIn`) responsible for maintaining outbound connection pools.
  
- **Features:**
  - **Connection Pools:**
    - **active_conns:**  
      Maps a `RemotePeer` to a set of connections currently in use for data transfer.
    - **passive_conns:**  
      Maps a `RemotePeer` to a set of connections that are idle but available.
  - **Connection Waiters:**  
    Maintains a dictionary of connection waiters using `asyncio.Condition` to handle situations when the maximum number of concurrent connections (defined by `const.MAX_CONNECTIONS_BETWEEN_PEERS`) is reached.
  
- **connect() Method:**  
  Defined as an async context manager, its behavior includes:
  1. **Checking Existing Connections:**  
     Looks for a usable (passive) connection in the connection pool.
  2. **Handling Maximum Connections:**  
     If no passive connection is available and the number of connections has reached the maximum, it raises a `ResourceBusy` exception (if the `raise_if_busy` flag is set). This exception carries a condition object to signal when a connection might be freed.
  3. **Creating New Connections:**  
     If allowed, it attempts to create a new connection (using `_create_conn`). Once established, the connection is yielded to the caller.
  - **Bookkeeping:**  
    When the context is exited, the connection is either moved to the passive pool (if still active) or removed from the active pool, with adjustments made to the global connection count.
  - **Helper Method:**  
    `_yield_connection_and_maintain()` handles maintenance tasks while holding a lock on the connection.
  - **Additional Properties:**  
    Properties like `conn_count` and `number_of_connections(peer)` help in tracking the overall connection state.

---


Together, they form a robust system that supports efficient and reliable peer-to-peer communications. Developers extending these modules should refer to the inline comments and additional modules (such as [bandwidth](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/bandwidth.md) and [dispatcher](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/dispatcher.md) logic) for more comprehensive insights.
