class RemotePeer:
    def __init__(self, username: str = 'admin', ip='localhost', port=8088):
        self.username = username
        self.uri = (ip, port)

    def __str__(self):
        return f'{self.username}~^~{self.uri[0]}~^~{self.uri[1]}'
