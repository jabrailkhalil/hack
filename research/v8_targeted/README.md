# v8_residual070: кандидат с проверенным development-выигрышем

**DEVELOPMENT_PASS / VALIDATION_PENDING. Не заменяет canonical v8.**
Исходник: `0ac3e7caa0ced4bcafc18cecb5eb226e0f7bb2da`.
[Результаты и все 14 попыток](../../reports/v8_targeted_20260926/REPORT.md).

Изменяется только `disturbance_limit_mps2`: 0.6 -> 0.7 м/с².
Файл хранит точный измеренный float `0.7000000000000001` (результат .6*(.7/.6)),
без округления после измерений. Это предел существующей адаптивной поправки,
не оценка физического уклона. Тяга, мощность, торможение, скорости адаптации,
readout, wheel/innovation gates, zero-lock, common-mode quarantine и Timeline
остаются прежними. Нет новых runtime-входов/состояний или идентификации bag/vehicle.
Обычный checkout/launch остаётся v8; новый профиль включается только явно.

## Локальные тесты

Из полного checkout репозитория с research-зависимостями:

```bash
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s research/v8_targeted -p 'test_*.py' -v
python research/v8_targeted/selected.py
```

27 новых тестов, 156 исторических runtime и 43 integrity пройдены локально.
Это 226 test invocations, не 226 независимых измерений точности.
`selected.make_observer(enabled=False)` воспроизводит исходный v8.

## Воспроизведение без нового подбора

`DATA_ROOT` должен содержать только разрешённые development DB вида
`30618_xxxxxxxx/30618_xxxxxxxx_0.db3`, соответствующие frozen split.
Каждый DB hash проверяется до read-only SQLite. Validation/test отвергаются до IO.
Каждый каталог результата должен быть новым. Не запускайте несколько сравнений
в потоках одного процесса: frozen comparator временно заменяет фабрику модуля.
Изолированные процессы в runner допустимы.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/v8_targeted/evaluate.py --data-root "$DATA_ROOT" \
  --output /tmp/v8-residual-primary-new --names main,disturbance_070 --full --workers 2
python research/v8_targeted/supplemental.py --data-root "$DATA_ROOT" \
  --output /tmp/v8-residual-supp-new --names main,disturbance_070
python research/v8_targeted/audit.py --primary /tmp/v8-residual-primary-new \
  --supplemental /tmp/v8-residual-supp-new --candidate disturbance_070 \
  --output /tmp/v8-residual-audit-new
```

Все 14 исследованных вариантов сохранены в `candidates.py`; исходные бюджеты и
порядок адаптивных раундов в PLAN/ROUND2_PLAN/ROUND3_PLAN/ROUND4_PLAN.
`evaluate.py --names` позволяет повторять заданный набор, не выполняет fitting.
Полный перебор по умолчанию не является новым независимым экспериментом.

## Явный ROS-запуск кандидата

```bash
bash submission/build.sh
source /opt/ros/humble/setup.bash
source install_main/setup.bash
ros2 launch reserve_odometry odometry.launch.py \
  params_file:="$PWD/research/v8_targeted/v8_residual070.yaml"
```

Рецепт использует существующий launch, но **enabled ROS здесь не запускался**.
`bash submission/run.sh` остаётся прежним v8. Не переносите коэффициент в main
до отдельного validation и проверки установленной ROS-ноды/ограничений ресурсов.
Новый final test не выполнялся и этим runner не поддерживается.
