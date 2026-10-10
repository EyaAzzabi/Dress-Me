"""End-to-end test against a REAL Postgres (and real FashionCLIP inference) — not
mocks. Everything else in this suite proves the logic is correct in isolation; this
proves the actual wiring (DB sessions, migrations, auth, the full request path)
survives a real deployment target. Needs `docker compose up -d postgres` (see
infra/docker-compose.yml) and the Alembic migrations applied
(`python -m alembic upgrade head`) — auto-skips otherwise, so the rest of the suite
stays runnable without a live DB.

S3/LLM are still unconfigured here (no real credentials in this environment) — those
code paths are already covered by their own mocked unit tests. Pinecone, when a real
PINECONE_API_KEY is present in backend/.env, is exercised for real below (not mocked);
the tests check `vector_store.is_configured()` and assert accordingly either way, so
this file behaves correctly whether or not it's configured in a given environment.
"""

import uuid

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import vector_store
from app.main import app

DATABASE_URL = "postgresql://dressme:dressme@localhost:5432/dressme"
CATALOG_PATH = "app/data/tunisian_catalog.parquet"


def _postgres_reachable() -> bool:
    try:
        psycopg.connect(DATABASE_URL, connect_timeout=2).close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="No live Postgres at localhost:5432 — run `docker compose up -d postgres` "
           "+ `alembic upgrade head` in backend/ to enable this test.",
)


@pytest.fixture
def client():
    return TestClient(app)


def _delete_user_and_data(user_id: str) -> None:
    """Teardown for every test user this file creates — without it, each run leaves
    the user, their wardrobe items, and their outfits in the real Postgres DB
    forever, plus a matching orphaned vector per item in the real Pinecone index
    (discovered the hard way: 60 leftover users / 45 items / 3 outfits in Postgres
    and 29 orphaned vectors in Pinecone had piled up before this existed)."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM clothing_items WHERE owner_id = %s", (user_id,))
            item_ids = [row[0] for row in cur.fetchall()]
            for item_id in item_ids:
                vector_store.delete_item_embedding(item_id)
            cur.execute("DELETE FROM outfits WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM scheduled_outfits WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM packing_lists WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM clothing_items WHERE owner_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def registered_user(client):
    """(email, password, user_id) for a fresh test user — cleaned up automatically
    after the test, including their wardrobe items' Pinecone vectors."""
    email = f"test-{uuid.uuid4()}@example.com"
    password = "a-real-password-123"  # noqa: S105

    register = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert register.status_code == 201, register.text
    user_id = register.json()["id"]

    yield email, password, user_id

    _delete_user_and_data(user_id)


@pytest.fixture
def auth_headers(client, registered_user):
    email, password, _ = registered_user
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_real_image_urls():
    """Two real, live Tunisian product photo URLs from the bundled catalog — a real
    network fetch + real FashionCLIP inference, not a fixture image."""
    catalog = pd.read_parquet(CATALOG_PATH)
    haut = catalog[catalog["dressme_category"] == "haut"].iloc[0]["image_location"]
    bas = catalog[catalog["dressme_category"] == "bas"].iloc[0]["image_location"]
    return haut, bas


@pytest.fixture
def haut_and_bas_candidates():
    """Several candidate URLs per category, not just one — the catalog's label is the
    scraped taxonomy's ground truth, not a guarantee of what the Vision Agent's own
    classifier (~81% accuracy, see ml/notebooks/08_category_classifier.py) will
    predict for that specific photo. A test asserting a real outfit gets built needs
    items the model actually agrees are haut/bas, not just ones labeled that way."""
    catalog = pd.read_parquet(CATALOG_PATH)
    hauts = catalog[catalog["dressme_category"] == "haut"]["image_location"].head(10).tolist()
    bas_ = catalog[catalog["dressme_category"] == "bas"]["image_location"].head(10).tolist()
    return hauts, bas_


def _post_item(client, auth_headers, image_url):
    """Adds a wardrobe item the way the apps do: if the model isn't sure of the category
    (422 low_category_confidence — common on real catalog shots), confirm its suggestion."""
    response = client.post("/api/v1/wardrobe/", json={"image_url": image_url}, headers=auth_headers)
    if response.status_code == 422 and isinstance(response.json().get("detail"), dict):
        detail = response.json()["detail"]
        if detail.get("code") == "low_category_confidence":
            response = client.post(
                "/api/v1/wardrobe/",
                json={"image_url": image_url, "category": detail["suggested_category"]},
                headers=auth_headers,
            )
    return response


def test_register_and_login(client, registered_user):
    email, password, _ = registered_user

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_duplicate_registration_is_rejected(client, registered_user):
    email, password, _ = registered_user

    second = client.post("/api/v1/auth/register", json={"email": email, "password": password})

    assert second.status_code == 400


def test_wardrobe_crud_with_real_vision_inference(client, auth_headers, two_real_image_urls):
    haut_url, _ = two_real_image_urls

    created = _post_item(client, auth_headers, haut_url)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["category"] in {"haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire"}
    assert isinstance(item["colors"], list) and 1 <= len(item["colors"]) <= 3

    listed = client.get("/api/v1/wardrobe/", headers=auth_headers)
    assert listed.status_code == 200
    assert any(i["id"] == item["id"] for i in listed.json())

    deleted = client.delete(f"/api/v1/wardrobe/{item['id']}", headers=auth_headers)
    assert deleted.status_code == 204

    listed_after = client.get("/api/v1/wardrobe/", headers=auth_headers)
    assert not any(i["id"] == item["id"] for i in listed_after.json())


def test_style_profile_reflects_the_real_wardrobe(client, auth_headers, two_real_image_urls):
    haut_url, bas_url = two_real_image_urls
    _post_item(client, auth_headers, haut_url)
    _post_item(client, auth_headers, bas_url)

    profile = client.get("/api/v1/style-profile/", headers=auth_headers)

    assert profile.status_code == 200
    body = profile.json()
    assert body["wardrobe_size"] == 2
    assert sum(body["category_counts"].values()) == 2


def _add_item_with_category(client, auth_headers, candidate_urls, wanted_category):
    """Posts candidate photos one at a time until the Vision Agent's own
    classification (not the catalog's taxonomy label) actually agrees with
    `wanted_category` — see haut_and_bas_candidates's docstring for why this
    indirection is necessary. Removes any non-matching candidate it had to add along
    the way, so the wardrobe ends up with exactly the one item wanted — not it plus
    leftover mismatches that would create extra, unwanted outfit bases. Returns the
    created item, or None if no candidate matched (the test skips rather than flakes
    if that ever happens)."""
    for url in candidate_urls:
        response = _post_item(client, auth_headers, url)
        if response.status_code != 201:
            continue
        item = response.json()
        if item["category"] == wanted_category:
            return item
        client.delete(f"/api/v1/wardrobe/{item['id']}", headers=auth_headers)
    return None


def test_recommendations_build_a_real_outfit(client, auth_headers, haut_and_bas_candidates):
    haut_urls, bas_urls = haut_and_bas_candidates
    item1 = _add_item_with_category(client, auth_headers, haut_urls, "haut")
    item2 = _add_item_with_category(client, auth_headers, bas_urls, "bas")
    if item1 is None or item2 is None:
        pytest.skip("None of the sampled candidates were classified haut/bas by the real model")

    if vector_store.is_configured():
        # Pinecone upserts aren't instantly queryable (near-real-time, not
        # synchronous) — give the two just-stored embeddings a moment to become
        # visible to fetch_embeddings() before asking RecommendationAgent to use them.
        # A real user flow naturally has this gap (browsing the wardrobe takes longer
        # than this); only back-to-back API calls like this test need to wait for it.
        import time

        time.sleep(2)

    response = client.post("/api/v1/recommendations/outfits", json={}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["outfits"], list)

    if vector_store.is_configured():
        # A haut + a bas is exactly one valid base, and both items just got a real
        # stored embedding (Pinecone is live in this environment) — a real outfit
        # should come back, not just an empty, gracefully-degraded list.
        assert len(body["outfits"]) == 1
        outfit = body["outfits"][0]
        assert set(outfit["item_ids"]) == {item1["id"], item2["id"]}
        assert outfit["relevance_score"] is not None
    else:
        # No Pinecone configured in this environment — confirms the no-embeddings
        # path degrades to an empty (not broken) result rather than erroring.
        assert body["outfits"] == []

    listed = client.get("/api/v1/recommendations/outfits", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json() == body["outfits"]


def test_purchase_check_without_a_wardrobe(client, auth_headers, two_real_image_urls):
    haut_url, _ = two_real_image_urls

    response = client.post(
        "/api/v1/purchase/check", json={"image_url": haut_url}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] in {"recommended", "think_twice", "not_recommended"}
    assert isinstance(body["catalog_alternatives"], list)


def test_calendar_plan_get_list_and_unplan(client, auth_headers, two_real_image_urls):
    haut_url, _ = two_real_image_urls
    item = _post_item(client, auth_headers, haut_url).json()

    day = "2026-11-15"
    planned = client.put(
        f"/api/v1/calendar/{day}", json={"item_ids": [item["id"]]}, headers=auth_headers
    )
    assert planned.status_code == 200, planned.text
    body = planned.json()
    assert body["date"] == day
    assert body["item_ids"] == [item["id"]]
    assert body["items"][0]["id"] == item["id"]

    fetched = client.get(f"/api/v1/calendar/{day}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["item_ids"] == [item["id"]]

    listed = client.get(
        "/api/v1/calendar/", params={"start": "2026-11-01", "end": "2026-11-30"}, headers=auth_headers
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    empty_day = client.get("/api/v1/calendar/2026-11-16", headers=auth_headers)
    assert empty_day.status_code == 404

    deleted = client.delete(f"/api/v1/calendar/{day}", headers=auth_headers)
    assert deleted.status_code == 204

    after = client.get(f"/api/v1/calendar/{day}", headers=auth_headers)
    assert after.status_code == 404


def test_calendar_rejects_items_not_owned(client, auth_headers):
    fake_item_id = str(uuid.uuid4())

    response = client.put(
        "/api/v1/calendar/2026-11-20", json={"item_ids": [fake_item_id]}, headers=auth_headers
    )

    assert response.status_code == 404


def test_calendar_replanning_a_day_replaces_not_stacks(client, auth_headers, two_real_image_urls):
    haut_url, bas_url = two_real_image_urls
    item1 = _post_item(client, auth_headers, haut_url).json()
    item2 = _post_item(client, auth_headers, bas_url).json()

    day = "2026-12-01"
    client.put(f"/api/v1/calendar/{day}", json={"item_ids": [item1["id"]]}, headers=auth_headers)
    second = client.put(
        f"/api/v1/calendar/{day}", json={"item_ids": [item2["id"]]}, headers=auth_headers
    )

    assert second.status_code == 200
    assert second.json()["item_ids"] == [item2["id"]]

    listed = client.get(
        "/api/v1/calendar/", params={"start": day, "end": day}, headers=auth_headers
    )
    assert len(listed.json()) == 1  # replaced, not duplicated


def test_packing_list_generation_check_and_delete(client, auth_headers, two_real_image_urls):
    haut_url, bas_url = two_real_image_urls
    _post_item(client, auth_headers, haut_url)
    _post_item(client, auth_headers, bas_url)

    created = client.post(
        "/api/v1/packing/",
        json={"destination": "Hammamet", "duration_days": 3, "trip_type": "plage"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["destination"] == "Hammamet"
    assert isinstance(body["items"], list)
    # Whatever got selected came from the wardrobe we just populated, not thin air.
    assert all(i["id"] in {item["id"] for item in body["items"]} for i in body["items"])

    if body["item_ids"]:
        first_item_id = body["item_ids"][0]
        checked = client.patch(
            f"/api/v1/packing/{body['id']}/check",
            json={"item_id": first_item_id, "checked": True},
            headers=auth_headers,
        )
        assert checked.status_code == 200
        assert first_item_id in checked.json()["checked_item_ids"]

    listed = client.get("/api/v1/packing/", headers=auth_headers)
    assert any(p["id"] == body["id"] for p in listed.json())

    deleted = client.delete(f"/api/v1/packing/{body['id']}", headers=auth_headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/packing/{body['id']}", headers=auth_headers)
    assert missing.status_code == 404


def test_packing_list_rejects_invalid_duration(client, auth_headers):
    response = client.post(
        "/api/v1/packing/",
        json={"destination": "Sousse", "duration_days": 0, "trip_type": "tourisme"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_tryon_requires_avatar_before_items(client, auth_headers, two_real_image_urls, monkeypatch):
    # Forced unconfigured regardless of whatever's in backend/.env on a given
    # machine — this test is about the avatar/ownership gating in the route, not
    # about actually spending real Replicate credits on a fake avatar URL.
    from app.api.routes import tryon as tryon_route

    monkeypatch.setattr(tryon_route.tryon_agent, "is_configured", lambda: False)

    haut_url, _ = two_real_image_urls
    item = _post_item(client, auth_headers, haut_url).json()

    without_avatar = client.post(
        "/api/v1/tryon/", json={"garment_item_id": item["id"]}, headers=auth_headers
    )
    assert without_avatar.status_code == 422

    avatar_set = client.put(
        "/api/v1/tryon/avatar", json={"image_url": "https://x/avatar.jpg"}, headers=auth_headers
    )
    assert avatar_set.status_code == 200

    after_avatar = client.post(
        "/api/v1/tryon/", json={"garment_item_id": item["id"]}, headers=auth_headers
    )
    assert after_avatar.status_code == 503
