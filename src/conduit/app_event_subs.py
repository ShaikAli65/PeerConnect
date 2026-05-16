"""Functions to subscribe to app events and propagate them to the UI or other perform some routines"""
from src.conduit.ui_events import PeerPresenceChanged
from src.core.app_events import AppEventsBus, PeerStatusUpdate
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
