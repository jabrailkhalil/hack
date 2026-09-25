# Наш вариант D — заданная геометрия пути

Ветка: `experiments/tram-d`. **SYNTHETIC_GEOMETRY_ONLY / REAL_MAP_NOT_EVALUATED.**

[Результаты](tools/tram_port/RESULTS.md) · [Метрики](tools/tram_port/metrics.csv) · [Запуск](tools/tram_port/README.md).

D преобразует координату вдоль заданной полилинии в xyz, но не восстанавливает неизвестный маршрут. Запуск: `python tools/tram_port/run_variant.py --output tools/tram_port/runs/fresh`. Это отдельная проверка геометрии; активный ROS champion не заменяется.
