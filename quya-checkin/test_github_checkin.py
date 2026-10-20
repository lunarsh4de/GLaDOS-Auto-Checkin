"""Exercise the check-in client against a local HTTP service, without secrets."""

import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests


spec = importlib.util.spec_from_file_location(
    "quya_checkin", Path(__file__).with_name("github-checkin.py")
)
checkin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkin)


class PointsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, body=None, **headers):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def do_GET(self):
        self.server.calls.append(("GET", self.path.split("?")[0]))
        if self.path.startswith("/current/points?"):
            self.respond(200, Set_Cookie="points_session=test; Path=/current")
        elif self.path == "/current/api/user/points/bootstrap":
            if "points_session=test" not in self.headers.get("Cookie", ""):
                self.respond(401)
                return
            self.respond(200, {"code": 0, "data": {
                "checked_in_today": self.server.checked_in,
            }})
        else:
            self.respond(404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.calls.append(("POST", self.path))
        if self.path == "/api/v1/auth/login":
            self.respond(200, {"code": 0, "data": {
                "access_token": "test-session-token-not-a-real-secret",
                "user": {"id": 1},
            }})
        elif self.path == "/legacy/api/user/points/checkin" or (
            self.path == "/current/api/user/points/checkin" and self.server.redirect
        ):
            self.respond(301, Location="/moved/api/user/points/checkin")
        elif self.path == "/current/api/user/points/checkin":
            self.server.checked_in = self.server.verify_success
            self.respond(200, {"code": 0, "data": {}})
        else:
            self.respond(404)


class CheckinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PointsHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join()
        cls.server.server_close()

    def setUp(self):
        self.server.calls = []
        self.server.checked_in = False
        self.server.redirect = False
        self.server.verify_success = True
        self.addCleanup(patch.stopall)
        patch.object(checkin, "API_BASE", self.origin + "/api/v1").start()
        patch.object(checkin, "POINTS_BASE", self.origin + "/current").start()

    def run_account(self, probe=False):
        return checkin.check_account("test@example.invalid", "test-password", probe)

    def test_old_host_redirect_reproduces_post_becoming_get(self):
        response = requests.post(
            self.origin + "/legacy/api/user/points/checkin", json={}, timeout=5
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.history[0].status_code, 301)
        self.assertEqual(response.request.method, "GET")

    def test_current_host_checks_in_and_verifies_status(self):
        self.assertEqual(self.run_account(), "checked_in_now")
        self.assertIn(("POST", "/current/api/user/points/checkin"), self.server.calls)
        self.assertEqual(self.server.calls[-1], ("GET", "/current/api/user/points/bootstrap"))

    def test_already_checked_in_does_not_post_again(self):
        self.server.checked_in = True
        self.assertEqual(self.run_account(), "already_checked_in")
        self.assertEqual(sum(method == "POST" for method, _ in self.server.calls), 1)

    def test_probe_does_not_check_in(self):
        self.assertEqual(self.run_account(probe=True), "ready")
        self.assertFalse(self.server.checked_in)

    def test_redirect_does_not_silently_change_the_method(self):
        self.server.redirect = True
        with self.assertRaisesRegex(RuntimeError, "Check-in was redirected"):
            self.run_account()
        self.assertNotIn(("GET", "/moved/api/user/points/checkin"), self.server.calls)

    def test_success_response_requires_verified_checkin(self):
        self.server.verify_success = False
        with self.assertRaisesRegex(RuntimeError, "could not be verified"):
            self.run_account()


if __name__ == "__main__":
    unittest.main()
