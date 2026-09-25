from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.seed import seed


def test_case_read_endpoints(engine) -> None:
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        seed(db)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        cases = client.get("/cases").json()
        assert [item["case_number"] for item in cases] == [
            "CASE-1001",
            "CASE-1002",
            "CASE-1003",
            "CASE-1004",
            "CASE-1005",
        ]
        assert cases[0]["status"] == "IN_PROGRESS"
        assert cases[1]["status"] == "OPEN"
        assert client.post("/cases/2/close").json()["status"] == "CLOSED"
        assert client.post("/cases/2/reopen").json()["status"] == "OPEN"
        response = client.get("/cases/1/activities")
        assert response.status_code == 200
        body = response.json()
        assert body[0]["redactions"][0]["ending_position"] == 27
        assert body[1]["redactions"] == []
        ai_redaction = next(item for item in body[0]["redactions"] if item["source"] == "AI")
        assert client.delete(f"/redactions/{ai_redaction['id']}").status_code == 204
        assert client.get("/cases/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_review_workflows(engine, monkeypatch) -> None:
    from app import ai_router
    from app.schemas import AIRecommendation, AIRecommendationResponse, AISummaryResponse

    class FakeProvider:
        def recommend(self, text, types):
            return AIRecommendationResponse(
                recommendations=[
                    AIRecommendation(
                        redaction_type="PERSONAL_INFO",
                        redaction_text="Daniel Kim",
                        starting_position=text.index("Daniel Kim"),
                        reason="Synthetic name",
                    )
                ]
            )

        def summarize(self, text):
            return AISummaryResponse(summary="Synthetic case summary.")

    monkeypatch.setattr(ai_router, "provider", FakeProvider())
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        seed(db)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            cases = client.get("/cases").json()
            case_id = next(c["id"] for c in cases if c["case_number"] == "CASE-1002")
            activity = client.get(f"/cases/{case_id}/activities").json()[0]
            aid = activity["id"]
            original = activity["description"]
            types = client.get("/redaction-types").json()
            assert [t["name"] for t in types] == sorted(t["name"] for t in types)
            payload = {
                "redaction_type_id": types[0]["id"],
                "redaction_text": "cust",
                "starting_position": original.index("cust"),
            }
            path = f"/activities/{aid}/redactions"
            assert client.post(path, json={**payload, "starting_position": -1}).status_code == 422
            created = client.post(path, json=payload)
            assert created.status_code == 201
            saved = created.json()
            assert saved["source"] == "MANUAL"
            assert saved["user"]["first_name"] == "Jordan"
            assert client.post(path, json=payload).status_code == 409
            rid = saved["id"]
            assert (
                client.patch(
                    f"/redactions/{rid}", json={"redaction_type_id": types[1]["id"]}
                ).status_code
                == 200
            )
            refreshed = client.get(f"/cases/{case_id}/activities").json()[0]
            assert refreshed["redactions"][0]["redaction_type"]["id"] == types[1]["id"]
            assert refreshed["description"] == original
            assert client.delete(f"/redactions/{rid}").status_code == 204
            assert client.get(f"/cases/{case_id}/activities").json()[0]["redactions"] == []
            response = client.post(f"/activities/{aid}/ai-recommendations")
            assert response.status_code == 200
            recommendation = response.json()["recommendations"][0]
            assert client.get(f"/cases/{case_id}/activities").json()[0]["redactions"] == []
            accepted = client.post(
                f"/activities/{aid}/ai-recommendations/accept", json=recommendation
            )
            assert accepted.status_code == 201
            assert accepted.json()["source"] == "AI"
            assert client.post(f"/cases/{case_id}/close").json()["status"] == "CLOSED"
            assert client.post(path, json=payload).status_code == 409
            assert client.post(f"/cases/{case_id}/reopen").json()["status"] == "IN_PROGRESS"
            assert (
                client.post(f"/cases/{case_id}/ai-summary").json()["summary"]
                == "Synthetic case summary."
            )
            assert client.get(f"/cases/{case_id}").json()["ai_summary"] == "Synthetic case summary."
    finally:
        app.dependency_overrides.clear()
