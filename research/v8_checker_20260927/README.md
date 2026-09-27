# Проверка загруженного check-code-with-bag.zip

Кандидат и baseline не меняются. Этот каталог — offline harness, не ROS-нода,
не новый алгоритм и не разрешение на main. Внешний bag `30618_88aea4d9` не входит
ни именем, ни DB SHA256 в исторический split из 122 записей. У него другой временной
диапазон. Исходные 19 validation DB этим файлом не заменены.

## Запуск

Из корня полного checkout PR62 с исследовательским кодом, после распаковки
пользовательского архива в `/absolute/check-code`:

```bash
CHECKER_ROOT=/absolute/check-code PYTHONPATH=src/reserve_odometry \
  python -m unittest discover -s research/v8_checker_20260927 -p 'test_*.py' -v
python research/v8_checker_20260927/runner.py \
  --checker-root /absolute/check-code --output /absolute/NEW-results
```

Python 3.13.5 / NumPy 2.3.5 использованы в проверке. Проверяются SHA256 DB,
приложенного metrics.py, 19 исходных pins и 10 frozen candidate-файлов. Выходной
каталог должен быть новым. ZIP/DB не коммитятся. Нужна именно приложенная версия
checker, не произвольный Python-файл. Из проверенного AST берутся исходные
ErrorAccumulator, position_errors и callbacks; ROS-инициализация не исполняется.

## Методика

Только два профиля: v8 и frozen disturbance_070. На вход модели идут ровно три
vehicle-топика, старые масштабы 1/3.6 и 1/15. Localization и GNSS не входят в модель.
Native replay и четыре fault anchor/crops, low/abrupt/slow генераторы неизменны.
Reference скорости здесь — `/localization/kinematic_state.twist.twist.linear.x`,
а не GNSS hypot. Изменена только подпись distance_surrogate в новом отчёте:
интегрируется matched longitudinal reference speed, не GNSS. Значения неизменны.

Основная таблица: native source-clock, 20 Hz, ближайший reference в пределах
50 ms. Отдельно: receipt-order двухочередная схема, queue_size=100, строго <50 ms,
consume-once по логике двух потоков Humble ApproximateTimeSynchronizer. Она не
моделирует DDS. Также два заранее выбранных timer phase (0 и 5 ms) у идеального
100 Hz callback при clock_mode=input_stamp; ни один из них не выбирается по выигрышу.
Эти прогоны показывают чувствительность к планированию, не измеренную ROS latency.

Положение намеренно сравнивается как оно публикуется без карты: `(s,0,0)` в
`odom_path_1d` против XYZ reference в `map`. Это показывает провал coordinate
contract, а не корректную абсолютную точность. Приложенный checker сам не делает
TF-transform и не проверяет совпадение frame_id. Подгонка translation/yaw/scale
к эталонной траектории, построение карты из всей проверяемой записи и запуск
`relay_result.py` запрещены этим harness. Relay копирует reference и потому не
является моделью — даже если возвращает нулевые ошибки.

29 новых wire/sync/arithmetic/isolation тестов и 27 неизменных candidate-тестов
прошли. Повтор complete runner выполнен без изменения параметров. Протокол не
выдаётся за preregistered holdout: harness завершён после schema inspection и
первого диагностического replay, без подбора моделей. Первая попытка полного
прогона прервана лимитом инструмента 45 s; для отчёта использован завершённый
повтор, а затем ещё один полностью совпавший прогон.

Ограничения: ROS/DDS/Docker не запускались; результат не заменяет 19-bag validation,
не доказывает −24% на новых данных и не даёт допуска к main. Для координат нужны
внешний разрешённый маршрут/pathgraph, его CRS и начальная привязка. Одного
переименования frame_id недостаточно.
