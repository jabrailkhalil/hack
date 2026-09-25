# Резервная одометрия трамвая

ROS 2 Humble: нелинейная продольная модель, раздельная проверка тележек, адаптивная поправка, скорость и дистанция. Runtime получает **только три vehicle-топика**, без GNSS, IMU, LLM или научных Python-зависимостей.

## Текущий результат: калибровка v3

Выполнен воспроизводимый цикл обучения и проверки четырёх вариантов, включая прежний baseline. Выбрана `balanced_physics`: подобраны эффективные коэффициенты тяги, мощности, торможения, сопротивления, нелинейность контроллера и постоянная времени привода. Код фильтра, пороги, масштаб колёс и временная логика не подбирались.

| Метрика на grouped validation | Baseline v2 | Выбранная v3 | Изменение |
|---|---:|---:|---:|
| Group-macro RMSE скорости, м/с | 0.117973 | 0.115339 | -2.23% |
| Macro RMSE внутри введённых fault-окон, м/с | 0.743942 | 0.573744 | -22.88% |

Это результаты **validation**, не финального test и не официальный балл жюри. 64 train-bag / 27 групп; 19 validation-bag / 10 групп; 22 test-bag / 10 групп не использованы в fitting/evaluation; 17 ранее просмотренных или связанных bag оставлены development. Обучение использовало 87453 точки из 60 train-bag и только wheel/controller псевдоразметку. Четыре validation-bag без GNSS-метрики не считаются нулевой ошибкой.

**Полный результат:** [REPORT.md](reports/research_v3/REPORT.md), [таблица CSV](reports/research_v3/leaderboard.csv), [решение по кандидатам](reports/research_v3/decision.json), [все validation/fault-метрики](reports/research_v3/validation.json), [закреплённое разделение](research/split_v3.json).

Проверка новой конфигурации: 35 dependency-free unit tests, исследовательские тесты изоляции/причинности, сборка Humble, отдельный реальный запуск установленного launch-default, offline-проверка в контейнере 2 CPU / 512 MiB. [Подтверждение CI](https://github.com/jabrailkhalil/hack/actions/runs/36154901770). Короткий integration smoke не заменяет длительный ресурсный и end-to-end latency benchmark.

## Быстрый запуск

В подготовленной Ubuntu 22.04 / ROS 2 Humble:

```bash
git clone git@github.com:jabrailkhalil/hack.git
cd hack
source /opt/ros/humble/setup.bash
colcon build --executor sequential
source install/setup.bash
PYTHONPATH=src/reserve_odometry python3 -m unittest discover -s tests -v
python3 tests/ros_calibrated_smoke.py
ros2 launch reserve_odometry odometry.launch.py
```

`ros2 launch` загружает выбранную v3 из `config/default.yaml`. **Голый `ros2 run` без params-file использует прежние Config defaults**, которые намеренно сохранены для воспроизводимого baseline. Прямой запуск с v3:

```bash
ros2 run reserve_odometry odometry_node --ros-args \
  --params-file src/reserve_odometry/config/calibrated_v3.yaml
```

Для сравнения с прежней конфигурацией:

```bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/src/reserve_odometry/config/candidates_v3/baseline_v2.yaml"
```

Во втором терминале выполнить source обоих setup, затем:

```bash
python3 tools/get_dataset.py
ros2 bag play dataset/data/30618_0652866c --topics \
  /vehicle/driver_position_cmd \
  /vehicle/front_bogie_velocity \
  /vehicle/rear_bogie_velocity
```

## Контракт и ограничения

`/result/velocity`: `tram_vehicle_msgs/msg/VelocitySensor`, м/с. `/result/position`: `nav_msgs/msg/Odometry`. Частота настроена на 20 Гц; timestamps относятся ко времени входных данных. `input_stamp` не продвигает время при исчезновении всех входов; для полного dropout нужен `ros_clock` и `/clock`.

Масштаб `front_scale=rear_scale=1/3.6` остаётся явным эмпирическим допущением: README организатора пишет м/с, но исследованные данные показывают коэффициент около 3.6 относительно GNSS. Не менять скрыто и не утверждать, что организатор уже подтвердил единицы.

Без разрешённой карты позиция `(s,0,0)` в `odom_path_1d` - относительная дистанция, **не восстановленная xyz-траектория**. Загрузчик известного ordered route реализован, но карта, origin, начальная привязка и правила GNSS требуют уточнения. Правдоподобная общая ошибка обеих тележек остаётся неоднозначной.

Обучены эффективные отношения сил/мощности к массе. Фиксированные масса, радиус и передача не стали измеренными паспортными параметрами. Не выполнены финальный test, проверка 3D и длительное измерение полной задержки. Решение не является сертифицированным навигационным компонентом.

## Документация и дальнейшая работа

Начать с [руководства v3](docs/CALIBRATION_V3.md) и [полного отчёта](reports/research_v3/REPORT.md). Исходные уравнения: [SOLUTION](docs/SOLUTION.md); подробная ROS-инструкция: [RUNBOOK](docs/RUNBOOK.md); расхождения контракта: [DATA_AUDIT](docs/DATA_AUDIT.md); [вопросы организаторам](docs/ORGANIZER_QUESTIONS.md). Разделы прежних документов о ещё не выполненной калибровке относятся к v1/v2; текущие параметры и результаты приведены здесь и в отчёте v3.

`tools/research_v3/` - конечный runner заранее заданных гипотез. Workflow повторяет fitting/validation и публикует доказательства в feature-ветку с защитой от устаревшего SHA; это ещё не автономный LLM-консилиум. RunPod, платные GPU и внешние агенты не запускались. Научные зависимости устанавливать в отдельное Python 3.13 окружение, не в Python 3.10 ROS.

Промежуточные этапы также сохранены: [CHECKPOINTS](reports/research_v3/CHECKPOINTS.md). Raw bags не добавлены в Git. Репозиторий остаётся приватным; доступ жюри и отправка на платформу не выполнялись. Финальный test запускать отдельно после заморозки решения и согласования контракта.
