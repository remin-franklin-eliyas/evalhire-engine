"""
Tests for auth routes (/auth/register, /auth/login, /auth/me),
the history endpoint (/history), and the free-tier evaluation cap.

All tests use the `db_client` fixture from conftest.py which wires the app
to a fresh in-memory SQLite database and tears it down after each test.
"""
from unittest.mock import patch

MOCK_ANALYSIS = {
    "score": 75,
    "critique": ["Good depth.", "High agency.", "Fast mover."],
    "verdict": "Strong hire.",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _register(client, email="user@example.com", password="password123"):
    return client.post("/auth/register", json={"email": email, "password": password})

def _token(client, email="user@example.com", password="password123"):
    res = _register(client, email, password)
    return res.json()["access_token"]

def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Registration ───────────────────────────────────────────────────────────────

def test_register_success(db_client):
    res = _register(db_client)
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert body["email"] == "user@example.com"
    assert body["token_type"] == "bearer"


def test_register_duplicate_email(db_client):
    _register(db_client)
    res = _register(db_client)  # same email
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_register_short_password(db_client):
    res = _register(db_client, password="short")
    assert res.status_code == 400
    assert "8 characters" in res.json()["detail"]


def test_register_invalid_email(db_client):
    res = db_client.post("/auth/register", json={"email": "notanemail", "password": "password123"})
    assert res.status_code == 422


# ── Login ──────────────────────────────────────────────────────────────────────

def test_login_success(db_client):
    _register(db_client)
    res = db_client.post("/auth/login", json={"email": "user@example.com", "password": "password123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(db_client):
    _register(db_client)
    res = db_client.post("/auth/login", json={"email": "user@example.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_login_unknown_email(db_client):
    res = db_client.post("/auth/login", json={"email": "ghost@example.com", "password": "password123"})
    assert res.status_code == 401


# ── /auth/me ───────────────────────────────────────────────────────────────────

def test_me_requires_token(db_client):
    res = db_client.get("/auth/me")
    assert res.status_code == 401


def test_me_with_valid_token(db_client):
    token = _token(db_client)
    res = db_client.get("/auth/me", headers=_auth_headers(token))
    assert res.status_code == 200
    assert res.json()["email"] == "user@example.com"


def test_me_with_invalid_token(db_client):
    res = db_client.get("/auth/me", headers={"Authorization": "Bearer totally.fake.token"})
    assert res.status_code == 401


# ── /history ───────────────────────────────────────────────────────────────────

def test_history_requires_auth(db_client):
    res = db_client.get("/history")
    assert res.status_code == 401


def test_history_empty_for_new_user(db_client):
    token = _token(db_client)
    res = db_client.get("/history", headers=_auth_headers(token))
    assert res.status_code == 200
    assert res.json() == []


def test_history_populated_after_evaluate(db_client):
    token = _token(db_client)
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            res = db_client.post(
                "/evaluate",
                files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                data={"jd": "We need an engineer."},
                headers=_auth_headers(token),
            )
    assert res.status_code == 200

    history = db_client.get("/history", headers=_auth_headers(token)).json()
    assert len(history) == 1
    assert history[0]["filename"] == "cv.pdf"
    assert history[0]["score"] == 75
    assert history[0]["verdict"] == "Strong hire."


def test_history_isolated_between_users(db_client):
    token_a = _token(db_client, email="a@example.com")
    token_b = _token(db_client, email="b@example.com")

    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            db_client.post(
                "/evaluate",
                files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                data={"jd": "Engineer role."},
                headers=_auth_headers(token_a),
            )

    # User B should see empty history
    history_b = db_client.get("/history", headers=_auth_headers(token_b)).json()
    assert history_b == []

    # User A should see 1 item
    history_a = db_client.get("/history", headers=_auth_headers(token_a)).json()
    assert len(history_a) == 1


# ── Free tier cap ──────────────────────────────────────────────────────────────

def test_free_tier_allows_up_to_limit(db_client):
    from app.main import FREE_TIER_MONTHLY_LIMIT
    token = _token(db_client)
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            for _ in range(FREE_TIER_MONTHLY_LIMIT):
                res = db_client.post(
                    "/evaluate",
                    files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                    data={"jd": "Engineer."},
                    headers=_auth_headers(token),
                )
                assert res.status_code == 200


def test_free_tier_blocks_on_exceeded(db_client):
    from app.main import FREE_TIER_MONTHLY_LIMIT
    token = _token(db_client)
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            for _ in range(FREE_TIER_MONTHLY_LIMIT):
                db_client.post(
                    "/evaluate",
                    files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                    data={"jd": "Engineer."},
                    headers=_auth_headers(token),
                )
            # One more — should be blocked
            res = db_client.post(
                "/evaluate",
                files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                data={"jd": "Engineer."},
                headers=_auth_headers(token),
            )
    assert res.status_code == 429
    assert "Free tier limit reached" in res.json()["detail"]
    assert "Upgrade to Pro" in res.json()["detail"]


def test_free_tier_not_applied_without_auth(db_client):
    """Anonymous API-key callers are not subject to the free tier cap."""
    from app.main import FREE_TIER_MONTHLY_LIMIT
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            for _ in range(FREE_TIER_MONTHLY_LIMIT + 1):
                res = db_client.post(
                    "/evaluate",
                    files={"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")},
                    data={"jd": "Engineer."},
                    # No Authorization header — X-API-Key path
                )
                assert res.status_code == 200


def test_batch_free_tier_blocks_when_pdf_count_exceeds_quota(db_client):
    from app.main import FREE_TIER_MONTHLY_LIMIT
    token = _token(db_client)
    pdf_files = [
        ("files", (f"cv{i}.pdf", b"%PDF-1.4", "application/pdf"))
        for i in range(FREE_TIER_MONTHLY_LIMIT + 1)
    ]
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="CV text"):
            res = db_client.post(
                "/evaluate/batch",
                files=pdf_files,
                data={"jd": "Engineer."},
                headers=_auth_headers(token),
            )
    assert res.status_code == 429
    assert "Free tier limit reached" in res.json()["detail"]
