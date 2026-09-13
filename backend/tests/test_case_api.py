from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.seed import seed


def test_case_read_endpoints(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")

    @event.listens_for(engine, "connect")
    def enable_fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
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
        assert client.get("/cases/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()
