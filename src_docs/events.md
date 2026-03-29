# Events

## Types of Events

* Network Events [link](/src/net/events.py)
* Application Events [link](/src/core/app_events.py)
* UI Based Events [link](/src/conduit/ui_events.py)

## Event Dispatch Mechanism
Two types of event dispatch mechanism are used in this application.

## [EventBus](/src/core/app_events.py)

You can subscribe to `AppEventBase` events.
This provides a simple way to listen to events in the application.
You register for a specific event and a queue will be created or a queue passed as a parameter is notified when that
event is produced.

```python
import asyncio
from src.core.app_events import AppEventBase, PeerStatusUpdate

async def peer_status_worker(bus):
    q = bus.subscribe(PeerStatusUpdate)
    while True:
        event = await q.get()
        print("got event:", event)

bus = AppEventBase()

asyncio.create_task(peer_status_worker(bus))

```

## Dispatchers [ex](/src/core/requests.py)

This method is used to dispatch events. This is a callback based mechanism.
Preferred when you want to run long running tasks or heavy functions when something happens.
A task is created in a taskgroup and will be owned by the dispatcher.
You register for a specific event and the event handler will be called when the event is dispatched.

```python

```

> Note:
> Use channel based communication when you want to do simple things.

Avoid doing this:

```python
import asyncio
from src.core.app_events import AppEventBase, PeerStatusUpdate

async def peer_status_worker(bus):
    async def callback(ev):...
    q = bus.subscribe(PeerStatusUpdate)
    while True:
        event = await q.get()
        asyncio.create_task(callback(event))  # some callback again

bus = AppEventBase()

asyncio.create_task(peer_status_worker(bus))
```

> Prefer dispatchers in this case as they schedule callbacks in a taskgroup internally
