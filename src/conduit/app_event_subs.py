"""Functions to subscribe to app events and propagate them to the UI or other perform some routines"""
from src.conduit.ui_events import PeerPresenceChanged, TransferStatusChanged, TransferUpdate, MessageReceived as UIMessageReceived
from src.core.app_events import (
    AppEventsBus,
    MessageReceived, PeerStatusUpdate,
    TransferCompleted,
    TransferConfirmation,
    TransferIncomplete,
    TransferProgressUpdated,
    TransferStarted,
)
from .bases import FrontEnd
from .ui_codec import remote_peer_to_peer_summary


def sub_to_remote_peer_updates(app_event_bus: AppEventsBus, frontend: FrontEnd, task_group):
    """Propagates RemotePeerStatusUpdate events to the webpage."""
    async def _handler():
        while True:
            event: PeerStatusUpdate = await stat_update_queue.get()
            if event is None:
                return
            ui_notification = PeerPresenceChanged(
                remote_peer_to_peer_summary(event.remote_peer)
            )
            frontend.notify(ui_notification)

    stat_update_queue = app_event_bus.subscribe(PeerStatusUpdate)
    task_group.create_task(_handler(), name="app-event-handler-peer-status-update")


def sub_to_transfer_updates(app_event_bus: AppEventsBus, frontend: FrontEnd, task_group):
    """Propagate transfer app events to the UI."""
    transfer_queue = app_event_bus.subscribe(TransferStarted)
    for event_type in (
            TransferProgressUpdated,
            TransferCompleted,
            TransferIncomplete,
            TransferConfirmation,
    ):
        app_event_bus.subscribe(event_type, queue=transfer_queue)

    converters = {
        TransferStarted: _started_to_ui_update,
        TransferProgressUpdated: _progress_to_ui_update,
        TransferCompleted: _completed_to_ui_update,
        TransferIncomplete: _incomplete_to_ui_update,
        TransferConfirmation: _confirmation_to_ui_update,
    }

    async def _handler():
        while True:
            event = await transfer_queue.get()
            if event is None:
                return
            frontend.notify(TransferStatusChanged(converters[type(event)](event)))

    task_group.create_task(_handler(), name="app-event-handler-transfer-updates")


def sub_to_messages(app_event_bus, frontend: FrontEnd, task_group):
    q = app_event_bus.subscribe(MessageReceived)

    async def _handler():
        while True:
            event = await q.get()
            if event is None:
                return
            frontend.notify(UIMessageReceived(event.peer_id, event.msg))

    task_group.create_task(_handler(), name="app-event-handler-message")


def _started_to_ui_update(event: TransferStarted):
    return TransferUpdate(
        transfer_id=event.transfer_id,
        peer_id=event.peer_id,
    )


def _progress_to_ui_update(event: TransferProgressUpdated):
    return TransferUpdate(
        transfer_id=event.transfer_id,
        peer_id=event.peer_id,
        item_path=event.item_path,
        progress=event.progress,
    )


def _completed_to_ui_update(event: TransferCompleted):
    return TransferUpdate(
        transfer_id=event.transfer_id,
        peer_id=event.peer_id,
        completed=True,
    )


def _incomplete_to_ui_update(event: TransferIncomplete):
    return TransferUpdate(
        transfer_id=event.transfer_id,
        peer_id=event.peer_id,
        item_path=event.item_path,
        progress=event.progress,
        cancelled=True,
        error=event.error,
    )


def _confirmation_to_ui_update(event: TransferConfirmation):
    return TransferUpdate(
        transfer_id=event.transfer_id,
        peer_id=event.peer_id,
        confirmation=event.confirmed,
    )
