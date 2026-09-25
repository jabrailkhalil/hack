# Инструкция для жюри: резервная одометрия v4

## Что проверяется

Решение оценивает продольную скорость и относительную дистанцию трамвая по трём vehicle-топикам. Основной режим положения: `(s,0,0)` в `odom_path_1d`. Это вариант относительной одометрии, допускаемый PDF на странице 5 при отсутствии абсолютной привязки, **не восстановленная ENU/xyz-траектория**. README датасета содержит иной xyz-контракт; расхождение явно зафиксировано в [LIMITATIONS.md](LIMITATIONS.md). Карта пути, origin и ветвь маршрута не выдумываются.

Состав исходников: `src/tram_vehicle_msgs` (два сообщения), `src/reserve_odometry` (ядро и ROS-нода). Никаких внешних моделей, GNSS/IMU-подписок или научных Python-библиотек в runtime. Научные зависимости используются только отдельным offline-evaluator.

## 1. Среда и сборка

Ubuntu 22.04 x86_64, ROS 2 Humble, системный Python 3.10, colcon. Не устанавливать `requirements-research.txt` в системный Python ROS. Перед отключением интернета подготовить ROS base, colcon и пакеты diagnostic_msgs, nav_msgs, std_srvs. `Dockerfile.environment` содержит воспроизводимый рецепт такой предварительной подготовки.

Распаковать `reserve-odometry-v4.zip`, перейти в одноимённую папку:

```bash
cd reserve-odometry-v4
bash submission/build.sh
```

Скрипт выполняет стандартный `colcon build --base-paths src --executor sequential` и unit/ROS-проверки. Интернет при сборке и исполнении решения не нужен. Команда не скачивает датасет и не запускает финальную статистическую оценку.

## 2. Основной запуск

Терминал 1 из корня пакета:

```bash
bash submission/run.sh
```

Терминал 2:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 bag play /absolute/path/to/bag --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

Ноду запускать до bag. После каждого независимого bag перезапускать ноду. `run.sh` всегда подключает проверенный `default.yaml`: обученные коэффициенты v3 и исправленный runtime v4, 20 Гц, без искусственной задержки выравнивания. Голый `ros2 run ...` без params-file оставляет старые defaults и **не является запуском сдаваемой конфигурации**.

## 3. Режим с /clock

Для испытания полного пропадания всех трёх входов нужен продолжающийся источник времени:

```bash
# Терминал 1
bash submission/run.sh --clock
# Терминал 2 (после source)
ros2 bag play /absolute/path/to/bag --clock 100 --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

В основном `input_stamp` режиме время продвигается только входными stamps, поэтому без вообще всех входов оно останавливается. В `ros_clock` режиме оценка продолжает прогноз при dropout, но не интегрирует wall time на паузе `/clock`. Обратный скачок авторитетного `/clock` начинает новый относительный сегмент; без `/clock` seek требует явного reset/перезапуска.

```bash
ros2 service call /reserve_odometry/reset std_srvs/srv/Trigger '{}'
```

## 4. Топики и единицы

| Направление | Топик | Тип / поле |
|---|---|---|
| Вход | `/vehicle/driver_position_cmd` | DriverControllerCommand / `position`, int8 notch −15..15 |
| Вход | `/vehicle/front_bogie_velocity` | VelocitySensor / `velocity` |
| Вход | `/vehicle/rear_bogie_velocity` | VelocitySensor / `velocity` |
| Выход | `/result/velocity` | VelocitySensor / `velocity`, м/с, frame `base_link` |
| Выход | `/result/position` | Odometry / `pose.pose.position`, метры; `twist.twist.linear.x`, м/с |
| Диагностика | `/result/diagnostics` | DiagnosticArray: состояние, причины отказа входов, сбросы, stale |

VelocitySensor и DriverControllerCommand находятся в `tram_vehicle_msgs/msg`. Положение по умолчанию имеет `header.frame_id=odom_path_1d`, `child_frame_id=base_link`. Quaternion единичный для условной продольной оси. Stamps восстанавливаются из исходного integer origin, а не из часов машины. Выходные сообщения не публикуются до двух согласованных валидных колёсных измерений.

Входной коэффициент `front_scale=rear_scale=1/3.6` выбран по эмпирическому аудиту. README организатора называет вход м/с, тогда как отношение raw/GNSS в исследованных записях близко к 3.6. Это **не подтверждённое организатором исправление единиц**. Параметр явный, output всегда SI.

```bash
ros2 node info /reserve_odometry
ros2 topic info /result/velocity -v
ros2 topic echo /result/velocity --once
ros2 topic echo /result/position --once
ros2 topic hz /result/velocity
ros2 topic hz /result/position
ros2 topic echo /result/diagnostics --once
```

## 5. Измерения и воспроизведение

Финальная точность и пропуски эталона приведены в [RESULTS.md](RESULTS.md), полные результаты всех 22 test-bag — `reports/final/test/results.json` и `reports/final/test/bags/`. Train/validation/test разделены по группам, источник/параметры/evaluator закреплены в `FREEZE.json` до теста. GNSS используется только эталоном offline, оба приёмника сохранены.

`tools/finalization/ros_benchmark.py` запускает отдельную ROS-ноду и независимые publisher/subscribers. Он проигрывает реальные SQLite/CDR vehicle-сообщения в порядке записи при 1x и измеряет первое соответствующее сообщение обоих выходов. Непривязанные входы явно учитываются. Это не просто timer callback duration и не ускоренный replay.

```bash
# Датасет загружается заранее, с интернетом и проверкой SHA256.
python3 tools/get_dataset.py
# После source ROS и install; полный заранее просмотренный development-bag:
python3 tools/finalization/ros_benchmark.py --seconds 0 --clock-mode input_stamp \
  --output /tmp/odometry-runtime.json
```

Результат: JSON метрик, trace CSV, resource CSV и node.log. Для исследования/пересчёта точности использовать отдельный Python 3.13 и `requirements-research.txt`. Final-test запуск требует `--authorize-final-test`, проверяет неизменность FREEZE и отказывается перезаписывать существующую папку результатов. Повторное применение test для подбора решения не допускается.

## 6. Проверка без сети и в лимитах

```bash
# Только предварительная подготовка с интернетом:
docker build -t odometry-env -f Dockerfile.environment .
# Сборка и проверки уже без интернета:
docker run --rm --network none --cpus 2 --memory 500000000 \
  -v "$PWD:/work" -w /work odometry-env bash -lc 'bash submission/build.sh'
```

Лимит всего контейнера включает тестовые процессы. Полный performance-прогон и проверка исходников именно из ZIP выполняются отдельно и имеют собственные протоколы. Короткий integration smoke не называется доказательством неограниченной работы без утечек.

## 7. Карта (не включена в базовую сдачу)

Уже реализован загрузчик упорядоченного CSV `x,y,z` в разрешённой метрической системе: `route_csv`, `route_s0`, `route_frame`. Он интерполирует позицию по накопленной длине, а не создаёт маршрут из test GNSS. Без разрешённых карты, origin и выбора ветвей этот режим не используется. За границей известной карты position не подменяется конечной точкой: публикация position прекращается, velocity продолжается и диагностика сообщает ошибку.
