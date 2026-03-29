"""Functions to subscribe to app events and propagate them to the UI or other perform some routines"""
from src.conduit.ui_events import PeerPresenceChanged
from src.core import app_events
from . import webpage
from .ui_codec import remote_peer_to_peer_summary


def sub_to_remote_peer_updates(app_event_bus: app_events.AppEventsBus, task_group):
    """Propagates RemotePeerStatusUpdate events to the webpage."""
    async def _handler():
        event: app_events.PeerStatusUpdate = await stat_update_queue.get()
        if event is None:
            return
        ui_notification = PeerPresenceChanged(
            remote_peer_to_peer_summary(event.remote_peer)
        )
        webpage.notify(ui_notification)

    stat_update_queue = app_event_bus.subscribe(app_events.PeerStatusUpdate)
    task_group.create_task(_handler(), name="app-event-handler-peer-status-update")
