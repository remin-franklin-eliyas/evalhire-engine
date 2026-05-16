"""
Tests for Phase 1 features:
  - Persona Marketplace (GET/POST /personas, GET /personas/{id})
  - persona_id in /evaluate (dimensions, percentile, use_count)
  - POST /compare (ranked side-by-side comparison)
  - Dimensions + percentile fields in /history

All tests use the `db_client` fixture from conftest.py.
System personas are seeded from the real DB at startup — the test DB starts empty,
so tests create their own personas via POST /personas.
"""
from unittest.mock import patch

MOCK_ANALYSIS = {
    "score": 75,
    "critique": ["Good depth.", "High agency.", "Fast mover."],
    "verdict": "Strong hire.",
    "dimensions": {},
}

MOCK_ANALYSIS_WITH_DIMS = {
    "score": 80,
    "critique": ["Solid.", "Shows ownership.", "Moves fast."],
    "verdict": "Hire.",
    "dimensions": {"Agency": 8, "Technical Depth": 9, "Velocity": 7},
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _register(client, email="p@example.com", password="password123"):
    return client.post("/auth/register", json={"email": email, "password": password})

def _token(client, email="p@example.com", password="password123"):
    return _register(client, email, password).json()["access_token"]

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── GET /personas ──────────────────────────────────────────────────────────────

def test_list_personas_returns_list(db_client):
    res = db_client.get("/personas")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_personas_pagination(db_client):
    res = db_client.get("/personas?skip=0&limit=5")
    assert res.status_code == 200
    assert len(res.json()) <= 5


# ── POST /personas ─────────────────────────────────────────────────────────────

def test_create_persona_requires_auth(db_client):
    res = db_client.post("/personas", json={
        "name": "Test", "prompt": "You are a tester.", "dimensions": []
    })
    assert res.status_code == 401


def test_create_persona_success(db_client):
    token = _token(db_client)
    res = db_client.post("/personas", json={
        "name": "My Persona",
        "description": "A custom hiring lens.",
        "prompt": "You are a demanding senior engineer.",
        "dimensions": ["Agency", "Technical Depth"],
        "is_public": True,
    }, headers=_auth(token))
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "My Persona"
    assert body["dimensions"] == ["Agency", "Technical Depth"]
    assert body["is_system"] is False
    assert body["use_count"] == 0
    assert "id" in body


def test_create_persona_rejects_empty_name(db_client):
    token = _token(db_client)
    res = db_client.post("/personas", json={
        "name": "  ", "prompt": "Some prompt.", "dimensions": []
    }, headers=_auth(token))
    assert res.status_code == 400
    assert "name" in res.json()["detail"].lower()


def test_create_persona_rejects_empty_prompt(db_client):
    token = _token(db_client)
    res = db_client.post("/personas", json={
        "name": "Valid Name", "prompt": "", "dimensions": []
    }, headers=_auth(token))
    assert res.status_code == 400
    assert "prompt" in res.json()["detail"].lower()


# ── GET /personas/{id} ─────────────────────────────────────────────────────────

def test_get_persona_by_id(db_client):
    token = _token(db_client)
    create_res = db_client.post("/personas", json={
        "name": "Lookup Test", "prompt": "Be strict.", "dimensions": ["Focus"],
    }, headers=_auth(token))
    persona_id = create_res.json()["id"]

    res = db_client.get(f"/personas/{persona_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Lookup Test"


def test_get_persona_404(db_client):
    res = db_client.get("/personas/999999")
    assert res.status_code == 404


# ── /evaluate with persona_id ──────────────────────────────────────────────────

def test_evaluate_with_persona_id_increments_use_count(db_client):
    token = _token(db_client)
    # Create a persona
    create_res = db_client.post("/personas", json={
        "name": "Strict CTO",
        "prompt": "You are a strict CTO.",
        "dimensions": ["Agency", "Technical Depth", "Velocity"],
    }, headers=_auth(token))
    assert create_res.status_code == 201
    persona_id = create_res.json()["id"]
    assert create_res.json()["use_count"] == 0

    # Evaluate with that persona_id
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS_WITH_DIMS):
        with patch("app.main.extract_text_from_pdf", return_value="Candidate text"):
            files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
            data = {"jd": "We need a CTO.", "persona_id": persona_id}
            res = db_client.post(
                "/evaluate", files=files, data=data, headers=_auth(token)
            )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "dimensions" in body["data"]["analysis"]

    # Check use_count incremented
    updated = db_client.get(f"/personas/{persona_id}")
    assert updated.json()["use_count"] == 1


def test_evaluate_with_persona_id_stores_dimensions_in_history(db_client):
    token = _token(db_client)
    create_res = db_client.post("/personas", json={
        "name": "Dims Persona",
        "prompt": "Evaluate with dimensions.",
        "dimensions": ["Agency", "Technical Depth", "Velocity"],
    }, headers=_auth(token))
    persona_id = create_res.json()["id"]

    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS_WITH_DIMS):
        with patch("app.main.extract_text_from_pdf", return_value="Candidate text"):
            files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
            data = {"jd": "We need an engineer.", "persona_id": persona_id}
            db_client.post("/evaluate", files=files, data=data, headers=_auth(token))

    history = db_client.get("/history", headers=_auth(token))
    assert history.status_code == 200
    items = history.json()
    assert len(items) >= 1
    item = items[0]
    assert item["persona_id"] == persona_id
    assert item["dimensions"] == {"Agency": 8, "Technical Depth": 9, "Velocity": 7}


def test_evaluate_persona_id_404(db_client):
    token = _token(db_client)
    with patch("app.main.extract_text_from_pdf", return_value="Candidate text"):
        files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
        data = {"jd": "Some JD.", "persona_id": 999999}
        res = db_client.post(
            "/evaluate", files=files, data=data, headers=_auth(token)
        )
    assert res.status_code == 404


# ── POST /compare ──────────────────────────────────────────────────────────────

def test_compare_requires_auth(db_client):
    files = [
        ("files", ("a.pdf", b"%PDF", "application/pdf")),
        ("files", ("b.pdf", b"%PDF", "application/pdf")),
    ]
    res = db_client.post("/compare", files=files, data={"jd": "Some JD."})
    assert res.status_code == 401


def test_compare_requires_at_least_two_files(db_client):
    token = _token(db_client)
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="text"):
            files = [("files", ("a.pdf", b"%PDF", "application/pdf"))]
            res = db_client.post(
                "/compare", files=files,
                data={"jd": "Some JD."}, headers=_auth(token)
            )
    assert res.status_code == 400
    assert "2" in res.json()["detail"]


def test_compare_response_shape_and_sorted(db_client):
    token = _token(db_client)

    call_count = {"n": 0}
    scores = [90, 60]

    def mock_evaluate_cv(*args, **kwargs):
        score = scores[call_count["n"] % 2]
        call_count["n"] += 1
        return {
            "score": score,
            "critique": ["A.", "B.", "C."],
            "verdict": f"Score {score}",
            "dimensions": {},
        }

    with patch("app.main.evaluate_cv", side_effect=mock_evaluate_cv):
        with patch("app.main.extract_text_from_pdf", return_value="Candidate text"):
            files = [
                ("files", ("alice.pdf", b"%PDF-1.4", "application/pdf")),
                ("files", ("bob.pdf", b"%PDF-1.4", "application/pdf")),
            ]
            res = db_client.post(
                "/compare", files=files,
                data={"jd": "We need an engineer."}, headers=_auth(token)
            )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "jd_preview" in body
    results = body["results"]
    assert len(results) == 2
    # Sorted descending by score
    assert results[0]["score"] >= results[1]["score"]
    for item in results:
        assert "filename" in item
        assert "score" in item
        assert "verdict" in item
        assert "dimensions" in item


def test_compare_with_persona_id(db_client):
    token = _token(db_client)
    create_res = db_client.post("/personas", json={
        "name": "Compare Persona",
        "prompt": "You compare candidates.",
        "dimensions": ["Agency", "Velocity"],
    }, headers=_auth(token))
    persona_id = create_res.json()["id"]

    with patch("app.main.evaluate_cv", return_value={
        "score": 70, "critique": ["Ok.", "Ok.", "Ok."],
        "verdict": "Maybe.", "dimensions": {"Agency": 7, "Velocity": 8},
    }):
        with patch("app.main.extract_text_from_pdf", return_value="text"):
            files = [
                ("files", ("a.pdf", b"%PDF", "application/pdf")),
                ("files", ("b.pdf", b"%PDF", "application/pdf")),
            ]
            res = db_client.post(
                "/compare", files=files,
                data={"jd": "JD here.", "persona_id": persona_id},
                headers=_auth(token),
            )

    assert res.status_code == 200
    body = res.json()
    assert body["persona_name"] == "Compare Persona"
    assert body["results"][0]["dimensions"] == {"Agency": 7, "Velocity": 8}

    # use_count should have incremented by 2 (one per successful file)
    updated = db_client.get(f"/personas/{persona_id}")
    assert updated.json()["use_count"] == 2


def test_compare_skips_non_pdf(db_client):
    token = _token(db_client)
    with patch("app.main.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.main.extract_text_from_pdf", return_value="text"):
            files = [
                ("files", ("cv.txt", b"not a pdf", "text/plain")),
                ("files", ("cv.pdf", b"%PDF-1.4", "application/pdf")),
            ]
            res = db_client.post(
                "/compare", files=files,
                data={"jd": "JD."}, headers=_auth(token),
            )
    assert res.status_code == 200
    results = res.json()["results"]
    skipped = [r for r in results if r.get("error")]
    assert len(skipped) == 1
    assert skipped[0]["filename"] == "cv.txt"
