# Проверки текущего выбора и упаковки

## Фактически выполнено

1. Первый полный локальный replay девяти оценивателей: все 19 validation-bag, 152 fault-сценария, параметры не менялись; baseline v8 0.1145498613174081 воспроизведён точно.
2. Повтор тем же frozen bench.py с 8 worker вместо 4: все 19 per-bag JSON совпали побайтово, все prediction hashes и численные aggregate/gate поля идентичны. Канонический hash summary без wall elapsed: 6dd0d194308f17334a5521f7db0300eac58b95865164d626aa5daca9feba2a4e. Это два исполнения, не новый независимый test.
3. 161 вызов unit-тестов после упаковки — PASS. Включает пять новых packaging/source-lock тестов; наследуемые сценарии не обозначаются 161 независимой гипотезой.
4. 43 research-integrity tests — PASS. Historical evaluator/config/final-test evidence не переписывались.
5. `setup.py bdist_wheel` — PASS. В созданном wheel один console_script, один установленный launch и один YAML; старые варианты не установлены.
6. Проверка 10 SHA256 runtime/config/launch против e3b0c9c — PASS, ни одно уравнение/коэффициент/адаптер не изменены.
7. Геометрический D smoke: 802 точки, max difference 0; реальная карта и ориентация не проверены.

## Что НЕ выполнено заново

Новая installed ROS / colcon / no-network 2CPU/500MB проверка упаковки и удалённый повтор сравнения НЕ завершены. Первый preflight runner исполнился и выявил неоднозначный historical path; prepare.py исправлен, frozen сценарии/bench/hashes не изменены. Следующий run 36230840124 и retry имеют failure без steps и без исполняемых логов. Причина невыделения runner через доступные инструменты не установлена; billing/quota не объявляются фактом. Не приписывать новые ROS измерения этой упаковке.

Сохраняются ранее проверенные численные и ROS-исходники v8. Выбор не внедряет новый неподтверждённый алгоритм: меняются только упаковка, однозначный публичный запуск, документация и тестовая маршрутизация. Для повторения свежей ROS-проверки в готовой среде: `bash submission/build.sh`; она использует отдельный install_main.

Полный локальный raw архив приложен в разговоре, SHA256/размер в decision.json. На GitHub сохранены frozen runner/протокол, selected-source lock, clean per-bag CSV, fault-by-type CSV, machine-readable decision и этот журнал. Workflow сохраняет полный raw checkpoint при восстановлении возможности запуска, но такой будущий checkpoint сейчас не заявляется созданным.
