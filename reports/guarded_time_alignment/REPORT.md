# Guarded readout v7: точность без ухудшения fault RMSE

База сравнения — main `efc473e415795d64770ef9dfa4f1bc417078da32`, активный default/v5.
Начальный план и первый прогон использовали `984fdf2`; после объединения PR #11
повторены все 19 bags и 76 faults с новым main. Метрики совпали точно.
Встроенная компенсация PR #11 при этом выключена (`wheel_time_compensation=0`),
как в текущем default. Опциональный профиль PR #11 также сохранён и сравнен отдельно.
Ветка: `research/guarded-time-alignment-v7`. PR #14. Это продолжение PR #11,
но его ветка, исходники и результаты этим PR не изменены.

## Измеренный результат

| Метрика | Main/v5 | PR #11 | Guarded v7 |
|---|---:|---:|---:|
| Clean group-macro RMSE скорости, м/с | 0.117138274 | 0.114476684 | 0.114549861 |
| Pooled RMSE скорости, м/с | 0.216723603 | 0.216396651 | 0.216406794 |
| Scalar span distance group-macro RMSE, м | 4.630977808 | 4.577133777 | 4.595480653 |
| Fault-event group-macro RMSE, м/с | 0.538434411 | 0.548979449 | 0.538286783 |
| Среднее recovery, с | 0.239840173 | 0.256506840 | 0.254840173 |
| Matched clean speed samples | 698891 | 698891 | 698891 |
| False stops, clean / fault | 18 / 0 | 18 / 0 | 18 / 0 |
| Нет recovery за 10 с | 0 | 0 | 0 |

К main: **−2,2097% clean macro**, −0,1462% pooled, **−0,7665% scalar distance**,
−0,0274% fault RMSE. У прежнего PR #11 fault RMSE была хуже main на 1,9585%.
Новый вариант устраняет эту регрессию, немного уступая PR #11 в clean-точности.
Маленькое изменение fault RMSE не объявляется статистически значимым улучшением.

Все 19 validation bags / 10 групп включены. GNSS доступен в 9 группах,
30 clean bag/receiver-парах. Четыре bags без reference остаются missing.
Сравниваются оба приёмника; всего 76 fault-сценариев и 120 receiver-сравнений.
В clean 25 пар улучшились, 5 ухудшились. Наибольшая регрессия около 4,84%.
Число выигравших пар само по себе не доказывает отсутствие случайности.

## Строгие критерии main

План опубликован коммитом `c15bcb8` до новых измерений. Использованы прежние
критерии main: минимум 2% clean gain либо 5% fault gain; aggregate clean/fault
регрессия не более 0,5%; scalar distance не более 1%; per-bag/receiver clean
регрессия не более max(0,005 м/с, 5% baseline); без потери покрытия, роста ложных
остановок и числа невосстановленных faults. **Все численные условия выполнены.**
Порог 5% из первоначального PR #11 здесь не используется.

Recovery не улучшился: 118 из 120 сравнений без изменений, два медленнее.
На `30618_49fe4c54/master`, bias 5 с: 0.205104267 → 1.005104267 с;
на той же паре dropout 5 с: 0.005104267 → 1.005104267 с.
Среднее +0,015 с; худшее увеличение +1,0 с. Оба восстановления остаются внутри
10 с. Это отдельный компромисс: gate main ограничивает число невосстановленных
faults, а не максимальную/среднюю задержку recovery. Универсальное превосходство
по всем характеристикам не заявляется.

## Почему это работает

При переносе старого wheel measurement прямо в Kalman update (PR #11) менялось
внутреннее состояние модели. Простое выключение компенсации при подозрении на
fault не устранило регрессию на development.

В v7 исходный Observer и его конфигурация остаются прежними. Производный
`GuardedReadoutObserver` добавляет поправку только к возвращаемому Estimate:

```text
delta_v_next = (1 - K) * delta_v + K * a_model * mean_accepted_sample_age
v_output = v_v5 + delta_v_next
s_output = s_v5 + integral(delta_v)
```

K получается из прежнего scalar Joseph update: K = 1 - P_post/P_prior, с учётом
variance floor через ограничение [0,1]. Поправка применяется лишь при двух свежих
согласованных held wheels, без rejection/stale command. При плохих данных она
сбрасывается и блокируется до 0,5 с непрерывно здоровых данных. Prediction-only
ticks не ассимилируют held wheels заново. Ограничение поправки: max_accel × max_age.

Поправка НЕ меняет внутренние v, s, covariance, disturbance и stop/reacquire gates.
Публичные данные нужно брать из возвращаемого Estimate / last_estimate; поля
v/s у объекта остаются внутренним baseline state. В runtime нет второго фильтра.
Добавлены консервативные uncertainty envelopes, не калиброванные интервалы.
Сброс поправки может создавать переходный скачок выходной скорости; дистанция
остаётся согласованным трапециевидным интегралом опубликованной скорости.

Wolfram подтвердил аналитическую рекурсию: при постоянном ускорении и точной
модели сумма baseline bias и поправки равна (1-K) × предыдущая сумма. Это частный
аналитический случай, не гарантия точности при любых faults или манёврах.

## Отбор и воспроизведение

На всех 17 development bags сравнены пять новых гипотез и два baseline.
Все результаты, включая неудачный pair_guard, приведены в development.csv.
Из прошедших строгие development gates выбран readout_long с минимальным clean
macro RMSE. Development clean gain 3,387%; fault RMSE +0,00223%; scalar distance
+0,226%. Общие для baseline и кандидата 46 fault false-stop samples и четыре
неподтверждённых recovery на development не скрыты.

Код опубликован в `be84bef`, затем выбор закреплён в `f525b09` ДО validation.
После validation алгоритм и параметры не менялись. Изменены только pin нового
main в runner и совместимая ROS smoke-интеграция; выбранный модуль сохранил SHA256. Итоговый переносимый runner
точно воспроизвёл все clean/fault per-bag/receiver-метрики и runtime-счётчики.
При --check-inner каждое внутреннее поле сравнивалось с независимым baseline
на каждом такте, в том числе в faults. При --check-disabled выходные массивы
совпали с main точно. Расписание выходов, matching и покрытие одинаковы.

Исходный dataset.zip: SHA256
`d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52`.
Использованы прежние split, evaluator, fault placement, единицы и физика v5.
Test DB не открывались; train GNSS не использовался; физика не переобучалась.
Python 3.13.5, NumPy 2.3.5. Полные локальные журналы, JSON каждого bag, исходники
отклонённых вариантов и повторные прогоны включены в прилагаемый к ответу evidence ZIP.
В репозитории сохранены компактные таблицы и переносимый runner.

```bash
python3 tools/get_dataset.py
python3.13 -m venv .venv-research
.venv-research/bin/python -m pip install -r requirements-research.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-research/bin/python \
  tools/research_guarded/compare.py --output /tmp/guarded-v7-fresh \
  --workers 2 --check-disabled --check-inner
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
.venv-research/bin/python -m unittest discover -s research/tests -v
```

Runner сохраняет started.json, access.json, bags/*.json и results.json, проверяет
SHA256 и роль до DB IO и не перезаписывает существующий output. Для проверки
канонических измерений взять clean/stress/summary/decision из results.json и
сериализовать json.dumps(payload, sort_keys=True, separators=(',', ':')).encode().
SHA256 результата: `f344855ae43403c8aae7b075af9924a11eb1a225b4095bae328aa46eaa466139`.
Времена запуска/elapsed не входят в этот digest.

## Тесты и активация

Добавлено 30 dependency-free unit-тестов и 8 research-тестов. Локально они прошли.
Новый установленный ROS launch проверяется существующим calibrated smoke вместе
с baseline и прежним time-aligned launch. В существующих CI jobs это выполняется и offline при 2 CPU /
500 MB. Статусы конкретного финального commit и ссылки на CI — в PR #14.
Базовые core.py, node.py, timeline.py, setup.py, default YAML, v5-профиль,
promotion decisions, workflow-файлы и старые integrity tests не менялись.

После сборки и source install/setup.bash:

```bash
ros2 launch reserve_odometry guarded_odometry.launch.py
```

Нужен новый launch: старый odometry.launch.py продолжает запускать v5, даже если
ему передать только новый YAML. readout.gain=0 у нового adapter возвращает точный
baseline. Default не переключён, merge не выполнен, архив сдачи не переиздан.

## Границы результата

Validation уже использовался ранее, это не новый независимый test. Независимая
статистическая значимость и универсальное обобщение не заявляются. Дистанция —
переякоренные spans интеграла GNSS-speed, не XYZ/ENU и не полный terminal drift.
Предположение о единицах 1/3.6 сохранено. Новый длительный real-bag ROS latency
benchmark не выполнен. Решение не является сертифицированным компонентом безопасности.
