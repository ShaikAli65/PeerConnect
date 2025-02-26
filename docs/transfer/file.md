# File Sender Module

This module implements the logic for sending files from one peer to another. It defines the `Sender` class, which is responsible for reading file data from disk, dividing files into chunks, and transmitting these chunks over the network using an asynchronous workflow.

### Overview

The `Sender` class encapsulates the entire lifecycle of a file transfer. It leverages several mixins to handle common behaviors such as exception handling, pause/resume capability, and cancellation. The sender works with a list of `FileItem` objects—each representing a file to be sent.

### Key Components

- **Initialization (`__init__`):**  
  - Converts the list of file paths into `FileItem` objects.
  - Stores a unique transfer ID and sets up internal state (e.g., current file index, status updater, and communication functions).
  - Prepares the sender for initiating the transfer, including setting the default timeout and linking with the peer’s connection.

- **send_files (Coroutine):**  
  - Transitions the transfer state from *PREPARING* to *SENDING*.
  - Uses the current asynchronous task as the main task and begins sending file chunks.
  - Reads from each file using a thread pool optimized for disk I/O.
  - Continuously sends data chunks by calculating an optimal chunk size (using `calculate_chunk_size`).
  - Updates file seek positions as chunks are successfully transmitted.
  - Handles errors and interruptions through the inherited exception handlers.

### Workflow

1. **Setup Phase:**  
   The sender is instantiated with the target peer and a list of files. File metadata (such as size and path) is prepared.

2. **Transfer Phase:**  
   The `send_files` coroutine initiates the data transfer. It opens each file in binary mode (using asynchronous calls via a thread pool) and reads it in chunks. Each chunk is sent asynchronously using the provided `send_function`.

3. **Progress Reporting:**  
   As chunks are sent, the sender updates the file’s progress (i.e. how many bytes have been transmitted) and yields the current state back to the caller. This allows for real-time progress updates to be relayed to the UI or status manager.

### Integration

The `Sender` module integrates closely with other components in the PeerConnect ecosystem. For example, the file manager coordinates between sender instances and the network layer, ensuring that connections are properly established and maintained during a transfer.

> For detailed code structure and error-handling routines, refer to the Sender class implementation in the [source code](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/transfers/files/sender.py).
---


# File Receiver Module

This module is responsible for receiving file data sent by a remote peer. It defines the `Receiver` class, which coordinates the reception of file chunks, writes these chunks to disk, and manages transfer state and metadata. A specialized subclass, `DirReceiver`, is also defined to handle [directory](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/managers/directory.md) transfers.

### Overview

The file receiver module implements a robust, asynchronous mechanism for file reception. It supports the following functionalities:

- **Receiving Chunks:**  
  Continuously awaits data chunks from the sender and writes them to the appropriate file.

- **File Metadata Management:**  
  Uses metadata (such as file size and target file paths) to correctly map incoming data to the right file. This ensures that multiple files can be sent over a single continuous byte stream.

- **State Management:**  
  The receiver maintains an [internal state machine](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/transfers/__init__.py) to track progress and handle errors.

### Key Components

- **Receiver Class:**  
  - Inherits from several mixins (such as `CommonExceptionHandlersMixIn`, `PauseMixIn`, and `CommonCancelMixIn`) to provide a unified interface for error handling and cancellation.
  - The `recv_files` coroutine is the primary entry point for file reception. It:
    - Waits for connection confirmation.
    - Continuously receives file chunks until the end-of-transfer signal is detected.
    - Calls the helper method `_write_chunk` to write data to the correct file.
  - Uses an asynchronous context manager (`_open_files`) to open all target file descriptors safely before writing.
  - Implements a helper method `_should_proceed` to determine whether to continue receiving data (for instance, checking for a termination signal).

- **DirReceiver Subclass:**  
  - Extends `Receiver` for handling directory transfers.
  - Implements additional logic to receive and reconstruct directory structures. For example, it handles both file and path codes so that directories are created on the receiving side before file data is written.
  - Uses helper functions such as `_recv_parts` to extract directory metadata (like parent paths and file names) from the incoming stream.

### Workflow

1. **Metadata Update:**  
   The receiver begins by obtaining metadata for the files to be received. This metadata (often transmitted as a packed message using umsgpack) includes file sizes and target paths.

2. **Data Reception:**  
   The `recv_files` method enters a loop where it awaits incoming chunks. For each chunk:
   - It aligns the chunk with the corresponding file (in case a chunk spans multiple files).
   - It writes the appropriate slice of data to the file.
   - It updates the file’s seek position and moves to the next file when one is complete.

3. **Completion:**  
   When all files have been received and written to disk, the receiver changes its state to COMPLETED and closes all open file descriptors.

### Integration

The Receiver module is integrated into the broader PeerConnect file transfer framework. It works in tandem with the Sender module and higher-level managers that coordinate transfers. The use of asynchronous generators allows for progress updates to be streamed back to the UI or logging components in real time.

> For more implementation details, see the [source code](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/transfers/files/receiver.py) for the Receiver class.
