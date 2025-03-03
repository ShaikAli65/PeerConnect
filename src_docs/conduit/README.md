# Conduit Module Documentation

***Def**: a natural or artificial channel through which something is conveyed*

Interfacing/Interaction with web based UI [more](/src_docs/ui)

**Pagehandle Module**: [src.conduit.pagehandle](/src/conduit/pagehandle.py)

- WebSocket & Server Management

## Dispatchers

### `FrontEndWebSocketDispatcher`

```python
class FrontEndWebSocketDispatcher(BaseDispatcher)
```

Manages *(wraps)* a WebSocket connection with message buffering

**Features:**

- Automatic reconnection handling
- Message queuing (max 1000 messages) [const.MAX_FRONTEND_MESSAGE_BUFFER_LEN](/src/avails/constants.py)
- Connection health monitoring

**Note**: if max buffer length is reached older messages are pruned and warning statements are logged  

#### Public Methods Defined Here

```py
    async def submit(self, data: DataWeaver):
```

- Attempts to send DataWeaver object, if webpage not connected (through transport attributed), buffers it

```py
    async def update_transport(self, transport):
```

- Update internal reference to transport, this also updates the connection status to active

### `FrontEndDispatcher`

```python
class FrontEndDispatcher(QueueMixIn, AExitStackMixIn, BaseDispatcher)
    """Dispatcher that SENDS packets to frontend"""
```

- Singleton class
- Main dispatch hub for frontend communication
- Uses [websocket dispatchers](#frontendwebsocketdispatcher) to send messages based on msg codes [more](/src_docs/avails/wire.md#dataweaver)
- Owns life time of dispatchers that are registered, enters context managers of those

**Key Methods:**

- `add_dispatcher()`: Registers new protocol handlers
- `submit()`: Routes messages to appropriate handlers
  - **Note**: this function is not called explicity, [QueueMixIn](/src_docs/avails/mixins.md#queuemixin) deals with that

### `MessageFromFrontEndDispatcher`

```py
@singleton_mixin
class MessageFromFrontEndDispatcher(QueueMixIn, BaseDispatcher):
```

As the name clearly mentions, this class is responsible for dealing with incoming messages from front-end
Does not contain any i/o, just maintains a registry, see [handle_client](#handle_client) for that

## Core Functions

### handle_client

```python
async def handle_client(web_socket: WebSocketServerProtocol)
```

Main WebSocket connection handler

- Validates connections
- Processes incoming messages from UI websocket
- parses data to [DataWeaver](/src_docs/avails/wire.md#dataweaver)
- submit that into [MessageFromFrontEndDispatcher](#messagefromfrontenddispatcher)

### start_websocket_server

```python
async def start_websocket_server()
```

Starts WebSocket server on port [const.PORT_PAGE](/src_docs/avails/constants.md)

- Uses `websockets` library
- Handles UI connections

### run_page_server

```python
@asynccontextmanager
async def run_page_server(host="localhost"):
```

- context manager that runs python's `http.server` in a subprocess and finalizes when application quits
- serves [webpage](/webpage/index.html)

### initiate_page_handle

```py
async def initiate_page_handle(exit_stack):
```

- Initiates all the dispatchers, enters their contexts into module level [exit_stack](#exit_stack) and enters exit_stack's context into app level `exit_stack`
- Starts websocket server
- Starts page serving server

### exit_stack

```py
_exit_stack = AsyncExitStack()
```

PageHandle maintains it's own [exit_stack](<https://www.google.com/search?q=asyncexitstack+site:python.org>) to maintain [dispatchers](#dispatchers) life time

## Dispatcher registered with [MessageFromFrontEndDispatcher](#messagefromfrontenddispatcher)

### FrontEndSignalDispatcher

```python
class FrontEndSignalDispatcher(BaseDispatcher)
```

Handles system-level signaling

**Registered Handlers:**

- Peer connections
- Profile synchronization
- User searches
- Peer list management
- sync_users ([WIP](/src_docs/README.md#legend))

---

### `FrontEndDataDispatcher`

```python
class FrontEndDataDispatcher(BaseDispatcher)
```

Handles data operations between backend and frontend

- Dir Transfer
- Send File
- Send Text
- Send Files To Multiple Peers
