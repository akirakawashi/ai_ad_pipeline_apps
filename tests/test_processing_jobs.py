"""Внутренний HTTP-контракт между backend и отдельным ML worker."""

from __future__ import annotations

from sqlmodel import Session, select

from conftest import PROCESSING_TOKEN, payload
from infrastructure.database.models import PipelineArtifact, PipelineRun
from infrastructure.database.session import engine

INTERNAL_URL = "/internal/v1/processing/jobs"
INTERNAL_HEADERS = {"X-Processing-Token": PROCESSING_TOKEN}


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
    artifact_key = f"runs/{run_id}/artifacts/tracks.csv"
    storage.objects[artifact_key] = b"track"

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
                    "size_bytes": 5,
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
    assert {(item.artifact_type, item.object_key) for item in artifact} == {
        ("source_video", f"runs/{run_id}/source/pass.mp4"),
        ("tracks", artifact_key),
    }


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
