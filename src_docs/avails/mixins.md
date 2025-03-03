# Mixin Classes

Mixin classes and decorators that extend the functionality of other classes in the PeerConnect system.

## Key components

## ReplyRegistryMixIn

- **Purpose:**  
  Provides functionality for registering replies to messages.  
- **Key Methods:**  
  - `msg_arrived(message)`: Checks if a reply is expected for a message and, if so, resolves the corresponding future.
  - `register_reply(reply_id)`: Registers a future that will be completed when the expected message arrives.
  - `id_factory`: A property that generates unique identifiers.

## QueueMixIn

- **Purpose:**  
  Enables a class to manage tasks using an internal `asyncio.TaskGroup`.  
- **Features:**  
  - Overrides the `__call__` method to spawn tasks from the `submit` method.
  - Provides asynchronous context management to properly handle task lifetimes.

## AExitStackMixIn & AggregatingAsyncExitStack

- **Purpose:**  
  Facilitates asynchronous cleanup and context management by aggregating exceptions during exit.
- **Features:**  
  - Provides an internal asynchronous exit stack.
  - Aggregates multiple exceptions into an `ExceptionGroup` if needed.

## AsyncMultiContextManagerMixIn

- **Purpose:**  
  Helps in managing multiple async context managers across inheritance hierarchies.

- **Features:**  
  - Ensures proper entry and exit of contexts.
  - Aggregates exceptions from different parent classes via ExceptionGroup.

- Complex context management

## Utility Decorators

- **singleton_mixin:**  
  A decorator to enforce the singleton pattern on a class.
- **awaitable:**  
  A decorator that allows a function to be called in both synchronous and asynchronous contexts, depending on how it is invoked.

## Purpose

Provides reusable behavioral components through multiple inheritance.

[back](/src_docs/avails)
