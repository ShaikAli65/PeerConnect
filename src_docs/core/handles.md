# Deprecated Task Handles Module (core/handles.py)

⚠️ **Deprecation Notice**: This module is no longer in use and maintained for legacy reference only

## Overview

Provided abstract base classes for task management in the legacy process system:

- Task execution templates
- Proxy pattern for cross-process operations
- Basic task lifecycle management

## Key Components

### 1. Base Classes

```python
class TaskHandle(ABC):
    """Abstract base class defining task lifecycle:
    - start()
    - cancel() 
    - status()
    """

class TaskHandleProxy(BaseProxy):
    """Proxy object for cross-process method exposure"""
```

### 2. Implementations

```python
class FileTaskHandle(TaskHandle):
    """Placeholder for file operations (never fully implemented)"""
```

## Architecture Notes

1. **Proxy Pattern**
   - Enabled cross-process method calls
   - Exposed specific methods via `_exposed_` list
   - Used `multiprocessing.managers.BaseProxy`

2. **Intended Use Case**

    ```python
    # Original intended usage flow
    handle = FileTaskHandle()
    proxy = manager.FileTaskHandle(handle)
    result = proxy.start()
    ```

3. **Deprecation Factors**
   - Tight coupling with legacy process manager
   - Unfinished implementations
   - Complexity in error handling

> [back](/src_docs/core)
