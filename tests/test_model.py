import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
from io import BytesIO
from urllib.error import HTTPError
from model import Claude, ModelError


class ModelTests(unittest.TestCase):
    def test_extraction_uses_its_own_schema_and_returns_draft(self):
        payload = json.dumps({"content": [{"type": "text", "text": '{"principles":[]}'}],
                              "stop_reason": "end_turn"}).encode()
        requests = []
        def receive(request, **kwargs):
            requests.append(json.loads(request.data))
            return BytesIO(payload)
        with patch("model.urlopen", side_effect=receive):
            result = Claude("test-key")({"task": "extract_viewpoint", "sources": []})
        self.assertEqual(result, {"principles": []})
        self.assertEqual(requests[0]["output_config"]["format"]["schema"]["required"], ["principles"])

    def test_separate_pools_do_not_duplicate_full_text_in_request(self):
        payload = json.dumps({"content": [{"type": "text", "text": '{}'}], "stop_reason": "end_turn"}).encode()
        requests = []
        def receive(request, **kwargs):
            requests.append(json.loads(request.data))
            return BytesIO(payload)
        record = {"id": "P1", "text": "판단 기준 원문"}
        with patch("model.urlopen", side_effect=receive):
            Claude("test-key")({"sources": [record], "perspective_sources": [record], "research_sources": []})
        sent = json.loads(requests[0]["messages"][0]["content"])
        self.assertEqual(sent["perspective_sources"][0]["text"], "판단 기준 원문")
        self.assertNotIn("sources", sent)

    def test_http_errors_are_classified_without_exposing_body(self):
        cases = [(401, 'invalid key SECRET', 'authentication'),
                 (400, 'Your credit balance is too low SECRET', 'credits'),
                 (404, 'model unavailable SECRET', 'model_not_found'),
                 (429, 'too many requests SECRET', 'rate_limit')]
        for status, message, code in cases:
            error = HTTPError('https://api.anthropic.com/v1/messages', status, 'error', {},
                              BytesIO(json.dumps({'error': {'message': message}}).encode()))
            with self.subTest(status=status), patch('model.urlopen', side_effect=error):
                with self.assertRaises(ModelError) as caught:
                    Claude('test-key')({})
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('SECRET', str(caught.exception))

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
