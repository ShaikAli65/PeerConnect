from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import ClassVar

from src.avails.useables import camel_to_snake


class UIEventMeta(type):
    registry: dict[str, type["UIEvent"]] = {}
    inbound_registry: dict[str, type["UIInboundEvent"]] = {}
    outbound_registry: dict[str, type["UIOutboundEvent"]] = {}

    def __new__(mcls, name, bases, namespace):
        cls = super().__new__(mcls, name, bases, namespace)

        if namespace.get("__register__", True):
            header = namespace.get("HEADER") or camel_to_snake(name)
            cls.HEADER = header
            mcls.registry[header] = cls

            if any(base.__name__ == "UIInboundEvent" for base in bases) or any(
                    getattr(base, "__is_inbound_event_base__", False) for base in bases
            ):
                mcls.inbound_registry[header] = cls

            if any(base.__name__ == "UIOutboundEvent" for base in bases) or any(
                    getattr(base, "__is_outbound_event_base__", False) for base in bases
            ):
                mcls.outbound_registry[header] = cls

        return cls


@dataclass(frozen=True, slots=True)
class UIEvent(metaclass=UIEventMeta):
    """Base type for all UI boundary events."""

    __register__: ClassVar[bool] = False
    HEADER: ClassVar[str | None] = None

    @property
    def header(self) -> str:
        return type(self).event_name()

    @classmethod
    def event_name(cls) -> str:
        return cls.HEADER or camel_to_snake(cls.__name__)

    @classmethod
    def resolve(cls, header: str) -> AnyUIEvent:
        return UIEventMeta.registry[header]

    @classmethod
    def registered_headers(cls) -> tuple[str, ...]:
        return tuple(UIEventMeta.registry)


@dataclass(frozen=True, slots=True)
class UIInboundEvent(UIEvent):
    """Event originating from the UI."""
    __register__: ClassVar[bool] = False
    __is_inbound_event_base__: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class UIOutboundEvent(UIEvent):
    """Event emitted by the application towards the UI."""

    __register__: ClassVar[bool] = False
    __is_outbound_event_base__: ClassVar[bool] = True


@dataclass(frozen=True, slots=True)
class UICommand(UIInboundEvent):
    """User intent that requests some action inside the app."""

    __register__: ClassVar[bool] = False


@dataclass(frozen=True, slots=True)
class UIPromptReply(UIInboundEvent):
    """Reply to an earlier app-initiated prompt."""
    __register__: ClassVar[bool] = False
    msg_id: str  # mandatory when a reply is expected

    def id(self):
        return self.msg_id


@dataclass(frozen=True, slots=True)
class UINotification(UIOutboundEvent):
    """One-way outbound state change or status update."""

    __register__: ClassVar[bool] = False


@dataclass(frozen=True, slots=True)
class UIError(UINotification):
    """Outbound error notification."""
    __register__: ClassVar[bool] = False


@dataclass(frozen=True, slots=True)
class UIPrompt(UIOutboundEvent):
    """Outbound request for user input."""
    __register__: ClassVar[bool] = False
    msg_id: str  # mandatory when a reply is expected

    def id(self):
        return self.msg_id


@dataclass(frozen=True, slots=True)
class UIResult(UIOutboundEvent):
    """Outbound result for a specific request or query."""

    __register__: ClassVar[bool] = False


AnyUIEvent = typing.TypeVar("AnyUIEvent", bound=type["UIEvent"])
AnyUIEventObject = typing.TypeVar("AnyUIEventObject", bound="UIEvent")
AnyUICommand = typing.TypeVar("AnyUICommand", bound=UICommand)
AnyUIPromptReply = typing.TypeVar("AnyUIPromptReply", bound=UIPromptReply)
AnyUINotification = typing.TypeVar("AnyUINotification", bound=UINotification)
AnyUIPrompt = typing.TypeVar("AnyUIPrompt", bound=UIPrompt)
AnyUIResult = typing.TypeVar("AnyUIResult", bound=UIResult)
AnyUIError = typing.TypeVar("AnyUIError", bound=UIError)
