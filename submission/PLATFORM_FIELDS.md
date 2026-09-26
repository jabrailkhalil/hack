# Поля формы для единственного основного решения v8

Эти поля относятся к текущему main и выбранному v8. Исторический ZIP v4 имеет отдельные результаты. Форма не отправлена автоматически.

## 1. ROS 2 пакеты
https://github.com/jabrailkhalil/hack/tree/main/src

Пакеты tram_vehicle_msgs и reserve_odometry. Единственный устанавливаемый оцениватель: guarded_odometry_node, конфигурация champion_v8.yaml. Основная команда: ros2 launch reserve_odometry odometry.launch.py. Это один pipeline, не переключение между исследовательскими моделями.

## 2. Инструкция
https://github.com/jabrailkhalil/hack/blob/main/submission/JUDGE_GUIDE.md

В подготовленной Ubuntu 22.04 / ROS Humble выполнить bash submission/build.sh, затем bash submission/run.sh. Изолированный install_main исключает старые executables. Для полного dropout использовать продолжающийся /clock и run.sh --clock.

## 3. Модель
https://github.com/jabrailkhalil/hack/tree/main/src/reserve_odometry/reserve_odometry
https://github.com/jabrailkhalil/hack/blob/main/reports/adjudication/REPORT.md

Нелинейная тяга/торможение, продольный прогноз, индивидуальные проверки тележек, адаптивное disturbance, bounded reacquisition, guarded output-time correction, zero-lock protection и quarantine после резкого общего скачка. Интеграл скорости даёт относительный s. Исходники/коэффициенты совпадают с pinned v8, изменения касаются упаковки.

## 4. Параметры и ограничения
https://github.com/jabrailkhalil/hack/blob/main/ACTIVE_SOLUTION.json
https://github.com/jabrailkhalil/hack/blob/main/src/reserve_odometry/config/champion_v8.yaml

Физические коэффициенты эффективные, не паспортные. Входной масштаб 1/3.6 эмпирический. Runtime получает controller/front/rear, не GNSS/IMU/LLM. Положение relative_1d, не подтверждённая GNSS/ENU траектория. Требуются согласование карты/origin/геометрического критерия и единиц.

## 5. Точность и быстродействие
https://github.com/jabrailkhalil/hack/blob/main/reports/adjudication/REPORT.md

На 19 одинаковых reused-validation bags: clean group-macro speed RMSE 0.114550 м/с; pooled clean RMSE 0.216407 м/с; original-fault event RMSE 0.538287 м/с; scalar reanchored span-distance RMSE 4.595481 м. 698891 matched points, оба GNSS receivers. При выпадении wheel-данных controller сохранён. Это не independent final test и не официальный score.

Два локальных полных прогона совпали. 161 локальная unit-проверка, 43 research-integrity, clean wheel surface выполнены. Свежая GitHub/ROS-проверка упаковки не завершилась: jobs прекращаются до steps. Старые ROS timestamps/RSS/final-test не выданы за новые замеры. Частота программно настроена 20 Гц, но свежая wall-clock сертификация этой упаковки не заявляется.

## 6. Дальнейшее развитие

Плавный common-mode drift: event RMSE 3.07148 м/с, среднее recovery 4.41 с. Этот сценарий остаётся открытой слабостью; более простые методы иногда быстрее восстанавливаются. Нужны новые независимые записи, подтверждённая геометрия, тесты clock/latency на целевой машине и калибровка uncertainty. Отвергнутые гипотезы не активируются в main автоматически.
