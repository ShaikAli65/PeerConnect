import asyncio
import enum
import math
from asyncio import Future
from collections import defaultdict
from typing import Optional

from src.avails import (RemotePeer, WireData, connect, const, use, wire)
from src.avails.connect import UDPProtocol, get_free_port
# from src.avails.remotepeer import RemotePeer
from src.avails.wire import PalmTreeSession, Wire
from src.core import Dock, get_this_remote_peer, peers
from src.transfers import HEADERS
from src.transfers.otm.tree import TreeLink


class PalmTreeLink(TreeLink):

    def send_passive_message(self, message: bytes):
        Wire.send_datagram(self._connection, self.right, message)
        # :todo try adding timeout mechanisms

    async def recv(self, length):
        return await self._connection.arecv(length)

    async def send(self, data):
        return await self._connection.asendall(data)

    def __del__(self):
        self.clear()


class RelayState(enum.IntEnum):
    INITIAL = 1
    SESSION_INIT = 2
    LINKS_INITIALIZED = 3
    TREE_CHECK_DONE = 4


class PalmTreeRelay(asyncio.DatagramProtocol):
    """
    PalmTreeRelay manages peer-to-peer connections in a gossip tree structure.

    The relay establishes active/passive links, coordinates tree checks, upgrades
    connections, and maintains state across peers.

    Protocol rules:
    * trivial thing that a node in tree must have a single parent
    * we initiate the connections that we are going to forward
    * logically the connections come to us are the one we are reading from

    Attributes:
        session (PalmTreeSession): A session managing the relay state and settings.
        passive_endpoint_addr (tuple): Address for passive endpoint connections.
        active_endpoint_addr (tuple): Address for active endpoint connections.
        state (RelayState): Current state of the relay in the gossip protocol.

    Methods:
        session_init(): Initializes the session by creating a datagram endpoint.
        connection_made(): Establishes connection when datagram connection is made.
        datagram_received(): Handles incoming data packets, routes to functions.
        gossip_update_state(): Updates gossip state with links to other peers.
        gossip_tree_check(): Validates and forwards tree check packet.
        gossip_tree_reject(): Handles rejection of a gossip tree connection.
        gossip_downgrade_connection(): Downgrades an active link to passive.
        gossip_upgrade_connection(): Upgrades a passive link to active.
        gossip_add_stream_link(): Adds a stream connection for an incoming peer.
        gossip_gossip_tree_gather(): sends a reply to initiator peer according to protocol
        stop_session(): Cleans up and closes the session.
        print_state(): Prints relay state for debugging purposes.
    """

    link_init_class = PalmTreeLink

    def __init__(
            self,
            session,
            passive_endpoint_addr: tuple[str, int] = None,
            active_endpoint_addr: tuple[str, int] = None,
    ):

        self.transport = None
        self.session_task = None
        self.all_tasks = []
        self.session: PalmTreeSession = session

        self.passive_endpoint_addr = passive_endpoint_addr

        # keeping a reference for consistency
        self.active_endpoint_addr = active_endpoint_addr

        # all links are created initially
        self.all_links: dict[str, tuple[TreeLink, TreeLink]] = {}
        self._tree_check_window_index = 0

        self._parent_link_fut: Future[TreeLink] = (
            asyncio.get_event_loop().create_future()
        )

        self._parent_link_fut.add_done_callback(
            lambda _: self.print_state("initial link activated")
        )

        # this is to keep a reference to actual sender just a helper for classes inheriting this class
        self._read_link: Optional[TreeLink] = None

        # this set is used to book keep an id reference to the peers from whom we are expecting an incoming connection
        self.__expected_parent_peers = set()
        # :todo: this seems redundant, to be reviewed

        # references from all links should be sorted out based on connectivity
        self.active_links: dict[str, TreeLink] = {}
        self.passive_links: dict[str, TreeLink] = {}
        self.state = RelayState.INITIAL

    async def session_init(self):
        """
        Initializes the relay by creating a datagram endpoint based on the
        passive endpoint address. Transitions the relay state to SESSION_INIT.
        """
        if self.state >= RelayState.SESSION_INIT:
            self.print_state("session already initialized")
            return

        loop = asyncio.get_event_loop()
        func = loop.create_datagram_endpoint(
            lambda: self,
            self.passive_endpoint_addr,
            family=const.IP_VERSION,
        )
        try:
            await func
        except PermissionError:
            self.print_state("got permission error while creating datagram endpoint")
            raise  # to be rechecked
        self.print_state("initialized datagram endpoint successfully")
        self.state = RelayState.SESSION_INIT

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        """
        Processes incoming data as an RPC by matching headers to method names.

        Args:
            data (bytes): Incoming data from peers.
            addr (tuple): Address of the sending peer.
        """

        unpacked_data = wire.unpack_datagram(data)
        if unpacked_data is None:
            return
        self.print_state("got some data at passive endpoint", unpacked_data)
        if unpacked_data.header in dir(self):
            f = use.wrap_with_tryexcept(
                getattr(self, unpacked_data.header), unpacked_data, addr
            )
            asyncio.create_task(f())

    async def gossip_update_state(self, state_data, addr=None):
        """
        Updates the relay's links to other peers based on gossip data, sets
        relay state to LINKS_INITIALIZED.

        Args:
            state_data (WireData): Contains peer addresses for relay status_setup.
            addr (tuple): Address of the peer initiating the update.
        """
        if self.state >= RelayState.LINKS_INITIALIZED:
            self.print_state("state mismatched, rejecting state update", self.state)
            return

        addresses = state_data["addresses_mapping"]

        for peer_id, passive_addr, active_addr in addresses:
            active_link = self.link_init_class(
                self.active_endpoint_addr,
                tuple(active_addr),
                peer_id,
                link_type=TreeLink.ACTIVE,
            )
            passive_link = self.link_init_class(
                self.passive_endpoint_addr,
                tuple(passive_addr),
                peer_id,
                self.transport,
                link_type=TreeLink.PASSIVE,
            )
            passive_link.status = TreeLink.ONLINE
            self.all_links[peer_id] = (passive_link, active_link)

        self.session.fanout = min(len(self.all_links), self.session.fanout)
        self.print_state("updated gossip state", addr)
        self.state = RelayState.LINKS_INITIALIZED

    async def gossip_tree_check(self, tree_check_packet, addr):
        """
        Validates incoming tree check packet and forwards it if conditions are met.

        Args:
            tree_check_packet (WireData): Contains tree check data.
            addr (tuple): Address of the peer initiating the check.
        """
        peer = await peers.get_remote_peer_at_every_cost(tree_check_packet.id)
        self.print_state(f"checking gossip tree {peer.username}, {peer.ip}")
        if self._may_be_make_rejection(tree_check_packet, addr):
            return

        this_peer_id = get_this_remote_peer().peer_id
        sender_id = tree_check_packet.id
        self.__expected_parent_peers.add(tree_check_packet.id)

        try:
            await self._send_upgrade_packet(sender_id, this_peer_id)
        except ConnectionRefusedError:
            # we ain't messaging other peers if we ourselves don't have a connection in real
            self.print_state("an expected connection from sender peer has not came")
            return

        tree_check_packet.id = this_peer_id
        self.forward_tree_check_packet(sender_id, tree_check_packet)
        self.passive_links.update(
            {
                peer_id: self.all_links[peer_id][TreeLink.PASSIVE]
                for peer_id in set(self.all_links) - set(self.active_links)
            }
        )
        self.state = RelayState.TREE_CHECK_DONE
        self.print_state(f"gossip tree check completed {tree_check_packet.id}")

    def _may_be_make_rejection(self, tree_check_packet, addr):
        """
        Determines whether to reject a gossip tree check request based on relay state.

        Args:
            tree_check_packet (WireData): Packet for tree check.
            addr (tuple): Address of requesting peer.

        Returns:
            str: Reason for rejection, empty if not rejected.
        """
        reject_reason = ""
        if tree_check_packet.id not in self.all_links:
            reject_reason += "peer not found in all_links" " "
        if len(self.active_links) > self.session.fanout:
            reject_reason += "fully available active links" " "
        if self._parent_link_fut.done():
            # if this future is done then we ain't accepting any other parent links
            reject_reason += "parent link available" " "
        if self.state >= RelayState.TREE_CHECK_DONE:
            reject_reason += "tree check done"
        if reject_reason:
            gossip_link_reject_message = WireData(
                header=HEADERS.GOSSIP_TREE_REJECT,
                msg_id=get_this_remote_peer().peer_id,
            )
            Wire.send_datagram(self.transport, addr, bytes(gossip_link_reject_message))
            self.print_state(f"rejected gossip tree link {addr}", reject_reason)

        return reject_reason

    async def _send_upgrade_packet(self, sender_id, this_peer_id):
        """
        Attempts to upgrade a passive link to active by sending an upgrade request.

        Implementation Detail
                There is no mechanism currently to reject this upgrade request
            a stream connection will indeed come from peer if he is not offline
        Args:
            sender_id (str): ID of the sender peer.
            this_peer_id (str): ID of the receiving peer.

        Returns:
            bool: Whether the upgrade was successful.
        """
        upgrade_conn_packet = WireData(
            header=HEADERS.GOSSIP_UPGRADE_CONN,
            msg_id=this_peer_id,
        )
        passive_link, active_link = self.all_links[sender_id]

        # we are expecting this link to get activated so it's fine
        self.active_links[sender_id] = active_link

        for timeout in use.get_timeouts(
                initial=0.1, max_retries=3, max_value=self.session.link_wait_timeout
        ):
            if self._parent_link_fut.done():
                break
            passive_link.send_passive_message(bytes(upgrade_conn_packet))
            self.print_state("sent upgrade packet as a reply to tree check")
            self.print_state(passive_link)
            try:
                await asyncio.wait_for(self._parent_link_fut, timeout)
                # self._is_parent_link_active is set by self.gossip_add_stream_link
                # we will wait until a connection comes from parent
                active_link.direction = TreeLink.INCOMING
                break
            except TimeoutError:
                pass
        else:
            raise ConnectionRefusedError("no connection received from expected peer")

    def forward_tree_check_packet(self, sender_id, tree_check_packet):
        """
        Forwards the tree check packet to a sampled subset of peers.

        Args:
            sender_id (str): ID of the sender peer.
            tree_check_packet (WireData): Packet containing the tree check.
        """

        window_start = self._tree_check_window_index
        window_end = min(
            len(self.all_links), self._tree_check_window_index + self.session.fanout
        )

        # decreasing window size to make sure that we don't out value self.session.fanout
        window_end -= len(
            [x for x in self.active_links.values() if x.is_online and x.is_outgoing]
        )
        self._tree_check_window_index = window_end

        peer_ids = list(self.all_links)[window_start: window_end + 1]

        sampled_peer_ids = set(peer_ids) - {sender_id} - set(self.active_links.keys())

        self.print_state(f"sampled peers:")
        for peer in sampled_peer_ids:
            self.print_state(Dock.peer_list.get_peer(peer))

        for peer_id in sampled_peer_ids:
            try:
                passive_link, active_link = self.all_links[peer_id]
            except KeyError:
                pass
            else:
                passive_link.send_passive_message(bytes(tree_check_packet))
                self.active_links[peer_id] = active_link

    async def gossip_tree_reject(self, data, addr):
        """
        Handles rejection of a gossip tree connection by attempting to reconnect.

        Implementation Detail:
        ###
            our request to make an edge is rejected :(
            we need to look into our further links and try to make a connection until
            either we get `self.session.fanout` number of connections active,
            or we tried all links to make a connection
        ###

        Args:
            data (WireData): Contains peer data for rejected tree connection.
            addr (tuple): Address of rejecting peer.
        """

        if len(self.all_links) <= self._tree_check_window_index:
            return  # we already checked all our all_links no need to do anything

        if len(self.active_links) >= self.session.fanout:
            return  # we already have full of connections

        tree_check_packet = WireData(
            header=HEADERS.GOSSIP_TREE_CHECK,
            msg_id=get_this_remote_peer().peer_id,
            message_id=use.get_unique_id(str),
            session_id=self.session.session_id,
        )
        self.forward_tree_check_packet(data.id, tree_check_packet)

    # this function is used when we are making connections
    async def _activate_link(self, link: TreeLink):
        """
        Activates a passive link by establishing an async stream connection.

        Args:
            link (TreeLink): The link to activate.

        Returns:
            bool: Whether activation was successful.
        """
        if link.is_online:
            return
        stream_sock = await connect.create_connection_async(
            link.right, self.session.link_wait_timeout
        )
        await Wire.send_async(
            stream_sock,
            self._make_update_stream_link_packet(),
        )
        try:
            data = await Wire.receive_async(stream_sock)
        except OSError:
            return False
        if not data == HEADERS.GOSSIP_LINK_OK:
            return False
        link.connection = stream_sock
        link.direction = TreeLink.OUTGOING
        return True

    def _make_update_stream_link_packet(self):
        """
        Returns a packet for updating a stream link.
        PROTOCOLS using this class may overload this function

        Returns:
            bytes: Encoded packet for stream link update.
        """
        h = WireData(
            header=HEADERS.GOSSIP_UPDATE_STREAM_LINK,
            msg_id=get_this_remote_peer().peer_id,
            session_id=self.session.session_id,
            peer_addr=self.passive_endpoint_addr,
        )
        return bytes(h)

    async def gossip_tree_gather(self, data: WireData, addr: tuple[str, int]):
        data["level"] += 1
        data["parent"] = (await self._parent_link_fut).peer_id
        Wire.send_datagram(self.transport, data["reply_addr"], bytes(data))
        for child_link in self._get_forward_links():
            child_link.send_passive_message(bytes(data))

    async def gossip_downgrade_connection(self, data: WireData, addr: tuple[str, int]):
        """
        Downgrades a connection from active to passive, updating relay state.

        downgrade connection request is made to this peer, which
        removes connection from `self.active_links`,
        clears the active link,
        and adds passive link to `self.passive_links` list
        Args:
            data (WireData): Contains peer ID and session data.
            addr (tuple): Address of the peer initiating the downgrade.
        """
        self.print_state(f"downgrading connection {addr}")
        peer_id = data.id
        if peer_id in self.active_links:
            a_link = self.active_links.pop(peer_id)
            a_link.clear()
            self.passive_links[peer_id] = self.all_links[peer_id][TreeLink.PASSIVE]
            self.passive_links[peer_id].status = TreeLink.OFFLINE

    async def gossip_upgrade_connection(self, data: WireData, addr: tuple[str, int]):
        """
        Attempts to upgrade a connection from passive to active based on peer request.

        Args:
            data (WireData): Contains peer data for upgrade.
            addr (tuple): Address of the requesting peer.
        """
        if data.id in self.active_links:
            if self.active_links[data.id].is_online:
                self.print_state("not upgrading found an existing connection online ")
                self.print_state(self.active_links[data.id])
                return

        self.print_state(f"initiating a stream connection {addr}")
        peer_id = data.id
        if peer_id not in self.active_links:
            return
        link = self.active_links[peer_id]
        what = await self._activate_link(link)
        if what is False:
            self.print_state("failed to make a stream connection")

    # this function is invoked when connection came from other side
    async def gossip_add_stream_link(self, connection, data: WireData):
        """
        Handles an incoming stream connection, adding it if conditions are met.
        Implementation Detail:
            Protocol assumptions:
            1. This function is invoked when an incoming connection relates to this relay.
            2. This means that this function is not invoked until the system sends an upgrade packet.
            3. The current implementation accepts only one incoming connection at a time.
            4. If a parent connection already exists, the system does not accept any other connections.

        Args:
            connection (connect.Socket): The incoming connection stream.
            data (WireData): Peer and session data for validation.
        """

        assert self.session.session_id == data["session_id"]

        peer_id = data.id
        if peer_id not in self.active_links:
            # somehow we are not expecting this connection to come in
            self.print_state(
                f"peer not found in active links, rejecting stream link from {data['peer_addr']}"
            )
            connection.close()
            return
        active_link = self.active_links[peer_id]

        if active_link.is_online or active_link.is_lagging:
            # a possible case where we may get a new connection from an already connected peer
            active_link.clear()
            active_link.connection = connection
            self.print_state(f"updated stream link {data['peer_addr']}")
            return

        if self._parent_link_fut.done():
            self.print_state("found parent link active rejecting further connections")
            connection.close()
        elif (
                peer_id in self.__expected_parent_peers
        ):  # this confirms that we have requested the peer to make a connection
            active_link.connection = connection
            await Wire.send_async(connection, HEADERS.GOSSIP_LINK_OK)
            # :todo: add timeout's
            self.print_state(f"added stream link {data['peer_addr']}")
            self._parent_link_fut.set_result(active_link)

        # stream connections are assumed to be active links for now

    async def _parent_link_broken(self):
        ...

    def _get_forward_links(self):
        """
        Returns a set of outgoing active links excluding the main read link.

        Returns:
            set[TreeLink]: Set of active outgoing links for forwarding data.
        """
        _l = set(self.active_links.values()) - {self._read_link}
        return set(x for x in _l if x.is_online and x.is_outgoing)

    def stop_session(self):
        """
        Stops the relay session by closing transport and canceling tasks.
        :todo: add finalizing logic
        """

        if self.transport:
            self.transport.close()
        if self.session_task:
            self.session_task.cancel()

    def print_state(self, *string, **kwargs):
        """
        Logs relay state with session-specific prefix for debugging.

        Args:
            *string: Variable arguments to include in log.
            **kwargs: Additional print options.
        """
        return print(
            f"[:]{use.COLORS[4]}[{self.session.session_id}][:] {" ".join(str(x) for x in string)}{use.COLOR_RESET}",
            **kwargs,
        )

    async def gossip_print_every_onces_states(self, data, addr):
        """
        Prints relay state, forwarding data to all online outgoing active links.

        Args:
            data (WireData): Data to forward.
            addr (tuple): Address of requesting peer.
        """
        # if hasattr(self, '_is_state_printed'):
        #     return

        self._print_full_state()
        for link in self._get_forward_links():
            passive_link_of_active_peer = self.all_links[link.peer_id][0]
            passive_link_of_active_peer.send_passive_message(bytes(data))

    def _print_full_state(self):
        """
        Logs a complete state overview of the relay, showing all links.
        """
        self._is_state_printed = None
        self.print_state("=" * 80)
        self.print_state("ALL LINKS")
        for all_link in self.all_links:
            self.print_state(all_link)

        self.print_state("=" * 40)

        self.print_state("ACTIVE LINKS")
        for active_link in self.active_links.values():
            self.print_state(active_link)

        self.print_state("=" * 40)

        self.print_state("PASSIVE LINKS")
        self.print_state(", ".join(str(x) for x in self.passive_links.values()))
        self.print_state("=" * 40)
        self.print_state("PARENT EDGE:")
        if self._parent_link_fut.done():
            self.print_state(self._parent_link_fut.result())
        self.print_state("=" * 80)


class PalmTreeProtocol:
    request_timeout = 3
    mediator_class = None

    def __init__(self, center_peer, session, peers_list):
        """

        Builds tree using top down approach
        # call order :
        # inform peers
        # self.mediator.start_session
        # update states
        # trigger_spanning_formation
        # gather_tree

        Note:
            Do not include center_peer in peers list passed in

        Args:
            center_peer(RemotePeer) : center peer of the session, usually this peer
            session(PalmTreeSession): session object related to current transfer
            peers_list(list[RemotePeer]): list of remote peer objects participating in transfer

        """

        self.peer_list = peers_list
        self.center_peer = center_peer
        self.adjacency_list: dict[str: list[RemotePeer]] = defaultdict(list)
        self.confirmed_peers: dict[str, wire.PalmTreeInformResponse] = {}
        self.create_hypercube()
        self.session = session
        self.session.adjacent_peers = self.adjacency_list[self.center_peer.id]
        self.gathered_tree = None

        if self.mediator_class is None:
            self.mediator_class = PalmTreeRelay

        self.relay = self.mediator_class(
            self.session,
            (self.center_peer.ip, get_free_port()),
            center_peer.uri,
        )

    def create_hypercube(self):
        """Create the hypercube topology of peers"""
        center_peer_included_list = [self.center_peer] + self.peer_list
        peer_id_to_peer_mapping = dict(enumerate(center_peer_included_list))

        dimensions = (
                             2 ** math.ceil(math.log2(len(center_peer_included_list)))
                     ).bit_length() - 1

        for i in range(len(center_peer_included_list)):
            for j in range(dimensions):
                neighbor = i ^ (1 << j)
                if neighbor < len(center_peer_included_list):
                    peer = peer_id_to_peer_mapping[i]
                    neigh = peer_id_to_peer_mapping[neighbor]
                    self.adjacency_list[peer.id].append(neigh.id)

    async def inform_peers(self, trigger_header: WireData):

        # updating center peer's data
        self.confirmed_peers[self.center_peer.id] = wire.PalmTreeInformResponse(
            self.center_peer.id,
            self.relay.passive_endpoint_addr,
            self.relay.active_endpoint_addr,
            self.session.key,
        )

        req_tasks = [
            self._trigger_schedular_of_peer(bytes(trigger_header), peer)
            for peer in self.peer_list
        ]

        for f in asyncio.as_completed(req_tasks):
            what, conformation = await f
            if what is True:
                self.confirmed_peers[conformation.peer_id] = conformation
            else:
                discard_peer_id = conformation.peer_id
                for peer_id in self.adjacency_list[discard_peer_id]:
                    self.adjacency_list[peer_id].remove(discard_peer_id)
                del self.adjacency_list[discard_peer_id]
        # send an audit event to page confirming peers

    async def _trigger_schedular_of_peer(self, trigger_request, peer):
        """
        Args:
            trigger_request: packet that triggers schedular
            peer(RemotePeer): object corresponds to that peer

        Returns:
            tuple[bool, Union[RemotePeer, wire.PalmTreeInformResponse]]
        """
        loop = asyncio.get_event_loop()
        connection = await UDPProtocol.create_connection_async(
            loop, peer.req_uri, self.session.link_wait_timeout
        )
        with connection:
            Wire.send_datagram(connection, peer.req_uri, trigger_request)
            try:
                data, addr = await asyncio.wait_for(
                    Wire.recv_datagram_async(connection), self.session.link_wait_timeout
                )
            except TimeoutError:
                return False, peer

            reply_data = wire.PalmTreeInformResponse.load_from(data)
            return True, reply_data

    async def update_states(self):
        await self.__update_internal_mediator_state()
        states_data = WireData(
            header=HEADERS.GOSSIP_SESSION_STATE_UPDATE,
            addresses_mapping=None,
        )
        with connect.UDPProtocol.create_sync_sock(const.IP_VERSION) as s:
            for peer_id in set(self.confirmed_peers) - {self.center_peer.id}:
                response_data = self.confirmed_peers[peer_id]
                peer_ids = self.adjacency_list[peer_id]
                peer_responses = [self.confirmed_peers.get(p_id) for p_id in peer_ids]

                states_data["addresses_mapping"] = [
                    (p_id, peer_response.passive_addr, peer_response.active_addr)
                    for p_id, peer_response in zip(peer_ids, peer_responses)
                    if peer_response
                ]
                Wire.send_datagram(s, response_data.passive_addr, bytes(states_data))

    async def __update_internal_mediator_state(self):
        await self.relay.gossip_update_state(
            WireData(
                header=HEADERS.GOSSIP_SESSION_STATE_UPDATE,
                addresses_mapping=(
                    (peer_id, peer_response.passive_addr, peer_response.active_addr)
                    for peer_id, peer_response in zip(
                    self.adjacency_list[self.center_peer.id],
                    map(
                        lambda x: self.confirmed_peers.get(x),
                        self.adjacency_list[self.center_peer.id],
                    ),
                )
                    if peer_response
                ),  # keeping this as a generator because it's gonna
                #    directly iterated over in the underlying function
            )
        )

    async def trigger_spanning_formation(self):
        tree_check_message_id = use.get_unique_id(str)
        spanning_trigger_header = WireData(
            header=HEADERS.GOSSIP_TREE_CHECK,
            msg_id=self.center_peer.id,
            message_id=tree_check_message_id,
            session_id=self.session.session_id,
        )
        # initial_peers = self.adjacency_list[self.center_peer]
        # if not initial_peers:
        #     # :todo: handle the case where all the peers adjacent to center peer went offline
        #     pass
        self.relay.forward_tree_check_packet(
            self.center_peer.id, spanning_trigger_header
        )

    async def gather_tree(self):
        replies = []
        loop = asyncio.get_event_loop()
        with UDPProtocol.create_async_sock(loop, const.IP_VERSION) as s:
            tree_gather_packet = WireData(
                header=HEADERS.GOSSIP_TREE_GATHER,
                msg_id=self.center_peer.id,
                level=0,
                parent=None,
                reply_addr=s.getsockname(),
            )
            await self.relay.gossip_tree_gather(tree_gather_packet, s.getsockname())
            counter = 0
            while counter >= len(self.confirmed_peers):
                data, addr = await Wire.recv_datagram_async(s)
                unpacked_response = wire.unpack_datagram(data)
                if unpacked_response:
                    replies.append(unpacked_response)
        replies.sort(key=lambda x: x["level"])
        self.gathered_tree = replies
