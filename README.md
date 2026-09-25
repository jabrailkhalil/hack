# Резервная одометрия трамвая — активный champion v7

**Стандартный запуск теперь использует guarded v7**: внутренний observer остаётся
проверенным v5, а опубликованная скорость получает причинную output-only
компенсацию возраста свежих колёсных измерений. Дополнительно в общем ядре
включена защита от ложной остановки при общей блокировке колёс на малой скорости.

| Одинаковый validation-набор | Inner v5 | Champion v7 | Изменение |
|---|---:|---:|---:|
| Group-macro RMSE скорости, м/с | 0.117138 | **0.114550** | **−2.21%** |
| Group-macro RMSE в исходных fault-окнах, м/с | 0.538434 | **0.538287** | −0.03% |
| Скалярная RMSE дистанции по непрерывным отрезкам, м | 4.630978 | **4.595481** | −0.77% |

698891 сопоставленная точка; clean улучшился в 25 из 30 bag/receiver-пар.
Это повторно используемый validation, **не новый независимый final test** и не
официальный балл.

Отдельная low-speed wheel-lock suite проверяет другой отказ: при блокировке обеих
тележек на скорости 1–2 м/с event RMSE v5 снижен с 2.68877 до **0.316586 м/с**,
false-stop samples 200→0 и unrecovered 1→0. Число 88.23% относится только к этой
инъекции, не ко всему датасету.

**[Champion evidence](reports/champion_v7/README.md)** ·
**[Promotion record](reports/champion_v7/PROMOTION.json)** ·
**[Инструкция запуска](submission/JUDGE_GUIDE.md)**.

## Запуск текущего champion

В подготовленной Ubuntu 22.04 / ROS 2 Humble:

```bash
bash submission/build.sh
bash submission/run.sh
```

или:

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch reserve_odometry odometry.launch.py
```

Канонический `odometry.launch.py` запускает `guarded_odometry_node` с
`guarded_readout_v7.yaml`. Для A/B-воспроизведения внутреннего v5:

```bash
ros2 launch reserve_odometry v5_odometry.launch.py
```

Исторический v4 остаётся в `frozen_v4.yaml` и в неизменном standalone ZIP.
Основной runtime использует только controller/front/rear vehicle-топики, без
GNSS, IMU, LLM, numpy или SciPy. Выходы: VelocitySensor, Odometry и diagnostics,
20 Гц, deliberate alignment delay = 0.

## Две разные версии доказательств

Текущая конфигурация и её проверки: `reports/research_v6/`, история v5: `reports/research_v5/`. Исторический standalone **`submission/dist/reserve-odometry-v4.zip` оставлен неизменным**. Его 22-bag final test, 24-минутный runtime-прогон, `submission/FREEZE.json` и `submission/RESULTS.md` относятся **только к v4**, не к активному v5.

Проверки исходников теперь разделены: старые хеши проверяются по точному опубликованному архиву, активные — по отдельному `PROMOTION.json`. Старый evaluator намеренно не принимает новую конфигурацию за прежнюю замороженную v4. Для воспроизведения старой процедуры использовать архив или её закреплённый commit; не редактировать FREEZE ради прохождения проверки.

Новые проверки текущего default включают unit/integrity тесты, реальный установленный ROS launch и отдельное измерение задержки в двух clock-режимах под 2 CPU / 500 MB без сети. Точный объём выполненных проверок, номера запусков и измерения находятся в текущем отчёте; короткие проверки не приравниваются к старому 24-минутному прогону.

## Ограничения

`(s,0,0)` в `odom_path_1d` — **относительная дистанция вдоль пути, не восстановленная GNSS/ENU xyz-траектория**. Требования PDF и README к положению расходятся; разрешённая карта, origin и маршрут не подтверждены. Входной `scale=1/3.6` остаётся явным эмпирическим допущением до ответа организаторов. Правдоподобная общая ошибка обеих тележек не всегда распознаётся без независимого источника.

В `input_stamp` полное отсутствие всех входов останавливает источник времени. Для такого dropout нужен продолжающийся `/clock`: `bash submission/run.sh --clock`. Независимые bags требуют перезапуска; backward `/clock` seek начинает новый относительный сегмент.

[Вопросы организаторам](docs/ORGANIZER_QUESTIONS.md) · [Математическая модель v4](submission/MODEL.md) · [Текущие поля формы с разграничением версий](submission/PLATFORM_FIELDS.md). Репозиторий остаётся приватным; права доступа и отправка на платформу не менялись.
