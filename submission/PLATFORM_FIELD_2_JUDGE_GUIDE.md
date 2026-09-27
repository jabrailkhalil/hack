# 2. Инструкция для жюри

https://github.com/jabrailkhalil/hack/blob/main/submission/JUDGE_GUIDE.md

Инструкция содержит подготовку Ubuntu 22.04 / ROS 2 Humble, сборку, запуск ноды, воспроизведение rosbag с /clock, точные входные и выходные топики, команды просмотра результатов и диагностики. Для измерения задержки, частоты, CPU и памяти предусмотрен tools/benchmark_selected.py, запускающий установленный v8 и сохраняющий JSON, CSV и логи.

Веб-демонстрация: https://github.com/jabrailkhalil/hack/blob/main/submission/WEB_DEMO.md — графики скорости, пути и ошибок, сравнение v8 с базовыми моделями, просмотр GNSS и экспорт результатов. UI воспроизводит запись офлайн; рабочая ROS-нода запускается отдельно.
