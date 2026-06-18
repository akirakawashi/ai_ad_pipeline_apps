# Ad Detection

Проект для обучения и проверки YOLO-моделей детекции рекламных поверхностей.

## Структура

- `detect_new.zip` - полный экспорт проекта CVAT в формате Ultralytics YOLO Detection.
- `data/yolo/ad_surface_full_v1/` - чистый train/val датасет для обучения.
- `models/pretrained/` - исходные pretrained веса YOLO, если нужны для экспериментов.
- `models/trained/` - сохранённые обученные веса и параметры запусков.
- `scripts/` - вспомогательные скрипты.

## Подготовка датасета

Сбор train/val датасета из полного CVAT export:

```bash
.venv/bin/python scripts/prepare_yolo_dataset_from_cvat_export.py --overwrite
```

По умолчанию скрипт читает `detect_new.zip` и пишет результат в `data/yolo/ad_surface_full_v1/`.
Split делается `80/20` со стратификацией по наличию bbox: размеченные и пустые кадры распределяются пропорционально между `train` и `val`.

## Эксперименты обучения

Подготовлены три независимых запуска:

```bash
.venv/bin/python scripts/train_yolo11m_pretrained_img1280_b6_v1.py --dry-run
.venv/bin/python scripts/train_yolo11m_pretrained_img960_b10_antifp_v1.py --dry-run
.venv/bin/python scripts/train_yolo11x_pretrained_img960_b5_v1.py --dry-run
```

`--dry-run` показывает настройки без старта обучения. Чтобы запустить эксперимент, убери `--dry-run`.

Для запуска `train_yolo11x_pretrained_img960_b5_v1.py` нужен файл весов `models/pretrained/yolo11x.pt`.
