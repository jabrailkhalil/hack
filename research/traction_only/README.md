# Traction-only: один кандидат поверх v8

**Подготовлен к эксперименту, не объявлен новым чемпионом.** Основное решение остаётся v8, main `b2783206000091ab11a1c11ac3ff79082188a4fb`. В этой ветке меняется только исследовательский каталог; обычный запуск по-прежнему использует v8.

## Почему эта база и это изменение

Полное сравнение A/B/C/H1/H2 на тех же 19 validation bags оставило v8: clean group-macro RMSE 0.114549861 м/с, original fault-event RMSE 0.538286783 м/с. Это reused validation, не официальный score. Источник: `reports/adjudication/REPORT.md` на main.

Поздние результаты не дают допустимой замены. H36 уменьшает development fault RMSE на 18.624%, но ухудшает полную faulted distance на 5.503%; H44 G: -9.705% / +3.835%. H41 выглядит более сбалансированным (-0.632% clean, -2.196% fault), но не прошёл заранее установленный минимум выигрыша; его стоимость step выросла примерно на 40-49%. I01 causal reserve также не прошёл distance/gain gates. H42/H43 являются компонентами данных/диагностики, а не новыми runtime-оценивателями. Остальные рассмотренные незавершённые и отклонённые исследования не получают статус победителя без сопоставимого законченного результата.

Основание следующего изменения: `review/h44-diagnosis-20260926/reports/review_H44/REVIEW.md`. В трёх заранее известных development-контрпримерах раздельное вмешательство показало вред изменения тормозного коэффициента H44 и пользу исследования тяги отдельно. Это выбранные диагностические случаи, не общий тест нового кандидата.

| Параметр | v8 | Этот кандидат |
|---|---:|---:|
| total_motor_torque_nm | 2905.0616664738573 | 3149.748421403977 |
| max_power_w | 280873.5334860941 | 429127.7144908343 |
| max_brake_force_n | 45568.80940352644 | **45568.80940352644** |

Два новых значения взяты без округления из H44 `research/R5/H44/fitted/gnss.json`, commit `0ca93500d4d305c21c998bfd8d2a2e78c98b90ad`, blob `de7936ed7923422f216361e632510a9437f7c0ff`. Это эффективная параметризация, не паспортные характеристики трамвая. Повторного fitting или перебора не было.

Используется настоящий неизменный `GuardedReadoutObserver`: вся физическая структура, торможение как функция одинакового состояния, адаптация d, readout, guards, Timeline и масштабы прежние. Однако другая тяга меняет предысторию d/v: нельзя обещать совпадение всей последующей тормозной траектории. Конфигурация включена с начала каждого replay, не переключается при обнаружении dropout. Нет GNSS/IMU, bag ID, fault flags или второго фильтра в runtime.

## Что находится в ветке

`runtime.py` создаёт кандидат и точный выключенный v8; `traction_only.yaml` позволяет явно запустить кандидат существующей ROS-нодой. `BASELINE_PINS.json` фиксирует неизменные numerical/scorer/source bytes. `replay.py` готовит пять фиксированных профилей: v8, кандидат, полный H44 G, только торможение H44 и выключенный кандидат. Два H44 controls нужны для объяснения механизма и не могут автоматически стать новым победителем.

Стенд по явной команде читает только 17 development bags, проверяет их SHA256 до SQLite, сохраняет оба GNSS и missing=null. Сравнивает прежние cropped original faults и полные faulted trajectories, сохраняет NPZ/JSON, residual delta_s после отказа и в конце записи. Формулы scoring/matching/fault anchors импортируются неизменными. Полная ошибка пути не подменяется скоростью внутри короткого отказа. Дистанция остаётся scalar span surrogate, не XYZ.

Это **подготовленный primary-stage driver**, не полный автоматический допуск: low-speed/common-mode suites, per-group/safety/train-check и enabled ROS ещё требуют отдельного этапа по PROTOCOL.md. Даже положительный primary результат не разрешает merge. Validation/final test CLI здесь отсутствует.

## Команды

Из корня репозитория, с установленными research-зависимостями:

```bash
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/traction_only -p 'test_*.py' -v
python research/traction_only/replay.py
```

Вторая команда только проверяет hashes и печатает конфигурации, не читает измерения. Следующий эксперимент запускается отдельно:

```bash
python research/traction_only/replay.py --run-development \
  --data-root /absolute/path/to/dataset/data \
  --output /absolute/path/to/NEW-traction-development
```

Каталог результата не должен существовать. Последовательный offline replay намеренный: прежний comparator временно подменяет factory в модуле, его нельзя вызывать из параллельных threads. Никакого Actions dispatch или автоматического fitting.

Явный исследовательский ROS-запуск после обычной сборки main-пакета:

```bash
bash submission/build.sh
source /opt/ros/humble/setup.bash
source install_main/setup.bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/research/traction_only/traction_only.yaml"
```

Этот ROS-рецепт подготовлен, но не исполнен в текущем проходе. Обычный `bash submission/run.sh` остаётся v8.

## Выполнено сейчас

21 новый synthetic/config/runner test, 156 historical runtime tests и 43 research-integrity tests прошли локально. Реальные bags не открывались; fitting, development accuracy, validation, final test, ROS latency/RSS не выполнялись. См. VERIFICATION.json. Эти числа не являются результатом сравнительного эксперимента или новым CI PASS.
