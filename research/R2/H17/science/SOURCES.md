# H17: источники и фактический доступ

## Один релевантный первичный источник
Jie Zhang, Qianrong Fan, Ming Wang, Bangji Zhang, Yuanchang Chen (2022).
*Robust Speed Tracking Control for Future Electric Vehicles under Network-Induced Delay and Road Slope Variation*. Sensors 22(5),1787. DOI: 10.3390/s22051787.
https://doi.org/10.3390/s22051787

Consensus: узкий поиск по названию; затем fetch `b5409ecad6415ef980dafbc4fdcd27f7`. Прочитаны карточка и abstract, НЕ полный текст через Consensus. Дополнительные поисковые результаты (Lai/Pan 2024, sensor-fusion editorial 2023, PWM converter 2023) не использованы: другие задачи/сенсорные предпосылки.

Scite: фактический вызов search_literature(doi, term="slip", limit=1) вернул месячный лимит 25 calls, reset 2026-10-01 UTC. Карточка/полный текст/контекст цитирования НЕ получены. Ничего не покупалось. Сам факт citations или mentioning не является проверкой H17.

У издателя через web доступен полный HTML; прочитаны постановка/модель и ограничения, включая Remark 4. Это исследование управления скоростью IMT, не доказательство wheel-only reserve odometry. Оно различает сетевую задержку и динамику/возмущения. Использует motor-speed/torque измерения и vehicle-speed предпосылку через скорость колеса; схема не переносится в наш интерфейс. В Remark 4 отмечено нарушение связи wheel speed/vehicle speed при slip. Предлагаемые там внешние acceleration/GPS средства здесь запрещены. Сетевые CAN задержки 1–20 ms и их распределение из чужой модели не обосновывают наши 50–200 ms. Линеаризация и симуляционное исследование ограничивают перенос выводов. Здесь источник используется только для различения delay/lag/disturbance и оговорок идентифицируемости.

## Математика
WolframContext выполнен, затем WolframLanguageEvaluator фактически проверил формулы, пределы и чувствительности. `wolfram.wl` — исполнимый worksheet с явно разрешёнными единицами; `wolfram_output.txt` сохраняет фактический результат сервиса, включая сообщения и исходные natural-language macros. Математика при идеальной модели не является результатом replay.

## Предыдущие исследования (не данные для R2-подбора)
Прочитаны v6 REPORT и относящийся к теме H07/#22, H05/#17 из предыдущего задания, PR #14/#23 и соседний #26/H11. H07 менял tau тяги/торможения, H17 меняет только causal command argument. v6 wheel projection влиял на внутренний фильтр и имел fault-регрессии; output-only guarded v7 уже включён в baseline. H11 quarantine общей wheel anomaly не включается. Числа старого baseline не переносятся на R2. Валидация других R2-агентов не использовалась.
