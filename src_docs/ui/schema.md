### Signals

|        Incoming         |          Outgoing           |
|:-----------------------:|:---------------------------:|
|     SEARCH_FOR_NAME     |       SEARCH_RESPONSE       |
| SEND_PEER_LIST_RESPONSE |       SEND_PEER_LIST        |
|       SET_PROFILE       |          PEER_LIST          |
|       SYNC_USERS        |       TRANSFER_UPDATE       |
|                         | REQ_PEER_NAME_FOR_DISCOVERY |
|      CONNECT_USER       |                             |

### Data

|          Incoming           |   Outgoing   |
|:---------------------------:|:------------:|
|          SEND_DIR           | SENDING_DIR  |
|          SEND_FILE          | SENDING_FILE |
|          SEND_TEXT          |  TEXT_SENT   |
| SEND_FILE_TO_MULTIPLE_PEERS |              |


**peer update schema**

```
> data = DataWeaver(
> header=HANDLE.REMOVE_PEER,
> peer_id=peer.peer_id,
> )
```

**adding peer schema**
```
> data = DataWeaver(
>   header= [NEW_PEER](#transfer_update),
>   content={
>       "name": peer.username,
>       "ip": peer.ip,
>   },
>   peer_id=peer.peer_id,
> )
``` 

**transfer completed**
```
> status_update = DataWeaver(
>   header=[TRANSFER_UPDATE](#TRANSFER_UPDATE),
>   content={
>       'item_path': str(file_item.path),
>       'received': received,
>       'transfer_id': receiver_handle.id,
>       'cancelled': True,  # gets toggled accordingly
>       'error': str(e),
>   },
>   peer_id=file_req.peer_id,
> )
```

**transfer update**
```
> status_update = DataWeaver(
>    header=HANDLE.TRANSFER_UPDATE,
>    content={
>        'item_path': str(file_item.path),
>        'received': received,  # length
>        'transfer_id': receiver_handle.id,
>    },
>    peer_id=file_req.peer_id,
>)
```

**profiles list**

```
> header = [HANDLE.PROFILE_LIST](#PROFILE_LIST)
> content = {
>     file_name : {
>         'USER' : {
>             'name' : *,
>             'id' : *,
>         },
>         'SERVER' : {
>             'ip' : *,
>             'port' : *,
>         },
>     },
>     ...
> }
```

**search response**

```
> response_data = DataWeaver(
>     header= HANDLE.SEARCH_RESPONSE,
>     content=[
>         {
>             "name": peer.username,
>             "peerId": peer.peer_id,
>             "ip": peer.ip,
>         } for peer in peer_list
>     ],
>    searchId=TBD
> )
```


### HEADERS:

#### REMOVE_PEER

> '1remove peer'

#### COMMAND

> "this is command "

#### SEARCH_RESPONSE

> "0result for search name"

#### SEND_PEER_LIST_RESPONSE

> "0result for send peer list"

#### RELOAD

> "1this is reload  "

#### POP_DIR_SELECTOR

> "1pop dir selector"

#### OPEN_FILE

> "1open file       "

#### NEW_PEER

> '1new peer'

#### REMOVE_PEER

> '1remove peer'

#### SEARCH_FOR_NAME

> "1search name"

#### SEND_PROFILES

> "1send profiles"

#### PROFILE_LIST

> "1this is a profiles list"

#### SYNC_USERS

> "1sync users"

#### CONNECT_USER

> "1connect_peer"

#### SEND_PEER_LIST

> "1send peer list"

#### VERIFICATION

> "1han verification"

#### SET_PROFILE

> "1set selected profile"

#### TRANSFER_UPDATE

> "1transfer update"

#### REQ_PEER_NAME_FOR_DISCOVERY

> '1get a peer name for discovery'

#### SEND_DIR

> "0send_a_directory"

#### SEND_FILE

> "0send_file_to_peer"

#### SEND_TEXT

> "0send_text"

#### SEND_FILE_TO_MULTIPLE_PEERS

> "0send_file_to_multiple_peers"

#### SEND_DIR_TO_MULTIPLE_PEERS

> "0send_dir_to_multiple_peers"

#### SENDING_FILE

> "0sending file"

#### SENDING_DIR

> "0send_a_directory"

#### TEXT_SENT

> "0textsent"