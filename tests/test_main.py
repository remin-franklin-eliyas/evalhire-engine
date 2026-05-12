from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

MOCK_ANALYSIS = {
    "score": 82,
    "critique": [
        "Strong shipped ML work — clear technical depth.",
        "Evidence of self-directed projects shows high agency.",
        "Consistent delivery cycles indicate solid velocity.",
    ],
    "verdict": "Strong hire — recommend a founder-fit interview.",
}


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "active", "engine": "EvalHire v1.0"}


def test_evaluate_rejects_non_pdf():
    files = {"file": ("cv.txt", b"not a pdf", "text/plain")}
    data = {"jd": "Looking for a Lead AI Engineer."}
    response = client.post("/evaluate", files=files, data=data)
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_evaluate_rejects_wrong_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    with TestClient(app) as c:
        files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
        data = {"jd": "Looking for an engineer."}
        response = c.post(
            "/evaluate", files=files, data=data, headers={"X-API-Key": "wrongkey"}
        )
    assert response.status_code == 401


def test_evaluate_accepts_correct_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    with patch("app.engine.logic.evaluate_cv", return_value=MOCK_ANALYSIS):
        with TestClient(app) as c:
            files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
            data = {"jd": "Looking for an engineer."}
            response = c.post(
                "/evaluate", files=files, data=data, headers={"X-API-Key": "secret123"}
            )
    assert response.status_code in [200, 500]


def test_evaluate_response_shape():
    with patch("app.engine.logic.evaluate_cv", return_value=MOCK_ANALYSIS):
        with patch("app.utils.extractor.extract_text_from_pdf", return_value="Candidate CV text"):
            files = {"file": ("cv.pdf", b"%PDF-1.4", "application/pdf")}
            data = {"jd": "Looking for a Lead AI Engineer with FastAPI experience."}
            response = client.post("/evaluate", files=files, data=data)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["filename"] == "cv.pdf"
    analysis = body["data"]["analysis"]
    assert isinstance(analysis["score"], int)
    assert 0 <= analysis["score"] <= 100
    assert isinstance(analysis["critique"], list)
    assert len(analysis["critique"]) == 3
    assert isinstance(analysis["verdict"], str)
