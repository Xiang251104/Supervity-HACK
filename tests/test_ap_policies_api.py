"""API contract tests for editable AP policies and their version history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import app
from app.middleware import AuditMiddleware
from app.models.ap import Policy, PolicyVersion
from app.security import get_current_user, verify_access


@dataclass
class PolicyApiHarness:
    client: TestClient
    session_factory: sessionmaker
    current_user: dict[str, Any]

    def add_policy(
        self,
        *,
        key: str,
        name: str | None = None,
        description: str = "A policy used by the API contract tests.",
        value_type: str = "number",
        value: Any = 1,
        options: list[Any] | None = None,
        unit: str | None = None,
        severity: str = "escalate",
        active: bool = True,
        version: int = 1,
        updated_by: str | None = "seed@example.com",
    ) -> None:
        with self.session_factory() as db:
            db.add(
                Policy(
                    key=key,
                    name=name or key.title(),
                    description=description,
                    value_type=value_type,
                    value=value,
                    options=options,
                    unit=unit,
                    severity=severity,
                    active=active,
                    version=version,
                    updated_at=datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc),
                    updated_by=updated_by,
                )
            )
            db.commit()

    def policy_state(self, key: str) -> tuple[Any, int, str | None, int]:
        with self.session_factory() as db:
            policy = db.query(Policy).filter(Policy.key == key).one()
            history_count = (
                db.query(PolicyVersion)
                .filter(PolicyVersion.policy_key == key)
                .count()
            )
            return policy.value, policy.version, policy.updated_by, history_count

    def policy_versions(self, key: str) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            versions = (
                db.query(PolicyVersion)
                .filter(PolicyVersion.policy_key == key)
                .order_by(PolicyVersion.version.desc())
                .all()
            )
            return [
                {
                    "version": row.version,
                    "value": row.value,
                    "previous_value": row.previous_value,
                    "changed_by": row.changed_by,
                    "note": row.note,
                }
                for row in versions
            ]


@pytest.fixture
def policy_api(tmp_path: Path) -> PolicyApiHarness:
    database_path = tmp_path / "ap-policies-api.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Policy.__table__.create(engine)
    PolicyVersion.__table__.create(engine)

    current_user: dict[str, Any] = {
        "email": "reviewer@example.com",
        "sub": "user-1",
        "realm_access": {"roles": ["admin", "user"]},
    }

    def override_get_db():
        db: Session = test_session()
        try:
            yield db
        finally:
            db.close()

    def override_get_current_user() -> dict[str, Any]:
        return current_user

    def override_verify_access() -> None:
        return None

    original_dependency_overrides = app.dependency_overrides.copy()
    original_user_middleware = app.user_middleware
    original_middleware_stack = app.middleware_stack
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[verify_access] = override_verify_access
    app.user_middleware = [
        middleware
        for middleware in original_user_middleware
        if middleware.cls is not AuditMiddleware
    ]
    app.middleware_stack = None

    try:
        with TestClient(app) as client:
            yield PolicyApiHarness(client, test_session, current_user)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_dependency_overrides)
        app.user_middleware = original_user_middleware
        app.middleware_stack = original_middleware_stack
        engine.dispose()
        database_path.unlink(missing_ok=True)


def test_list_is_key_ordered_and_returns_public_fields_and_active_snapshot(
    policy_api: PolicyApiHarness,
):
    policy_api.add_policy(
        key="Z-DATE",
        name="As-of date",
        description="Date used for policy evaluation.",
        value_type="date",
        value="2026-07-15",
        severity="advise",
        active=True,
        version=4,
    )
    policy_api.add_policy(
        key="A-INACTIVE",
        name="Inactive threshold",
        value=99,
        unit="MYR",
        severity="block",
        active=False,
        version=9,
    )
    policy_api.add_policy(
        key="M-MODE",
        name="Review mode",
        value_type="enum",
        value="review",
        options=["advisory", "review"],
        active=True,
        version=2,
    )

    response = policy_api.client.get("/api/ap/policies")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["snapshot_label"] == "v2.4"
    assert [item["key"] for item in body["items"]] == [
        "A-INACTIVE",
        "M-MODE",
        "Z-DATE",
    ]
    assert body["items"][1] == {
        "key": "M-MODE",
        "name": "Review mode",
        "description": "A policy used by the API contract tests.",
        "value_type": "enum",
        "value": "review",
        "options": ["advisory", "review"],
        "unit": None,
        "severity": "escalate",
        "active": True,
        "version": 2,
        "updated_at": "2026-08-01T12:30:00",
        "updated_by": "seed@example.com",
    }


@pytest.mark.parametrize(
    ("key", "value_type", "initial", "options", "replacement"),
    [
        ("NUMBER", "number", 10, None, 10.5),
        ("ENUM", "enum", "advisory", ["advisory", "review"], "review"),
        ("BOOLEAN", "boolean", False, None, True),
        ("DATE", "date", "2026-07-15", None, "2026-08-07"),
    ],
)
def test_patch_supports_each_policy_value_type(
    policy_api: PolicyApiHarness,
    key: str,
    value_type: str,
    initial: Any,
    options: list[Any] | None,
    replacement: Any,
):
    policy_api.add_policy(
        key=key,
        value_type=value_type,
        value=initial,
        options=options,
    )

    response = policy_api.client.patch(
        f"/api/ap/policies/{key}", json={"value": replacement}
    )

    assert response.status_code == 200
    assert response.json()["value"] == replacement
    assert response.json()["version"] == 2


@pytest.mark.parametrize(
    ("key", "value_type", "initial", "options", "candidate"),
    [
        ("NUMBER-STRING", "number", 10, None, "10"),
        ("NUMBER-BOOL", "number", 10, None, True),
        ("ENUM-CASE", "enum", "review", ["review", "advisory"], "Review"),
        ("ENUM-NUMBER", "enum", "review", [1, True, "review"], 1),
        ("ENUM-BOOLEAN", "enum", "review", [1, True, "review"], True),
        ("BOOLEAN-STRING", "boolean", False, None, "true"),
        ("BOOLEAN-ONE", "boolean", False, None, 1),
        ("BOOLEAN-ZERO", "boolean", True, None, 0),
        ("DATE-FORMAT", "date", "2026-07-15", None, "2026/08/07"),
        ("DATE-IMPOSSIBLE", "date", "2026-07-15", None, "2026-02-30"),
        ("UNKNOWN-TYPE", "currency", "MYR", None, "USD"),
    ],
)
def test_invalid_patch_returns_422_without_mutation_or_history(
    policy_api: PolicyApiHarness,
    key: str,
    value_type: str,
    initial: Any,
    options: list[Any] | None,
    candidate: Any,
):
    policy_api.add_policy(
        key=key,
        value_type=value_type,
        value=initial,
        options=options,
        version=7,
        updated_by="original@example.com",
    )

    response = policy_api.client.patch(
        f"/api/ap/policies/{key}", json={"value": candidate}
    )

    assert response.status_code == 422
    assert policy_api.policy_state(key) == (initial, 7, "original@example.com", 0)


def test_unknown_patch_and_history_keys_return_404(policy_api: PolicyApiHarness):
    patch_response = policy_api.client.patch(
        "/api/ap/policies/UNKNOWN", json={"value": 10}
    )
    history_response = policy_api.client.get("/api/ap/policies/UNKNOWN/history")

    assert patch_response.status_code == 404
    assert patch_response.json()["detail"] == "Policy not found"
    assert history_response.status_code == 404
    assert history_response.json()["detail"] == "Policy not found"


def test_valid_update_increments_version_and_appends_one_history_row(
    policy_api: PolicyApiHarness,
):
    policy_api.add_policy(key="LIMIT", value=100, version=3)

    response = policy_api.client.patch(
        "/api/ap/policies/LIMIT", json={"value": 125, "note": "  Raised limit  "}
    )

    assert response.status_code == 200
    assert response.json()["version"] == 4
    assert response.json()["updated_by"] == "reviewer@example.com"
    assert policy_api.policy_state("LIMIT") == (125, 4, "reviewer@example.com", 1)
    assert policy_api.policy_versions("LIMIT") == [
        {
            "version": 4,
            "value": 125,
            "previous_value": 100,
            "changed_by": "reviewer@example.com",
            "note": "Raised limit",
        }
    ]
    history = policy_api.client.get("/api/ap/policies/LIMIT/history").json()
    assert history["policy_key"] == "LIMIT"
    assert history["total"] == 1
    assert history["items"][0] == {
        "version": 4,
        "value": 125,
        "previous_value": 100,
        "changed_by": "reviewer@example.com",
        "changed_at": history["items"][0]["changed_at"],
        "note": "Raised limit",
    }
    assert datetime.fromisoformat(history["items"][0]["changed_at"])


def test_same_value_update_is_a_no_op(policy_api: PolicyApiHarness):
    policy_api.add_policy(
        key="NO-OP", value=25, version=6, updated_by="original@example.com"
    )

    response = policy_api.client.patch(
        "/api/ap/policies/NO-OP",
        json={"value": 25, "note": "This must not create history"},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 6
    assert response.json()["updated_by"] == "original@example.com"
    assert policy_api.policy_state("NO-OP") == (25, 6, "original@example.com", 0)


@pytest.mark.parametrize(
    ("claims", "expected_actor"),
    [
        (
            {
                "email": "email@example.com",
                "preferred_username": "preferred-user",
                "sub": "subject-user",
            },
            "email@example.com",
        ),
        (
            {"preferred_username": "preferred-user", "sub": "subject-user"},
            "preferred-user",
        ),
        ({"sub": "subject-user"}, "subject-user"),
        ({}, "unknown-actor"),
    ],
)
def test_update_actor_uses_authenticated_claim_fallback_order(
    policy_api: PolicyApiHarness,
    claims: dict[str, str],
    expected_actor: str,
):
    policy_api.current_user.clear()
    policy_api.current_user.update(claims)
    policy_api.add_policy(key="ACTOR", value=1)

    response = policy_api.client.patch(
        "/api/ap/policies/ACTOR", json={"value": 2}
    )

    assert response.status_code == 200
    assert response.json()["updated_by"] == expected_actor
    history = policy_api.client.get("/api/ap/policies/ACTOR/history").json()
    assert history["items"][0]["changed_by"] == expected_actor


def test_note_is_trimmed_and_limited_to_1000_characters(
    policy_api: PolicyApiHarness,
):
    policy_api.add_policy(key="NOTE", value=1)

    accepted = policy_api.client.patch(
        "/api/ap/policies/NOTE", json={"value": 2, "note": "  concise note  "}
    )
    rejected = policy_api.client.patch(
        "/api/ap/policies/NOTE", json={"value": 3, "note": "x" * 1001}
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    history = policy_api.client.get("/api/ap/policies/NOTE/history").json()
    assert history["total"] == 1
    assert history["items"][0]["note"] == "concise note"
    assert policy_api.policy_state("NOTE")[:2] == (2, 2)


def test_history_is_newest_first_and_known_policy_can_have_empty_history(
    policy_api: PolicyApiHarness,
):
    policy_api.add_policy(key="WITH-HISTORY", value=1)
    policy_api.add_policy(key="NO-HISTORY", value=50)
    assert policy_api.client.patch(
        "/api/ap/policies/WITH-HISTORY", json={"value": 2, "note": "first"}
    ).status_code == 200
    assert policy_api.client.patch(
        "/api/ap/policies/WITH-HISTORY", json={"value": 3, "note": "second"}
    ).status_code == 200

    history = policy_api.client.get("/api/ap/policies/WITH-HISTORY/history")
    empty_history = policy_api.client.get("/api/ap/policies/NO-HISTORY/history")

    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert [item["version"] for item in history.json()["items"]] == [3, 2]
    assert [item["previous_value"] for item in history.json()["items"]] == [2, 1]
    assert [item["value"] for item in history.json()["items"]] == [3, 2]
    assert [item["note"] for item in history.json()["items"]] == ["second", "first"]
    assert policy_api.policy_versions("WITH-HISTORY") == [
        {
            "version": 3,
            "value": 3,
            "previous_value": 2,
            "changed_by": "reviewer@example.com",
            "note": "second",
        },
        {
            "version": 2,
            "value": 2,
            "previous_value": 1,
            "changed_by": "reviewer@example.com",
            "note": "first",
        },
    ]
    assert empty_history.status_code == 200
    assert empty_history.json() == {
        "policy_key": "NO-HISTORY",
        "items": [],
        "total": 0,
    }
