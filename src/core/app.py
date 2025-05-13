import asyncio
import functools
import inspect
from types import FunctionType
from typing import Callable

from src.avails import PeerDict, RemotePeer
from src.avails.mixins import AggregatingAsyncExitStack


class _NoSetter:
    __slots__ = ()

    def __setattr__(self, item, value):
        raise NotImplementedError("not allowed to set")


class _GlobalGossip(_NoSetter):
    __slots__ = ()
    dispatcher = None
    transport = None
    gossiper = None


class _Requests(_NoSetter):
    __slots__ = ()
    dispatcher = None
    transport = None


class _Connections(_NoSetter):
    __slots__ = ()
    dispatcher = None


class _Messages(_NoSetter):
    __slots__ = ()
    dispatcher = None


class _Discovery(_NoSetter):
    __slots__ = ()
    dispatcher = None
    transport = None


class _RemotePeerDesc:
    """Sets both this_peer_id and this_remote_peer of App class"""
    __slots__ = "name", "value"

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        return self.value

    def __set__(self, instance, value):
        assert isinstance(value, RemotePeer), "RemotePeer instance expected"
        self.value = value
        setattr(instance, 'this_peer_id', value.peer_id)


class _ClassLevelDesc(type):
    def __setattr__(cls, name, value):
        attr = cls.__dict__.get(name)
        if attr is not None and hasattr(attr, '__set__'):
            attr.__set__(cls, value)
        else:
            super().__setattr__(name, value)


class App(_NoSetter, metaclass=_ClassLevelDesc):
    gossip = _GlobalGossip
    requests = _Requests
    discovery = _Discovery
    connections = _Connections
    messages = _Messages

    exit_stack = AggregatingAsyncExitStack()
    # exit_stack = AsyncExitStack()
    this_ip = None
    this_remote_peer = _RemotePeerDesc()
    this_peer_id = None
    kad_server = None
    in_network = asyncio.Event()
    finalizing = asyncio.Event()
    peer_list = PeerDict()
    current_config = None
    current_profile = None
    state_manager_handle = None
    interfaces = None
    __instance = None

    @classmethod
    def addr_tuple(cls, ip, port):
        return cls.this_ip.addr_tuple(port=port, ip=ip)

    @classmethod
    def read_only(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)  # Create an instance
            cls.__instance.__init__()
            return cls.__instance
        return cls.__instance

    def __new__(cls, *args, **kwargs):
        raise TypeError("use App.read_only to create instances")

    def __init__(self):
        # make read only
        self.__dict__["gossip"] = self.gossip()
        self.__dict__["requests"] = self.requests()
        self.__dict__["discovery"] = self.discovery()
        self.__dict__["connections"] = self.connections()
        self.__dict__["messages"] = self.messages()


AppType = type[App]
# AppType = TypeVar('AppType', App, None, covariant=True)

ReadOnlyAppType = App


def get_app_context():
    return App.read_only()


def provide_app_ctx(func: FunctionType | Callable):
    """
    Decorator that provides read only application context object with *kw* parameter ``app_ctx``

    If wrapped ``func`` does not take *kw* parameter with name ``app_ctx`` or if ``app_ctx`` is explicitly specified
    in *kw* args passed into ``func`` then it does not get wrapped

    Args:
        func: function to wrap

    """

    signature = inspect.signature(func)
    ok = "app_ctx" in signature.parameters and (
          signature.parameters["app_ctx"].kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    )
    app_ctx = get_app_context()

    if ok:
        @functools.wraps(func)
        def _func(*args, **kwargs):
            if 'app_ctx' not in kwargs:
                return func(*args, app_ctx=app_ctx, **kwargs)
            else:
                return func(*args, **kwargs)
    else:
        _func = func

    if inspect.iscoroutinefunction(func):
        # functools does not preserve coroutine-ness
        # Patch: set coroutine flag (0x80) on code object
        COROUTINE_FLAG = 0x80
        _func.__code__ = _func.__code__.replace(co_flags=(_func.__code__.co_flags | COROUTINE_FLAG))
        # this preserves the function as coroutine

    return _func
