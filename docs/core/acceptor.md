# Documentation for PeerConnect Core Module: Acceptor

The two modules work together to form the backbone of PeerConnect’s peer-to-peer networking architecture. The **Acceptor** handles incoming connections, while the [connector](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/connector.md) manages outbound connections and connection pooling.

---

## Table of Contents

- [Overview](#overview)
- [src/core/acceptor.py](#srccoreacceptorpy)
  - [Overview](#overview-1)
  - [Key Components](#key-components)
    - [initiate_acceptor(exit_stack, dispatchers)](#initiate_acceptorexit_stack-dispatchers)
    - [ConnectionDispatcher](#connectiondispatcher)
    - [Acceptor](#acceptor)

- This module is *closely coupled* with `core.connector` and handles the acceptance of incoming peer connections.
- It employs lazy loading (via the `initiate_acceptor` function) to avoid circular imports between the acceptor and connector.

### Key Components

#### initiate_acceptor(exit_stack, dispatchers)

- **Purpose:**  
  Sets up a `ConnectionDispatcher` (which registers various connection handlers—for example, for file and directory transfers) and creates an Acceptor instance.
  
- **Functionality:**  
  - The dispatcher is registered in the provided `dispatchers` dictionary under the `connections` key.
  - It enters both the dispatcher and acceptor contexts using an asynchronous exit stack to ensure that cleanup is handled automatically.

#### ConnectionDispatcher

- **Role:**  
  A subclass that combines functionalities from `QueueMixIn` and `BaseDispatcher`.

- **Responsibilities:**
  - **Parking Connections:**  
    Maintains a “parking lot” of connections that are waiting for activity.
  - **park() Method:**  
    Creates an asynchronous watcher on a connection. It waits for a service header (via `Wire.recv_msg` [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/avails/wire.md)) and, once received, submits a `ConnectionEvent` to the dispatcher.
  - **submit() Method:**  
    Retrieves the appropriate handler from its registry based on the event’s header and invokes it, awaiting the result if necessary.

#### Acceptor

- **Description:**  
  A singleton mixin class (which also mixes in `AExitStackMixIn`) that manages the lifecycle of the acceptor socket.
  
- **Key Features:**
  - **initiate() Method:**  
    - Starts listening on a designated address with a configurable backlog and timeout.
    - Repeatedly accepts new connections in an asynchronous loop while a “finalizer” (typically a signal or flag from `Dock.finalizing`) is not set.
    - For every new connection, a task (via its TaskGroup) is created to handle the connection. This task performs a handshake, obtains the remote peer’s information, and dispatches the connection event to the connection dispatcher.
  - **_start_socket() Method:**  
    Creates an asynchronous server socket using the protocol’s `create_async_server_sock`. The accept loop uses `asyncio.sleep(0)` to yield control.


**References:**  
- connector [docs](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/connector.md) [src](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/core/connector.md)
- bandwidth [docs](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/bandwidth.md) [src](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/core/bandwidth.md)