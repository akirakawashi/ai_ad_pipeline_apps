"""Внутренний HTTP-контракт между backend и отдельным ML worker."""

from __future__ import annotations

import csv
import io

from sqlmodel import Session, select

from application.services.pipeline_run_service import PipelineRunService
from conftest import PROCESSING_TOKEN, payload
from infrastructure.database.models import (
    Assignment,
    City,
    DwhVideoMetric,
    PipelineArtifact,
    PipelineRun,
    Route,
)
from infrastructure.database.session import engine
from infrastructure.repositories.assignment_mapping import assignment_title
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
from pipeline_contracts.artifacts import TRACK_CSV_FIELDS, TrackCsvRow
from pipeline_contracts.domain import FinalStatus

INTERNAL_URL = "/internal/v1/processing/jobs"
INTERNAL_HEADERS = {"X-Processing-Token": PROCESSING_TOKEN}


def _track(
    run_id: str,
    *,
    track_id: int,
    brand: str,
    timestamp: float,
    attention: float,
    confidence: float,
) -> TrackCsvRow:
    return TrackCsvRow(
        run_id=run_id,
        source_path="pass.mp4",
        track_id=track_id,
        object_id=track_id,
        first_frame_index=0,
        last_frame_index=10,
        first_timestamp_sec=timestamp,
        last_timestamp_sec=timestamp,
        visible_duration_sec=1.0,
        detections_count=5,
        best_crop_path=f"crops/{track_id}.jpg",
        best_timestamp_sec=timestamp,
        attention_seconds=attention,
        confidence_coef=confidence,
        final_brand="" if brand == "other" else brand,
        final_brand_conf=0.9,
        final_status=(
            FinalStatus.OTHER
            if brand == "other"
            else FinalStatus.DETECTED_BRAND
        ),
        business_brand=brand,
        business_visible=True,
        final_status_reason="ok",
        track_confirmed=True,
        manual_review_required=False,
    )


def _tracks_csv(rows: list[TrackCsvRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TRACK_CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_csv_row())
    return buffer.getvalue().encode("utf-8")


def _queued_run(client, storage, city_route) -> str:
    city_slug, route_slug = city_route
    assignment = payload(
        client.post(
            f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments",
            json={},
        )
    )
    created = payload(
        client.post(
            "/api/v1/runs",
            json={
                "file_name": "pass.mp4",
                "content_type": "video/mp4",
                "size_bytes": 5,
                "assignment_id": assignment["id"],
                "shot_started_at": "2026-08-04T10:00:00Z",
            },
        )
    )
    run_id = created["run_id"]
    storage.objects[f"runs/{run_id}/source/pass.mp4"] = b"video"
    assert client.post(f"/api/v1/runs/{run_id}/upload-complete").status_code == 200
    return run_id


def _claim(client) -> dict | None:
    response = client.post(
        f"{INTERNAL_URL}/claim",
        headers=INTERNAL_HEADERS,
        json={"contract_version": "1"},
    )
    assert response.status_code == 200
    return payload(response)


def test_processing_api_requires_service_token(client):
    response = client.post(
        f"{INTERNAL_URL}/claim",
        json={"contract_version": "1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный токен сервиса обработки."


def test_claim_empty_queue_returns_null(client):
    assert _claim(client) is None


def test_claim_is_atomic_and_returns_storage_contract(client, storage, city_route):
    run_id = _queued_run(client, storage, city_route)

    job = _claim(client)
    assert job == {
        "contract_version": "1",
        "run_id": run_id,
        "source_name": "pass.mp4",
        "source_object_key": f"runs/{run_id}/source/pass.mp4",
        "output_prefix": f"runs/{run_id}/artifacts",
    }
    assert _claim(client) is None
    assert payload(client.get(f"/api/v1/runs/{run_id}"))["status"] == "processing"


def test_progress_is_written_by_backend(client, storage, city_route):
    run_id = _queued_run(client, storage, city_route)
    assert _claim(client) is not None

    response = client.post(
        f"{INTERNAL_URL}/{run_id}/progress",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "1",
            "stage": "detection",
            "progress": 42,
            "message": "Проверяем кадры",
            "create_event": True,
        },
    )
    assert response.status_code == 204
    run = payload(client.get(f"/api/v1/runs/{run_id}"))
    assert run["stage"] == "detection"
    assert run["progress"] == 42
    assert run["status_message"] == "Проверяем кадры"


def test_complete_registers_manifest_and_metadata(client, storage, city_route):
    run_id = _queued_run(client, storage, city_route)
    assert _claim(client) is not None
    city_slug, route_slug = city_route
    zone = client.post(
        f"/api/v1/cities/{city_slug}/routes/{route_slug}/geozones",
        json={
            "name": "Первая половина",
            "start_fraction": 0.0,
            "end_fraction": 0.5,
            "coefficient": 2.0,
        },
    )
    assert zone.status_code == 201

    artifact_key = f"runs/{run_id}/artifacts/tracks.csv"
    storage.objects[artifact_key] = _tracks_csv(
        [
            _track(
                run_id,
                track_id=1,
                brand="mts",
                timestamp=2.0,
                attention=2.0,
                confidence=0.5,
            ),
            _track(
                run_id,
                track_id=2,
                brand="mts",
                timestamp=4.0,
                attention=3.0,
                confidence=1.0,
            ),
            _track(
                run_id,
                track_id=3,
                brand="other",
                timestamp=8.0,
                attention=4.0,
                confidence=0.5,
            ),
        ]
    )

    response = client.post(
        f"{INTERNAL_URL}/{run_id}/complete",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "1",
            "metadata": {
                "fps": 25.0,
                "frame_count": 250,
                "frame_stride": 1,
                "width": 1920,
                "height": 1080,
            },
            "artifacts": [
                {
                    "relative_path": "tracks.csv",
                    "content_type": "text/csv",
                    "size_bytes": len(storage.objects[artifact_key]),
                }
            ],
        },
    )
    assert response.status_code == 204

    run = payload(client.get(f"/api/v1/runs/{run_id}"))
    assert run["status"] == "completed"
    assert run["progress"] == 100
    assert run["duration_sec"] == 10.0
    with Session(engine) as session:
        artifact = session.exec(
            select(PipelineArtifact).where(PipelineArtifact.pipeline_runs_id == run_id)
        ).all()
        run_model = session.get(PipelineRun, run_id)
        assert run_model is not None
        assignment = session.get(Assignment, run_model.assignments_id)
        assert assignment is not None
        route = session.get(Route, assignment.routes_id)
        assert route is not None
        city = session.get(City, route.cities_id)
        assert city is not None
        metrics = session.exec(
            select(DwhVideoMetric)
            .where(DwhVideoMetric.pipeline_runs_id == run_id)
            .order_by(DwhVideoMetric.brand)
        ).all()
    assert {(item.artifact_type, item.object_key) for item in artifact} == {
        ("source_video", f"runs/{run_id}/source/pass.mp4"),
        ("tracks", artifact_key),
    }
    assert [(item.brand, item.sum_visibility_value) for item in metrics] == [
        ("mts", 8.0),
        ("other", 2.0),
    ]
    assert {item.revision for item in metrics} == {1}
    assert all(item.is_active for item in metrics)
    assert all(item.created_at is not None for item in metrics)
    assert all(item.cities_id == city.cities_id for item in metrics)
    assert all(item.city_name == city.name for item in metrics)
    assert all(item.routes_id == route.routes_id for item in metrics)
    assert all(item.route_name == route.name for item in metrics)
    assert all(item.assignments_id == assignment.assignments_id for item in metrics)
    assert all(item.assignment_name == assignment_title(assignment) for item in metrics)

    # Тот же писатель позже станет точкой пересчёта: он добавляет новую
    # ревизию и не меняет уже отданные DWH строки.
    with Session(engine) as session:
        repository = SqlPipelineRunRepository(session)
        PipelineRunService(repository, storage).append_dwh_revision(run_id)
        repository.commit()
        revisions = session.exec(
            select(DwhVideoMetric.revision)
            .where(DwhVideoMetric.pipeline_runs_id == run_id)
            .order_by(DwhVideoMetric.revision)
        ).all()
    assert revisions == [1, 1, 2, 2]


def test_complete_publishes_null_metric_when_no_brand_was_found(
    client, storage, city_route
):
    run_id = _queued_run(client, storage, city_route)
    assert _claim(client) is not None
    artifact_key = f"runs/{run_id}/artifacts/tracks.csv"
    storage.objects[artifact_key] = _tracks_csv([])

    response = client.post(
        f"{INTERNAL_URL}/{run_id}/complete",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "1",
            "metadata": {
                "fps": 25.0,
                "frame_count": 250,
                "frame_stride": 1,
                "width": 1920,
                "height": 1080,
            },
            "artifacts": [
                {
                    "relative_path": "tracks.csv",
                    "content_type": "text/csv",
                    "size_bytes": len(storage.objects[artifact_key]),
                }
            ],
        },
    )
    assert response.status_code == 204

    with Session(engine) as session:
        metrics = session.exec(
            select(DwhVideoMetric).where(
                DwhVideoMetric.pipeline_runs_id == run_id
            )
        ).all()
    assert len(metrics) == 1
    assert metrics[0].revision == 1
    assert metrics[0].brand is None
    assert metrics[0].sum_visibility_value is None
    assert metrics[0].is_active is True


def test_complete_rejects_path_escape(client, storage, city_route):
    run_id = _queued_run(client, storage, city_route)
    assert _claim(client) is not None
    response = client.post(
        f"{INTERNAL_URL}/{run_id}/complete",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "1",
            "metadata": {
                "fps": 25.0,
                "frame_count": 250,
                "frame_stride": 1,
                "width": 1920,
                "height": 1080,
            },
            "artifacts": [
                {
                    "relative_path": "../foreign.txt",
                    "content_type": "text/plain",
                    "size_bytes": 1,
                }
            ],
        },
    )
    assert response.status_code == 409
    with Session(engine) as session:
        status = session.exec(
            select(PipelineRun.status).where(PipelineRun.pipeline_runs_id == run_id)
        ).one()
    assert status == "processing"


def test_fail_marks_processing_failed(client, storage, city_route):
    run_id = _queued_run(client, storage, city_route)
    assert _claim(client) is not None
    response = client.post(
        f"{INTERNAL_URL}/{run_id}/fail",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "1",
            "error_code": "ModelLoadError",
            "error_message": "weights are unavailable",
        },
    )
    assert response.status_code == 204
    run = payload(client.get(f"/api/v1/runs/{run_id}"))
    assert run["status"] == "processing_failed"
    assert run["error_code"] == "ModelLoadError"


def test_contract_version_is_rejected_before_state_change(client):
    response = client.post(
        f"{INTERNAL_URL}/unknown/progress",
        headers=INTERNAL_HEADERS,
        json={
            "contract_version": "2",
            "stage": "detection",
            "progress": 10,
        },
    )
    assert response.status_code == 422


def test_claim_rejects_contract_version_before_taking_job(
    client, storage, city_route
):
    run_id = _queued_run(client, storage, city_route)
    response = client.post(
        f"{INTERNAL_URL}/claim",
        headers=INTERNAL_HEADERS,
        json={"contract_version": "2"},
    )
    assert response.status_code == 422
    assert payload(client.get(f"/api/v1/runs/{run_id}"))["status"] == "queued"
