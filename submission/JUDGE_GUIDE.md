# Единственное основное решение: v8

## Сборка и запуск

Среда: Ubuntu 22.04, ROS 2 Humble, colcon. Зависимости подготовить до offline-проверки; рецепт — Dockerfile.environment. Из текущего checkout:

```bash
bash submission/build.sh
bash submission/run.sh
```

Скрипт сборки использует `build_main`, `install_main`, `log_main`, чтобы не запускать устаревшие executables из предыдущего install/. В свежем терминале для штатного запуска:

```bash
source /opt/ros/humble/setup.bash
source install_main/setup.bash
ros2 launch reserve_odometry odometry.launch.py
```

Устанавливаются один executable `guarded_odometry_node`, один launch и один YAML `champion_v8.yaml`. Старый unguarded `odometry_node` больше не устанавливается. Внутренний executable отдельно без параметров не является штатной командой. Исторические варианты воспроизводить из соответствующего commit/архива, не передачей старого YAML в новый launch.

## Входы и результаты

Три входных vehicle-топика: controller position (notch -15..15), front/rear VelocitySensor. GNSS/IMU в runtime не используется. Выход скорости: `/result/velocity`, VelocitySensor, м/с, frame base_link. Положение: `/result/position`, Odometry, метры, `odom_path_1d`, child base_link. Диагностика: `/result/diagnostics`. Частота 20 Гц, timestamps относятся ко времени данных; deliberate alignment wait 0.

Для проверки полного исчезновения всех входов должен продолжаться `/clock`:

```bash
bash submission/run.sh --clock
# В другом подготовленном терминале:
ros2 bag play /absolute/path/to/bag --clock 100 --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

В input_stamp полное отсутствие всех входов останавливает модельные часы. В ros_clock пауза часов не интегрирует путь, backward seek начинает новый относительный сегмент. Для каждой независимой записи ноду перезапускать.

## Проверки

`build.sh` запускает unit tests, проверку установленной поверхности, правильных параметров v8, clock/dropout/pause/seek, low-speed lock и CDR. На дату выбора выполнены 161 локальный test invocation, 43 research tests, два полных paired replay и проверка собранного wheel. Новые GitHub ROS jobs завершаются до запуска шагов; **их PASS не заявляется**. Runtime/config/launch совпадают побайтово с прежним v8; новая упаковка не меняет формулы.

[Полный отчёт](../reports/adjudication/REPORT.md) фиксирует точный объём доказательств. Архив v4/final-test/старый 24-минутный benchmark остаются историческими и не заменяют свежую проверку упаковки.

## Ограничения сдачи

`(s,0,0)` — along-track relative odometry, не xyz/ENU. Карта, origin, допустимая начальная привязка и геометрический контракт судьи должны быть подтверждены отдельно. Масштаб raw wheel `1/3.6` эмпирический. Общий плавный дрейф обоих датчиков не устранён. Нода не сертифицирована для безопасности движения. Репозиторий приватный; доступ жюри и отправка формы автоматически не менялись.
