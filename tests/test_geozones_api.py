"""Геозоны через API: CRUD, валидация и живой β в сводке съёмки.

Требуют таблицу route_geozones — если миграция ещё не накатана, тесты
пропускаются фикстурой geozone_schema, а не краснеют.
"""

from __future__ import annotations

import csv
import io

import pytest
from sqlmodel import Session, select

from domain.entities import PipelineArtifactType, PipelineRunStatus
from infrastructure.database.models import (
    Assignment,
    City,
    PipelineArtifact,
    PipelineRun,
    Route,
)
from infrastructure.database.session import engine
from pipeline_contracts.artifacts import TRACK_CSV_FIELDS, TrackCsvRow
from pipeline_contracts.domain import FinalStatus

RUN_ID = "run-geo"
TRACKS_KEY = f"runs/{RUN_ID}/artifacts/tracks.csv"


def _geozones_url(city_slug: str, route_slug: str) -> str:
    return f"/api/v1/cities/{city_slug}/routes/{route_slug}/geozones"


def _track(track_id, object_id, brand, best_ts, attention, conf, visible):
    status = FinalStatus.DETECTED_BRAND if brand != "other" else FinalStatus.OTHER
    return TrackCsvRow(
        run_id=RUN_ID,
        source_path="in.mp4",
        track_id=track_id,
        object_id=object_id,
        first_frame_index=0,
        last_frame_index=10,
        first_timestamp_sec=best_ts,
        last_timestamp_sec=best_ts,
        visible_duration_sec=1.0,
        detections_count=5,
        best_crop_path="crops/x.jpg",
        best_timestamp_sec=best_ts,
        attention_seconds=attention,
        confidence_coef=conf,
        final_brand=brand if brand != "other" else "",
        final_brand_conf=0.9,
        final_status=status,
        business_brand=brand,
        business_visible=visible,
        final_status_reason="ok",
        track_confirmed=True,
        manual_review_required=False,
    )


def _tracks_csv(rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TRACK_CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_csv_row())
    return buffer.getvalue().encode("utf-8")


def _route_id(city_slug: str, route_slug: str) -> str:
    with Session(engine) as session:
        route = session.exec(
            select(Route)
            .join(City, City.cities_id == Route.cities_id)
            .where(City.slug == city_slug, Route.slug == route_slug)
        ).first()
        return route.routes_id


def _seed_completed_run(routes_id: str, *, with_assignment: bool) -> None:
    """Завершённая съёмка с артефактом TRACKS. CSV кладём отдельно в storage."""
    with Session(engine) as session:
        assignment_id = None
        if with_assignment:
            assignment = Assignment(routes_id=routes_id, sequence_number=1)
            session.add(assignment)
            session.flush()
            assignment_id = assignment.assignments_id
        session.add(
            PipelineRun(
                pipeline_runs_id=RUN_ID,
                source_name="in.mp4",
                source_object_key=f"runs/{RUN_ID}/source/in.mp4",
                source_size_bytes=1,
                duration_sec=40.0,
                status=PipelineRunStatus.COMPLETED.value,
                assignments_id=assignment_id,
            )
        )
        session.flush()
        session.add(
            PipelineArtifact(
                pipeline_runs_id=RUN_ID,
                artifact_type=PipelineArtifactType.TRACKS.value,
                object_key=TRACKS_KEY,
                content_type="text/csv",
                size_bytes=1,
            )
        )
        session.commit()


def _visibility_index(client, run_id: str) -> float:
    body = client.get(f"/api/v1/runs/{run_id}/summary").json()["data"]
    return body["totals"]["visibility_index"]


# --- CRUD и валидация ------------------------------------------------------


def test_crud_lifecycle(client, geozone_schema, city_route):
    city_slug, route_slug = city_route
    base = _geozones_url(city_slug, route_slug)

    assert client.get(base).json()["data"] == []

    created = client.post(
        base,
        json={"name": "Центр", "start_fraction": 0.35, "end_fraction": 0.6, "coefficient": 1.5},
    )
    assert created.status_code == 201
    geozone_id = created.json()["data"]["id"]

    # Пересечение запрещено, стык впритык — разрешён.
    overlap = client.post(
        base,
        json={"name": "X", "start_fraction": 0.5, "end_fraction": 0.7, "coefficient": 1.2},
    )
    assert overlap.status_code == 409
    adjacent = client.post(
        base,
        json={"name": "Город", "start_fraction": 0.6, "end_fraction": 0.8, "coefficient": 1.2},
    )
    assert adjacent.status_code == 201

    listed = client.get(base).json()["data"]
    assert [zone["start_fraction"] for zone in listed] == [0.35, 0.6]

    patched = client.patch(f"/api/v1/geozones/{geozone_id}", json={"coefficient": 2.0})
    assert patched.json()["data"]["coefficient"] == 2.0

    assert client.delete(f"/api/v1/geozones/{geozone_id}").status_code == 204
    assert len(client.get(base).json()["data"]) == 1


def test_patch_into_overlap_conflicts(client, geozone_schema, city_route):
    city_slug, route_slug = city_route
    base = _geozones_url(city_slug, route_slug)
    client.post(
        base,
        json={"name": "Центр", "start_fraction": 0.35, "end_fraction": 0.6, "coefficient": 1.5},
    )
    city = client.post(
        base,
        json={"name": "Город", "start_fraction": 0.6, "end_fraction": 0.8, "coefficient": 1.2},
    ).json()["data"]
    # Растянуть «Город» назад в «Центр» — пересечение.
    conflict = client.patch(f"/api/v1/geozones/{city['id']}", json={"start_fraction": 0.4})
    assert conflict.status_code == 409


def test_bad_bounds_rejected(client, geozone_schema, city_route):
    city_slug, route_slug = city_route
    base = _geozones_url(city_slug, route_slug)
    # start == end — 400 (сервис); вне [0,1] и coef ≤ 0 — 422 (Pydantic).
    assert client.post(
        base,
        json={"name": "B", "start_fraction": 0.8, "end_fraction": 0.8, "coefficient": 1.0},
    ).status_code == 400
    assert client.post(
        base,
        json={"name": "B", "start_fraction": -0.1, "end_fraction": 0.5, "coefficient": 1.0},
    ).status_code == 422
    assert client.post(
        base,
        json={"name": "B", "start_fraction": 0.1, "end_fraction": 0.2, "coefficient": 0},
    ).status_code == 422


def test_description_is_optional_and_editable(client, geozone_schema, city_route):
    """Описание — единственное место, где живёт причина коэффициента.

    Не обязательно при создании, стирается пустой строкой, null запрещён — как
    и остальные поля участка.
    """
    city_slug, route_slug = city_route
    base = _geozones_url(city_slug, route_slug)

    silent = client.post(
        base,
        json={"name": "Окраина", "start_fraction": 0.0, "end_fraction": 0.2, "coefficient": 0.8},
    ).json()["data"]
    assert silent["description"] == ""

    described = client.post(
        base,
        json={
            "name": "Центр",
            "description": "Пешеходный поток, светофор — стоим до 40 секунд.",
            "start_fraction": 0.35,
            "end_fraction": 0.6,
            "coefficient": 1.5,
        },
    )
    assert described.status_code == 201
    zone_id = described.json()["data"]["id"]
    assert client.get(base).json()["data"][1]["description"].startswith("Пешеходный")

    patched = client.patch(
        f"/api/v1/geozones/{zone_id}", json={"description": "Ремонт, поток упал."}
    )
    assert patched.json()["data"]["description"] == "Ремонт, поток упал."

    cleared = client.patch(f"/api/v1/geozones/{zone_id}", json={"description": ""})
    assert cleared.json()["data"]["description"] == ""

    assert (
        client.patch(
            f"/api/v1/geozones/{zone_id}", json={"description": None}
        ).status_code
        == 400
    )


def test_missing_targets_are_404(client, geozone_schema, city_route):
    city_slug, _ = city_route
    assert client.get(f"/api/v1/cities/{city_slug}/routes/nope/geozones").status_code == 404
    assert client.patch("/api/v1/geozones/nope", json={"coefficient": 1.1}).status_code == 404
    assert client.delete("/api/v1/geozones/nope").status_code == 404


# --- живой β в сводке ------------------------------------------------------


def test_summary_applies_beta_and_recalculates(client, storage, geozone_schema, city_route):
    city_slug, route_slug = city_route
    routes_id = _route_id(city_slug, route_slug)
    # duration 40s, зона [0.35,0.6) = секунды 14..24.
    #   obj1 best_ts=20 (доля 0.5) внутри → β; obj2 best_ts=4 (доля 0.1) дыра → β1.
    storage.objects[TRACKS_KEY] = _tracks_csv(
        [
            _track(1, 1, "mts", 20.0, 2.0, 0.5, 1),
            _track(2, 2, "mts", 4.0, 1.0, 0.8, 1),
        ]
    )
    _seed_completed_run(routes_id, with_assignment=True)

    created = client.post(
        _geozones_url(city_slug, route_slug),
        json={"name": "Центр", "start_fraction": 0.35, "end_fraction": 0.6, "coefficient": 1.5},
    )
    geozone_id = created.json()["data"]["id"]

    # V = 2.0·0.5·1.5 + 1.0·0.8·1.0 = 1.5 + 0.8 = 2.3
    assert _visibility_index(client, RUN_ID) == pytest.approx(2.3)

    # Сменили коэффициент — сводка свежая без перепрогона видео.
    client.patch(f"/api/v1/geozones/{geozone_id}", json={"coefficient": 2.0})
    assert _visibility_index(client, RUN_ID) == pytest.approx(2.8)  # 2.0 + 0.8


def test_summary_without_assignment_uses_neutral_beta(
    client, storage, geozone_schema, city_route
):
    city_slug, route_slug = city_route
    routes_id = _route_id(city_slug, route_slug)
    # У маршрута есть зона, но съёмка без задания её не видит: β = 1 у всех.
    client.post(
        _geozones_url(city_slug, route_slug),
        json={"name": "Центр", "start_fraction": 0.35, "end_fraction": 0.6, "coefficient": 1.5},
    )
    storage.objects[TRACKS_KEY] = _tracks_csv([_track(1, 1, "mts", 20.0, 2.0, 0.5, 1)])
    _seed_completed_run(routes_id, with_assignment=False)

    # V = 2.0·0.5·1.0 = 1.0 (β нейтральный, зоны съёмке недоступны).
    assert _visibility_index(client, RUN_ID) == pytest.approx(1.0)
