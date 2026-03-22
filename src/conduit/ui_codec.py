"""Codec between typed UI events and the legacy DataWeaver/HANDLE wire format.

This module lets the websocket layer keep using DataWeaver while the rest of the
application gradually moves to typed UI events.
"""

from __future__ import annotations

import dataclasses
import json as _json
from collections import defaultdict
from typing import Any, Union

from src.avails import RemotePeer, constants as _const
from src.avails.exceptions import InvalidPacket
from src.conduit.ui_events import (
    PeerSummary,
    TransferUpdate,
)
from src.conduit.ui_events_bases import AnyUIEventObject, UIEvent


def remote_peer_to_peer_summary(peer: RemotePeer) -> PeerSummary:
    return PeerSummary(
        name=peer.username,
        ip=peer.ip,
        peer_id=peer.peer_id,
        online=peer.is_online,
    )


def transfer_update_from_payload(payload: dict[str, Any], *, peer_id: str | None = None) -> TransferUpdate:
    return TransferUpdate(
        transfer_id=payload.get("transfer_id", payload.get("transferId")),
        peer_id=peer_id or str(payload.get("peer_id", "")),
        item_path=payload.get("item_path"),
        progress=payload.get("progress"),
        confirmation=payload.get("confirmation"),
        cancelled=bool(payload.get("cancelled", False)),
        error=payload.get("error"),
    )


class DataWeaver:
    """A wrapper purposely designed to handle data (as {header, content, msg_id, peer_id} format)

    Only to be used by `conduit` package, and is completely hidden from core API

    """

    __annotations__ = {
        "__data": dict,
    }
    __slots__ = "__data",

    def __init__(
            self,
            *,
            header: Union[str, int] = None,
            content: Union[str, dict, list, tuple] = None,
            peer_id: Union[int, str] = None,
            msg_id: Union[int, str] = None,
            _type: Union[_const.DATA, _const.SIGNAL] = _const.SIGNAL,
            serial_data: str | bytes = None,
    ):

        if serial_data:
            self.__data: dict = _json.loads(serial_data)
        else:
            self.__data: dict = defaultdict(str)
            self.__data["header"] = header
            self.__data["content"] = content
            self.__data["peerId"] = peer_id
            self.__data["msgId"] = msg_id
            self.__data["type"] = _type

    def dump(self) -> str:
        """
        Modifies data in json string format and,
        returns json string representation of the data
        """
        return str(self)

    def match_content(self, _content) -> bool:
        return self.__data["content"] == _content

    def match_header(self, _header) -> bool:
        return self.__data["header"] == _header

    def __iter__(self):
        # prevent from being an iterator cause sequence protocol may mess up
        raise NotImplemented

    def __getitem__(self, key):
        return self.__data["content"][key]

    def __contains__(self, item):
        return item in self.__data["content"]

    @property
    def content(self):
        return self.__data["content"]

    @property
    def header(self):
        return self.__data["header"]

    @property
    def peer_id(self):
        return self.__data["peerId"]

    @property
    def msg_id(self):
        return self.__data["msgId"]

    @property
    def id(self):  # just for compatibility with reply-registry-mix-in class
        return self.msg_id

    @property
    def type(self):
        return str(self.header)[0]

    def __str__(self):
        return _json.dumps(self.__data)

    def __repr__(self):
        data = self.__data.copy()
        content = data.pop("content")

        if content is None:
            data["content"] = None
        elif isinstance(content, dict):
            data["content"] = {}
            for k, v in content.items():
                data["content"][k] = repr(v)[:20]
        elif isinstance(content, str):
            data["content"] = content[:30]
        else:
            data["content"] = content

        return f"DataWeaver({data})"

    def field_check(self):
        match self.__data:
            case {
                'msgId': _,
                'content': _,
                'header': _,
                'peerId': _,
            }:
                return
            case _:
                missing_fields = [field for field in ['msgId', 'content', 'header'] if field not in self.__data]
                raise InvalidPacket(f"fields missing: {missing_fields}")


def decode_data(data: DataWeaver) -> AnyUIEventObject:
    event_class = UIEvent.resolve(data.header[1:])
    extra_kwargs = {}
    if data.peer_id:
        extra_kwargs["peer_id"] = data.peer_id
    if data.msg_id:
        extra_kwargs["msg_id"] = data.msg_id

    event = event_class(**data.content, **extra_kwargs)

    return event


def encode_event(event: UIEvent) -> DataWeaver:
    event_serialized = dataclasses.asdict(event)
    peer_id = event_serialized.pop("peer_id", None)
    msg_id = event_serialized.pop("msg_id", None)
    data_weaver = DataWeaver(
        header=event.header,
        content=event_serialized,
        peer_id=peer_id,
        msg_id=msg_id,
    )
    return data_weaver