import socket
from collections import deque


class RecentConnections:
    def __init__(self):
        self.connections = deque(maxlen=5)

    def add_connection(self, sock):
        self.connections.append(sock)

    def remove_connection(self, sock):
        self.connections.remove(sock)

    def get_recent_connections(self):
        return list(self.connections)

# Example usage
# if __name__ == "__main__":
#     rc = RecentConnections()
#
#     # Dummy socket connections for demonstration
#     for i in range(7):
#         sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         rc.add_connection(sock)
#
#     print("Recent Connections:")
#     for conn in rc.get_recent_connections():
#         print(conn)
#
#     # Disconnect one of the sockets
#     rc.remove_connection(rc.get_recent_connections()[2])
#
#     print("\nRecent Connections after removing one:")
#     for conn in rc.get_recent_connections():
#         print(conn)
