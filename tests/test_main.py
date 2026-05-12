from fastapi.testclient import TestClient
from app.main import app

# We initialize inside the test or use the standard constructor
client = TestClient(app)

def test_read_main():
    # Adding a context manager can sometimes resolve version-specific init issues
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "active", "engine": "EvalHire v1.0"}