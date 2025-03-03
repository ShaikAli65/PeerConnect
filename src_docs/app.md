# App Sequence

## Startup Sequence

### Initialization

- Sets necessary system paths. [more](/src_docs/startup/README.md)
- Configures logging mechanisms. [more](/src_docs/logging/README.md)
- Reads configuration files and loads user profiles. [more](/src_docs/startup/README.md)

### UI Server Initialization

- A WebSocket server endpoint and an HTTP endpoint are initialized upon application
  startup. [more](/src_docs/conduit/README.md)
- The application automatically opens `localhost:port` in the `PeerConnect/webpage` directory using a simple
  `webbrowser.open` call.
- The user's preferred browser communicates with the HTTP server, while JavaScript within the webpage interacts with the
  WebSocket endpoint.

- UI [docs](/src_docs/ui)

### User Interaction Workflow

1. Retrieves user profile preferences.
2. Validates and selects the appropriate network interface.
3. Establishes a reliable communication endpoint for direct peer-to-peer interactions. [more](/src_docs/core/README.md)
4. Initializes the messaging interface. [more](/src_docs/core/README.md)
5. Starts the request-handling endpoint for managing network requests. [more](/src_docs/core/README.md)
6. Managers [more](/src_docs/managers/README.md)

## Application Finalizing Sequence

- **User Requested**:
  1. Command from UI arrives to websocket endpoint.
  2. Application sets a finalizing flag that commands application services to stop their
     tasks. [more](/src_docs/core/README.md)
  3. Event Loop Finalizes. [more](/src_docs/core/README.md)

- **SIGINT or SIGTERM** :
  1. cpython runs a signal handler registered by asyncio's runner
  2. Application callback runs a routine that sets finalizing flag. [more](/src_docs/finalize/README.md)
  3. Application services smooth stop their functioning. [more](/src_docs/finalize/README.md)

---

> [back](/src_docs)
