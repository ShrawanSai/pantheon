from __future__ import annotations

import asyncio
import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import Base, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app
from apps.api.app.services.billing.enforcement import set_enforcement_override


class AdminSettingsRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = async_sessionmaker(
            bind=cls.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        cls.admin_user_id = "admin-settings-user"
        cls.admin_email = "admin-settings-user@example.com"
        cls.non_admin_user_id = "regular-settings-user"
        cls.non_admin_email = "regular-settings-user@example.com"

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": cls.current_user_id, "email": cls.current_user_email}

        cls._prev_admin_ids = os.environ.get("ADMIN_USER_IDS")
        cls._prev_low_balance = os.environ.get("LOW_BALANCE_THRESHOLD")
        cls._prev_pricing_version = os.environ.get("PRICING_VERSION")
        cls._prev_enforcement_default = os.environ.get("CREDIT_ENFORCEMENT_ENABLED")
        os.environ["ADMIN_USER_IDS"] = cls.admin_user_id
        os.environ["LOW_BALANCE_THRESHOLD"] = "5.0"
        os.environ["PRICING_VERSION"] = "2026-02-20"
        os.environ["CREDIT_ENFORCEMENT_ENABLED"] = "false"
        cls.current_user_id = cls.admin_user_id
        cls.current_user_email = cls.admin_email
        get_settings.cache_clear()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

        async def seed_users() -> None:
            async with cls.session_factory() as session:
                for user_id, email in [
                    (cls.admin_user_id, cls.admin_email),
                    (cls.non_admin_user_id, cls.non_admin_email),
                ]:
                    existing = await session.get(User, user_id)
                    if existing is None:
                        session.add(User(id=user_id, email=email))
                await session.commit()

        asyncio.run(seed_users())

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        if cls._prev_admin_ids is None:
            os.environ.pop("ADMIN_USER_IDS", None)
        else:
            os.environ["ADMIN_USER_IDS"] = cls._prev_admin_ids
        if cls._prev_low_balance is None:
            os.environ.pop("LOW_BALANCE_THRESHOLD", None)
        else:
            os.environ["LOW_BALANCE_THRESHOLD"] = cls._prev_low_balance
        if cls._prev_pricing_version is None:
            os.environ.pop("PRICING_VERSION", None)
        else:
            os.environ["PRICING_VERSION"] = cls._prev_pricing_version
        if cls._prev_enforcement_default is None:
            os.environ.pop("CREDIT_ENFORCEMENT_ENABLED", None)
        else:
            os.environ["CREDIT_ENFORCEMENT_ENABLED"] = cls._prev_enforcement_default
        get_settings.cache_clear()
        set_enforcement_override(None)

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def tearDown(self) -> None:
        self.__class__.current_user_id = self.__class__.admin_user_id
        self.__class__.current_user_email = self.__class__.admin_email
        set_enforcement_override(None)
        get_settings.cache_clear()

    def test_get_settings_returns_defaults(self) -> None:
        response = self.client.get("/api/v1/admin/settings")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["enforcement_enabled"], False)
        self.assertEqual(body["enforcement_source"], "config")
        self.assertEqual(body["low_balance_threshold"], 5.0)
        self.assertEqual(body["pricing_version"], "2026-02-20")

    def test_patch_enforcement_sets_override(self) -> None:
        patch_response = self.client.patch("/api/v1/admin/settings/enforcement", json={"enabled": True})
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(
            patch_response.json(),
            {"enforcement_enabled": True, "source": "override"},
        )
        get_response = self.client.get("/api/v1/admin/settings")
        self.assertEqual(get_response.status_code, 200)
        body = get_response.json()
        self.assertEqual(body["enforcement_enabled"], True)
        self.assertEqual(body["enforcement_source"], "override")

    def test_delete_enforcement_clears_override(self) -> None:
        patch_response = self.client.patch("/api/v1/admin/settings/enforcement", json={"enabled": True})
        self.assertEqual(patch_response.status_code, 200)
        delete_response = self.client.delete("/api/v1/admin/settings/enforcement")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(
            delete_response.json(),
            {"enforcement_enabled": False, "source": "config"},
        )
        get_response = self.client.get("/api/v1/admin/settings")
        self.assertEqual(get_response.status_code, 200)
        body = get_response.json()
        self.assertEqual(body["enforcement_enabled"], False)
        self.assertEqual(body["enforcement_source"], "config")

    def test_patch_enforcement_non_admin_forbidden(self) -> None:
        self.__class__.current_user_id = self.__class__.non_admin_user_id
        self.__class__.current_user_email = self.__class__.non_admin_email
        response = self.client.patch("/api/v1/admin/settings/enforcement", json={"enabled": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Admin access required."})


if __name__ == "__main__":
    unittest.main()
