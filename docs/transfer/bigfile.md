# Big File Transfer Protocol Documentation

This document provides a comprehensive overview of the protocol used for transferring large files (over 2GB) by leveraging multiple network streams to optimize bandwidth utilization.

## Table of Contents
- [Introduction](#introduction)
- [Challenges in Large File Transfers](#challenges-in-large-file-transfers)
- [System Design Overview](#system-design-overview)
  - [Sender’s Perspective](#senders-perspective)
  - [Receiver’s Perspective](#receivers-perspective)
- [Merging Strategies](#merging-strategies)
- [Conclusion](#conclusion)
- [References](#references)

## Introduction

Transferring very large files over the network has traditionally been hindered by limitations such as aggressive TCP flow control and the use of single-stream connections. These factors contribute to suboptimal bandwidth usage and significantly longer transfer times.

## Challenges in Large File Transfers

- **Aggressive TCP Flow Control:** The inherent limitations of TCP can restrict throughput, particularly for long-distance or high-latency connections.
- **Single-Stream Bottleneck:** Conventional file transfers rely on a single connection, which often fails to fully utilize the available network bandwidth.

Comparative tests revealed that while local network transfers in PeerConnect exhibited modest speeds, applications like Telegram and Chrome, which implement multi-stream techniques, achieved significantly higher throughput.

## System Design Overview

To address these issues, the protocol utilizes a multi-stream approach inspired by the strategies employed in modern messaging and browser clients.

### Sender’s Perspective

#### Setup Phase
1. **API Initialization:**  
   - The transfer is initiated at the **Manager API** level, which coordinates multiple connection requests via the [Connector API](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/connector.md).
2. **Negotiation:**  
   - A big file transfer session is negotiated between peers.
3. **Handle Creation:**  
   - BigFile handles are created at both the sender and receiver ends, with synchronized identifiers.

#### Transfer Phase
1. **Chunking the File:**  
   - The large file is segmented into *big chunks*. Each chunk is assigned a unique ID.
2. **Dynamic Connection Management:**  
   - The Manager API dynamically adds connections to facilitate parallel data transfer.
3. **Initiating Transfer:**  
   - Transfer commences as soon as the first connection is established.
   **Detail**: When connection arrives, a task is spwaned and that task requests a big chunk inside BigFile handle, this happens every time a big chunk is sent
4. **Data Framing:**  
   - Each big chunk is further divided into smaller sub-chunks and transmitted in frames. The frame format is as follows:
     ```
     [big chunk ID] [chunk] [chunk] ... [big chunk]
     ```
5. **Resilience:**  
   - The transfer handle preserves state to manage any network disruptions.
6. **UI Updates:**  
   - Incremental updates are provided to the user interface using Python’s generator API.

#### Finalization Phase
1. **Completion Check:**  
   - After all big chunks are transferred, resources are returned to the Manager API.
2. **Resource Release:**  
   - The Manager API then releases the resources back to the [Connector API](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/connector.md).

### Receiver’s Perspective

1. **Negotiation:**  
   - The receiver initiates an initial negotiation phase to set up the file transfer.
2. **Connection Aggregation:**  
   - Multiple connections are established to receive the incoming big chunks asynchronously.
3. **File Handling:**  
   - For every big chunk received, a new temporary file is created using the following naming convention:
     ```
     [filename].[big chunk id].[big chunk id].unconfirmed
     ```

## Merging Strategies

Efficient reassembly of the file from its big chunks is crucial. Two merging strategies are considered:

### Eager Merging
- **Incremental Merging:**  
  - As soon as adjacent big chunks (with consecutive IDs) are received, they are merged immediately.
- **File Renaming:**  
  - For example, if the received chunks are:
    - ` [filename].1.1 `
    - ` [filename].2.2 `
    - ` [filename].3.3 `
  - After merging, the resulting file segments are renamed to reflect the merged range:
    - Merged chunk: ` [filename].1.2 `, then updated to ` [filename].1.3 `.
- **Flexibility:**  
  - Chunks can be merged in any order as long as they are consecutive.

### Lazy Merging
- **Deferred Merging:**  
  - All big chunks are first fully received and stored.
- **Post-Transfer Combination:**  
  - The merging process is executed once the entire file has been received.
- **Current Implementation:**  
  - The system presently employs the *lazy merging* strategy.

## Conclusion

The multi-stream approach outlined in this documentation significantly improves the transfer speed of large files by mitigating the limitations of TCP flow control and single-stream transfers. Through dynamic connection management and robust merging strategies, the protocol efficiently utilizes available bandwidth, ensuring faster and more reliable file transfers.

## References

- [Manager API Documentation](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/managers/README.md)
- [Connector API Documentation](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/connector.md)
