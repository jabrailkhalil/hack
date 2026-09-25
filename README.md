# Резервная одометрия трамвая

Рабочая основа для кейса Московского транспорта: ROS 2 Humble, нелинейная продольная модель, адаптивная поправка, отдельная проверка передней/задней тележки, оценка скорости и расстояния. Runtime использует **только три vehicle-топика**, без GNSS и IMU.

**Статус:** baseline реализован, 26 unit-тестов пройдены; сборка и ROS integration smoke прошли в CI; выполнен причинный offline replay восьми реальных прогонов. Это не завершённая сдача: физические параметры ещё не идентифицированы, 3D-контракт требует уточнения, длительные dropout/recovery нуждаются в доработке.

## Сначала прочитать

1. [Аудит данных и три критических расхождения](docs/DATA_AUDIT.md): единицы около x3.6, отсутствующие GNSS-топики, относительное положение vs xyz.
2. [Решение и математическая модель](docs/SOLUTION.md): уравнения, алгоритм, ограничения и следующий этап.
3. [Сборка и запуск](docs/RUNBOOK.md), [результаты и методика](docs/VALIDATION.md), [план команды](docs/TEAM_PLAN.md).

[Готовые вопросы организаторам](docs/ORGANIZER_QUESTIONS.md) нужно отправить до дальнейшего усложнения алгоритма. Отправка вопросов и сдача на платформу пока не выполнялись.

## Быстрый старт

В Ubuntu 22.04 с установленными ROS 2 Humble и colcon:

```bash
git clone git@github.com:jabrailkhalil/hack.git
cd hack
source /opt/ros/humble/setup.bash
colcon build --executor sequential
source install/setup.bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_smoke.py
ros2 launch reserve_odometry odometry.launch.py
```

Во втором терминале также выполнить source обоих setup, затем:

```bash
python3 tools/get_dataset.py
ros2 bag play dataset/data/30618_0652866c --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

## Важные договорённости

Скорость на `/result/velocity` публикуется **tram_vehicle_msgs/msg/VelocitySensor**, не Float64. Положение на `/result/position` - nav_msgs/msg/Odometry. Выход настроен на 20 Гц; stamps относятся ко времени данных, не wall clock. `use_sim_time` и replay с `/clock` описаны отдельно в RUNBOOK.

Default `front_scale=rear_scale=1/3.6` основан на фактическом отношении wheel/GNSS в изученных записях. README организатора при этом пишет м/с. Это зафиксированное расхождение, а не официальное подтверждение единиц; параметры надо сверить с организаторами.

**Без разрешённой карты результат позиции - `(s,0,0)` в `odom_path_1d`, а не реконструированная xyz-траектория.** Для известного маршрута уже есть Route CSV -> интерполяция по s. Нельзя извлечь повороты из разности передней и задней тележек или подставить будущий GNSS проверочного bag.

## Структура

```
src/tram_vehicle_msgs/       сообщения организатора, исправленные build metadata
src/reserve_odometry/        ROS package, core, timeline, route, config, launch
tests/                      unit и ROS integration/serialization checks
tools/                      checksum download, SQLite/CDR export, units audit, replay
docs/                       модель, аудит, runbook, validation, план, вопросы
reports/                    реальные измерения и provenance
.github/workflows/          CI и аудит источника данных
Dockerfile.environment      подготовка offline-среды с ROS Humble
```

## Результат smoke, а не финальная точность

На `30618_0652866c`: RMSE observer 0.04355 м/с против 0.04897 у среднего колёс (после пересчёта масштаба). На других прогонах модель иногда хуже среднего. Все восемь результатов, покрытия, отсутствующие GNSS и причины ограничений опубликованы в [VALIDATION](docs/VALIDATION.md); нельзя обобщать один удачный прогон на весь датасет.

Параметры массы, момента, мощности и торможения в default.yaml иллюстративны. Калибровка на train, независимый test, восстановление после длительных аномалий и подтверждение координат судьи остаются задачами команды. См. [TEAM_PLAN](docs/TEAM_PLAN.md) и Issues.

Датасет и исходный README скачиваются отдельно по checksum; raw bags не добавлены в Git. Репозиторий остаётся приватным. Доступ жюри к материалам нужно организовать отдельно перед сдачей.
