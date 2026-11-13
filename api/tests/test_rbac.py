"""Integration tests against the running API; fixtures use trusted DB access."""

import json
import subprocess
import sys
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.database.connection import SessionLocal
from app.models import Profile, User
from app.schemas.user import UserCreate
from app.services.user_service import create_user
from sqlalchemy import delete


class RBACTests(unittest.TestCase):
    def test_admin_bootstrap(self):
        _, token = self.own
        username = self.request("GET", "/auth/me", token=token)["username"]
        subprocess.run(
            [sys.executable, "manage_admin.py", username],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(self.request("GET", "/auth/me", token=token)["role"], "admin")
        self.request("GET", "/users/", token=token)

    def request(self, method, path, status=200, body=None, token=None):
        request = Request(
            "http://localhost:8000" + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        if token:
            request.add_header("Authorization", "Bearer " + token)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            self.assertEqual(response.status, status, (path, data))
            return json.loads(data) if data else None

    def setUp(self):
        self.ids = []
        self.addCleanup(self.cleanup)
        self.users = []
        for role in ("user", "user", "admin"):
            data = UserCreate(
                username="rbac-" + uuid.uuid4().hex[:16],
                password="Rbac-test-password",
                profile={"firstname": "RBAC", "lastname": "Test"},
            )
            with SessionLocal() as db:
                user = create_user(db, data)
                self.ids.append(user.id)
                user.role = role
                db.commit()
                login = self.request(
                    "POST",
                    "/auth/login",
                    body={"username": data.username, "password": data.password},
                )
                self.users.append((user.id, login["access_token"]))
        self.own, self.other, self.admin = self.users

    def cleanup(self):
        with SessionLocal.begin() as db:
            db.execute(delete(Profile).where(Profile.user_id.in_(self.ids)))
            db.execute(delete(User).where(User.id.in_(self.ids)))

    def test_anonymous_cannot_manage_users(self):
        for method, path, body in (
            ("GET", "/users/", None),
            ("GET", f"/users/{self.own[0]}", None),
            ("PATCH", f"/users/{self.own[0]}", {"username": "blocked"}),
            ("DELETE", f"/users/{self.own[0]}", None),
            ("PATCH", f"/users/{self.own[0]}/role", {"role": "admin"}),
        ):
            with self.subTest(method=method, path=path):
                self.request(method, path, 401, body)

    def test_user_can_manage_own_account(self):
        user_id, token = self.own
        self.assertEqual(self.request("GET", f"/users/{user_id}", token=token)["role"], "user")
        changed = self.request(
            "PATCH",
            f"/users/{user_id}",
            token=token,
            body={"profile": {"firstname": "Updated"}},
        )
        self.assertEqual(changed["profile"]["firstname"], "Updated")
        self.request("DELETE", f"/users/{user_id}", 204, token=token)
        self.request("GET", "/auth/me", 401, token=token)

    def test_user_cannot_access_other_accounts_or_roles(self):
        user_id, token = self.other[0], self.own[1]
        self.request("GET", "/users/", 403, token=token)
        self.request("GET", f"/users/{user_id}", 403, token=token)
        self.request("PATCH", f"/users/{user_id}", 403, {}, token)
        self.request("DELETE", f"/users/{user_id}", 403, token=token)
        self.request("PATCH", f"/users/{self.own[0]}/role", 403, {"role": "admin"}, token)

    def test_role_injection_is_rejected(self):
        self.request(
            "POST",
            "/users/",
            422,
            {
                "username": "injection",
                "password": "test-password",
                "role": "admin",
                "profile": {"firstname": "Test", "lastname": "User"},
            },
        )
        self.request("PATCH", f"/users/{self.own[0]}", 422, {"role": "admin"}, self.own[1])
        self.request("PATCH", f"/users/{self.own[0]}/role", 422, {"role": "owner"}, self.admin[1])

    def test_admin_can_manage_other_users(self):
        token = self.admin[1]
        users = self.request("GET", "/users/", token=token)
        self.assertIn(self.own[0], {user["id"] for user in users})
        self.request("GET", f"/users/{self.own[0]}", token=token)
        self.request(
            "PATCH",
            f"/users/{self.own[0]}",
            body={"profile": {"lastname": "Admin edit"}},
            token=token,
        )
        self.request("DELETE", f"/users/{self.other[0]}", 204, token=token)
        self.request("GET", f"/users/{self.other[0]}", 404, token=token)

    def test_role_changes_take_effect_with_existing_token(self):
        user_id, token = self.own
        self.request("GET", "/users/", 403, token=token)
        self.request("PATCH", f"/users/{user_id}/role", body={"role": "admin"}, token=self.admin[1])
        self.request("GET", "/users/", token=token)
        self.assertEqual(self.request("GET", "/auth/me", token=token)["role"], "admin")
        self.request("PATCH", f"/users/{user_id}/role", body={"role": "user"}, token=self.admin[1])
        self.request("GET", "/users/", 403, token=token)
        self.request("PATCH", f"/users/{self.other[0]}/role", 403, {"role": "admin"}, token)
