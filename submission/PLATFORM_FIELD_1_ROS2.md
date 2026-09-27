# 1. Пакеты ROS 2 Humble

https://github.com/jabrailkhalil/hack/tree/main/src

Два пакета ROS 2 Humble: reserve_odometry и tram_vehicle_msgs, собираются colcon build. Нода guarded_odometry_node с профилем champion_v8.yaml получает /vehicle/driver_position_cmd, /vehicle/front_bogie_velocity и /vehicle/rear_bogie_velocity. Публикует /result/velocity (tram_vehicle_msgs/msg/VelocitySensor, м/с), /result/position (nav_msgs/msg/Odometry, м) и диагностику. Расчётная частота — 20 Гц. Сборка: bash submission/build.sh. Воспроизведение rosbag: bash submission/run.sh --clock.
