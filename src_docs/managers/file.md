# File Manager Module Documentation

## Managing file transfers between peers

Handles both sending and receiving files—and integrates with the UI to update transfer status. The module leverages asynchronous programming extensively and uses a global *transfers bookkeeper* to track transfer states.

---

## Overview

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

---

## Key Components and Functions

### File Sending

#### `send_files_to_peer(peer_id, selected_files)`

- **Description:**  
  An asynchronous context manager that initiates a file transfer to the remote peer identified by `peer_id` with the provided list of files.
- **Flow:**
  1. **Transfer Attachment:**  
     If a transfer is already running for the given peer, the new files are attached to the existing transfer.
  2. **Setup:**  
     Calls `_send_setup()` to initialize a file sender and a status updater.
  3. **Connection and Transfer:**  
     Uses `_sender_helper()` to establish a connection, wait for confirmation, and then send files. The sender periodically yields progress updates to the UI using `webpage.transfer_update`.
  4. **Finalization:**  
     Once the transfer completes, it is finalized by updating the transfers bookkeeper, and the status updater is closed.

#### `_send_setup(peer_id, selected_files)`

- **Purpose:**  
  Prepares the file sender and status updater for a new transfer.
- **Outcome:**  
  Returns a tuple of `(file_sender, status_updater)`.

#### `_sender_helper(file_sender, peer_id)`

- **Description:**  
  An asynchronous context manager that:
  - Prepares the connection using `prepare_connection()`.
  - Waits for a confirmation byte from the remote peer.
  - Yields an asynchronous generator for sending files.
- **Error Handling:**  
  If the connection fails or the remote peer rejects the transfer, it raises an exception (e.g., `TransferIncomplete` or `TransferRejected`) and notifies the UI accordingly.

---

### Connection Preparation

#### `prepare_connection(sender_handle)`

Async context manager

- **Purpose:**  
  Prepares and authenticates a connection for a file transfer.
- **Steps:**
  - Sets the sender state to `CONNECTING`.
  - Uses the `Connector` to establish a connection to the remote peer.
  - Configures socket options (such as `TCP_NODELAY`).
  - Sends an authorization handshake (a `WireData` message with header `HEADERS.CMD_FILE_CONN`).

Yields the established connection for use in file transfers.

---

### File Receiving

#### `file_receiver(file_req: WireData, connection: connect.Connection, status_updater)`

- **Description:**  
  An asynchronous context manager that wraps a `files.Receiver` object.
- **Functionality:**
  - Retrieves peer details and sets up the file receiver with a target download directory.
  - Registers the receiver in the transfers bookkeeper.
  - Yields the receiver for processing incoming file data.
  - Upon completion, updates the transfer status (completed or paused) in the transfers bookkeeper.

#### `FileConnectionHandler()`

- **Purpose:**  
  An asynchronous handler for incoming file transfer connection events.
- **Flow:**
  - Checks if a transfer with the same file ID is already running and, if so, directs the connection to that transfer.
  - Sends an acceptance byte (`b'\x01'`) to the remote peer based on desicion.
  - Uses an asynchronous exit stack to manage the file receiver lifecycle.
  - Iterates over the file receiver's asynchronous generator, updating the UI via `webpage.transfer_update` as progress is made.
  - On completion, marks the transfer as completed in the transfers bookkeeper.
- **Error Handling:**  
  Exceptions (such as `TransferIncomplete`) are caught and the UI is updated with appropriate error messages.

---

### OTM (One To Many Transfer) Support

#### `OTMConnectionHandler()`

- **Description:**  
  Handles connection events related to OTM sessions.
- **Behavior:**
  - Retrieves session data from the handshake.
  - Updates the corresponding OTM session relay with the new connection.
  - Logs errors if the OTM session cannot be found.

#### `start_new_otm_file_transfer(files_list: list[Path], peers: list[RemotePeer])`

- **Purpose:**  
  Initiates a new OTM file transfer session.
- **Process:**
  - Creates an instance of `otm.FilesSender` with the provided file list and peers.
  - Registers the sender in the transfers bookkeeper.
  - Returns the sender instance.

#### `new_otm_request_arrived(req_data: WireData, addr)`

- **Description:**  
  Processes incoming OTM requests.
- **Steps:**
  - Creates a new OTM session with parameters extracted from the request.
  - Sets up an `otm.FilesReceiver` to handle the incoming file transfer.
  - Registers the session in the transfers bookkeeper.
  - Returns an OTM inform response (as bytes) containing the passive and active addresses, and the session key.

---

### File Selection Utility

#### `open_file_selector()`

- **Purpose:**  
  Opens a file dialog window to allow the user to select files for transfer.
- **Implementation:**  
  Runs the file dialog in a background executor to avoid blocking the event loop.
- **Return:**  
  A list of selected file paths.

---

## Summary

The File Manager module provides a robust mechanism for handling file transfers between peers in PeerConnect. It encompasses:

- **File Sending:**  
  Managing sender setup, connection preparation, progress monitoring, and finalization.
- **File Receiving:**  
  Wrapping incoming connections into a receiver that processes and stores incoming file data.
- **OTM Support:**  
  Handling one to many file transfer sessions with dedicated OTM handlers.
- **User Interaction:**  
  Allowing file selection through a non-blocking file dialog.

[back](/src_docs/managers)
