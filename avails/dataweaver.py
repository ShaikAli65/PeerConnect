from core import *


class DataWeaver:
    def __init__(self, header: str = None, content: str = None, _id: str = None, byte_data: bytes = None):
        if byte_data:
            self.data = json.loads(byte_data)
            self.header = self.data['header']
            self.id = self.data['id']
            self.content = self.data['content']
            self.data_lock = threading.Lock()
        else:
            self.data = dict()
            self.data_lock = threading.Lock()
            self.data['header'] = header
            self.data['content'] = content
            self.data['id'] = _id

    def dump(self) -> str:
        with self.data_lock:
            return json.dumps(self.data)

    def match(self,_header: str = None,_content: str = None,_id: str = None) -> bool:
        with self.data_lock:
            if _header:
                return self.data['header'] == _header
            elif _content:
                return self.data['content'] == _content
            elif _id:
                return self.data['id'] == _id

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        with self.data_lock:
            self.data[key] = value

    def __str__(self):
        return self.data.__str__()

    def __repr__(self):
        return f'DataWeaver({self.data})'
