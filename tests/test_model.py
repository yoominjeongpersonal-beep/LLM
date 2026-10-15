import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from io import BytesIO
from model import Claude


class ModelTests(unittest.TestCase):
    def test_truncated_or_refused_response_is_rejected(self):
        for reason in ("max_tokens", "refusal"):
            payload = json.dumps({"content": [{"type": "text", "text": '{"verdict":"관망"}'}],
                                  "stop_reason": reason}).encode()
            with self.subTest(reason=reason), patch("model.urlopen", return_value=BytesIO(payload)):
                with self.assertRaises(ValueError):
                    Claude("test-key")({"question": "삼성전자"})

    def test_empty_api_key_is_rejected(self):
        with self.assertRaises(ValueError):
            Claude("  ")

    def test_chat_http_contract(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))), dict(self.headers)))
                payload = json.dumps({"content": [{"type": "text", "text": '{"verdict":"관망"}'}],
                                      "stop_reason": "end_turn"}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            model = Claude("test-key", "test-model", "http://127.0.0.1:" + str(server.server_port))
            result = model({"question": "삼성전자", "sources": []})
            self.assertEqual(result["verdict"], "관망")
            self.assertEqual(received[0][0], "/v1/messages")
            self.assertEqual(received[0][2]["X-Api-Key"], "test-key")
            self.assertEqual(received[0][2]["Anthropic-Version"], "2023-06-01")
            self.assertEqual(received[0][1]["model"], "test-model")
            self.assertEqual(received[0][1]["output_config"]["format"]["type"], "json_schema")
            self.assertEqual(json.loads(received[0][1]["messages"][0]["content"])["question"], "삼성전자")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
