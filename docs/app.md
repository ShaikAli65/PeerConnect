# Application Startup Sequence

## Initialization
- Sets necessary system paths. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/startup/README.md)
- Configures logging mechanisms. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/logging/README.md)
- Reads configuration files and loads user profiles. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/startup/README.md)

## System Architecture
PeerConnect follows an IPC-style design for seamless integration with the User Interface (React.js).
[more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)

## UI Server Initialization
- A WebSocket server endpoint and an HTTP endpoint are initialized upon application startup. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/conduit/README.md)
- The application automatically opens `localhost:port` in the `PeerConnect/webpage` directory using a simple `webbrowser.open` call.
- The user's preferred browser communicates with the HTTP server, while JavaScript within the webpage interacts with the WebSocket endpoint.

## User Interaction Workflow
1. Retrieves user profile preferences.
2. Validates and selects the appropriate network interface.
3. Establishes a reliable communication endpoint for direct peer-to-peer interactions. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)
4. Initializes the messaging interface. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)
5. Starts the request-handling endpoint for managing network requests. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)
6. Managers [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/managers/README.md)

## Finalizing
* **User Requested**:
  1. Command from UI arrives to websocket endpoint.
  2. Application sets a finalizing flag that commands application services to stop their tasks. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)
  3. Event Loop Finalizes. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/core/README.md)

* **SIGINT or SIGTERM** :
  1. cpython runs a signal handler registered by asyncio's runner
  2. Application callback runs a routine that sets finalizing flag. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/finalize/README.md)
  3. Application services smooth stop their functioning. [more](https://github.com/ShaikAli65/PeerConnect/blob/dev/docs/finalize/README.md)
