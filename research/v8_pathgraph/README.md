# v8 + внешний Pathgraph + редкий GNSS

**EXPERIMENTAL_PARTIAL_COVERAGE — не замена main.** Скорость и исходный интеграл
пути остаются от прежнего v8 / frozen residual070. Новый модуль независимо
вычисляет положение на разрешённой внешней карте. Эталон не входит в runtime.

## Состав

- `pathgraph.py`: загрузка исходного points/paths JSON по point_indices,
  строгая проверка данных, арк-длина 3D, поворот плеча антенны, причинная
  GNSS-привязка и ограниченная коррекция отдельного route offset.
- `import_maps.py`: lossless XYZ CSV для существующего route_csv, без догадок
  о стартовом s и системе координат. Ничего не замыкает и не дорисовывает.
- `evaluate.py`: сравнение двух frozen профилей и трёх режимов на bag/checker,
  отдельный учёт coverage/missing и один общий intersection для метрик.
- `ros_node.py`: подготовленный opt-in наследник установленной GuardedOdometryNode.
  Численное ядро и родительский publish скорости не переписаны. Пока позиции нет,
  родительский veto не публикует фиктивные координаты. Дополнительный топик
  `/result/map_diagnostics` содержит статус, counters и признак подтверждения CRS.

Runtime использует только свой исходный s, доступные rover NavSatFix и внешние
карты. Курс получается из прошлых rover fixes, GNSS velocity не используется.
Исходные velocity/raw s не заменяются координатными поправками. Антенный рычаг
rover=(2.563,0,3) взят из переданного пользователем уточнения. На кривой yaw/grade
приближены касательной участка; отдельная модель хорды кузова по базе7.55м пока
не применяется. Высота GNSS не подгоняет Z карты.

## Входные файлы

Оригиналы и точные CSV выданы в архиве этой беседы. Исходные карты и raw DB не
копируются в Git; помещаются пользователем в каталог input. Хеши исходных карт
зафиксированы в `MAPS.json`. Карты содержат 4710 и4709 точек, только points/paths;
в них НЕТ CRS/origin metadata. Без правильного point_indices порядок не менять.

Численно совместимая, но НЕ подтверждённая гипотеза преобразования:
WGS84 UTM37N, X=E-300000, Y=N-6100000. Это результат исследования координат,
не информация из JSON и не least-squares подгонка к эталону. В рабочем Grid
нет таких defaults: нужен явный контракт. Для эксперимента пример ниже включает
allow_hypothesis=true; такой режим предупреждает и не даёт права на выпуск.

```json
{
  "zone": 37,
  "easting_origin_m": 300000.0,
  "northing_origin_m": 6100000.0,
  "frame": "map",
  "provenance": "UNCONFIRMED experiment; verify with map provider",
  "confirmed": false,
  "allow_hypothesis": true
}
```

Горизонтальный UTM-код сверён с PROJ на16 точках региона (разность <2мм).
Это не доказывает соответствие данного CRS карте. PROJ описание UTM:
https://proj.org/en/stable/operations/projections/utm.html

## Повтор offline-проверки

Из полного checkout этой ветки, с research-зависимостями и pyproj для одного
unit-test проверки проекции. Фактическое окружение: Python3.13.5, NumPy2.3.5,
pyproj3.7.2/PROJ9.5.1. Сам runtime pathgraph не зависит от NumPy/pyproj.

```bash
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/v8_pathgraph -v
python research/v8_pathgraph/import_maps.py \
  '/absolute/щукинская - таллинская (1).json' '/absolute/таллинская - щукинская.json' \
  --output /absolute/NEW-normalized
python research/v8_pathgraph/evaluate.py --checker-root /absolute/check-code \
  --maps '/absolute/щукинская - таллинская (1).json' '/absolute/таллинская - щукинская.json' \
  --output /absolute/NEW-result
```

## Подготовленный ROS-запуск (НЕ выполнен здесь)

После обычной сборки исходного v8 и подготовки явного grid.json из примера:

```bash
source /opt/ros/humble/setup.bash
source install_main/setup.bash
python3 research/v8_pathgraph/ros_node.py --ros-args \
  --params-file src/reserve_odometry/config/champion_v8.yaml \
  -p 'map.paths:=["/absolute/shchukinskaya-tallinskaya.json", "/absolute/tallinskaya-shchukinskaya.json"]' \
  -p map.grid_config:=/absolute/grid.json -p map.mode:=sparse
```

Для residual070 явно заменить params-file на research/v8_targeted/v8_residual070.yaml.
Не задавать одновременно route_csv/route_s0. Обычно submission/run.sh остаётся
прежним, новый adapter не установлен и не включён по умолчанию.

## Результат и ограничения

На общем наборе18333 выходов: v8 initial-on-map XYZ RMSE2.024668м, sparse1.458760м;
residual070 initial-on-map1.798405м, sparse1.343460м. Шесть редких корректировок.
**Это70.008% всех выходов, НЕ full-bag RMSE.** Первый подходящий on-map fix даёт
привязку около315s source-clock, конец карты около1232s. Режим GNSS только в первых
5s не локализуется вообще: старт вне карты. Оставшиеся участки не заполнены
нулями/переименованными relative координатами, пропуски входят в coverage.

34 новых +27 candidate +29 checker +156 historical runtime =246 тестов выполнено.
Два завершённых offline-прогона: RESULT и7 NPZ/39 массивов совпали точно.
CSV сохраняет все исходные XYZ; legacy Route даёт те же точки с погрешностью
интерполяции <1.5e-11м. Runtime receipt clock отделён от source clock; исправление
проверено тестом и не изменило результаты этого bag.

**Не проверено:** ROS/DDS, установленный adapter, latency/RSS полного ROS процесса,
замороженный19-bag validation, скрытый тест. Нужны полные недостающие участки у
конечных и подтверждение CRS. Пропуски и гипотеза координат блокируют main.
