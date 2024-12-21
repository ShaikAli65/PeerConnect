from src.avails import GossipMessage
from src.core import Dock, get_gossip
from src.core.transfers import RumorMessageList, RumorMongerProtocol


class GlobalGossipMessageList(RumorMessageList):
    @staticmethod
    def _get_list_of_peers():
        return set(Dock.peer_list.keys())


class GossipEvents:
    # :todo: complete restructuring of all the gossip classes in OOPS ways, multiplex at requests.RequestsEndPoint
    registered_applications = {}

    def message_received(self, message: GossipMessage): ...

    def register(self, trigger_header, handler): ...


def join_gossip(data_transport):
    Dock.global_gossip = RumorMongerProtocol(data_transport, GlobalGossipMessageList)
    print("joined gossip network", get_gossip())
