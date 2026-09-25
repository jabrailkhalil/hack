# Инструкция сборки, запуска и проверки

## Среда

Целевая среда: Ubuntu 22.04, ROS 2 Humble, системный Python 3.10, colcon. Windows напрямую не является проверенной целевой средой; использовать Ubuntu/WSL2 или подготовленный Linux-контейнер. Runtime не требует numpy/pandas, torch, pip-догрузки моделей или интернета. Numpy/pandas нужны только отдельным offline tools.

Два ROS-пакета уже лежат в `src/`. Не копировать вторую папку `tram_vehicle_msgs` из архива в тот же workspace: получится дубликат пакета. `.msg` взяты у организатора; у служебных package.xml/CMakeLists добавлены maintainer и явный find_package(ament_cmake), чтобы пакет собирался.

## Сборка

```bash
cd hack
source /opt/ros/humble/setup.bash
colcon build --executor sequential
source install/setup.bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_smoke.py
python3 tests/cdr_roundtrip.py
```

При отсутствии зависимостей установить их **до отключения сети**:

```bash
sudo apt-get update
sudo apt-get install python3-colcon-common-extensions ros-humble-ros-base \
  ros-humble-diagnostic-msgs ros-humble-nav-msgs ros-humble-std-srvs
```

`ros-humble-ros-base` предполагает уже настроенный официальный apt-репозиторий ROS. Не запускать apt/pip/rosdep во время offline-проверки сборки.

## Получить ту же версию данных

```bash
python3 tools/get_dataset.py
ros2 bag info dataset/data/30618_0652866c
```

Скрипт скачивает публичный архив организатора, проверяет SHA256 и распаковывает две оболочки ZIP. Все raw-файлы игнорируются Git. Изменение SHA останавливает работу: сначала надо прочитать новый README.

## Запуск без /clock

Терминал 1:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch reserve_odometry odometry.launch.py
```

Терминал 2, также source обоих setup:

```bash
ros2 bag play dataset/data/30618_0652866c --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

По умолчанию `clock_mode=input_stamp`: время оценки идёт от header.stamp входов. Wall clock в результат не подставляется. Публикация начинается после двух согласованных колёсных измерений. Если все входы исчезли, source clock перестаёт двигаться; это ограничение данного режима.

## Replay с /clock для испытания полного dropout

Терминал 1:

```bash
ros2 run reserve_odometry odometry_node --ros-args \
  --params-file src/reserve_odometry/config/default.yaml \
  -p use_sim_time:=true -p clock_mode:=ros_clock
```

Терминал 2:

```bash
ros2 bag play dataset/data/30618_0652866c --clock 100 --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

`/clock` остаётся активным при отсутствии измерений, если продолжается bag. При паузе bag положение не должно продолжать изменяться. Для независимых bag перезапускать ноду. После seek вызвать reset и считать новый относительный сегмент:

```bash
ros2 service call /reserve_odometry/reset std_srvs/srv/Trigger '{}'
```

В текущем baseline большой скачок времени может автоматически сбросить относительную s; см. SOLUTION §9. Не выдавать это за отсутствие дрейфа полного прогона.

## Ожидаемый контракт

| Топик | Тип | Проверить |
|---|---|---|
| /result/velocity | tram_vehicle_msgs/msg/VelocitySensor | velocity в м/с; header.stamp из времени входа; frame_id=base_link |
| /result/position | nav_msgs/msg/Odometry | position, quaternion, twist.linear.x, covariance; child_frame_id=base_link |
| /result/diagnostics | diagnostic_msgs/msg/DiagnosticArray | режим, причины отклонения датчиков, ошибки, сбросы времени |

```bash
ros2 node info /reserve_odometry
ros2 topic info /result/velocity -v
ros2 topic echo /result/velocity --once
ros2 topic echo /result/position --once
ros2 topic hz /result/velocity
ros2 topic hz /result/position
ros2 topic echo /result/diagnostics --once
```

Проверить, что у estimator нет GNSS/IMU подписок. Входной QoS best-effort совместим и с reliable-проигрывателем. Выходной reliable совместим с best-effort-судьёй. Возможная потеря пакетов всё равно учитывается через age/diagnostics.

## Карта

CSV должен содержать x,y,z (z необязателен, тогда 0), без повторяющихся соседних точек, в **разрешённой и согласованной с судьёй** метрической системе. Запуск:

```bash
ros2 run reserve_odometry odometry_node --ros-args \
  -p route_csv:=/absolute/path/authorized_route.csv \
  -p route_s0:=0.0 -p route_frame:=map
```

Нода не определяет автоматически s0, GNSS-origin, маршрут и положение стрелок. Без CSV публикуется `(s,0,0)` в `odom_path_1d`, не ENU. За границей карты публикация position прекращается, а не возвращает фиктивную точку. Для полноценной сдачи это надо закрыть правильным маршрутом/правилом, согласованным с организатором.

## Воспроизвести offline smoke-метрики

```bash
python3 -m pip install -r requirements-dev.txt
python3 tools/export_bags.py \
  dataset/data/30618_0652866c dataset/data/30618_1551d0a9 \
  dataset/data/30618_27e994fc dataset/data/30618_e151d6e4 \
  dataset/data/30639_0ab96c59 dataset/data/30639_9c362687 \
  dataset/data/30639_c31df386 dataset/data/30639_e4379d7f
python3 tools/audit_units.py exports
python3 tools/replay_csv.py exports/*.csv.gz --output reports/reproduced_smoke.json
```

Команды pip относятся к разработке, не runtime/offline-colcon. Не использовать экспорт GNSS для runtime. `replay_csv.py` воспроизводит порядок поступления записей, а GNSS сравнивает после расчёта. Ветка inference продвигает время только по трём разрешённым топикам.

## Offline и ресурсный контейнер

Подготовить образ с интернетом:

```bash
docker build -t tram-odometry-env -f Dockerfile.environment .
```

Сборка и ROS smoke без сети, с ограничениями всего контейнера:

```bash
docker run --rm --network none --cpus 2 --memory 512m \
  -e CMAKE_BUILD_PARALLEL_LEVEL=2 -e MAKEFLAGS=-j2 \
  -v "$PWD:/work" -w /work tram-odometry-env bash -lc '
    set -e
    source /opt/ros/humble/setup.bash
    colcon --log-base log_offline build --build-base build_offline --install-base install_offline --executor sequential
    source install_offline/setup.bash
    python3 tests/ros_smoke.py
    python3 tests/cdr_roundtrip.py
  '
```

Это короткий integration smoke, а не долгий тест точности, RSS и worst-case latency на трамвае. Сетевой namespace none не мешает локальным узлам в одном контейнере; ROS_LOCALHOST_ONLY задан в образе.

## Измерение задержки перед сдачей

`callback_compute_ms` измеряет только работу timer callback. Его **нельзя** называть задержкой «вход -> результат». Для приёмки сопоставлять ingress каждого нового входа с первой публикацией, в которой он обработан; считать monotonic-time p50/p95/p99/max, отдельно source-stamp age и DDS транспорт. Задержку выравнивания, ожидание следующего шага и очередь включать. Измерение `ros2 topic hz` не заменяет latency. Общая цель из PDF: <=100 мс, пик <=250 мс, >=10 Гц, <=2 ядра, <=0.5 ГБ.
