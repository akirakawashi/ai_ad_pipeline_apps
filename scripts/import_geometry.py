"""Разовая заливка геометрии из файлов фронтенда в базу через API.

Нужен один раз: после миграции `d5e1a83f2c74` города и маршруты есть, а
геометрии у них нет — она лежала файлами в `apps/frontend/public/routes/`.
Alembic так сделать не может: он работает в контейнере бэкенда, где папки фронта
не существует. Скрипт запускают на хосте, где видно и файлы, и API.

    uv run python scripts/import_geometry.py            # localhost:8000
    uv run python scripts/import_geometry.py --dry-run   # только показать план

Раскладка файлов, на которую он рассчитан:

    routes/<город>/export.geojson    → дорожный слой города
    routes/<город>/route_N.geojson   → линия маршрута со слагом route-N

После проверки, что карта рисует, папку `apps/frontend/public/routes/` и этот
скрипт можно удалить: источник данных теперь база.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_DIR = ROOT / "apps" / "frontend" / "public" / "routes"
ROUTE_FILE = re.compile(r"^route_(\d+)\.geojson$")


def _put(client: httpx.Client, url: str, path: Path, *, dry_run: bool) -> bool:
    size_kb = path.stat().st_size // 1024
    if dry_run:
        print(f"  [план] {url} ← {path.name} ({size_kb} КБ)")
        return True
    with path.open("rb") as handle:
        response = client.put(
            url,
            files={"file": (path.name, handle, "application/geo+json")},
        )
    if response.is_success:
        print(f"  ок     {url} ← {path.name} ({size_kb} КБ)")
        return True
    detail = response.json().get("detail", response.text)
    print(f"  ОШИБКА {url} ← {path.name}: {response.status_code} {detail}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not GEOMETRY_DIR.is_dir():
        print(f"Нет папки {GEOMETRY_DIR} — заливать нечего.")
        return 1

    failures = 0
    # timeout щедрый: дорожный слой Севастополя — 1.5 МБ, и на слабой машине
    # разбор с пересчётом рамки занимает секунды.
    with httpx.Client(timeout=120.0) as client:
        for city_dir in sorted(path for path in GEOMETRY_DIR.iterdir() if path.is_dir()):
            city_slug = city_dir.name
            print(f"{city_slug}:")

            roads = city_dir / "export.geojson"
            if roads.is_file():
                url = f"{args.api}/cities/{city_slug}/roads-geometry"
                if not _put(client, url, roads, dry_run=args.dry_run):
                    failures += 1

            for path in sorted(city_dir.iterdir()):
                match = ROUTE_FILE.match(path.name)
                if match is None:
                    continue
                # В файлах route_1, в базе слаг route-1 — так их завели сиды.
                route_slug = f"route-{match.group(1)}"
                url = f"{args.api}/cities/{city_slug}/routes/{route_slug}/geometry"
                if not _put(client, url, path, dry_run=args.dry_run):
                    failures += 1

    if failures:
        print(f"\nНе залилось: {failures}. Города и маршруты должны существовать в базе.")
        return 1
    print("\nГотово." if not args.dry_run else "\nЭто был план, ничего не отправлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
