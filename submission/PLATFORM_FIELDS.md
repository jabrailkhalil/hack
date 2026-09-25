# Поля формы: активный профиль time_aligned_v6

Эта версия полей относится к **текущему checkout main с time_aligned_v6**, а не к оставленному неизменным архиву `reserve-odometry-v4.zip`. При отправке исторического архива использовать его собственные поля и результаты внутри ZIP. Не смешивать v6-код с final-test числами v4. Репозиторий приватный: доступ жюри или разрешённый способ передачи нужно обеспечить отдельно. Форма не отправлялась автоматически.

## 1. Ссылка на пакет(ы) ROS 2 Humble

https://github.com/jabrailkhalil/hack/tree/main/src

Пакеты tram_vehicle_msgs и reserve_odometry. Активная конфигурация time_aligned_v6: нелинейная модель продольной динамики, независимые проверки двух тележек, ограниченная адаптивная поправка. Стандартный default.yaml совпадает с выбранным профилем. Входы controller/front/rear; выходы скорости, относительного положения и диагностики. Runtime без GNSS/IMU/LLM.

## 2. Инструкция для жюри

https://github.com/jabrailkhalil/hack/blob/main/submission/JUDGE_GUIDE.md

В подготовленной Ubuntu 22.04 / ROS 2 Humble: bash submission/build.sh, затем bash submission/run.sh. Во втором терминале ros2 bag play с тремя vehicle-топиками. Указаны единицы, stamps, frames, режим /clock, ограничения, воспроизведение прежнего v4 и различие между активным профилем и архивом.

## 3. Математическая модель

https://github.com/jabrailkhalil/hack/blob/main/submission/MODEL.md
https://github.com/jabrailkhalil/hack/blob/main/reports/time_alignment_v6/REPORT.md

Базовая модель и адаптация v5 (0.5 с) дополнены компенсацией возраста принятых колесных измерений ограниченным модельным ускорением и неопределённостью переноса. Raw samples не меняются для gates, адаптации и остановки. Физические коэффициенты не переобучались; отклонённые исследовательские патчи не включены.

## 4. Допущения, ограничения и параметры

https://github.com/jabrailkhalil/hack/blob/main/src/reserve_odometry/config/default.yaml
https://github.com/jabrailkhalil/hack/blob/main/submission/ACTIVE_PROFILE.json
https://github.com/jabrailkhalil/hack/blob/main/submission/LIMITATIONS.md

Коэффициенты эффективные, не паспортные. scale=1/3.6 — эмпирическое допущение до ответа организатора. Положение (s,0,0) — относительная дистанция, не согласованная с GNSS xyz-траектория. Необходимые карта/origin/маршрут не подтверждены; общая правдоподобная ошибка обеих тележек может оставаться неразличимой. Система не сертифицирована для безопасности движения.

## 5. Точность и быстродействие

https://github.com/jabrailkhalil/hack/blob/main/reports/time_alignment_v6/REPORT.md
https://github.com/jabrailkhalil/hack/tree/main/reports/research_v6

На повторно используемом validation: group-macro RMSE скорости 0.114476684 м/с (v5: 0.117138274); pooled RMSE 0.216396651 м/с; scalar-span distance RMSE 4.577133777 м (v5: 4.630977808). Fault-event RMSE 0.548979449 м/с, хуже v5 на 1.9585%. 698891 сопоставленная точка, покрытие и число ложных остановок не ухудшились. Активация v6 — выбор владельца в пользу clean/distance, не pass прежнего 0.5% gate. Нового независимого final test нет. Новые runtime-измерения указываются отдельно по выполненным runs; старые числа v4/v5 не приписываются v6.

## 6. Ограничения и дальнейшее развитие

Согласовать единицы и координаты, подключить разрешённую карту/инициализацию, получить новые независимые проверочные записи, расширить подтверждённые сценарии общей пробуксовки, оценить uncertainty и перенос между трамваями. Весь поиск использовал уже существующий validation, а не новый независимый test; результаты не являются официальным баллом жюри.
