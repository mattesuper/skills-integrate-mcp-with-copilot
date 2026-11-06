import json
import secrets
import socket
import threading
import time
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import uvicorn

from src.app import activities, app
from src.auth import hash_password, sessions


class TeacherAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.socket = socket.socket()
        cls.socket.bind(("127.0.0.1", 0))
        cls.base_url = f"http://127.0.0.1:{cls.socket.getsockname()[1]}"
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        cls.thread = threading.Thread(
            target=cls.server.run, kwargs={"sockets": [cls.socket]}, daemon=True
        )
        cls.thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started and cls.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not cls.server.started:
            cls.server.should_exit = True
            cls.thread.join(timeout=5)
            cls.socket.close()
            raise RuntimeError("Test server failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.socket.close()
        if cls.thread.is_alive():
            raise RuntimeError("Test server failed to stop")

    def setUp(self):
        self.original = deepcopy(activities)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.password = secrets.token_urlsafe(24)
        salt = secrets.token_hex(16)
        self.teachers_file = Path(self.directory.name) / "teachers.json"
        self.teachers_file.write_text(json.dumps({
            "teacher": {"salt": salt, "password_hash": hash_password(self.password, salt)}
        }))
        self.file_patch = patch("src.auth.TEACHERS_FILE", self.teachers_file)
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)
        sessions.clear()
        self.activity_path = f"/activities/{quote('Chess Club')}"
        self.email = "student@mergington.edu"

    def tearDown(self):
        activities.clear()
        activities.update(self.original)
        sessions.clear()

    def request(self, method, path, body=None, token=None):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            content = response.read().decode()
            return response.status, (
                json.loads(content) if "application/json" in response.headers["Content-Type"]
                else content
            )

    def login(self):
        status, result = self.request("POST", "/auth/login", {
            "username": "teacher", "password": self.password
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["username"], "teacher")
        self.assertNotIn("password", result)
        return result["access_token"]

    def test_public_read_access_and_private_credentials(self):
        self.assertEqual(self.request("GET", "/activities")[0], 200)
        self.assertEqual(self.request("GET", "/static/index.html")[0], 200)
        self.assertEqual(self.request("GET", "/static/teachers.json")[0], 404)
        self.assertEqual(self.request("GET", "/teachers.json")[0], 404)

    def test_every_activity_mutation_requires_login(self):
        paths = [
            ("POST", "/signup?email=" + self.email, None),
            ("DELETE", "/unregister?email=michael@mergington.edu", None),
            ("PATCH", "/requests?email=" + self.email, {"decision": "approve"}),
            ("POST", "/announcements", {"title": "Title", "content": "Body"}),
            ("PUT", "/announcements/missing", {"title": "Title", "content": "Body"}),
            ("DELETE", "/announcements/missing", None),
        ]
        for token in [None, "invalid-token"]:
            for method, suffix, body in paths:
                with self.subTest(method=method, path=suffix, token=token):
                    status, result = self.request(method, self.activity_path + suffix, body, token)
                    self.assertEqual(status, 401)
                    self.assertEqual(result["detail"], "Teacher login required")
        self.assertEqual(activities, self.original)

    def test_wrong_password_and_unknown_user_have_same_error(self):
        for username, password in [("teacher", "wrong-password"), ("unknown", self.password)]:
            with self.subTest(username=username):
                status, result = self.request("POST", "/auth/login", {
                    "username": username, "password": password
                })
                self.assertEqual(status, 401)
                self.assertEqual(result["detail"], "Invalid username or password")
        self.assertEqual(sessions, {})

    def test_invalid_login_body(self):
        for body in [{}, {"username": "", "password": "x"}, {"username": "teacher", "password": ""}]:
            self.assertEqual(self.request("POST", "/auth/login", body)[0], 422)

    def test_teacher_registration_approval_and_removal(self):
        token = self.login()
        signup = self.activity_path + "/signup?email=" + self.email
        review = self.activity_path + "/requests?email=" + self.email
        self.assertEqual(self.request("POST", signup, token=token)[0], 200)
        self.assertIn(self.email, activities["Chess Club"]["pending_requests"])
        self.assertNotIn(self.email, activities["Chess Club"]["participants"])
        self.assertEqual(self.request("POST", signup, token=token)[0], 400)
        self.assertEqual(self.request("PATCH", review, {"decision": "approve"}, token)[0], 200)
        self.assertIn(self.email, activities["Chess Club"]["participants"])
        self.assertEqual(self.request(
            "DELETE", self.activity_path + "/unregister?email=" + self.email, token=token
        )[0], 200)
        self.assertNotIn(self.email, activities["Chess Club"]["participants"])

    def test_teacher_announcement_lifecycle(self):
        token = self.login()
        path = self.activity_path + "/announcements"
        status, item = self.request("POST", path, {"title": "Title", "content": "Body"}, token)
        self.assertEqual(status, 201)
        path += "/" + item["id"]
        self.assertEqual(self.request("PUT", path, {"title": "Edit", "content": "New"}, token)[0], 200)
        self.assertEqual(self.request("DELETE", path, token=token)[0], 200)

    def test_logout_revokes_token(self):
        token = self.login()
        self.assertEqual(self.request("POST", "/auth/logout", token=token)[0], 200)
        self.assertNotIn(token, sessions)
        self.assertEqual(self.request(
            "POST", self.activity_path + "/signup?email=" + self.email, token=token
        )[0], 401)
        self.assertEqual(self.request("POST", "/auth/logout")[0], 401)
        self.assertEqual(self.request("POST", "/auth/logout", token=token)[0], 401)

    def test_expired_session_is_rejected(self):
        token = self.login()
        sessions[token] = ("teacher", time.monotonic() - 1)
        self.assertEqual(self.request(
            "POST", self.activity_path + "/signup?email=" + self.email, token=token
        )[0], 401)
        self.assertNotIn(token, sessions)

    def test_login_discards_expired_sessions(self):
        sessions["expired"] = ("teacher", time.monotonic() - 1)
        self.login()
        self.assertNotIn("expired", sessions)


if __name__ == "__main__":
    unittest.main()
