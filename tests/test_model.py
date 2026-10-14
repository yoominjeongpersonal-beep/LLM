import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from model import Ollama


class ModelTests(unittest.TestCase):
    def test_chat_http_contract(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                payload = json.dumps({"message": {"role": "assistant", "content": '{"verdict":"관망"}'}}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            model = Ollama("test-model", "http://127.0.0.1:" + str(server.server_port))
            result = model({"question": "삼성전자", "sources": []})
            self.assertEqual(result["verdict"], "관망")
            self.assertEqual(received[0][0], "/api/chat")
            self.assertFalse(received[0][1]["stream"])
            self.assertEqual(received[0][1]["format"], "json")
            self.assertEqual(json.loads(received[0][1]["messages"][1]["content"])["question"], "삼성전자")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
