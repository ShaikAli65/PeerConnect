# Logging System Architecture

## Overview

Simple logging system using Python's standard `logging` module. The system is configured
through [log_config.json](/config/log_config.json) and features:

- Asynchronous queue-based logging
- Rotating file handlers
- Module-specific log configurations
- Non-blocking I/O operations
- Discovery subsystem isolation

## Configuration Structure

### 1. Formatters

| Name       | Format                                                                    | Use Case       |
|------------|---------------------------------------------------------------------------|----------------|
| `default`  | `%(levelname)-8s %(name)-30s %(funcName)-25s - %(message)s`               | Console output |
| `detailed` | `%(asctime)s - %(levelname)-8s %(name)-30s %(funcName)-25s - %(message)s` | File logging   |

### 2. Handlers

| Handler Name            | Type                     | File            | Rotation          |
|-------------------------|--------------------------|-----------------|-------------------|
| `rfile_handler`         | RotatingFileHandler      | `logs.log`      | 2.5MB × 3 backups |
| `discovery_sub_handler` | RotatingFileHandler      | `discovery.log` | 100KB × 3 backups |
| `console`               | StreamHandler            | -               | -                 |
| `queue_handler`         | QueueHandler (Composite) | -               | -                 |

### 3. Logger Hierarchy

| Logger Name         | Level | Propagate | Handlers            |
|---------------------|-------|-----------|---------------------|
| Root (`""`)         | DEBUG | Yes       | `queue_handler`     |
| `websockets`        | INFO  | Yes       | Inherited           |
| `kademlia`          | INFO  | Yes       | Inherited           |
| `src.core.discover` | DEBUG | No        | `discovery_handler` |

## Key Architectural Features

### 1. Queue-Based Logging

```python
log_queue = queue.SimpleQueue()
queue_listener.start()
```

- **Non-blocking Architecture**: Decouples log emission from write operations
- **Enhanced Performance**: Critical for maintaining event loop efficiency
- **Composite Handlers**: QueueHandler manages multiple output destinations

### 2. Discovery Subsystem Isolation

- Dedicated rotating file handler (`discovery.log`)
- Separate queue handler chain
- Non-propagating logger configuration

### 3. Runtime Configuration

```python
log_config["handlers"][handler]["filename"] = str(Path(const.PATH_LOG, ...))
```

- Dynamic path resolution for log files
- Environment-specific directory structure
- Graceful shutdown handling

## Initialization Sequence

1. Configuration loading with path resolution
2. Queue listener initialization
3. Handler chain registration
4. Shutdown hook registration

```python
Dock.exit_stack.callback(_log_exit)
```

> **Note:** The logging system integrates with PeerConnect's lifecycle management through `Dock.exit_stack` for graceful
> shutdowns [more](/src_docs/core/public.md).

[back](/src_docs)
