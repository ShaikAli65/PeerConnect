import socket
import time

# Define rate limit and throttle speed (bytes per second)
RATE_LIMIT = 1024 * 1024  # 1 MB/s
THROTTLE_SPEED = 1024  # 1 KB/s


def handle_client(client_socket):
    start_time = time.time()
    data_sent = 0

    while True:
        data = client_socket.recv(1024)  # Receive data from client
        if not data:
            break

        # Apply rate limiting
        elapsed_time = time.time() - start_time
        data_sent += len(data)
        if elapsed_time > 0:
            current_rate = data_sent / elapsed_time
            if current_rate > RATE_LIMIT:
                time.sleep(0.1)  # Delay to enforce rate limit

        # Apply download throttling
        time.sleep(len(data) / THROTTLE_SPEED)  # Simulate download throttling
        client_socket.sendall(data)  # Send data back to client

    client_socket.close()


# Example usage: Create a server socket and listen for connections
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('localhost', 8080))
server_socket.listen(5)

print('Server listening on port 8080...')

while True:
    client_socket, addr = server_socket.accept()
    print(f'Accepted connection from {addr}')
    handle_client(client_socket)
