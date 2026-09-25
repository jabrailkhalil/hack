# Запуск активного time_aligned_v6 и архива v4

## Выбор версии

Текущий main по решению владельца использует time_aligned_v6 из PR11. На повторно используемом validation он точнее v5 по обычной скорости на 2.2722% и scalar-span дистанции на 1.1627%, но хуже в fault-окнах на 1.9585%. Это компромисс, не pass прежнего автоматического gate и не независимый test. [ACTIVE_PROFILE.json](ACTIVE_PROFILE.json) содержит текущие параметры и хэши; [измерения PR11](../reports/time_alignment_v6/REPORT.md) — полные результаты.

Архив reserve-odometry-v4.zip остаётся историческим: его FREEZE/final-test/24-минутный runtime относятся только к v4. Для отката к v5 передать params_file с adaptive_v5.yaml.

## 1. Среда и сборка

Ubuntu 22.04 x86_64, ROS 2 Humble, системный Python 3.10, colcon. Зависимости подготовить заранее; рецепт — `Dockerfile.environment`. Исследовательские requirements предназначены для отдельного Python 3.13, не системного ROS Python.

Из корня текущего checkout:

```bash
bash submission/build.sh
bash submission/run.sh
```

`build.sh` не скачивает данные и не переоценивает final test. Ноду запускать до bag, после независимых bag перезапускать. Стандартный launch загружает `config/default.yaml`, побайтно равный выбранному `time_aligned_v6.yaml`. Все его model-параметры проверяются отдельным ROS-процессом через GetParameters, а не только чтением YAML.

Во втором терминале:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 bag play /absolute/path/to/bag --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

Голый `ros2 run` без params-file использует базовые `Config()` defaults и не запускает выбранную конфигурацию. Воспроизведение прежнего профиля:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/src/reserve_odometry/config/frozen_v4.yaml"
```

## 2. Контракт

Runtime получает только `/vehicle/driver_position_cmd` (DriverControllerCommand, notch −15..15), `/vehicle/front_bogie_velocity` и `/vehicle/rear_bogie_velocity` (VelocitySensor). GNSS/IMU/LLM и научных библиотек внутри ноды нет.

Выходы: `/result/velocity` — `tram_vehicle_msgs/msg/VelocitySensor`, м/с, frame `base_link`; `/result/position` — `nav_msgs/msg/Odometry`, метры, frame `odom_path_1d`, child `base_link`; `/result/diagnostics` — состояния и причины отклонения входов. Частота 20 Гц, искусственная задержка выравнивания 0 с, stamps относятся ко времени входов. Инициализация требует согласованных валидных показаний двух тележек.

Входной коэффициент `1/3.6` — эмпирическое допущение, а не подтверждённое исправление README организатора. `(s,0,0)` — относительная дистанция, не ENU-траектория; согласование карты и xyz-контракта остаётся обязательным для оценки пространственного положения. Геометрия не восстанавливается из будущего GNSS тестовой записи.

## 3. Полный dropout, pause и seek

Для пропадания всех трёх входов должен продолжаться `/clock`:

```bash
# Терминал 1
bash submission/run.sh --clock
# Терминал 2, после source
ros2 bag play /absolute/path/to/bag --clock 100 --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

В `input_stamp` отсутствие вообще всех входов останавливает время. В `ros_clock` модель прогнозирует при dropout и не продолжает движение на паузе часов. Backward seek начинает новый относительный сегмент; для seek без `/clock` нужен reset/перезапуск:

```bash
ros2 service call /reserve_odometry/reset std_srvs/srv/Trigger '{}'
```

## 4. Проверки и версия измерений

```bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_calibrated_smoke.py
ros2 node info /reserve_odometry
ros2 topic hz /result/velocity
ros2 topic hz /result/position
```

Текущие paired-метрики и реальные timing-отчёты находятся в `reports/research_v6/`. Старый `reports/final/` и `submission/RESULTS.md` — опубликованный v4. Тесты проверяют его точный ZIP и отдельно проверяют active-source по `PROMOTION.json`; смена профиля не получает автоматически старый сертификат freeze.

Сеть при сборке/работе не требуется после подготовки образа. Пример ограниченного окружения:

```bash
docker build -t odometry-env -f Dockerfile.environment .
docker run --rm --network none --cpus 2 --memory 500000000 \
  -v "$PWD:/work" -w /work odometry-env bash -lc 'bash submission/build.sh'
```

Для текущего измерения задержки после подготовки dataset и source ROS/install можно использовать `tools/finalization/ros_benchmark.py --seconds 180 --clock-mode input_stamp --output /tmp/active-timing.json`. Он открывает только заранее просмотренный development bag, не final test; сохраняет p95/p99/max, несопоставленные входы, trace, RSS и CPU. Повторный запуск не равен независимому тесту обобщения.
