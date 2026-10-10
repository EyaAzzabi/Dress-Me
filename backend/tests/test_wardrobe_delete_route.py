import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app

client = TestClient(app)


class _FakeUser:
    id = uuid.uuid4()


class _FakeItem:
    id = uuid.uuid4()


class _FakeQuery:
    def __init__(self, item):
        self.item = item
        self.filters = None

    def filter(self, *filters):
        self.filters = filters
        return self

    def first(self):
        return self.item

    def delete(self):  # wear-log cleanup
        return 0


class _FakeDb:
    def __init__(self, item):
        self.query_result = _FakeQuery(item)
        self.deleted = None
        self.committed = False

    def query(self, _model):
        return self.query_result

    def delete(self, item):
        self.deleted = item

    def commit(self):
        self.committed = True


@pytest.fixture
def fake_db():
    db = _FakeDb(_FakeItem())
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_delete_wardrobe_item_accepts_uuid_path_parameter(fake_db, monkeypatch):
    deleted_embeddings = []
    monkeypatch.setattr(
        "app.agents.metadata_agent.vector_store.delete_item_embedding",
        lambda item_id: deleted_embeddings.append(item_id),
    )

    response = client.delete(f"/api/v1/wardrobe/{_FakeItem.id}")

    assert response.status_code == 204
    assert fake_db.deleted is fake_db.query_result.item
    assert fake_db.committed
    assert deleted_embeddings == [fake_db.query_result.item.id]


def test_delete_wardrobe_item_rejects_invalid_uuid(fake_db):
    response = client.delete("/api/v1/wardrobe/not-a-uuid")

    assert response.status_code == 422
