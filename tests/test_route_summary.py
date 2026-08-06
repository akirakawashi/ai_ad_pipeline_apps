"""Свёртка маршрута: считается из съёмок напрямую, не из средних по заданиям.

Главный тест здесь — test_mean_is_flat_over_shootings: он ловит подмену модели.
Если кто-нибудь решит собирать маршрут из результатов заданий, кампания из одной
съёмки начнёт весить столько же, сколько кампания из трёх, и цифра изменится.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

import pytest
from sqlmodel import Session

from conftest import payload
from domain.entities import PipelineArtifactType, PipelineRunStatus
from infrastructure.database.models import PipelineArtifact, PipelineRun
from infrastructure.database.session import engine
from pipeline_contracts.artifacts import TRACK_CSV_FIELDS, TrackCsvRow
from pipeline_contracts.domain import FinalStatus


def _tracks_csv(run_id: str, brands_visibility: dict[str, float]) -> bytes:
    """CSV из одного трека на бренд. α = 1, поэтому V = attention_seconds."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TRACK_CSV_FIELDS)
    writer.writeheader()
    for index, (brand, visibility) in enumerate(brands_visibility.items(), start=1):
        row = TrackCsvRow(
            run_id=run_id,
            source_path="in.mp4",
            track_id=index,
            object_id=index,
            first_frame_index=0,
            last_frame_index=10,
            first_timestamp_sec=1.0,
            last_timestamp_sec=2.0,
            visible_duration_sec=1.0,
            detections_count=5,
            best_crop_path="crops/x.jpg",
            best_timestamp_sec=1.0,
            attention_seconds=visibility,
            confidence_coef=1.0,
            final_brand=brand if brand != "other" else "",
            final_brand_conf=0.9,
            final_status=(
                FinalStatus.OTHER if brand == "other" else FinalStatus.DETECTED_BRAND
            ),
            business_brand=brand,
            business_visible=True,
            final_status_reason="ok",
            track_confirmed=True,
            manual_review_required=False,
        )
        writer.writerow(row.to_csv_row())
    return buffer.getvalue().encode("utf-8")


def _seed_shooting(
    storage,
    *,
    run_id: str,
    assignment_id: str,
    shot_started_at: str,
    brands_visibility: dict[str, float],
    status: PipelineRunStatus = PipelineRunStatus.COMPLETED,
) -> None:
    """Завершённая съёмка с артефактом TRACKS; CSV кладём в фейковое хранилище."""
    tracks_key = f"runs/{run_id}/artifacts/tracks.csv"
    storage.objects[tracks_key] = _tracks_csv(run_id, brands_visibility)
    with Session(engine) as session:
        session.add(
            PipelineRun(
                pipeline_runs_id=run_id,
                source_name=f"{run_id}.mp4",
                source_object_key=f"runs/{run_id}/source/in.mp4",
                source_size_bytes=1,
                duration_sec=40.0,
                shot_started_at=datetime.fromisoformat(shot_started_at),
                status=status.value,
                assignments_id=assignment_id,
            )
        )
        session.flush()
        if status == PipelineRunStatus.COMPLETED:
            session.add(
                PipelineArtifact(
                    pipeline_runs_id=run_id,
                    artifact_type=PipelineArtifactType.TRACKS.value,
                    object_key=tracks_key,
                    content_type="text/csv",
                    size_bytes=1,
                )
            )
        session.commit()


def _brand_visibility(data: dict, brand: str = "mts") -> dict:
    return next(
        item["visibility_per_shooting"]
        for item in data["brands"]
        if item["brand"] == brand
    )


@pytest.fixture
def summary_url(city_route) -> str:
    city_slug, route_slug = city_route
    return f"/api/v1/cities/{city_slug}/routes/{route_slug}/summary"


@pytest.fixture
def assignments_url(city_route) -> str:
    city_slug, route_slug = city_route
    return f"/api/v1/cities/{city_slug}/routes/{route_slug}/assignments"


@pytest.fixture
def two_assignments(client, storage, assignments_url) -> tuple[str, str]:
    """Кампания из трёх съёмок по 100 и кампания из одной на 20.

    Плоское среднее — 80, среднее из средних было бы 60. Разница и есть предмет
    проверки.
    """
    big = payload(client.post(assignments_url, json={"title": "Май"}))["id"]
    small = payload(client.post(assignments_url, json={"title": "Июнь"}))["id"]
    for index, visibility in enumerate((100.0, 100.0, 100.0), start=1):
        _seed_shooting(
            storage,
            run_id=f"run-may-{index}",
            assignment_id=big,
            shot_started_at=f"2026-05-0{index}T09:00:00+00:00",
            brands_visibility={"mts": visibility},
        )
    _seed_shooting(
        storage,
        run_id="run-jun-1",
        assignment_id=small,
        shot_started_at="2026-06-01T09:00:00+00:00",
        brands_visibility={"mts": 20.0},
    )
    return big, small


def test_mean_is_flat_over_shootings(client, summary_url, two_assignments):
    data = payload(client.get(summary_url))
    totals = data["totals"]
    assert totals["shootings_completed"] == 4
    # (100 + 100 + 100 + 20) / 4 = 80. Среднее из средних дало бы 60.
    assert _brand_visibility(data)["mean"] == pytest.approx(80.0)
    assert "visibility_per_shooting" not in totals
    assert totals["objects_per_shooting"]["mean"] == pytest.approx(1.0)
    # Единственная суммируемая величина — «сколько наснимали».
    assert totals["duration_sec"] == pytest.approx(160.0)


def test_median_ships_alongside_mean(client, summary_url, two_assignments):
    """Обе оценки центра приходят одним ответом — переключатель ничего не грузит.

    Те же четыре съёмки: 100, 100, 100 и 20. Среднее тянется к выбившемуся
    проезду, медиана его не замечает; ради этой разницы выбор и сделали.
    """
    stat = _brand_visibility(payload(client.get(summary_url)))
    assert stat["mean"] == pytest.approx(80.0)
    assert stat["median"] == pytest.approx(100.0)
    # Разброс общий для обеих оценок: он про сами съёмки, а не про способ свёртки.
    assert stat["std"] == pytest.approx(40.0)


def test_brand_median_ignores_the_single_lucky_pass(
    client, storage, summary_url, assignments_url
):
    """Бренд, попавшийся в одну съёмку из трёх: среднее его видит, медиана — нет.

    Оба ответа верные, но отвечают на разные вопросы: «20 в среднем за проезд» и
    «в типичном проезде его не видно». Заодно проверяем, что доли в ответе нет:
    она зависит от выбранной оценки и считается там, где живёт выбор.
    """
    assignment_id = payload(client.post(assignments_url, json={}))["id"]
    for index, brands_visibility in enumerate(
        ({"mts": 100.0, "plus7": 60.0}, {"mts": 100.0}, {"mts": 100.0}),
        start=1,
    ):
        _seed_shooting(
            storage,
            run_id=f"run-luck-{index}",
            assignment_id=assignment_id,
            shot_started_at=f"2026-05-0{index}T09:00:00+00:00",
            brands_visibility=brands_visibility,
        )
    plus7 = next(
        row
        for row in payload(client.get(summary_url))["brands"]
        if row["brand"] == "plus7"
    )
    assert plus7["visibility_per_shooting"]["mean"] == pytest.approx(20.0)
    assert plus7["visibility_per_shooting"]["median"] == pytest.approx(0.0)
    assert "visibility_share" not in plus7


def test_lists_every_shooting_with_its_assignment(client, summary_url, two_assignments):
    data = payload(client.get(summary_url))
    shootings = data["shootings"]
    assert [item["run_id"] for item in shootings] == [
        "run-may-1",
        "run-may-2",
        "run-may-3",
        "run-jun-1",
    ]
    assert [item["assignment"]["title"] for item in shootings] == [
        "Май",
        "Май",
        "Май",
        "Июнь",
    ]
    assert shootings[0]["shot_started_at"].startswith("2026-05-01T09:00")
    assert data["assignments_total"] == 2


def test_counts_unfinished_but_leaves_them_out_of_metrics(
    client, storage, summary_url, assignments_url
):
    assignment_id = payload(client.post(assignments_url, json={}))["id"]
    _seed_shooting(
        storage,
        run_id="run-done",
        assignment_id=assignment_id,
        shot_started_at="2026-05-01T09:00:00+00:00",
        brands_visibility={"mts": 50.0},
    )
    _seed_shooting(
        storage,
        run_id="run-queued",
        assignment_id=assignment_id,
        shot_started_at="2026-05-02T09:00:00+00:00",
        brands_visibility={"mts": 999.0},
        status=PipelineRunStatus.QUEUED,
    )
    data = payload(client.get(summary_url))
    totals = data["totals"]
    assert totals["shootings_total"] == 2
    assert totals["shootings_completed"] == 1
    assert _brand_visibility(data)["mean"] == pytest.approx(50.0)


def test_shootings_without_assignment_are_invisible(client, storage, summary_url):
    """Съёмка без задания не принадлежит маршруту — её тут быть не может."""
    client.post(
        "/api/v1/runs",
        json={
            "file_name": "loose.mp4",
            "content_type": "video/mp4",
            "size_bytes": 1024,
            "shot_started_at": "2026-05-01T09:00:00Z",
        },
    )
    data = payload(client.get(summary_url))
    assert data["shootings"] == []
    assert data["totals"]["shootings_total"] == 0


def test_missing_brand_counts_as_zero(client, storage, summary_url, assignments_url):
    """Бренд, попавшийся в одну съёмку из двух, не должен выглядеть сильнее."""
    assignment_id = payload(client.post(assignments_url, json={}))["id"]
    _seed_shooting(
        storage,
        run_id="run-both",
        assignment_id=assignment_id,
        shot_started_at="2026-05-01T09:00:00+00:00",
        brands_visibility={"mts": 100.0, "plus7": 40.0},
    )
    _seed_shooting(
        storage,
        run_id="run-mts-only",
        assignment_id=assignment_id,
        shot_started_at="2026-05-02T09:00:00+00:00",
        brands_visibility={"mts": 100.0},
    )
    brands = {
        row["brand"]: row for row in payload(client.get(summary_url))["brands"]
    }
    assert brands["mts"]["visibility_per_shooting"]["mean"] == pytest.approx(100.0)
    # 40 в одной съёмке и ноль в другой → 20, а не 40.
    assert brands["plus7"]["visibility_per_shooting"]["mean"] == pytest.approx(20.0)


def test_geozone_changes_route_numbers(
    client, storage, geozone_schema, city_route, summary_url, assignments_url
):
    """Маршрут читает те же живые β: правка зоны меняет и его цифры."""
    city_slug, route_slug = city_route
    assignment_id = payload(client.post(assignments_url, json={}))["id"]
    # duration 40 c, best_timestamp 1 c → доля 0.025, попадает в зону [0, 0.5).
    _seed_shooting(
        storage,
        run_id="run-beta",
        assignment_id=assignment_id,
        shot_started_at="2026-05-01T09:00:00+00:00",
        brands_visibility={"mts": 100.0},
    )
    assert _brand_visibility(payload(client.get(summary_url)))["mean"] == pytest.approx(
        100.0
    )

    client.post(
        f"/api/v1/cities/{city_slug}/routes/{route_slug}/geozones",
        json={
            "name": "Центр",
            "start_fraction": 0.0,
            "end_fraction": 0.5,
            "coefficient": 1.5,
        },
    )
    assert _brand_visibility(payload(client.get(summary_url)))["mean"] == pytest.approx(
        150.0
    )


def test_unknown_route_is_404(client, city_route):
    city_slug, _ = city_route
    assert client.get(f"/api/v1/cities/{city_slug}/routes/nope/summary").status_code == 404


class TestPeriod:
    """Отбор съёмок по времени съёмки — «тот же список, только короче».

    Период не заводит новой математики: он укорачивает список до свёртки, а
    считает по нему та же `metrics_rollup`. Поэтому проверяем не формулы, а
    границы окна и то, что подписи под цифрой следуют за отбором.

    Фикстура `two_assignments` даёт три майские съёмки по 100 и одну июньскую
    на 20 — среднее по всем 80. Числа выбраны так, что по одному среднему видно,
    какие съёмки попали в окно.
    """

    def test_window_narrows_the_average(self, client, summary_url, two_assignments):
        """Только май: 100, 100, 100 — среднее 100 вместо 80 по всему маршруту."""
        data = payload(
            client.get(
                summary_url,
                params={
                    "shot_from": "2026-05-01T00:00:00+00:00",
                    "shot_to": "2026-06-01T00:00:00+00:00",
                },
            )
        )

        assert data["totals"]["shootings_completed"] == 3
        assert _brand_visibility(data)["mean"] == pytest.approx(100.0)

    def test_end_is_exclusive(self, client, summary_url, two_assignments):
        """Конец окна не включается: 1 июня как граница июньскую съёмку отсекает.

        Фронт прибавляет сутки к последней выбранной дате, поэтому «по 31 мая»
        приезжает сюда как конец 1 июня — и июньский проезд остаётся снаружи.
        """
        data = payload(
            client.get(
                summary_url,
                params={"shot_to": "2026-06-01T00:00:00+00:00"},
            )
        )

        assert [item["run_id"] for item in data["shootings"]] == [
            "run-may-1",
            "run-may-2",
            "run-may-3",
        ]

    def test_start_is_inclusive(self, client, summary_url, two_assignments):
        """Начало окна включается: съёмка ровно в этот момент остаётся внутри."""
        data = payload(
            client.get(
                summary_url,
                params={"shot_from": "2026-05-03T09:00:00+00:00"},
            )
        )

        assert [item["run_id"] for item in data["shootings"]] == [
            "run-may-3",
            "run-jun-1",
        ]

    def test_one_sided_window(self, client, summary_url, two_assignments):
        """Границы независимы: можно задать только начало."""
        data = payload(
            client.get(
                summary_url,
                params={"shot_from": "2026-06-01T00:00:00+00:00"},
            )
        )

        assert data["totals"]["shootings_completed"] == 1
        assert _brand_visibility(data)["mean"] == pytest.approx(20.0)

    def test_assignments_total_follows_the_window(
        self, client, summary_url, two_assignments
    ):
        """«Собрано из N заданий» — про попавшие съёмки, а не про маршрут.

        Без периода заданий два, в майском окне — одно. Иначе подпись
        «собрано из 2 заданий · 3 съёмок» врала бы прямо на экране.
        """
        assert payload(client.get(summary_url))["assignments_total"] == 2

        may = payload(
            client.get(
                summary_url,
                params={"shot_to": "2026-06-01T00:00:00+00:00"},
            )
        )
        assert may["assignments_total"] == 1

    def test_empty_window_is_not_an_error(self, client, summary_url, two_assignments):
        """Период без съёмок — законный ответ, а не 404: экран скажет «пусто»."""
        data = payload(
            client.get(
                summary_url,
                params={"shot_from": "2027-01-01T00:00:00+00:00"},
            )
        )

        assert data["totals"]["shootings_completed"] == 0
        assert data["shootings"] == []
        assert data["brands"] == []

    def test_end_before_start_is_refused(self, client, summary_url):
        response = client.get(
            summary_url,
            params={
                "shot_from": "2026-06-01T00:00:00+00:00",
                "shot_to": "2026-05-01T00:00:00+00:00",
            },
        )

        assert response.status_code == 400
        assert "раньше" in response.json()["detail"]

    def test_naive_bounds_are_refused(self, client, summary_url):
        """Границы обязаны нести зону: без неё «первое мая» — разный момент.

        Момент без зоны истолковался бы по зоне сервера, и вечерние съёмки на
        краю окна попадали бы то внутрь, то наружу в зависимости от того, где
        этот сервер стоит.
        """
        response = client.get(
            summary_url, params={"shot_from": "2026-05-01T00:00:00"}
        )

        assert response.status_code == 422


class TestHiddenAssignment:
    """Скрытое задание выпадает из метрики маршрута вместе со своими съёмками.

    Это и есть смысл кнопки: раз кампанию спрятали, её проезды не должны тянуть
    за собой средние по маршруту. Механизм тот же, что у периода, — список
    съёмок укорачивается **до** свёртки, а считает по нему та же
    `metrics_rollup`. Второй арифметики не появляется: иначе цифра под скрытием
    разошлась бы с цифрой без него, ровно как разошлась бы под периодом.

    Фикстура `two_assignments`: три майские съёмки по 100 и одна июньская на 20,
    среднее по всем — 80. По одному среднему видно, чьи съёмки остались.
    """

    def hide(self, client, assignment_id: str) -> None:
        response = client.patch(
            f"/api/v1/assignments/{assignment_id}", json={"is_active": False}
        )
        assert response.status_code == 200

    def test_its_shootings_leave_the_average(
        self, client, summary_url, two_assignments
    ):
        """Спрятали июнь — остаются три сотни, среднее 100 вместо 80."""
        _, small = two_assignments
        self.hide(client, small)

        data = payload(client.get(summary_url))
        totals = data["totals"]
        assert totals["shootings_completed"] == 3
        assert _brand_visibility(data)["mean"] == pytest.approx(100.0)
        # Суммируемая величина тоже: 3 × 40 секунд вместо 4 × 40.
        assert totals["duration_sec"] == pytest.approx(120.0)

    def test_shootings_and_assignment_count_follow(
        self, client, summary_url, two_assignments
    ):
        """Подпись «собрано из N заданий» считается по тем съёмкам, что дали цифру."""
        _, small = two_assignments
        self.hide(client, small)

        data = payload(client.get(summary_url))
        assert [item["run_id"] for item in data["shootings"]] == [
            "run-may-1",
            "run-may-2",
            "run-may-3",
        ]
        assert data["assignments_total"] == 1

    def test_restoring_returns_them(self, client, summary_url, two_assignments):
        _, small = two_assignments
        self.hide(client, small)
        client.patch(f"/api/v1/assignments/{small}", json={"is_active": True})

        data = payload(client.get(summary_url))
        totals = data["totals"]
        assert totals["shootings_completed"] == 4
        assert _brand_visibility(data)["mean"] == pytest.approx(80.0)

    def test_hiding_everything_is_not_an_error(
        self, client, summary_url, two_assignments
    ):
        """Маршрут без единого видимого задания — пустая сводка, а не 404."""
        for assignment_id in two_assignments:
            self.hide(client, assignment_id)

        data = payload(client.get(summary_url))
        assert data["totals"]["shootings_total"] == 0
        assert data["shootings"] == []
        assert data["assignments_total"] == 0
