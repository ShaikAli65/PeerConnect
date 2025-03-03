# Directory Manager Module Documentation

Handles both the sending and receiving of entire directories using specialized sender and receiver classes. The module also provides utilities for opening a directory selection dialog, confirming transfers, and pausing an ongoing transfer.

---

## Overview

The directory manager module is responsible for:

- **User Interaction:**  
  Allowing the user to select a directory via a dialog.
- **Sending Directories:**  
  Initiating directory transfers by signaling the receiving end, sending the directory contents, and updating transfer status.
- **Receiving Directories:**  
  Handling incoming directory transfer requests and saving the received directories in a designated download path.
- **Transfer Management:**  
  Managing transfer state with a `TransfersBookKeeper`, supporting pause/resume functionality, and updating the UI.

The module leverages several components:

- **TransfersBookKeeper:**  
  Tracks active, continued, and completed transfers.
- **Connector:**  
  Manages outgoing connections to remote peers.
- **DirSender and DirReceiver:**  
  Specialized classes for sending and receiving directory contents.
- **StatusMixIn:**  
  Provides periodic status updates during transfers.
- **Webpage Module:**  
  Notifies the UI about transfer progress (via `webpage.transfer_update`).

---

## Key Functions and Components

### `open_dir_selector()`

- **Purpose:**  
  Opens a directory selection dialog for the user.
- **Implementation:**  
  Uses the event loop's executor to run the dialog in a non-blocking way.
- **Usage:**  
  Returns the selected directory path asynchronously.

### `send_directory(remote_peer, dir_path)`

- **Purpose:**  
  Sends a directory from the local machine to a specified remote peer.
- **Process:**
  1. **Prepare Transfer Data:**  
     - Converts the given `dir_path` to a `Path` object.
     - Obtains a unique `transfer_id` from the `TransfersBookKeeper`.
     - Creates a signal packet (`WireData`) that contains transfer details (header, peer ID, transfer ID, and directory name).
  2. **Establish Connection:**  
     - Uses the `Connector` to connect to the remote peer.
     - Sends the directory receive signal and waits for confirmation using `_get_confirmation()`.
  3. **Transfer Execution:**  
     - Instantiates a `DirSender` with the remote peer, transfer ID, directory path, and a status mixin.
     - Sends directory files asynchronously while periodically updating transfer progress via the webpage interface.
  4. **Completion:**  
     - Closes the status mixin and logs the successful completion of the transfer.

### `_get_confirmation(connection)`

- **Purpose:**  
  Awaits a one-byte confirmation from the remote peer before proceeding with a directory transfer.
- **Behavior:**
  - Waits for a confirmation byte (`b'\x01'` expected).
  - If a rejection (`b'\x00'`) or timeout occurs, logs the event and raises an exception (e.g., `TransferRejected`).

### `pause_transfer(peer_id, transfer_id)`

- **Purpose:**  
  Pauses an ongoing transfer.
- **Mechanism:**  
  - Retrieves the transfer handle from `TransfersBookKeeper`.
  - Invokes the `pause()` method on the transfer handle.
  - Moves the transfer to the "continued" list in the bookkeeper for later resumption.

### `DirConnectionHandler()`

- **Purpose:**  
  Provides an asynchronous connection handler for incoming directory transfers.
- **Process:**
  1. **Extract Transfer Information:**  
     - Retrieves the transfer ID and directory name from the handshake data.
     - Generates a unique directory path by renaming (with an increment) based on the download path.
  2. **Setup Receiver:**  
     - Creates a `DirReceiver` instance with the remote peer, transfer ID, target directory path, and a status iterator.
     - Registers the receiver in the `TransfersBookKeeper`.
  3. **Transfer Execution:**  
     - Sends an initial confirmation (`b'\x01'`) to signal readiness to receive.
     - Receives the directory files asynchronously and updates the UI periodically.
  4. **Completion and Cleanup:**  
     - Logs the successful receipt of the directory.
     - Marks the transfer as completed in the bookkeeper.
  5. **Error Handling:**  
     - Catches exceptions, prints a stack trace in debug mode, and logs any errors encountered during the transfer.

[back](/src_docs/managers)
