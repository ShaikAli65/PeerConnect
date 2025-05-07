# Manager API

High level managers for different application functionalities

## List of Managers

- File transfer
- Directory transfer
- Message transfer
- State
- Profiles

## File Manager

The module's primary responsibilities are to:

- **Send Files to Peers:**  
  - Prepare a file sender with the selected files.
  - Establish a connection using the Connector.
  - Send files over an authenticated connection while monitoring progress.
  - Update the UI periodically with transfer status.
- **Receive Files from Peers:**  
  - Handle incoming file transfer connections.
  - Create a file receiver that writes files to a designated download directory.
  - Manage transfer state and notify the UI upon progress or completion.
- **OTM (One To Many) Support:**  
  - Initiate new OTM file transfer sessions.
  - Process incoming OTM requests and update session relays.
- **File Selection:**  
  - Provide a utility to open a file selection dialog for the user.

## Directory Manager

Same as File Manager, but works with directory transfers  

## Message Manager

Responsible for managing message processing and dispatching in PeerConnect. It handles incoming message connections, dispatches messages to appropriate handlers, and provides utilities for sending messages to peers. The module leverages asynchronous programming, connection pooling, and concurrency control to process messages efficiently.

- **Key Responsibilities:**  
  - Initiate and register message dispatching services.
  - Process incoming messages over established TCP connections.
  - Provide a mechanism for sending messages to a specified peer.
  - Handle ping messages to maintain connectivity.

two classes from [messages](/src/transfers/messages.py) module are used here

```py
class MsgSender:...
class MsgReceiver:...
```

Both of the classes have internal looping mechanisms that takes in a connection and process those
incoming (or outgoing) messages.

Message manager uses a single `Stream` connection to both send and receive messages b/w a pair of peers

### Flow

#### Connecting

- User wants to send a message, connection helpers try connecting to a peer (with retries) using `MsgSender` object

- After the connection succeedes, the same connection is sort of loop backed into [acceptor](/src_docs/core/acceptor.md) dispatcher routines.

- Loop Back handler starts a new `MsgReceiver` and starts iterating over `tcp` stream until connection breaks

#### Accepting

- When a connection arrives at [acceptor](/src_docs/core/acceptor.md), it forwards connection to registered message handler.

- Message handler adds the connection to pool, this prevents msg connection mechanisms to try connecting again and they pick this connection from pool instead of connecting again

- After that it starts receiving messages from connection using `MsgReceiver`.

### Handling race condition

What if two users exactly try to connect each other at once ??

We send a close connection request to other end and raise a `CannotConnect` error with message *try again*

And when next time we try to connect we already have a connection in pool

## State Manager

visit [here](/src_docs/managers/state.md)

## Profile Manager

visit [here](/src_docs/managers/profiles.md)

---

[back](/src_docs)
