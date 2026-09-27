# Пакеты ROS 2 Humble

https://github.com/jabrailkhalil/hack/tree/main/src

В составе два ROS 2 Humble пакета: `reserve_odometry` и `tram_vehicle_msgs`.

Основной executable: `guarded_odometry_node`.  
Основная конфигурация: `champion_v8.yaml`.  
Штатный запуск:

```bash
ros2 launch reserve_odometry odometry.launch.py
```

Нода подписывается на входные топики:

- `/vehicle/driver_position_cmd` — положение контроллера;
- `/vehicle/front_bogie_velocity` — скорость передней тележки;
- `/vehicle/rear_bogie_velocity` — скорость задней тележки.

Публикуемые выходы:

- `/result/velocity` — оценка продольной скорости, м/с;
- `/result/position` — относительная одометрия;
- `/result/diagnostics` — диагностическая информация.

Сборка выполняется через `colcon`; штатные скрипты сборки и запуска находятся в каталоге `submission/`.
