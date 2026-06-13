# Ad Detection

Проект для обучения и проверки YOLO-моделей детекции рекламных поверхностей.

## Структура

- `notebooks/` - рабочие ноутбуки для подготовки датасета и обучения.
- `data/cvat_exports/photo_cv/` - последний экспорт проекта CVAT в формате Ultralytics YOLO.
- `data/yolo/ad_surface_v2/` - чистый train/val датасет для обучения.
- `models/pretrained/` - исходные pretrained веса YOLO, если нужны для экспериментов.
- `models/trained/` - сохранённые обученные веса и параметры запусков.
- `runs/detect/ad_surface_v2/` - последний run обучения YOLO11x.
- `scripts/` - вспомогательные скрипты.

## Подготовка и авторазметка для CVAT

Скрипт `scripts/prelabel_for_cvat.py` работает в два шага: сначала готовит стабильный архив для CVAT, потом строит авторазметку по этим же файлам.

```bash
.venv/bin/python scripts/prelabel_for_cvat.py prepare --seed 42
```

Команда читает `photo.zip`, перемешивает изображения, переименовывает их в `photo_001.jpg`, `photo_002.jpg` и т.д., пишет маппинг в `data/prelabel/photo/name_mapping.csv` и создаёт архив `cvat_import/photo_cvat.zip`.

Этот архив нужно загрузить в CVAT при создании task. После этого можно сгенерировать XML-разметку:

```bash
.venv/bin/python scripts/prelabel_for_cvat.py label
```

По умолчанию используется модель `models/trained/yolo11x_scratch_img1280/best.pt`, а результат пишется в `cvat_import/photo_annotations.xml`.

Если label в CVAT task называется не `ad_object`, передай нужное имя:

```bash
.venv/bin/python scripts/prelabel_for_cvat.py label --label-name ad_surface
```

## Дообучение модели

Сначала собирается новый датасет из `data/yolo/ad_surface_v2/` и проверенных CVAT-кадров из `data/cvat_exports/video_predict_curated_checked/`:

```bash
.venv/bin/python scripts/build_yolo_finetune_dataset.py --overwrite
```

Результат пишется в `data/yolo/ad_surface_v3_finetune/`.

После этого можно дообучить X-модель от весов `models/trained/yolo11x_scratch_img1280/best.pt`:

```bash
.venv/bin/python scripts/train_yolo_finetune_v3.py
```

Run сохранится в `runs/detect/ad_surface_v3/yolo11x_finetune_hard_negatives_v1/`, а основные артефакты будут скопированы в `models/trained/yolo11x_finetune_hard_negatives_v1/`.

## Сбор новых видео-ошибок для CVAT

Для сбора кадров с оставшимися срабатываниями fine-tuned модели из `test.mp4`, `test_2.mp4`, `test_3.mp4` и `test_4.mp4`:

```bash
.venv/bin/python scripts/export_finetune_video_fp_for_cvat.py --overwrite
```

По умолчанию скрипт проверяет каждый 10-й кадр, группирует близкие срабатывания в эпизоды, берет до 3 кадров из каждого эпизода, перемешивает кадры между видео и переименовывает их в `video_hard_000001.jpg`, `video_hard_000002.jpg` и т.д. `--device auto` использует GPU, если она доступна. Результат пишется в `cvat_import/video_finetune_fp_review_all4/`. Для более быстрого чернового прохода можно отдельно передать `--vid-stride 20`.
