# H15 / R2-v7-fixed

Исследовательский механизм, не включён в canonical launch. Checkout НЕ активирует core patch. В отдельной чистой рабочей копии запустить `python research/R2/H15/apply.py`; затем H15 включается фабрикой `DriveDependentObserver(Config(**profile['config']), readout=ReadoutConfig(**profile['readout']), correction=DriveCorrectionConfig(ridge=0.01))` либо ridge=0.04. Выключение `enabled=False` должно точно воспроизводить канонический GuardedReadoutObserver R2, не plain Observer.

`run.py` использует исходные score/replay, matching и fault_windows, заменяя только конструктор observer. Исторические файлы evaluator/pins не переписываются. `_canonical` создаётся apply.py, не коммитится; это точная копия baseline core+readout для независимого исполнения. Ветки/отчёты H11 и других R2 агентов не используются при подборе.

`PLAN.md` зарегистрирован commit 3b1c63e6a1536843f866f800f851f357691ff350 до экспериментов. Локальные релевантные проверки до real-data: 28 H15/driver, 26 core и 10 timeline PASS. Локальный dataset download недоступен из-за DNS; выполнение на реальных записях предоставлено отдельному GitHub Actions workflow и не считается выполненным до его результатов.

Все команды и этапы в `.github/workflows/research-R2-H15.yml`. Для manual replay нужен новый OUT, pinned requirements, apply.py, train/development. Freeze публикуется отдельным git commit до validation; `H15_FREEZE_COMMIT` обязателен. Перезапись outputs запрещена. Смотрите финальный REPORT для фактически исполненных этапов, а не это описание инфраструктуры.
