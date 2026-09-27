# Новый bag и реальный контракт checker: 27.09.2026

**Решение: main не менять.** Протестированы прежний v8 и frozen residual070.
Изменения модели, fitting и подстройка по новому bag: 0. Это один дополнительный
проверочный пример, не весь замороженный validation. Проверяемый head PR62:
`123d351aae6794cf2cb1795a2afdcf5fd472dcc0`.

## Что действительно предоставлено

Пользователь загрузил `check-code-with-bag.zip`: checker ROS2, демонстрационный
relay и один `30618_88aea4d9_0.db3`. DB SHA256:
`48f846d134d0584b38f9ca06b7ba812a16aeeecc896594313e3fa9acd27e10c3`.
В SQLite 117976 сообщений; 65579 — `/localization/kinematic_state`. Длительность
по receipt time около 1309.59 s (21 min 50 s). Имя и hash не встречаются в старом
split; диапазон времени позже всех старых записей. Отсюда не следует независимость
маршрута/условий. Исходных 19 validation DB в архиве нет.

Приложенный `metrics.py` сравнивает скорость именно с
`kinematic_state.twist.twist.linear.x`, положение — отдельные XYZ и 3D norm.
Default sync_tolerance_sec=0.05, queue_size=100. Reference в bag имеет header.frame_id
`map` и child_frame_id `base_link`. Первое XYZ:
(103634.10014667963, 86057.89949207648, 165.16277041075705).
Источник этих фактов — проверенные байты пользовательского архива, а не прежняя
неподтверждённая суммаризация. Происхождение архива от организаторов независимо
не удостоверялось.

## Скорость: новый существенный выигрыш не подтверждён

20 Hz native replay, исходный evaluator/Timeline и зафиксированные параметры.
Ближайшие timestamps <=50 ms; 26187 matched выходов, coverage=100% для обоих.
Epoch nanoseconds хранятся целыми. Arithmetic считается неизменными callbacks
загруженного checker и независимо сверяется с frozen NumPy scorer.

| Сценарий | v8 RMSE, m/s | residual070 RMSE, m/s | Изменение ошибки |
|---|---:|---:|---:|
| Native source-clock | 0.051538351 | 0.051353959 | -0.357776% |
| Имитация 100 Hz timer, phase 0 ms | 0.051118979 | 0.051112133 | -0.013393% |
| Имитация 100 Hz timer, phase 5 ms | 0.050733917 | 0.050749835 | +0.031376% |

Native MAE: 0.035286199 -> 0.035202011 m/s. Maximum error одинаковая:
0.390544155 m/s. Receipt-order consume-once synchronizer на native выходах дал
то же число пар и итоговую арифметику; это не утверждение об идентичности
индексов пар. Timer sensitivity тоже сохранила 26187 matched сообщений.
ROS/DDS в этой среде отсутствуют: это НЕ фактический live checker, не measurement
latency и не доказательство поведения всех executor schedules. Timer phase не
оптимизировалась; оба знака результата опубликованы.

Вывод: по новой записи оценки скорости практически равноценны. Старые -23.98%
на development не переносятся на неё. Утверждение «новый v8 лучше на 24% везде»
было бы неверным.

## Исходные и дополнительные отказы

Четыре неизменных fault types, первый прежний admissible anchor t=131.4 s. При
wheel dropout команда контроллера доступна. Event RMSE (оба профиля совпали):

| Отказ | Event RMSE, m/s |
|---|---:|
| Front bias +5 m/s, 5 s | 0.026482028 |
| Оба wheel inputs пропали, 5 s | 0.061210091 |
| Оба wheel inputs пропали, 10 s | 0.066528045 |
| Оба wheel inputs равны 0, 3 s | 0.029488483 |

Это один anchor, не распределение из десятков независимых отказов. Все четыре
полные faulted trajectories также просчитаны, без сброса накопленной s при
восстановлении. Prefault совпадает точно, max integral identity error
2.8760882564426993e-12 m. Новых false stops/nonrecoveries в этих сценариях нет.

2 low-speed cases одинаковы (mean event RMSE 0.207242210). 2 abrupt common-mode
cases одинаковы (0.040794494). 2 slow-common cases ухудшились:
3.100386322 -> 3.110017299 m/s, +0.310638%. Медленный совместный drift остаётся
слабым местом обоих профилей. Все per-case результаты и runtime counters сохранены.

## Интеграл пути не равен XYZ

На общей временной сетке интеграл эталонной продольной скорости: 5483.657384 m.
RMSE накопленного scalar-path discrepancy: 3.997748289 -> 3.805481568 m (-4.81%).
Однако ошибка интеграла в конце: +3.751733099 -> +3.865729457 m — кандидат хуже
примерно на 0.114 m. Terminal relative error: 0.068417% -> 0.070495%.
Ни одна из этих величин не является map position accuracy или pathgraph score.

## Главный блокер — координаты положения

Без route_csv основной node.py публикует `(s,0,0)`, frame `odom_path_1d`. Reference
checker в `map`. Приложенные position_errors непосредственно вычитают координаты:
не проверяют frame_id и не выполняют преобразование через TF.

При таком же сыром вычитании native output даёт 3D RMSE около **130335 m** у обоих
профилей. Это НЕ физический дрейф в 130 km. Это несопоставимые системы координат;
именно такую большую численную ошибку проверяющая формула получит от default
выхода без карты. Нулевая/маленькая скорость RMSE проблему положения не решает.

Нельзя исправить это переименованием frame_id или подгонкой по всей эталонной
траектории. Нужны разрешённый внешний pathgraph/маршрут в согласованной `map`,
описание CRS и начальная привязка; дальше продвижение по нему по wheel/model
интегралу и, если допустимо, редкая GNSS-коррекция. Положение reference помечено
base_link; антенную точку без lever-arm correction подставлять нельзя. Полный
официальный transform/CRS из этого checker-кода не следует.

Отдельное предупреждение: реальное тело `scripts/relay_result.py` отправляет
kinematic_state в /result/position и его linear.x в /result/velocity. Front-wheel
callback пустой. Его комментарий про relay wheel velocity устарел. Поэтому его
нулевые ошибки были бы копированием эталона, НЕ качеством решения. В тесте relay
не запускался; reference/GNSS ни разу не передавались модели.

## Воспроизводимость и публикация

29 новых tests PASS: CDR little/big endian/padding/truncation, strict sync bounds,
consume-once/queue eviction, integer timestamp precision, исходные checker
callbacks, source/config pins, запрет reference inputs, causal prefix и integral.
27 прежних candidate tests PASS. Всего 56 фактически выполненных тестов; это не
повторное заявление о 255 предыдущих тестах или ROS smoke.

Полный runner повторён без изменений: RESULT.json и все 10 NPZ / 28 массивов
совпали точно. Число строк здесь включает отдельно prediction, publish timestamps
и pairing indices; не следует складывать их как независимые samples. Первый
запуск оборван лимитом инструмента 45 s и сохранён как INCOMPLETE, не PASS.
Код/описание harness завершены после первоначального schema inspection/replay;
это не выдаётся за preregistration до первого доступа к новому bag.

Исторические исходники взяты из предоставленного adjudication source snapshot
и exact PR62 overlays; numerical/evaluator bytes совпадают с 19 pins и 10 frozen
candidate files. Это не новая полная ROS installation. Код кандидата, default,
main и старые freezes не менялись. Полные результаты/NPZ/logs сохраняются архивом
беседы; raw DB в Git не публикуется.

**Допуск к main не получен:** одна дополнительная запись не заменяет 19-bag
validation; существенного устойчивого выигрыша скорости здесь нет; установленные
ROS/DDS/ресурсные проверки и корректная map position остаются отдельными задачами.
