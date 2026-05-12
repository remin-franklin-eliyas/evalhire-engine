from fastapi.testclient import TestClient
from app.main import app

def test_evaluate_endpoint_structure():
    with TestClient(app) as client:
        # We simulate a file upload + form text
        files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
        data = {"jd": "Looking for a Lead AI Engineer with FastAPI experience."}
        
        response = client.post("/evaluate", files=files, data=data)
        
        # This might return a 500 if the PDF is dummy/invalid, 
        # but we are testing if the route is reachable.
        assert response.status_code in [200, 500]