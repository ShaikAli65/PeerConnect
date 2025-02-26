# Directory Transfer Module

This module provides functionality for transferring entire directories between peers. It exports several key components that help manage directory transfers within PeerConnect. In particular, it makes available:

- **DirSender** – (Sender counterpart for directories)  
  *Handles packaging and sending a directory’s contents and structure to a remote peer.*

- **DirReceiver** – (Receiver counterpart for directories)  
  *Extends file-receiving functionality to support reconstructing directory structures on the receiving side. (See also the DirReceiver class in the [receiver](https://github.com/ShaikAli65/PeerConnect/blob/dev/src/transfers/files/directory.py) module)*

- **rename_directory_with_increment** – (Helper Function)  
  *Renames a directory by appending an increment if the target path already exists. This ensures that incoming directory transfers do not overwrite existing data.*

### Overview

The directory module is designed to complement the file transfer system by providing support for hierarchical data. When a directory transfer is initiated (for example, via a user sharing a folder), the module:

- Analyzes the folder structure.
- Packages the file metadata and directory hierarchy.
- Uses the helper function to determine a unique destination name if conflicts arise.
- Integrates with the higher‐level file manager (see usage in the file manager’s DirConnectionHandler [here](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/managers/directory.md)) to initiate the transfer.

### Key Concepts

- **Directory Abstraction:**  
  The module treats a directory as a collection of files and subdirectories. The same core transfer mechanisms are reused, with additional metadata to preserve structure.

- **Conflict Handling:**  
  The `rename_directory_with_increment` function automatically adjusts directory names so that repeated transfers (or transfers to a destination with existing content) do not cause data loss.

### Usage

When a directory transfer is requested, the file manager instantiates a sender or receiver from this module. For instance, the receiver side (DirReceiver) creates a target directory using the unique name provided by `rename_directory_with_increment` and then reconstructs the file hierarchy accordingly.

> **Note:** `DirSender` API mirrors file sender functionality while handling directory-specific data.
