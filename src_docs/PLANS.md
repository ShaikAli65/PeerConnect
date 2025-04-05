# Future plans and Features

- **Further Protocol Optimization**: Continue developing and refining the custom gossip protocol for enhanced scalability.

- **Sockets Multiplexer**: Introduce an async sockets multiplexer which works on multiple connections connected to same addr and provide high level functions that expose functions like send and recv as single connection,
  but underlying mechanism select which socket to send data on, and on receive side the data should be and ordered stream,
  should respect backpressure, utilizing maximum bandwidth

## More Features

These are not planned for completion but code (Internal High Level APIs) tries it's best to be extensible to include various functionalities

- **Shared directory**: Allow users to share a directory and other peers can search for files they want

- **Building Reputation System**: Not planned to be made, will take forever

- **Calls**: Voice and Video Calls

- **Cluster-aware Hierarchical Random Walk (CHRW)**:  To Design a **search algorithm** for **clustered overlay networks** that are **network proximity-aware** (i.e., where nodes are grouped into clusters based on latency or geography) must strike a balance between **intra-cluster efficiency** and **inter-cluster reachability**.

- Nodes are **grouped into clusters** (e.g., based on proximity or domain).
- Each node maintains:
  - **Intra-cluster links** (low latency, dense connectivity).
  - A few **inter-cluster links** (sparse, long-distance links to other clusters).
- Clusters form a **virtual overlay** (like a higher-level ring or mesh).

---

### Algorithm

1. **Phase 1: Local Intra-cluster Search**  
   - Start with a **k-limited random walk** or **short flood** inside the current cluster.  
   - If the resource is found, return early.  
   - If not found, go to Phase 2.

2. **Phase 2: Inter-cluster Exploration**  
   - Forward the query to a **random set of inter-cluster neighbors**.  
   - Each of these nodes performs **Phase 1 locally** in their own cluster.
   - Continue until:
     - Resource is found.
     - A **TTL (Time To Live)** budget is exhausted.

---

### Optimizations

- **Biased Forwarding**: Favor inter-cluster links with **historically higher hit rates** (adaptive routing).
- **Cluster Index Caching**: Maintain a **cache of cluster-level resource hints**, updated passively as queries succeed.
- **Bloom Filters per Cluster**: Clusters can optionally share Bloom filters indicating which resource types they have—cheap and fast to check.

---

[back](/src_docs/README.md)
