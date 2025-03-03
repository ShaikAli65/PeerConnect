# PeerConnect source code documentation

## System Architecture

PeerConnect follows an IPC-style design for seamless integration with the User Interface (React.js).

[diagrams](<https://excalidraw.com/?#json=JwupHwQ7QuQyK1BEYFhdl,528_biXX7getTXAvT763uw>)

## Table of Contents

| module             |                 src                 |                    docs                    | desc                               |
|:-------------------|:-----------------------------------:|:------------------------------------------:|:-----------------------------------|
| src.avails         |         [link](/src/avails)         |      [link](/src_docs/core/README.md)      | helpers, bases, utilites           |
| src.core           |          [link](/src/core)          |      [link](/src_docs/core/README.md)      | core application functionality     |
| src.managers       |        [link](/src/managers)        |    [link](/src_docs/managers/README.md)    | high level service APIs            |
| src.transfers      |       [link](/src/transfers)        |    [link](/src_docs/transfer/README.md)    | transfers files                    |
| src.conduit        |        [link](/src/conduit)         |    [link](/src_docs/conduit/README.md)     | communicating with User Interface  |
| src.configurations |     [link](/src/configurations)     | [link](/src_docs/configurations/README.md) | start up configurations            |
| src.server         |         [link](/src/server)         |                    N/A                     | connecting to peer-connect servers |
| logging            | [link](/src/managers/logmanager.py) |    [link](/src_docs/logging/README.md)     | logging configurations             |

## Legend

| notation | meaning              |
|:--------:|:---------------------|
|   WIP    | work in progress     |
|   RIP    | refactor in progress |
|   DEP    | deprecated           |
|   TBD    | To Be Decided        |
