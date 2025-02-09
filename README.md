# PeerConnect

PeerConnect is a peer-to-peer (P2P) data transfer and messaging application designed to work efficiently in local networks. The backend is powered solely by Python, leveraging the standard library for core functionality, while the frontend is developed using HTML, CSS, and JavaScript. 

The primary goal of PeerConnect is to provide fast and efficient data transfers and messaging between peers without relying on centralized servers, making it highly suitable for localized networks.

## Features

- **P2P Communication**: Enables direct data transfer and messaging between peers, eliminating the need for centralized control.
- **Local Network Optimization**: Tuned for high-performance within local area networks (LANs).
- **Custom Protocols**: Implements several distributed protocols to optimize communication and data sharing between peers.
- **Standard Library Use**: Core functionality implemented using Python’s standard library to avoid unnecessary dependencies.

## Internals
- **Network Discovery**: finds other peers incrementally in the local network and lists them to the user   
- **k 
- **Messaging**: 

## Main Branch

The code in the main branch is a fully functional version of PeerConnect. It employs a **threaded synchronous model** and includes:

- **Mesh Networking**: Maintains peer-to-peer connections with local storage of peer information.
- **Signaling Server**: Requires a centralized signaling server for coordinating peer connections.
- **Basic Mesh Network Topology**: Simple peer connections stored locally; works best in small to medium-sized networks (up to 500-1000 peers).
- **Synchronous Execution**: Uses a basic, custom-built asynchronous event loop written from scratch, though predominantly threaded and synchronous in operation.

### Dependencies

- **[tqdm](https://github.com/tqdm/tqdm)**: Provides progress bars for data transfers in the console.
- **[pyqt](https://riverbankcomputing.com/software/pyqt/intro)**: Utilized for file picker (though a lighter alternative is desired).
- **[websockets](https://websockets.readthedocs.io/)**: Facilitates Inter-Process Communication (IPC) between the backend and the frontend.

## Dev Branch (Under Development)

The dev branch is a complete rewrite using Python’s asynchronous features, aiming to scale PeerConnect for **larger, distributed networks** without a centralized entity. This branch includes:

- **Distributed Hash Tables (DHT)**: Implements the **Kademlia** protocol for maintaining decentralized peer connections.
- **Advanced P2P Protocols**: Incorporates sophisticated algorithms for peer communication and gossiping:
  - **HyParView/Palm Tree Protocol**: A protocol for maintaining highly connected and robust overlay networks, distributed tree-based communication model.
  - **Rumor-Mongering**: Epidemic-based message dissemination protocol.
  - **Custom Gossip Protocol**: A lightweight, under-development gossip protocol designed for efficient large-scale peer messaging.
  
- **Fully Asynchronous**: Leverages Python’s `asyncio` to handle asynchronous network communication efficiently.
- **Decentralized Coordination**: Removes the need for a centralized signaling server, enabling pure peer-to-peer operations.
- **Scalability**: Expected to handle large networks of over 1500 peers concurrently.
  
### Additional Dependencies

- **[kademlia](https://github.com/bmuller/kademlia)**: A distributed hash table implementation used for decentralized peer discovery.

## Future Plans

- **Further Protocol Optimization**: Continue developing and refining the custom gossip protocol for enhanced scalability.
- **Sockets Multiplexer**: Introduce an async sockets multiplexer which works on multiple connections connected to same addr and provide high level functions that expose functions like send and recv as single connection,
  but underlying mechanism select which socket to send data on, and on receive side the data should be and ordered stream, 
  should respect backpressure, utilizing maximum bandwidth 
## Usage

PeerConnect is designed for local networks. Clone the repository and follow the instructions to get started with either the **Main** (stable) or **Dev** (development) branch.
