# RESULTS — C

**SYNTHETIC_NATIVE_FIXTURES_ONLY / REAL_DATA_NOT_EVALUATED.** Ветка `experiments/tram-c`.

Исходный ResidualEKF: B с ограниченной ridge-поправкой ускорения. Включены B как зависимость, нормализация и обученные коэффициенты vendor/ours/research/model.json. Ни формулы, ни параметры не изменены и не переобучены на hack. Вызов — через OurObserver и pinned hack Timeline.

metrics.csv содержит все 19 строк C из предыдущего полного native-аудита. rmse_mps — paired RMSE всего случая; event_rmse_mps — окно отказа; path_rmse_m — относительный путь, не ENU. Пустое значение означает N/A. Протокол и происхождение — PROTOCOL.json и SOURCES.json.

Mixed stream: RMSE 0.38182774592627283 м/с. Общий скачок 1,2 с: event RMSE 0.8376269876224531 м/с. Отказ обоих колёс 10 с при постоянной скорости: event RMSE 0.18670160498740582 м/с. Блокировка обоих 1 с: event RMSE 0.013352105097612126 м/с.

На mixed stream и десятисекундном пропуске C не улучшает B. Это отрицательный результат переноса замороженной поправки, не доказательство бесполезности обучения в общем случае. Постоянная скорость dropout и несовпадение stamp/value в ramp-fixture ограничивают интерпретацию. Spike 20 мс не дошёл до step. Общая таблица — COMPARISON.md.

Перед публикацией 23 контрактных теста и selector повторно прошли; хеши совпали с прошлым аудитом. См. PUBLISH_CHECKS.json. Для исходной десятимодельной paired-маски запускать run_variant.py --all. Реальный GNSS validation, ROS/Docker/colcon и лимиты CPU/RAM не проверены; сертификатов точности или безопасности нет.
