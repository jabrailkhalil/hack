# Поля формы «Загрузка решения»

Ниже шесть обязательных полей из PDF (страница 8). Перед отправкой убедиться, что жюри имеет доступ: репозиторий приватный. В противном случае передать standalone ZIP по разрешённой организаторами ссылке. Этот документ не означает, что форма уже отправлена.

## 1. Ссылка на пакет(ы) ROS 2 Humble

https://github.com/jabrailkhalil/hack/tree/main/src

Два пакета: tram_vehicle_msgs и reserve_odometry. Нелинейная резервная продольная одометрия по контроллеру и двум тележкам. Входы: /vehicle/driver_position_cmd, /vehicle/front_bogie_velocity, /vehicle/rear_bogie_velocity. Выходы: /result/velocity (VelocitySensor), /result/position (Odometry), /result/diagnostics. Базовый режим позиции — относительная дистанция (s,0,0), не восстановленная GNSS/ENU-траектория. Standalone пакет: submission/dist/reserve-odometry-v4.zip, SHA256 рядом.

## 2. Инструкция для жюри

https://github.com/jabrailkhalil/hack/blob/main/submission/JUDGE_GUIDE.md

Ubuntu 22.04, ROS 2 Humble. В подготовленной среде: bash submission/build.sh, затем bash submission/run.sh. Во втором терминале ros2 bag play с тремя входными vehicle-топиками. В инструкции указаны типы, единицы, frames, диагностика, режим /clock, offline-проверка и воспроизведение измерений. Runtime не требует интернета, GNSS/IMU, LLM или научных Python-зависимостей.

## 3. Математическая модель

https://github.com/jabrailkhalil/hack/blob/main/submission/MODEL.md

Нелинейная характеристика controller→тяговый/тормозной момент с ограничением мощности, первый порядок динамики привода, сопротивление и ограниченная адаптивная поправка. Предсказание скорости сочетается с раздельной проверкой тележек и робастной скалярной коррекцией; расстояние интегрируется причинно. Описаны единицы, состояния, формулы и стратегия ограниченного повторного захвата датчиков.

## 4. Допущения, ограничения и параметры

https://github.com/jabrailkhalil/hack/blob/main/submission/LIMITATIONS.md
https://github.com/jabrailkhalil/hack/blob/main/src/reserve_odometry/config/default.yaml

Коэффициенты эффективные, не паспортные. Входные scale=1/3.6 — явное эмпирическое допущение, требующее подтверждения организатора. Без разрешённой карты публикуется относительная одометрия, допускаемая PDF; соответствие противоречащему ей xyz-контракту README не подтверждено. Runtime использует только три vehicle-топика. Научные зависимости применяются лишь offline.

## 5. Точность и быстродействие

https://github.com/jabrailkhalil/hack/blob/main/submission/RESULTS.md
https://github.com/jabrailkhalil/hack/tree/main/reports/final

Отдельно сохранены validation и отложенный final test после source/config/evaluator freeze, все bag/receiver метрики, coverage и отсутствующий reference. GNSS — только эталон, не вход ноды. Производительность измеряется настоящими ROS-процессами при 1x replay, включая публикацию и независимые подписчики обоих результатов; ресурсный лимит 2 CPU / 500000000 байт, сеть отключена. Скалярные дистанционные метрики не объявляются 3D-ошибкой. Точные числа и границы выводов приведены в отчёте, а не пересчитываются из старых smoke-результатов.

## 6. Ограничения и развитие после хакатона

https://github.com/jabrailkhalil/hack/blob/main/submission/LIMITATIONS.md

Приоритеты: согласовать единицы и систему координат; подключить разрешённую карту и начальную привязку; проверить xyz и перенос между трамваями; расширить независимо размеченные случаи общей пробуксовки; калибровать uncertainty и проводить длительные аппаратные испытания. Система не заявляется сертифицированным компонентом безопасности.
