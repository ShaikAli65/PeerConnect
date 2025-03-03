# Documentation for `core.gossip` Module

The `core.gossip` module implements the gossip protocol used in PeerConnect to disseminate messages across peers using a rumor-mongering strategy. It integrates with the transport layer, peer management, and event handling to probabilistically propagate messages throughout the network.

---

## Table of Contents

- [Overview](#overview)
- [Module Dependencies](#module-dependencies)
- [Components](#components)
  - [GlobalGossipRumorMessageList](#globalgossiprumormessagelist)
  - [GlobalRumorMonger](#globalrumormonger)
  - [GlobalGossipMessageHandler](#globalgossipmessagehandler)
  - [GossipSearchReqHandler](#gossipsearchreqhandler)
  - [GossipSearchReplyHandler](#gossipsearchreplyhandler)
  - [GossipDispatcher](#gossipdispatcher)
  - [initiate_gossip](#initiate_gossip)
- [Gossip Communication Flow](#gossip-communication-flow)
- [Conclusion](#conclusion)

---

## Overview

The `core/gossip` module provides the core functionality for gossip-based communication in PeerConnect. It uses a rumor-mongering approach to ensure that new messages and search requests are disseminated efficiently among peers. The design emphasizes a probabilistic strategy to reduce network overhead while ensuring eventual message delivery.

---

## Module Dependencies

The module relies on several other components in the application:

- **`src.avails`**: Supplies base classes for dispatchers (`BaseDispatcher`), mixins (`QueueMixIn`), and message/event types (e.g., `GossipMessage`, `GossipEvent`).
- **`src.core.peers`**: Provides helper functions like `get_search_handler` to manage search-related events.
- **`src.core.public`**: Manages global state through the `Dock` object and provides utility functions such as `get_gossip`.
- **`src.transfers`**: Contains definitions for gossip constants (`GOSSIP`), the gossip transport layer (`GossipTransport`), and the underlying rumor-mongering protocol (`RumorMongerProtocol`, `SimpleRumorMessageList`).

---

## Components

### GlobalGossipRumorMessageList

**Purpose:**  
Extends the basic `SimpleRumorMessageList` to support global gossip functionality.

**Key Feature:**  
Overrides the `_get_list_of_peers` method to return a dynamic set of peer identifiers from the global `Dock.peer_list`. This allows the rumor mongering mechanism to sample the current peers available for message propagation.

**Code:**

```python
class GlobalGossipRumorMessageList(SimpleRumorMessageList):  # inspired from java
    @staticmethod
    def _get_list_of_peers():
        return set(Dock.peer_list.keys())
```

---

### GlobalRumorMonger

**Purpose:**  
Implements a global instance of the rumor-mongering protocol using the specialized message list.

**Key Feature:**  
Initializes the rumor-mongering mechanism by combining a `GossipTransport` with the `GlobalGossipRumorMessageList`.

**Code:**

```python
class GlobalRumorMonger(RumorMongerProtocol):
    def __init__(self, transport):
        super().__init__(transport, GlobalGossipRumorMessageList)
```

---

### GlobalGossipMessageHandler

**Purpose:**  
Creates an asynchronous handler for processing incoming gossip messages.

**Key Feature:**  
Logs the arrival of a new gossip message and delegates its processing to the global gossip instance via the `message_arrived` method.

**Code:**

```python
def GlobalGossipMessageHandler(global_gossiper):
    async def handle(event: GossipEvent):
        print("[GOSSIP] new message arrived", event.message, "from", event.from_addr)
        return global_gossiper.message_arrived(*event)
    return handle
```

---

### GossipSearchReqHandler

**Purpose:**  
Handles incoming gossip search requests by determining whether the search query relates to the local peer and, if so, sending an appropriate reply.

**Workflow:**

- **Message Check:**  
  If the gossiper has not seen the message before, the handler calls the global gossip message handler.
- **Search Delegation:**  
  Uses the `searcher` object to process the request; if a reply is generated, it sends the reply back via the `GossipTransport`.

**Code:**

```python
def GossipSearchReqHandler(searcher, transport, gossiper, gossip_handler):
    """
    Working:
        * A GossipEvent is passed when a peer issues a search request.
        * If the message is unseen, it is first gossiped.
        * The searcher then determines if the search query is relevant and, if so, generates a reply.
        * The reply is sent back to the originating peer using the transport.
    """
    async def handle(event: GossipEvent):
        if not gossiper.is_seen(event.message):
            await gossip_handler(event)
        if reply := searcher.request_arrived(*event):
            return transport.sendto(reply, event.from_addr)
    return handle
```

---

### GossipSearchReplyHandler

**Purpose:**  
Processes replies to gossip search requests.

**Key Feature:**  
Logs the receipt of a search reply and delegates processing to the `reply_arrived` method on the `searcher`.

**Code:**

```python
def GossipSearchReplyHandler(searcher):
    async def handle(event: GossipEvent):
        print("[GOSSIP][SEARCH] reply received:", event.message, "for", event.from_addr)
        return searcher.reply_arrived(*event)
    return handle
```

---

### GossipDispatcher

**Purpose:**  
Acts as the central hub for dispatching gossip events to their appropriate handlers.

**Key Features:**

- Inherits from both `QueueMixIn` and `BaseDispatcher` to enable asynchronous queuing and event handling.
- Implements the `submit` method which:
  - Converts the incoming event’s request into a `GossipMessage`.
  - Retrieves the corresponding handler from its registry using the message header.
  - Wraps the message and sender’s address into a `GossipEvent` and calls the handler.

**Code:**

```python
class GossipDispatcher(QueueMixIn, BaseDispatcher):
    async def submit(self, event):
        gossip_message = GossipMessage(event.request)
        handler = self.registry[gossip_message.header]
        g_event = GossipEvent(gossip_message, event.from_addr)
        await handler(g_event)
```

---

### initiate_gossip

**Purpose:**  
Bootstraps the gossip subsystem, initializing the transport layer, global gossip instance, and event handlers.

**Workflow:**

1. **Transport Initialization:**  
   Creates a `GossipTransport` from the provided data transport.
2. **Global Gossip Setup:**  
   Instantiates the global gossip instance (`Dock.global_gossip`) using `GlobalRumorMonger`.
3. **Dispatcher Configuration:**  
   - Creates a `GossipDispatcher`.
   - Retrieves a search handler via `get_search_handler()`.
   - Configures handlers for incoming gossip messages, search requests, and search replies.
4. **Handler Registration:**  
   Registers the handlers with the dispatcher using keys defined in the `GOSSIP` constants.
5. **Integration:**  
   Links the gossip dispatcher to the overall request dispatcher under the `REQUESTS_HEADERS.GOSSIP` key.
6. **Finalization:**  
   Logs that the node has joined the gossip network and returns the configured dispatcher.

**Code:**

```python
def initiate_gossip(data_transport, req_dispatcher):
    gossip_transport = GossipTransport(data_transport)
    Dock.global_gossip = GlobalRumorMonger(gossip_transport)

    g_dispatcher = GossipDispatcher()

    gossip_searcher = get_search_handler()

    gossip_message_handler = GlobalGossipMessageHandler(Dock.global_gossip)
    req_handler = GossipSearchReqHandler(
        gossip_searcher,
        gossip_transport,
        Dock.global_gossip,
        gossip_message_handler
    )
    reply_handler = GossipSearchReplyHandler(gossip_searcher)
    g_dispatcher.register_handler(GOSSIP.MESSAGE, gossip_message_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REQ, req_handler)
    g_dispatcher.register_handler(GOSSIP.SEARCH_REPLY, reply_handler)

    req_dispatcher.register_handler(REQUESTS_HEADERS.GOSSIP, g_dispatcher)
    print("joined gossip network", get_gossip())
    return g_dispatcher
```

---

## Gossip Communication Flow

1. **Message Creation and Dissemination:**  
   When a peer creates a new gossip message, the global gossip instance (a `GlobalRumorMonger`) uses the `GlobalGossipRumorMessageList` to decide which peers to forward the message to. The `GlobalGossipMessageHandler` logs the message and processes it via `message_arrived`.

2. **Search Request Handling:**  
   A gossip search request is handled by the function returned from `GossipSearchReqHandler`. This function:
   - Checks if the message is already seen.
   - If not, it gossips the new message.
   - Uses the `searcher` helper to determine whether the request is relevant, sending a reply if appropriate.

3. **Search Reply Processing:**  
   Replies to search requests are processed by the handler from `GossipSearchReplyHandler`, which logs the receipt and forwards the reply for further processing.

4. **Event Dispatching:**  
   The `GossipDispatcher` routes incoming events to the correct handlers based on the message header, ensuring that each type of gossip event is handled appropriately.

5. **Subsystem Initialization:**  
   The `initiate_gossip` function integrates all components—transport, global gossip instance, dispatcher, and event handlers—to establish the node’s participation in the gossip network.

---

## Conclusion

The `core/gossip` module provides a comprehensive, modular implementation of a gossip protocol in PeerConnect. Its design leverages global state management (via `Dock`), specialized message lists for rumor mongering, and asynchronous event dispatching to ensure efficient and scalable message propagation. Developers can extend or modify to fine-tune the gossip behavior, adjust probabilistic parameters, or integrate additional event types as needed.

> [back](/src_docs/core)
