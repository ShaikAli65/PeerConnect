# Module: avails.connect

Serves as the public interface for network connection functionality in PeerConnect. It aggregates three lower-level modules—`_asocket`, `_conn`, and `_netproto` and provides high-level utilities for creating, managing, and inspecting socket connections. Supports both synchronous and asynchronous operations, as well as specialized helpers for multicast configurations.

---

## Overview

The module is organized into the following subcomponents:

- **Module `_asocket`**  [src](/src/avails/_asocket.py)
  Provides the custom `Socket` class, a subclass of Python’s built-in socket. Integrates with asyncio for asynchronous I/O while retaining synchronous methods.

- **Module `_conn`**  [src](/src/avails/_conn.py)
  Contains mixins and helper classes to extend socket functionality with throughput measurement and flow control:
  - **_PauseMixIn / _ResumeMixIn:**  
    Provide methods to pause and resume data flow.
  - **ThroughputMixin:**  
    Measures and updates I/O throughput.
  - **Sender and Receiver:**  
    Wrap asynchronous send/receive operations while tracking data rates.
  - **Connection:**  
    A NamedTuple wrapper that bundles a socket, sender, receiver, peer information, and a concurrency lock. It supports asynchronous context management.
  - **MsgConnection / MsgConnectionNoRecv:**  
    Handle sending and receiving of marshalled wire data, with the latter disabling receive operations.

- **Module `_netproto`**  [src](/src/avails/_netproto_.py)
  Defines an abstract network protocol interface and concrete implementations for TCP and UDP:
  - **NetworkProtocol (abstract):**  
    Specifies methods to create asynchronous/synchronous sockets and server sockets.
  - **TCPProtocol:**  
    Implements the interface for TCP connections.
  - **UDPProtocol:**  
    Implements the interface for UDP connections.

- **High-Level Module Functions (connect):**  [src](/src/avails/connect.py)
  Offers a set of utilities for establishing and managing connections:
  - **IPAddress (NamedTuple):**  
    Represents an IP address.
  - **create_connection_sync(address, timeout=None) -> Socket:**  
    Creates a synchronous connection to the specified address.
  - **create_connection_async(address, timeout=None) -> Socket:**  
    Asynchronously creates a connection.
  - **Constants:**
    - `CONN_URI`: Default identifier for connection URIs.
    - `REQ_URI`: Default identifier for request URIs.
  - **connect_to_peer(...):**  
    Establishes a basic socket connection to a remote peer, supporting configurable timeouts and retry attempts.
  - **Utility Functions:**
    - `is_socket_connected(sock: Socket)`: Checks if a socket is still connected.
    - `get_free_port(ip=None) -> int`: Returns a free port available on the specified IP.
    - `ipv4_multicast_socket_helper(...)`: Configures a socket for IPv4 multicast [[1]](#ref1).
    - `ipv6_multicast_socket_helper(...)`: Configures a socket for IPv6 multicast [[1]](#ref1).

---

## Detailed Documentation

### Module: `_asocket`

#### Socket Class

- **Description:**  
  A custom subclass of Python's built-in `socket.socket` designed for asynchronous integration using asyncio. It provides both synchronous and asynchronous methods for typical socket operations.
  
- **Key Methods:**
  - `set_loop(loop)`: Sets the asyncio event loop for asynchronous methods.
  - `remove_loop()`: Clears the assigned event loop.
  - `accept()`: Synchronously accepts a new connection and returns a new `Socket` instance along with the client’s address.
  - `aaccept()`: Asynchronously accepts a new connection.
  - `arecv(bufsize)`, `aconnect(address)`, `asendall(data)`: Asynchronous methods for receiving, connecting, and sending data, respectively.
  - Additional methods like `asendfile`, `asendto`, and various receive functions support full asynchronous I/O.

---

### Module: `_conn`

#### Mixins and Throughput Measurement

- **_PauseMixIn & _ResumeMixIn:**
  - Provide `pause()` and `resume()` methods that control the data transfer by toggling an internal asyncio event (`_limiter`).

- **ThroughputMixin:**
  - **Attributes:**
    - `BYTES_PER_KB`: Number of bytes per kilobyte (constant).
    - `RATE_WINDOW`: Time window over which throughput is measured.
  - **Functionality:**
    - Tracks the total bytes transferred and calculates throughput (in KB/s) over a specified window.
    - Method `_update_throughput(nbytes, current_time)` updates counters and resets the window when needed.

#### Sender and Receiver

- **Sender:**  
  Inherits from `_PauseMixIn`, `_ResumeMixIn`, and `ThroughputMixin`. It wraps an asynchronous send function (`loop.sock_sendall`) to send data through the socket and update throughput metrics.

- **Receiver:**  
  Similarly inherits from the same mixins and throughput class, providing an asynchronous receive function (`loop.sock_recv`) and updating throughput based on received data.

#### Connection

- **Description:**  
  A NamedTuple that encapsulates:
  - `socket`: A `TransportSocket` (wrapped custom Socket).
  - `send`: A `Sender` instance.
  - `recv`: A `Receiver` instance.
  - `peer`: Information about the remote peer.
  - `lock`: An asyncio lock for safe concurrent access.
  
- **Factory Method:**  
  `create_from(socket, peer)` creates a new `Connection` object from an existing socket and associated peer.
  
- **Context Management:**  
  Implements asynchronous context management via `__aenter__` and `__aexit__` to ensure proper acquisition and release of the lock.

#### Message Connections

- **MsgConnection:**  
  Provides methods to send and receive wire data objects. It prefixes the data with a 4-byte length header (using struct packing) before sending.
  
- **MsgConnectionNoRecv:**  
  Inherits from `MsgConnection` but disables receiving functionality (raises a `NotImplementedError` on calling `recv`).

---

### Module: `_netproto`

#### NetworkProtocol (Abstract Base Class)

- **Purpose:**  
  Defines the interface for creating both asynchronous and synchronous sockets, as well as server sockets.
  
- **Abstract Methods:**
  - `create_async_sock(loop, family, fileno)`: Create an asynchronous socket.
  - `create_sync_sock(family, fileno)`: Create a synchronous socket.
  - `create_async_server_sock(loop, bind_address, family, backlog, fileno)`: Create an asynchronous server socket.
  - `create_sync_server_sock(bind_address, family, backlog, fileno)`: Create a synchronous server socket.
  - `create_connection_async(loop, address, timeout)`: Asynchronously establish a connection.

#### TCPProtocol

- **Description:**  
  Implements `NetworkProtocol` for TCP sockets.
  
- **Key Features:**
  - Creates asynchronous TCP sockets that are non-blocking.
  - Binds, listens, and accepts connections.
  - Provides an asynchronous method to establish connections with a timeout.

#### UDPProtocol

- **Description:**  
  Implements `NetworkProtocol` for UDP sockets.
  
- **Key Features:**
  - Creates asynchronous UDP sockets.
  - Supports both binding and sending operations for UDP communication.
  - Implements a connection method that configures the socket for UDP.

---

### Module: `connect`

#### High-Level Connection Utilities

##### IPAddress (NamedTuple)

- **Purpose:**  
  Represents an IP address structure, used throughout the connection utilities.

##### create_connection_sync(address, timeout=None) -> Socket

- **Description:**  
  Establishes a synchronous socket connection to the specified address.
  
- **Parameters:**
  - `address`: The target address (IP and port).
  - `timeout`: Optional timeout for the connection attempt.

##### create_connection_async(address, timeout=None) -> Socket

- **Description:**  
  Asynchronously creates a socket connection using the asyncio event loop.
  
- **Parameters:**
  - `address`: The target address.
  - `timeout`: Optional timeout for the connection attempt.

##### Constants

- **CONN_URI:**  
  Default identifier (string `"uri"`) used to denote the connection URI.
  
- **REQ_URI:**  
  Default identifier (string `"req_uri"`) used for request connections.

##### connect_to_peer(...)

- **Function Signature:**

  ```python
  def connect_to_peer(_peer_obj=None, to_which: str = CONN_URI, timeout=None, retries: int = 1) -> Socket:
  ```
  
- **Description:**  
  Creates a basic socket connection to a remote peer. If the `to_which` parameter is set to `REQ_URI`, the connection is made to the peer's request URI.
  
- **Parameters:**
  - `_peer_obj`: The remote peer object (typically an instance representing a remote peer).
  - `to_which`: Specifies which URI to connect to (`CONN_URI` or `REQ_URI`).
  - `timeout`: Initial timeout for the connection attempt.
  - `retries`: Number of retry attempts with exponential backoff (using helper functions such as `useables.get_timeouts`).
  
- **Asynchronous Variant:**  
  The function is also available in an asynchronous form, decorated with `@useables.awaitable(connect_to_peer)`, enabling non-blocking connection attempts.

##### Utility Functions

- **is_socket_connected(sock: Socket):**  
  Checks whether the specified socket is currently connected.

- **get_free_port(ip=None) -> int:**  
  Returns an available free port on the given IP address, or a default port if none is specified.

- **ipv4_multicast_socket_helper(sock, local_addr, multicast_addr, *, loop_back=0, ttl=1, add_membership=True):**  
  Configures a socket for IPv4 multicast.  
  - **Parameters:**
    - `sock`: The socket to configure.
    - `local_addr`: The local address to bind.
    - `multicast_addr`: The multicast group address.
    - `loop_back`: Flag to enable loopback (default is off).
    - `ttl`: Time-to-live for multicast packets.
    - `add_membership`: If True, adds the socket to the multicast group.

- **ipv6_multicast_socket_helper(sock, multicast_addr, *, loop_back=0, add_membership=True, hops=1):**  
  Configures a socket for IPv6 multicast.
  - **Parameters:**
    - `sock`: The socket to configure.
    - `multicast_addr`: The multicast group address.
    - `loop_back`: Flag to enable loopback (default is off).
    - `add_membership`: If True, adds the socket to the multicast group.
    - `hops`: Specifies the number of hops for multicast packets.

---

<a id="ref1">[1]</a>: used by [core.requests](/src_docs/core/requests.md)

## Conclusion

The `avails.connect` module consolidates essential low-level socket functionalities and high-level API for network connectivity within PeerConnect.

[back](/src_docs/avails)
