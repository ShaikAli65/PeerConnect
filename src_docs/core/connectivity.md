# Connectivity Check Module Documentation

Connectivity checking for remote peers. It verifies whether a peer is reachable using a two-step process: first via a UDP-based "ping" (using the requests endpoint) and then-if necessary-by attempting a TCP connection. The module is designed to track and manage these connectivity checks using a singleton class, ensuring that recent checks are reused and that pending checks are properly canceled during shutdown.

---

## Overview

- **Purpose:**  
  To perform connectivity checks on remote peers to determine if they are reachable. The module combines UDP "ping" messages with a fallback TCP connection attempt, ensuring robust detection of connectivity issues.

- **Key Components:**  
  - **ConnectivityCheckState (Enum):**  
    Defines the various stages of a connectivity check.
  - **CheckRequest:**  
    Encapsulates the details of a connectivity check request for a specific peer.
  - **Connectivity (Singleton Class):**  
    Manages the scheduling and execution of connectivity checks and tracks the most recent check per peer.
  - **Helper Functions:**  
    - `new_check(peer)`: Initiates a new connectivity check or returns a recent check if available.
    - `initiate(exit_stack)`: Enters the connectivity context, ensuring the connectivity watcher is active within the application’s lifecycle.

---

## Detailed Components

### ConnectivityCheckState (Enum)

Defines the following states for a connectivity check:

- **INITIATED:**  
  Check request has been initiated.
- **REQ_CHECK:**  
  UDP-based request check is in progress.
- **CON_CHECK:**  
  TCP connection check is underway (fallback for poor UDP performance or system-specific issues).
- **COMPLETED:**  
  The connectivity check is finished.

---

### CheckRequest Class

- **Attributes:**
  - `time_stamp`: The time when the check was initiated.
  - `peer`: The remote peer for which the check is performed.
  - `serious`: A flag indicating the seriousness of the check.
  - `status`: The current status of the check (an instance of `ConnectivityCheckState`).

- **Purpose:**  
  To encapsulate all necessary data about a connectivity check request so that its status and timing can be managed effectively.

---

### Connectivity Class

- **Design:**  
  Implemented as a singleton (using a mixin) and extends `QueueMixIn` for queuing functionality.

- **Responsibilities:**
  - **Tracking Checks:**  
    Maintains a mapping (`last_checked`) from each peer to a tuple containing the last `CheckRequest` and its associated future.
  - **Submitting New Checks:**  
    The `submit()` method registers a new connectivity check request and schedules its execution via the private `_new_check()` function.
  - **Reusing Recent Checks:**  
    The `check_for_recent()` method returns an existing future if a check for the same peer has been performed within a specified time window (`const.PING_TIME_CHECK_WINDOW`).
  - **Resource Management:**  
    Implements asynchronous context management to ensure that all pending check futures are canceled on exit.

- **Key Methods:**
  - **`async def submit(request: CheckRequest)`**  
    Schedules a new connectivity check and returns the result (a boolean indicating success).
  - **`def check_for_recent(request)`**  
    Checks if a recent connectivity check exists for the peer and, if so, returns its future.
  - **`@staticmethod async def _new_check(request)`**  
    Performs the actual connectivity check:
    - Sends a UDP ping via `send_msg_to_requests_endpoint` and waits for a reply with a timeout.
    - On timeout, attempts a TCP connection using `connect.connect_to_peer` and sends a simple packet. [[RIP](/src_docs/README.md#legend), that integrates *Connector*]
    - Returns `True` if the check succeeds; otherwise, returns `False`.

---

### Helper Functions

- **`new_check(peer) -> tuple[CheckRequest, asyncio.Future[bool]]`**  
  - **Purpose:**  
    Initiates a connectivity check for the given peer.
  - **Behavior:**  
    Reuses a recent check if one exists; otherwise, submits a new check via the `Connectivity` singleton.
  
- **`async def initiate(exit_stack)`**  
  - **Purpose:**  
    Integrates the `Connectivity` instance into the application's asynchronous exit stack.
  - **Behavior:**  
    Ensures that connectivity checking is active and properly managed during application shutdown.

---

## Summary

The Connectivity Check Module provides a robust mechanism to determine the reachability of remote peers. By combining both UDP-based pings and fallback TCP checks, it accommodates various network conditions. The module also efficiently manages check requests—preventing redundant checks through caching recent results and ensuring proper cleanup of pending tasks.

> [back](/src_docs/core)
