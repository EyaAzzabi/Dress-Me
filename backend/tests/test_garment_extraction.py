import io

import numpy as np
import pytest
from PIL import Image

from app.agents import extraction_agent
from app.agents.extraction_agent import ExtractionAgent
from app.ml import garment_segmentation, vision_model
from app.ml.garment_segmentation import Garment, Segmentation

HAIR, FACE, TOP, PANTS, DRESS, BELT, SCARF, BAG, LEFT_SHOE, RIGHT_SHOE = 2, 11, 4, 6, 7, 8, 17, 16, 9, 10


def _person(labels, left, top_label=TOP, bottom_label=PANTS):
    """Draws a 40px-wide standing figure starting at column `left`."""
    labels[10:30, left + 10:left + 30] = FACE
    labels[30:110, left:left + 40] = top_label
    labels[110:185, left:left + 40] = bottom_label
    labels[185:205, left:left + 15] = LEFT_SHOE
    labels[185:205, left + 25:left + 40] = RIGHT_SHOE


def _segment(monkeypatch, labels):
    monkeypatch.setattr(garment_segmentation, "_label_map", lambda image: labels)
    buffer = io.BytesIO()
    Image.new("RGB", labels.shape[::-1], "gray").save(buffer, format="JPEG")
    return garment_segmentation.segment_garments(buffer.getvalue())


def test_photo_without_anyone_reports_no_person(monkeypatch):
    labels = np.zeros((200, 200), dtype=np.int64)
    labels[50:150, 50:150] = TOP  # a flat product photo: garment labels, no body parts

    result = _segment(monkeypatch, labels)

    assert result.person_detected is False
    assert result.garments == []


def test_each_garment_worn_is_cut_out_once(monkeypatch):
    labels = np.zeros((220, 200), dtype=np.int64)
    _person(labels, 80)

    result = _segment(monkeypatch, labels)

    assert result.person_detected is True
    assert sorted(g.category for g in result.garments) == ["bas", "chaussures", "haut"]
    assert all(g.image.size[0] == g.image.size[1] for g in result.garments)


def test_two_people_wearing_tops_give_two_tops(monkeypatch):
    labels = np.zeros((220, 300), dtype=np.int64)
    _person(labels, 20)
    _person(labels, 200)

    result = _segment(monkeypatch, labels)

    assert [g.category for g in result.garments].count("haut") == 2


def test_dress_split_by_a_bag_in_front_stays_one_garment(monkeypatch):
    labels = np.zeros((220, 200), dtype=np.int64)
    _person(labels, 80, top_label=DRESS, bottom_label=DRESS)
    labels[90:130, 70:130] = BAG  # cuts the dress in two

    result = _segment(monkeypatch, labels)

    assert sorted(g.category for g in result.garments) == ["chaussures", "robe", "sac"]


def test_a_coherent_belt_is_kept_but_scattered_scarf_pixels_are_not(monkeypatch):
    labels = np.zeros((220, 200), dtype=np.int64)
    _person(labels, 80)
    labels[105:115, 80:120] = BELT
    for row in range(32, 102, 14):  # patterned top mislabeled as scarf here and there
        labels[row:row + 8, 82 + (row % 3) * 12:92 + (row % 3) * 12] = SCARF

    result = _segment(monkeypatch, labels)

    assert [g.category for g in result.garments].count("accessoire") == 1


def test_cohesion_measures_the_largest_blob():
    mask = np.zeros((10, 10), dtype=bool)
    mask[0:3, 0:3] = True  # 9 px
    mask[7:10, 7:8] = True  # 3 px

    assert garment_segmentation._cohesion(mask) == pytest.approx(9 / 12)


class _FakeStorage:
    def __init__(self):
        self.uploads = []

    def upload_image(self, content, content_type):
        self.uploads.append(content)
        return f"http://storage/crop-{len(self.uploads)}.jpg"


class _FakeResponse:
    content = b"photo"

    def raise_for_status(self):
        pass


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(extraction_agent.httpx, "get", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(vision_model, "embed_image_bytes", lambda content: np.zeros(512))
    monkeypatch.setattr(vision_model, "predict_color", lambda embedding: "noir")
    monkeypatch.setattr(vision_model, "predict_category", lambda embedding: "haut")
    agent = ExtractionAgent.__new__(ExtractionAgent)
    agent.storage = _FakeStorage()
    return agent


def test_agent_uploads_one_cut_out_per_garment(monkeypatch, agent):
    image = Image.new("RGB", (10, 10), "white")
    monkeypatch.setattr(garment_segmentation, "segment_garments", lambda content: Segmentation(
        person_detected=True,
        garments=[Garment("bas", 0.4, image), Garment("chaussures", 0.05, image)],
    ))

    result = agent.run(image_url="http://storage/photo.jpg")

    assert result["person_detected"] is True
    assert [g["category"] for g in result["garments"]] == ["bas", "chaussures"]
    assert [g["image_url"] for g in result["garments"]] == [
        "http://storage/crop-1.jpg", "http://storage/crop-2.jpg"]


def test_agent_tells_a_jacket_from_a_top(monkeypatch, agent):
    image = Image.new("RGB", (10, 10), "white")
    monkeypatch.setattr(garment_segmentation, "segment_garments", lambda content: Segmentation(
        person_detected=True, garments=[Garment("haut", 0.5, image)]))
    monkeypatch.setattr(extraction_agent, "_upper_body_category", lambda embedding: "veste")

    result = agent.run(image_url="http://storage/photo.jpg")

    assert result["garments"][0]["category"] == "veste"


def test_product_photo_is_returned_whole(monkeypatch, agent):
    monkeypatch.setattr(garment_segmentation, "segment_garments",
                        lambda content: Segmentation(person_detected=False, garments=[]))

    result = agent.run(image_url="http://storage/photo.jpg")

    assert result["person_detected"] is False
    assert result["garments"] == [
        {"category": "haut", "color": "noir", "image_url": "http://storage/photo.jpg", "share": 1.0}]
    assert agent.storage.uploads == []
