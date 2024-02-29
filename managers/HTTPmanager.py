import http.server
import socketserver
import webbrowser


def serve_page():
    PORT = 8000
    Handler = http.server.SimpleHTTPRequestHandler

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at https://localhost:{PORT}")