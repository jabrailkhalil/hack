# Штатный запуск выбранного v8

Актуальная инструкция: [submission/JUDGE_GUIDE.md](../submission/JUDGE_GUIDE.md).

```bash
bash submission/build.sh
bash submission/run.sh
```

Сборка использует install_main, а не старый install. Устанавливается только один executable guarded_odometry_node, odometry.launch.py и champion_v8.yaml. Не выбирайте default.yaml/adaptive_v5/frozen_v4 на текущем установленном пакете: это исторические source fixtures. Для старых опытов используйте их закреплённый commit или неизменный архив.

Список выбранного решения: [ACTIVE_SOLUTION.json](../ACTIVE_SOLUTION.json). Доказательства и ограничения: [reports/adjudication/REPORT.md](../reports/adjudication/REPORT.md). Свежий ROS CI этой упаковки пока не выполнен из-за отказа запуска runners; локальные unit/research/replay/wheel checks не заменяют его.
