# Merge-кандидат v5: более быстрая адаптация disturbance

Выбран `adaptation_05s`: `adaptation_tau_s=0.5` вместо 8.0 с. Остальные
параметры, физическая модель, runtime, масштаб колёс и временная логика совпадают
с main `bfdcace8da9d8db16c43e803c513f4aeb2531f63`. Меньшая постоянная времени
быстрее подстраивает ограниченную оценку неучтённого ускорения по двум
согласованным, прошедшим model-gate колёсам. При сбоях обучение disturbance
по-прежнему приостанавливается.

Профиль добавлен отдельно как `config/adaptive_v5.yaml`. `default.yaml` и
опубликованный релиз v4 сохраняются. Новый профиль не проходил независимый
final test и не является заменой ранее опубликованного архива сдачи.

## Измеренный результат относительно текущего main

| Метрика | Main v4 | Кандидат v5 | Изменение |
|---|---:|---:|---:|
| Clean group-macro RMSE скорости, м/с | 0.118067743 | 0.117138274 | −0.787% |
| Fault-event group-macro RMSE, м/с | 0.569972910 | 0.538434411 | −5.533% |
| Pooled RMSE скорости, м/с | 0.216872431 | 0.216723603 | −0.069% |
| Scalar span group-macro RMSE дистанции, м | 4.620252 | 4.630978 | **+0.232%** |
| Сопоставленные точки скорости | 698891 | 698891 | без потери |
| Ложные stop samples, чистые данные | 18 | 18 | без роста |
| Ложные stop samples, fault-окна | 0 | 0 | без роста |
| Fault-сравнения без подтверждённого recovery | 0 | 0 | без роста |

Дистанция здесь — переякоренная скалярная ошибка на непрерывных отрезках GNSS-speed,
не xyz и не полный терминальный дрейф. Небольшое ухудшение сохранено в отчёте:
кандидат сильнее по основным метрикам скорости и сбоев, но не по всем метрикам.

Все 19 validation-bag / 10 групп обработаны; GNSS-метрики доступны в 9 группах,
30 bag/receiver-парах. Четыре bag без reference не считаются нулевой ошибкой.
76 fault-сценариев, 120 сравнений с доступным приёмником. Оба приёмника сохранены.
Baseline точно воспроизводит все bag/receiver clean RMSE из опубликованной v4.

## Критерий принятия и история отбора

До первого запуска задано: минимум 2% clean gain **или** 5% fault-event gain;
ухудшение каждой из этих агрегированных метрик не более 1%; отсутствие
bag/receiver clean-регрессии больше max(0.01 м/с, 10%); отсутствие потери
покрытия, увеличения ложных остановок, изменения расписания или нарушения
причинности. Кандидат 0.5 с прошёл все эти условия.

За три последовательных раунда проверено 10 вариантов, в каждом повторён main.
Планы каждого раунда закреплены коммитом до вычисления его метрик. Результаты
предыдущего раунда использованы для выбора следующего; это адаптивный поиск
на повторно используемом validation, а не независимая проверка обобщения.

| Раунд | Варианты | Итог |
|---|---|---|
| 1 | process noise ×2/×4, адаптация 4/16 с | Все отклонены; ×4 добавил ложные остановки и ухудшил fault RMSE на 11.3% |
| 2 | адаптация 1/2 с, отдельно и с noise ×2 | Все отклонены: лучший fault gain 4.22%, ниже заданных 5% |
| 3 | адаптация 0.5/0.25 с | 0.5 с принят; 0.25 с отклонён (fault gain 1.94%) |

Исторический H01 на v3 сохранён в ветке `research/reacquire-multirate`, commit
`219ec2a`. После обновления main выяснилось, что v4 уже устраняет эту проблему;
H01 не засчитывается как новое улучшение.

Описательный paired-group bootstrap после отбора: 95%-интервал clean gain
0.38…1.59%, fault gain −2.55…28.72%. Последний включает ноль; нет основания
заявлять независимую статистическую значимость или универсальную устойчивость.
Новые test-payloads не читались; старый final test v4 не переоценивался.

## Запуск

После обычной ROS Humble сборки и `source install/setup.bash`:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/src/reserve_odometry/config/adaptive_v5.yaml"
```

После установки пакет содержит `share/reserve_odometry/config/adaptive_v5.yaml`.
Для сравнения с main передать `config/default.yaml`. Runtime по-прежнему
получает только три vehicle-топика; научные зависимости нужны лишь исследованию.

## Проверки и воспроизведение

65 dependency-free тестов, включая повтор существующих observer-сценариев с
выбранной конфигурацией; 26 исследовательских проверок. CI запускает **установленный**
профиль v5 отдельным ROS launch, сверяет все model-параметры с измеренным JSON,
проверяет частоту, timestamps, типы и отсутствие GNSS/IMU подписок. Та же проверка
добавлена в offline-контейнер с 2 CPU / 500 MB. Короткий smoke не заменяет новый
длительный latency benchmark; измерения v4 не выдаются за измерения v5.

```bash
python3 tools/get_dataset.py
python3.13 -m venv .venv-research
.venv-research/bin/python -m pip install -r requirements-research.txt
OPENBLAS_NUM_THREADS=1 .venv-research/bin/python tools/research_v5/compare.py \
  --output /tmp/v5-fresh-verification --workers 2
.venv-research/bin/python tools/research_v5/report.py
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
.venv-research/bin/python -m unittest discover -s research/tests -v
```

Runner отказывается перезаписывать существующий output. Повторяет последний
закреплённый план (main / 0.5 с / 0.25 с); старые планы и результаты сохранены.
Для предыдущих раундов использовать соответствующие коммиты, а не менять
опубликованные результаты. Датасет проверяется по SHA256 архива и каждого bag;
загрузчик запрещает test ещё до SQLite IO.

Полные evidence: [selection.json](selection.json),
[round1](round1/decision.json), [round2](round2/decision.json),
[round3](round3/decision.json), [все bag-level метрики](round3/results.json).
Исходники evaluator и модели, план, split и версии Python/NumPy закреплены
SHA256 в `started.json` каждого раунда.

Удалённые измерения:
[раунд 1](https://github.com/jabrailkhalil/hack/actions/runs/36162455899),
[раунд 2](https://github.com/jabrailkhalil/hack/actions/runs/36163069572),
[раунд 3](https://github.com/jabrailkhalil/hack/actions/runs/36163407638).
