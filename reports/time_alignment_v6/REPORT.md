# Компенсация возраста измерений: сравнение с текущим main

База PR #11: **984fdf2fc4faf05325249215d6b8541c0e68209a**, после PR #12.
Активный main теперь использует уже существующий v5. Наш патч оставляет этот
профиль стандартным, добавляя opt-in `time_aligned_v6.yaml`.

| Метрика | Текущий main / v5 | Кандидат | Изменение |
|---|---:|---:|---:|
| Group-macro RMSE скорости, м/с | 0.117138274 | 0.114476684 | **−2.2722%** |
| Pooled RMSE скорости, м/с | 0.216723603 | 0.216396651 | −0.1509% |
| Group-macro scalar-distance RMSE, м | 4.630977808 | 4.577133777 | **−1.1627%** |
| Fault-event RMSE скорости, м/с | 0.538434411 | 0.548979449 | **+1.9585% хуже** |
| Среднее recovery, с | 0.239840173 | 0.256506840 | +0.01667 с |

Все 19 validation-bags / 10 групп; GNSS в девяти группах, оба приёмника,
698891 сопоставленная точка. 25 из 30 bag/receiver-пар улучшились, пять хуже.
Покрытие и число ложных остановок не изменились. 76 fault-сценариев, 120
сравнимых receiver-случаев; во всех восстановление подтверждено за 10 с.

**Кандидат не проходит порог автоматического promotion текущего main:**
проект допускает 0.5% fault-регрессии, измерено 1.9585%. Наш исходный локальный
план допускал 5%; эти критерии различаются и не подменяются после результата.
Это альтернативный профиль ради точности обычного движения, а не универсально
лучший champion. Стандартный запуск, default.yaml и решение promotion из #12
не изменены. Объединение PR само по себе не включает новую компенсацию.

## Механизм и получение результата

Main применяет принятые значения колёс без переноса от timestamp измерения к
моменту выхода. При постоянном ускорении возникает ошибка `-a*age`. Патч после
прежних raw rate/model-gates использует `z + a_model*age` и добавляет к R
`process_noise_v*age` (x4 при устаревшей команде). Остаются прежние ограничения
скорости/ускорения, исходные timestamps, однократная ассимиляция, stop/adaptation/
reacquisition. Wolfram проверил остаточную ошибку `age*error(a_model)`; это не
доказательство точной Kalman covariance или статистической значимости.

На 17 development-bags сравнивались шесть вариантов и два baseline. Точное
интегрирование actuator не помогло и было отклонено. Выбран age+uncertainty на
профиле v5, код/параметры зафиксированы до validation и затем не подбирались.
Подробные первоначальные эксперименты: [HISTORICAL_REPORT.md](HISTORICAL_REPORT.md),
[development.csv](development.csv), [локальный план](selection_before_validation.json),
[символьная проверка](wolfram.wl).

После изменения main выполнен новый полный paired replay на актуальной базе:
**все per-bag clean/fault-метрики и runtime-счётчики точно совпали** с прежним
результатом. Отключённая компенсация на всех 19 bags побайтно воспроизвела
массивы выходов и счётчики обоих baseline. Подтверждение:
[current_main_confirmation.json](current_main_confirmation.json).

Core main по-прежнему имеет blob `f6fc8ecd0b4e16018d814407b1944ce26ea550b0`;
actual default.yaml побайтно совпадает с прежним adaptive_v5.yaml. Runner проверяет
их и evaluator/split по хэшам, не выдаёт более слабый v4 за текущий main.
В сохранённых исходных JSON ключ `main_v5` означает актуальный main, а `main`
означает исторический v4 до #12. Полные агрегаты: [summary.json](summary.json),
все clean-пары с отсутствующими значениями: [clean.csv](clean.csv).

Наш runner/отчёты перенесены в отдельные каталоги; чужие `tools/research_v6` и
`reports/research_v6`, решения и отклонённые эксперименты сохранены без изменений.
Исторические хэши core проверяются по неизменяемому архиву, а совместимость
активного v5 дополнительно проверяется функционально. Старые evidence не переписаны.

## Воспроизведение

```bash
python3 tools/get_dataset.py
python3.13 -m venv .venv-research
.venv-research/bin/python -m pip install -r requirements-research.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-research/bin/python \
  tools/research_time_alignment/compare.py --output /tmp/time-alignment-new --workers 2 --check-disabled
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
.venv-research/bin/python -m unittest discover -s research/tests -v
```

Runner не перезаписывает output, сохраняет per-bag JSON, access.json и полный
results.json. Его поле eligible относится к исходному локальному плану 5%,
**не** к политике promotion проекта 0.5%. Test DB не открываются.
После обычной сборки и `source install/setup.bash`:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/src/reserve_odometry/config/time_aligned_v6.yaml"
```

## Ограничения

Validation ранее использовался при выборе v5; это не независимый final test.
Дистанция — RMSE переякоренных непрерывных spans интеграла GNSS-speed, не XYZ/ENU
и не полный terminal drift. GNSS не используется runtime. Единицы 1/3.6 остаются
эмпирическим допущением. Длительный новый ROS-бенчмарк кандидата не заявляется;
актуальные core/research/ROS/offline checks находятся в PR #11.
