# Одометрия v6: причинная компенсация возраста колёсных измерений

База — **main 2f7851364c6afe9786fad040e0938454d8b0d210**, включая PR #10.
Изменён алгоритм коррекции в `core.py`, новый профиль `time_aligned_v6.yaml`.
Сравниваются оба существующих профиля main, не устаревший baseline v2.

## Результат на реальных validation-bags

| Метрика | Main default | Main v5 | V6 |
|---|---:|---:|---:|
| Group-macro speed RMSE, м/с | 0.118067743 | 0.117138274 | **0.114476684** |
| Pooled speed RMSE, м/с | 0.216872431 | 0.216723603 | **0.216396651** |
| Group-macro scalar distance RMSE, м | 4.620252102 | 4.630977808 | **4.577133777** |
| Group-macro fault-event speed RMSE, м/с | 0.569972910 | **0.538434411** | 0.548979449 |
| Matched samples | 698891 | 698891 | 698891 |
| Ложные stop samples clean / fault | 18 / 0 | 18 / 0 | 18 / 0 |
| Среднее recovery, с | 0.294006840 | **0.239840173** | 0.256506840 |

V6 против default: clean macro **−3.0415%**, pooled −0.2194%, distance −0.9332%,
fault −3.6832%. Против уже имеющегося v5: clean macro **−2.2722%**, pooled
−0.1509%, distance −1.1627%, но **fault RMSE хуже на 1.9585%**, recovery
медленнее в среднем на 0.01667 с. Превосходство по всем метрикам не заявляется.

Все 19 validation-bags / 10 групп, GNSS в девяти группах. Оба приёмника сохранены,
30 сравнимых bag/receiver-пар, четыре bags без reference не считаются нулевой
ошибкой. К каждому baseline улучшились 25 пар, пять ухудшились. Ни одна
clean-регрессия не превысила `max(0.01 м/с, 10% baseline)`; покрытие одинаковое.
76 fault-сценариев / 120 сравнимых receiver-случаев, recovery за 10 с подтверждён
во всех случаях с reference. Отдельные ошибки и отсутствующие значения:
[clean.csv](clean.csv); полная точность агрегатов и хэши: [summary.json](summary.json).

## Почему помогает и как выбран вариант

В main принятая скорость в `t_sample` корректирует состояние в `t` без поправки
на возраст. При постоянном ускорении это вносит `−a*age`. V6 после неизменённых
raw rate/model-gates применяет `z_aligned = z + a_model*age` с прежними пределами
скорости и ускорения. `R` увеличивается на `process_noise_v*age` (вчетверо при
устаревшей команде). Это инженерный запас, не точная out-of-sequence Kalman
covariance и не калиброванный CI. Wolfram символически подтвердил остаточную
ошибку `age*error(a_model)` вместо `−age*a`; [проверка](wolfram.wl).

Samples/timestamps не меняются: адаптация, stop, reacquisition, duplicate gates
по-прежнему используют исходные данные. Нет GNSS в runtime, будущих данных,
повторной ассимиляции, смены Timeline/20 Гц/нулевой deliberate delay.

На 17 development-bags проверено шесть новых вариантов и два baseline в двух
локальных раундах: [development.csv](development.csv). Точный интегратор
actuator ухудшил результат и не вошёл в патч. Выбран `v5 + age + noise allowance`:
development clean gain 4.3884% к default. Без добавки R выигрыш был больше, но
выбран более осторожный по доверию к старым данным вариант. Scalar distance на
development у него хуже v5 (5.326236295 против 5.298327606 м), хотя лучше default
(5.356044492 м); улучшение к v5 по дистанции получено на validation.

Код/параметры зафиксированы до validation: [локальный план](selection_before_validation.json).
Это не внешняя предрегистрация. После validation модель не менялась. Условия:
lower clean macro к обоим профилям; нет указанных bag-регрессий, потери покрытия,
роста false stops; fault macro не хуже каждого baseline более чем на 5%, distance
не хуже более чем на 1%. Кандидат прошёл, пороги после результата не менялись.

## Как проверено

Runner использует неизменённые evaluator/match/metrics текущего main, одинаковые
входы, порядок прихода, timestamps и общие маски reference. Baseline-core из
неизменяемого ZIP проверяется по blob `f6fc8ecd0b4e16018d814407b1944ce26ea550b0`:
он **побайтно идентичен core.py в main 2f785136**. Конфигурации — именно
текущие default/v5; их старые validation-агрегаты воспроизведены. Остальные
baseline/evaluator/split-файлы также закреплены SHA256.

Fault placement, 20-секундный прогрев и 10-секундный recovery взяты из main:
front +5 м/с на 5 с, оба dropout на 5/10 с, оба lock на 3 с. Recovery требует
20 последовательных ticks с ошибкой <0.25 м/с. Group-macro сначала усредняет
RMSE внутри групп, затем группы с равным весом; pooled взвешен числом samples.

Повторный переносимый runner **точно воспроизвёл все bag/receiver clean/fault
метрики и runtime-счётчики**. На всех 19 bags оба профиля с выключенной новой
функцией дают точно прежние массивы выходов и счётчики. Локально PASS: 92 unit
(было 65), 25 доступных research tests, compileall. Полный remote CI дополнительно
проверяет шесть существующих v5 research tests и установленный профиль v6
в ROS Humble/offline 2 CPU / 500 MB. Актуальные статусы — checks PR #11.

Исторические v4/v5 integrity-тесты проверяют старый core в неизменяемом ZIP,
а не запрещают новую opt-in модель в worktree. Старые хэши, FREEZE, ZIP, отчёты
и пороги evaluator не переписаны. Workflow-файлы не изменены.

Датасет взят из существующего artifact `research-workspace`, run 36151739124;
проверены SHA256 organizer ZIP и использованных bags. Test DB не открывались,
train GNSS не использовался, физическая модель не переобучалась.

## Воспроизведение и запуск

```bash
python3 tools/get_dataset.py
python3.13 -m venv .venv-research
.venv-research/bin/python -m pip install -r requirements-research.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-research/bin/python \
  tools/research_v6/compare.py --output /tmp/v6-new-run --workers 2 --check-disabled
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
.venv-research/bin/python -m unittest discover -s research/tests -v
```

Output не перезаписывается, test-доступ запрещён, каждый DB проверяется по SHA.
`results.json` содержит все clean/fault метрики без округления; `bags/` и
`access.json` содержат детали и журнал доступа. CSV округлён до 12 значащих цифр.
После сборки и `source install/setup.bash` новый профиль включается явно:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/src/reserve_odometry/config/time_aligned_v6.yaml"
```

## Ограничения

Validation ранее использовался для v5: это **не новый независимый test** и не
доказательство статистической значимости. Дистанция — переякоренные непрерывные
spans интеграла GNSS-speed, не xyz/ENU и не полный terminal drift. Старые final
баллы v4 не приписываются кандидату. Эмпирические единицы 1/3.6 сохранены.
Обычный default и архив v4 не заменены. Перед сменой релизного профиля нужны
независимые bags и новый длительный ROS/runtime benchmark; сертификация
безопасности не заявляется.
