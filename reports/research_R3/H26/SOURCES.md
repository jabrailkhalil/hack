# R3-H26: источники и уровень проверки

## Задание и прошлые исследования

R3-H26_colored_measurement_noise.md: baseline e3b0c9c039d2953fbfcda51231263d38ef9f1024, canonical GuardedReadoutObserver/champion_v8. Прочитаны PR18 (scientific H10, joint [v,d], старый R1), H18/PR37 report eaba504f35b546bc5149b476b84fb0c0d749e897/reports/research_R2/H18/36185008785-1/REPORT.md и H18/PR38 report abfec83ef52cf0c7c0b210a273c369613a7e091c/reports/research_R2/H18/covariance-36186808559-1/REPORT.md. Их accuracy не является результатом H26.

## Первичный научный источник

Wei Liu, Peng Shi, Huiyan Zhang. Kalman filtering with finite-step autocorrelated measurement noise. Journal of Computational and Applied Mathematics 408 (July 2022), 114138. DOI: 10.1016/j.cam.2022.114138.

Publisher: https://www.sciencedirect.com/science/article/pii/S0377042722000334
University metadata: https://digital.library.adelaide.edu.au/items/07a6dac6-83a6-4c12-b9bc-a34c77b61961

Фактически прочитаны индексируемые web-выдержки metadata и abstract самого издателя; авторство сверено по университетской карточке. Прямой open ScienceDirect вернул HTTP403; университетская страница — cache miss. Полный текст не прочитан. Ранние DOI/страницы тома были недоступны; поздний узкий поиск вернул publisher abstract.

Abstract о дискретных линейных системах, finite-step autocorrelated measurement noise, state augmentation и специальной covariance recurrence мотивирует исследование. Он не доказывает пригодность AR(1), правильность нелинейного v8 или улучшение на наших данных. AR(1) здесь условный вариант, не воспроизведение статьи.

Consensus и Scite НЕ запрашивались заново: известные месячные quota stops указаны в задании. Новый отказ сервиса не выдумывается; покупок/обхода квот нет.

## Математика

Фактически исполнены WolframLanguageEvaluator с явной матричной Joseph-формулой и локальный независимый numeric check 5000 PSD-случаев. Worksheet/output/assumptions приложены. Предшествующий WolframContext почти везде дал No Results Found и неверно истолковал разность gain как конечную разность по c; этот результат не использован. Линейные формулы не доказывают устойчивость полного switched observer.
