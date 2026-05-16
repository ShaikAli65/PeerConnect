from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Protocol

from src.avails.useables import camel_to_snake


class IDialogs(ABC):
    @classmethod
    @abstractmethod
    def open_file_dialog_window(cls) -> list[str]: ...

    @classmethod
    @abstractmethod
    def open_directory_dialog_window(cls) -> str: ...


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


class FrontEnd(Protocol):
    """
    Interface for defining the structure and interaction of a front-end system.

    This protocol specifies the standard methods that a front-end system should
    implement in order to communicate with the back-end or other functional
    components. It lays out how to notify users, handle errors, send prompts,
    and deliver results.

    Methods are specified with no implementation, allowing concrete implementations
    to define their own behavior.
    """

    def notify(self, message: AnyUINotification):
        """
        Sends a notification using the provided message.

        This method handles the delivery of a notification to a target, where the
        specific implementation depends on the notification details provided.

        Args:
            message (AnyUINotification): The notification object that contains the
                details and data required for delivery.
        """

    def send_error(self, error: AnyUIError):
        """
        Sends an error for handling or display to the user interface.

        This method processes a given error and ensures it is handled or passed
        to a relevant component for user notification or logging.

        Args:
            error: The error to be sent for handling. This should be an
                instance of `AnyUIError`, representing an error intended for
                user interface handling.
        """

    async def send_prompt_and_get_response(
          self,
          prompt: AnyUIPrompt,
          resp_type: type[AnyUIPromptReply] | None = None,
    ) -> AnyUIPromptReply:
        """
        Sends a prompt to the designated handler and retrieves the response.

        This asynchronous method is responsible for delivering the provided prompt
        to the intended recipient or processor and awaiting the corresponding
        response. The interaction occurs within the constraints of the system's
        defined execution flow.

        Args:
            resp_type: Optional parameter specifying the expected type of the result
            prompt: The prompt to be sent, containing all necessary details for
                the interaction. Must conform to the type AnyUIPrompt.

        Returns:
            The response generated as a result of the prompt being sent. The exact
            type depends on the implementation of the recipient's response logic.

        Raises:
            Any errors that occur during communication or the response process
            may be propagated. These should be handled accordingly based on the
            specific implementation.
        """

    def send_result(self, result: AnyUIResult):
        """
        Sends the result to the appropriate handler or processor. This method is intended
        to process or forward the provided result object.

        Args:
            result (AnyUIResult): The result object containing data necessary for
                further processing or handling.
        """
