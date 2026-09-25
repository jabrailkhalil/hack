# Поля формы: active champion v8

Эта версия полей относится к **текущему checkout main с champion v8**.
Исторический `reserve-odometry-v4.zip` остаётся отдельной frozen-версией;
его final-test нельзя выдавать за test v8. Репозиторий приватный: доступ жюри
или разрешённый способ передачи нужно обеспечить отдельно. Форма автоматически
не отправлялась.

## 1. Ссылка на пакет(ы) ROS 2 Humble

https://github.com/jabrailkhalil/hack/tree/main/src

Пакеты tram_vehicle_msgs и reserve_odometry. Активный runtime: champion v8 readout поверх v5 inner observer плюс low-speed
zero-lock protection. Стандартный `odometry.launch.py` запускает именно этот
профиль. Входы controller/front/rear; выходы скорости, относительного положения
и диагностики. Runtime без GNSS/IMU/LLM.

## 2. Инструкция для жюри

https://github.com/jabrailkhalil/hack/blob/main/submission/JUDGE_GUIDE.md

В подготовленной Ubuntu 22.04 / ROS 2 Humble: bash submission/build.sh, затем bash submission/run.sh. Во втором терминале ros2 bag play с тремя vehicle-топиками. Указаны единицы, stamps, frames, режим /clock, ограничения, воспроизведение прежнего v4 и различие между активным профилем и архивом.

## 3. Математическая модель

https://github.com/jabrailkhalil/hack/blob/main/submission/MODEL.md
https://github.com/jabrailkhalil/hack/blob/main/reports/research_v6/REPORT.md

Базовые уравнения и runtime из v4 сохранены. Внутренний v5 использует adaptation_tau_s=0.5. Champion v8 не меняет внутреннее
состояние фильтра: рекурсивная поправка применяется только к публикуемым v/s и
сбрасывается/блокируется при недостоверных wheel evidence. Общая нулевая пара не ассимилируется как остановка, пока модельная скорость
выше порога. После почти одновременного RATE_ANOMALY на обеих тележках
common-mode reacquisition блокируется на 1.5 с; ordinary fusion не меняется.

## 4. Допущения, ограничения и параметры

https://github.com/jabrailkhalil/hack/blob/main/src/reserve_odometry/config/default.yaml
https://github.com/jabrailkhalil/hack/blob/main/reports/research_v6/PROMOTION.json
https://github.com/jabrailkhalil/hack/blob/main/submission/LIMITATIONS.md

Коэффициенты эффективные, не паспортные. scale=1/3.6 — эмпирическое допущение до ответа организатора. Положение (s,0,0) — относительная дистанция, не согласованная с GNSS xyz-траектория. Необходимые карта/origin/маршрут не подтверждены; общая правдоподобная ошибка обеих тележек может оставаться неразличимой. Система не сертифицирована для безопасности движения.

## 5. Точность и быстродействие

https://github.com/jabrailkhalil/hack/blob/main/reports/research_v6/REPORT.md
https://github.com/jabrailkhalil/hack/tree/main/reports/research_v6

На одинаковом повторно используемом validation: group-macro RMSE скорости
**0.117138→0.114550 м/с**, исходный fault-event RMSE
**0.538434→0.538287 м/с**, scalar span distance **4.630978→4.595481 м**.
698891 matched samples. На отдельной low-speed lock suite event RMSE
2.68877→0.316586 м/с; это специальный fault scenario, не full-dataset gain.
Нового независимого final test для v8 нет; исторический v4 final test к нему
не относится. На отдельной common-mode +5 м/с suite event RMSE
0.092438→0.063562 м/с (-31.24%), REACQUIRING ticks 47→0; это специальная
инъекция, не full-dataset metric.

## 6. Ограничения и дальнейшее развитие

Согласовать единицы и координаты, подключить разрешённую карту/инициализацию, получить новые независимые проверочные записи, расширить подтверждённые сценарии общей пробуксовки, оценить uncertainty и перенос между трамваями. Весь поиск использовал уже существующий validation, а не новый независимый test; результаты не являются официальным баллом жюри.
