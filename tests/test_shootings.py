"""Съёмка — видеофайл с реквизитами: когда снимали и кто снимал.

Ключевое, что легко сломать: реквизиты съёмки и времена обработки живут рядом
и называются похоже. Окончание съёмки не хранится — оно выводится из
длительности видео и потому не может с ним разойтись.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import Session, text

from conftest import payload
from infrastructure.database.session import engine


@pytest.fixture
def assignment(client, city_route) -> dict:
    city_slug, route_slug = city_route
    url = f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments"
    return payload(client.post(url, json={}))


@pytest.fixture
def other_assignment(client, city_route) -> dict:
    """Второе задание на том же маршруте — чтобы фильтру было из чего выбирать."""
    city_slug, route_slug = city_route
    url = f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments"
    return payload(client.post(url, json={}))


@pytest.fixture
def operator(client) -> dict:
    return payload(client.post("/api/v1/users", json={"full_name": "Петров Пётр"}))


def create_run(client, **overrides):
    body = {
        "file_name": "pass.mp4",
        "content_type": "video/mp4",
        "size_bytes": 1024,
    }
    body.update(overrides)
    return client.post("/api/v1/runs", json=body)


def set_duration(run_id: str, seconds: float) -> None:
    """Длительность проставляет воркер после обработки — здесь имитируем."""
    with Session(engine) as session:
        # execute, а не exec: exec у SQLModel типизирован под select.
        session.execute(
            text(
                "UPDATE pipeline_runs SET duration_sec = :d WHERE pipeline_runs_id = :i"
            ).bindparams(d=seconds, i=run_id)
        )
        session.commit()


def test_stores_shooting_details(client, assignment, operator):
    run = payload(
        create_run(
            client,
            assignment_id=assignment["id"],
            shot_started_at="2026-08-02T09:30:00Z",
            operator_user_id=operator["id"],
        )
    )
    got = payload(client.get(f"/api/v1/runs/{run['run_id']}"))
    assert got["shot_started_at"].startswith("2026-08-02T09:30")
    assert got["operator"]["full_name"] == "Петров Пётр"


def test_processing_times_are_separate_from_shooting(client, assignment):
    """started_at/completed_at — про обработку, их создание съёмки не трогает."""
    run = payload(
        create_run(
            client,
            assignment_id=assignment["id"],
            shot_started_at="2026-08-02T09:30:00Z",
        )
    )
    got = payload(client.get(f"/api/v1/runs/{run['run_id']}"))
    assert got["started_at"] is None
    assert got["completed_at"] is None
    assert got["shot_started_at"] is not None


def test_finish_unknown_until_duration_known(client, assignment):
    run = payload(
        create_run(
            client,
            assignment_id=assignment["id"],
            shot_started_at="2026-08-02T09:30:00Z",
        )
    )
    assert payload(client.get(f"/api/v1/runs/{run['run_id']}"))["shot_finished_at"] is None


def test_finish_is_start_plus_duration(client, assignment):
    run = payload(
        create_run(
            client,
            assignment_id=assignment["id"],
            shot_started_at="2026-08-02T10:00:00Z",
        )
    )
    set_duration(run["run_id"], 754.5)

    got = payload(client.get(f"/api/v1/runs/{run['run_id']}"))
    started = datetime.fromisoformat(got["shot_started_at"])
    finished = datetime.fromisoformat(got["shot_finished_at"])
    assert (finished - started).total_seconds() == pytest.approx(754.5)


def test_finish_unknown_without_start(client, assignment):
    run = payload(create_run(client, assignment_id=assignment["id"]))
    set_duration(run["run_id"], 100.0)
    assert payload(client.get(f"/api/v1/runs/{run['run_id']}"))["shot_finished_at"] is None


def test_patch_changes_operator_only(client, assignment, operator):
    run = payload(
        create_run(
            client,
            assignment_id=assignment["id"],
            shot_started_at="2026-08-02T09:30:00Z",
            operator_user_id=operator["id"],
        )
    )
    other = payload(client.post("/api/v1/users", json={"full_name": "Сидоров Сидор"}))

    updated = payload(
        client.patch(f"/api/v1/runs/{run['run_id']}", json={"operator_user_id": other["id"]})
    )
    assert updated["operator"]["id"] == other["id"]
    assert updated["shot_started_at"].startswith("2026-08-02T09:30")


def test_patch_rejects_naive_datetime(client, assignment):
    run = payload(create_run(client, assignment_id=assignment["id"]))
    response = client.patch(
        f"/api/v1/runs/{run['run_id']}", json={"shot_started_at": "2026-08-02T09:30:00"}
    )
    assert response.status_code == 422


def test_unknown_operator_is_not_500(client, assignment):
    run = payload(create_run(client, assignment_id=assignment["id"]))
    response = client.patch(
        f"/api/v1/runs/{run['run_id']}",
        json={"operator_user_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 400


def test_rejects_non_video(client, assignment):
    response = create_run(
        client,
        file_name="notes.txt",
        content_type="text/plain",
        assignment_id=assignment["id"],
    )
    assert response.status_code == 400


def test_shooting_limit_per_assignment(client, assignment):
    from application.services.pipeline_run_service import MAX_ASSIGNMENT_SHOOTINGS

    for index in range(MAX_ASSIGNMENT_SHOOTINGS):
        response = create_run(
            client, file_name=f"v{index}.mp4", assignment_id=assignment["id"]
        )
        assert response.status_code == 201

    over = create_run(client, file_name="extra.mp4", assignment_id=assignment["id"])
    assert over.status_code == 409


def test_unknown_assignment_is_404(client):
    response = create_run(
        client, assignment_id="00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


class TestAssignmentIsMandatory:
    """Съёмки вне маршрута не существует — ни завести, ни отфильтровать.

    Это не только правило продукта: без маршрута у съёмки нет геозон, значит нет
    и значимости места, и положить её в сводку задания или маршрута некуда.
    Такое видео занимало место в хранилище и не отвечало ни на один вопрос.
    """

    def test_without_assignment_is_refused(self, client):
        """Поле обязательное, поэтому отказ приходит от разбора запроса — 422."""
        assert create_run(client, file_name="solo.mp4").status_code == 422

    def test_explicit_null_is_refused_too(self, client):
        """Явный null — та же дыра, что и пропущенное поле; закрыта тем же."""
        response = create_run(client, file_name="solo.mp4", assignment_id=None)
        assert response.status_code == 422

    def test_empty_string_is_refused(self, client):
        """Пустая строка прошла бы `str`, поэтому у поля есть min_length."""
        response = create_run(client, file_name="solo.mp4", assignment_id="")
        assert response.status_code == 422


class TestHiddenAssignment:
    """Скрыли задание — вместе с ним пропали и его съёмки.

    Не косметика: съёмка скрытого задания не должна остаться ни в списке видео,
    ни по прямой ссылке. Иначе карточка вела бы на страницу, которой нет, а
    «скрыто» означало бы разное в разных местах.
    """

    def hide(self, client, assignment: dict) -> None:
        response = client.patch(
            f"/api/v1/assignments/{assignment['id']}", json={"is_active": False}
        )
        assert response.status_code == 200

    def test_shootings_leave_the_list(self, client, assignment, other_assignment):
        create_run(client, file_name="hidden.mp4", assignment_id=assignment["id"])
        create_run(client, file_name="visible.mp4", assignment_id=other_assignment["id"])
        self.hide(client, assignment)

        items = payload(client.get("/api/v1/runs?page_size=50"))["items"]
        assert [item["source_name"] for item in items] == ["visible.mp4"]

    def test_direct_link_to_a_shooting_is_404(self, client, assignment):
        run = payload(create_run(client, assignment_id=assignment["id"]))
        self.hide(client, assignment)
        assert client.get(f"/api/v1/runs/{run['run_id']}").status_code == 404

    def test_uploading_into_it_is_refused(self, client, assignment):
        """Идентификатор задания стоит в адресе страницы загрузки.

        Из выпадашки скрытое уже не выбрать, но открытая со вчера вкладка
        отправила бы видео по старой ссылке — отказ приходит с сервера.
        """
        self.hide(client, assignment)
        assert create_run(client, assignment_id=assignment["id"]).status_code == 404

    def test_restoring_brings_the_shootings_back(self, client, assignment):
        run = payload(create_run(client, assignment_id=assignment["id"]))
        self.hide(client, assignment)
        client.patch(f"/api/v1/assignments/{assignment['id']}", json={"is_active": True})

        assert client.get(f"/api/v1/runs/{run['run_id']}").status_code == 200

    def test_upload_started_before_hiding_still_completes(self, client, assignment):
        """Файл уже в хранилище: отказать здесь — оставить мусор и строку в `uploading`.

        Дозагрузка — путь записи, а пути записи скрытия не знают: по ним же
        ходит воркер. Видно съёмку всё равно не будет, пока задание не вернут.
        """
        run = payload(create_run(client, assignment_id=assignment["id"]))
        self.hide(client, assignment)

        response = client.post(f"/api/v1/runs/{run['run_id']}/upload-complete")
        assert response.status_code == 200
        assert payload(response)["status"] == "queued"


class TestFilters:
    def test_by_assignment(self, client, assignment, other_assignment):
        create_run(client, file_name="in.mp4", assignment_id=assignment["id"])
        create_run(client, file_name="solo.mp4", assignment_id=other_assignment["id"])

        page = payload(
            client.get(f"/api/v1/runs?assignment_id={assignment['id']}&page_size=50")
        )
        assert page["total"] == 1

    def test_list_carries_assignment_and_operator(self, client, assignment, operator):
        create_run(
            client, assignment_id=assignment["id"], operator_user_id=operator["id"]
        )
        items = payload(client.get("/api/v1/runs?page_size=50"))["items"]
        assert items[0]["assignment"]["assignment_id"] == assignment["id"]
        assert items[0]["operator"]["id"] == operator["id"]
