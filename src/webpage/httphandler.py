import http.server
import socketserver
import threading
import time

from src.core import *
safe_stop = True


class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global safe_stop
        if safe_stop:
            super().do_GET()
        else:
            self.send_error(404, "Server stopped serving")


def start_serving():
    port = 40001
    global safe_stop
    safe_stop = True
    handler = MyHttpRequestHandler
    httpd = socketserver.TCPServer(("", port), handler)
    print(f"Serving at http://localhost:{port}")
    httpd.serve_forever()


def end_serving():
    global safe_stop
    safe_stop = False
    print("Server stopped serving")
    exit(0)


# threading.Thread(target=start_serving).start()
# time.sleep(5)
# end_serving()
