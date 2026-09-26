# R5-H48 — MAP_FIT построена и проверена; REJECTED

**Прежний DEPENDENCY_PENDING снят. Две карты реально построены, но готового MAP_V0 / H48-v1 нет.** Робастное представление проиграло контролю; обе карты имеют 1899 рёбер при лимите интерфейса 1024. Это отрицательный результат конкретного fixed design, не запрет дальнейшего исследования геометрии. Draft PR59 не готов к merge; merge/auto-merge/force не выполнялись.

[Полный русский отчёт](https://drive.google.com/file/d/1gkZhpYPwyysQB-wmEG2407hme1xjf3SD/view) · [H48 workspace](https://drive.google.com/drive/folders/1WaThXKdTEmGfoDekuBtIyBJlFLxhmgxj) · [44.51 МБ evidence](https://drive.google.com/file/d/1cVU6ehuhqKzOi7kKU-cQ7m1eXkIUk3zq/view).

## Версии и методика

Baseline b2783206000091ab11a1c11ac3ff79082188a4fb/tree973d50d288e050325ee1c71a90fa8d81f2a099af; все320paths/bytes/modes проверены. H42 native85files/H43 native53files и bridge64fold assignments прошли до coordinate IO. Dataset exact SHA d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52. Извлечены только64train DB.

DESIGN_FREEZE опубликован до координат: f2ac8dc1bbd0c108d58256a19b43bb247f806e63. **Измеренный geometry source:7a29145e942406ed374d94f9bf4bc00b2b4d0049.** Prefix-only fix/source:a792e976dfc26e429c860cd21fb4f67079b2f53b; он не меняет fit/scorer/maps.

50fitting bags/20групп;14check bags/7групп. 1769241train GNSS row декодированы frozen H42 storage/decoder. Его teacher/masks не регенерировались. Wire duplicates не считаются повторно в primary, но per-bag сохранены. **200370check points,6непустых групп**, одна группа missing, не ошибка0. Development/validation/final-test не открывались.

CONTROL: ordered antenna tracklets, разрывы сохраняются, 3D RDP0.25м, отдельные master/roverlayers. ROBUST: group-balanced median lateral offsets, радиус2м, tangent15°, минимум3группы, cap0.5м, один triangular5мpass, тот же RDP. Ровно2представления без post-check tuning. 121137/132218якорей реально изменены, 125155с поддержкой. Никаких выдуманных связей на crossing/proximity.

WGS84 ECEF→ENU с origin только fitting. Unknown geoid/MGRS/base_link/antenna extrinsics не подставлены. ANTENNA_TRAJECTORY_PROXY_ONLY, tangent не body heading. Около242км суммы повторных проходов не длина уникального маршрута.

## Результаты

| Метрика | CONTROL | ROBUST |
|---|---:|---:|
| Group-macro XY RMSE, м |84.894825733|84.919256748|
| Group-macro p95, м |88.117751335|88.210954416|
| Pooled RMSE, м |25.031487485|25.033635204|
| Pooled p95, м |0.685675958|0.812091078|
| Covered≤10м, из200370 |197990|197989|
| Ambiguous projections |92.961521186%|93.127214653%|
| Edges, limit1024 |1899|1899|
| Vertices |12191|13037|
| Uncompressed JSON bytes, limit1МБ |780744|811417|

RMSE ухудшение **+0.028777979%**; p95macro+0.105771061%. Два ранее покрытых отсчёта потеряны, один приобретён; pointwise veto не подменён общим count. ROBUST больше на30673байта. Метрики включают ВСЕ конечные accepted check points: nearest-XY-segment одного receiver, без отбрасывания далёких точек. Source-group RMSE усредняется по группам; это не официальный XYZ/longitudinal scorer.

**Контрпример49fc4c6fb44fd0ea / bag30618_bc5e53c2:**502точки, coverage0, RMSE494.593734162м у обоих. Он остаётся в основном агрегате; нельзя сообщить только субметровый pooledp95. Причина расхождения не объявлена доказанной GNSS-ошибкой. Пять других непустых групп ухудшились: в eeabf7d118bbcdac0.103056759→0.140281238м. Leave-one-group-out sensitivity без refit: даже без дальней группы2.955044047→2.984361265м(+0.9921%). Все группы в per_group.csv.

Whole graph не проходит cap, хотя JSONsize проходит. Master823edges, rover1076; последний превышает предел и отдельно. Контрольный fallback не разрешён. **SELECTION.selected=null; MAP_V0 не строилась; H49–H51 не получают готовый handoff.** Не повышался cap и не удалялись плохие группы ради прохождения.

## Фактические проверки

161canonical,43integrity,13coordinator,44geometry доfit — PASS; послеprefixfix всего45geometry, compileallPASS. Whole-map verifier останавливался на edgebudget: его нулевые reverseполя НЕ являются измерениями. Отдельный post-audit проверил каждое ребро:17091forward/reverse pairs на модель, max<9.4e-13м; ENUroundtrip<3.7e-9м; pyproj3.7.2ECEF cross-check<1.4e-9м. Brute force400запросов на каждую карту полностью совпал с indexed projection (delta0). Агрегаты пересчитаны из residuals точно. JSONroundtrip проверен; повторного полного fitting не было.

Wolfram actual worksheet подтвердил ENUorthonormality/det1, reverseprojection/arclength/pruning identities; это implementation checks, не accuracyproof. Consensus/Scite после известного quota stop не вызывались.

Prefix test сначала FAIL на stalearrival; до реальныхprefixs исправлена только freshness к arrivalrecord с прежними250мс. FAIL/PASSлоги сохранены. На14rawprefix≤3с:13UNLOCALIZED,1ANCHORED_ANTENNA_PROXY через0.194014474с, residual0.365779122м. Это не правильность начальной локализации/edge. Все14prefixextensionchecks одинаковы; использовать можно только masterlayer диагностически, wholecomponentневалиден.

Python3.13.5/NumPy2.3.5/SciPy1.17.0, threads1. Fitwall/CPU66.7513/66.7464с, check52.9383/52.8998с. **Локальные прогоны, не Actions/ROS latency.** После работы320baseline files в2копиях неизменны; teacher85/atlas53payload hashes повторно совпали. Patchсначала не прошёл из-за сериализации отсутствующего newline в старомPLAN; исправлен только diff export, затем git apply --checkPASS. Никакого изменения научного кода ради результата.

## Evidence и воспроизведение

[CONTROL MAP_FIT](https://drive.google.com/file/d/1JPyobrfNI1P1BdZp1mCskAGODtFupv5c/view), SHAef58333e1ca44f0f742947fe11fe93fae6592086bad706475a5f293f0f44caed.
[ROBUST MAP_FIT](https://drive.google.com/file/d/1W3oJkBgVL1wkWyOxh8AALxXkoWn4tQKj/view), SHA059516dddb3a71f0113e20eb0b75f7de953547bc1e8bc8aed06fa8dea837ccf2.
[Карта с check overlay](https://drive.google.com/file/d/10Ki1wPOQQEWp6CzXGncrGeOyLrC_Ynow/view).
[Все per-bag/receiver](https://drive.google.com/file/d/1jNUqICQ7ChGREwbA4qD2R7ScNTUZzpaw/view).
[Итоговый research patch](https://drive.google.com/file/d/18WVpfwf_jZTljocKNNgEpSCMOICwDk9w/view).

ZIP44512271bytes SHA2565a3d3abb841d7a84723dd1fc24b7cfa1d8134282028ef3b82d81764b986d72c2:249manifestfiles/CRC+allSHAverified. Внутри обе fitmaps/cache/residuals/prefix/receipts/tests/math и REPRODUCE.md; исходные canonical source/dataset/teacher/atlas не дублируются. Старые reportsimmutable. Source snapshots7a29145 и fixedprefix отдельно.

```bash
# Полный checkout7a29145, verified deps/native locks, новыеoutput dirs:
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python research/R5/H48/map_pipeline.py --stage fit --output "$FIT" --teacher "$TEACHER" --dataset "$DATASET" --data-root "$DATA_ROOT" --folds "$FOLDS"
python research/R5/H48/map_pipeline.py --stage check --output "$CHECK" --fit "$FIT" --teacher "$TEACHER" --dataset "$DATASET" --data-root "$DATA_ROOT" --folds "$FOLDS"
```

Значения путей и pinneddeps в lock/REPRODUCE; полныйmeasurement7a29145, prefixfixa792. **Fullstageзапрещён дляselected=null.** Validation/finaltest, enabledROS и longitudinalaccuracy не выполнялись. Нельзя присваивать H48 исторические результатыv8.

Следующий возможный отдельный протокол: консолидация повторных цепочек в компактную корректную топологию и проверка покрытия. Это ещё не выполненный новый дизайн. Сначала START HERE/frozen artifacts/hash/новыйlock, не повторный fitting наугад.
