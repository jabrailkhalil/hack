"""One-shot activation of reviewed PR11; preserve old evidence, never retune.

Run only on the dedicated activation branch. CI commits the resulting files to
an isolated checkpoint for review; this script never moves main or calls APIs.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace(path, old, new):
    target = ROOT / path
    text = target.read_text()
    if old not in text:
        raise ValueError('Unexpected source before activation: ' + path)
    target.write_text(text.replace(old, new, 1))


def main():
    record_path = ROOT / 'submission/ACTIVE_PROFILE.json'
    if record_path.exists():
        raise FileExistsError('Activation is one-shot; preserve the previous decision')
    cfg = ROOT / 'src/reserve_odometry/config'
    if (cfg / 'default.yaml').read_bytes() != (cfg / 'adaptive_v5.yaml').read_bytes():
        raise ValueError('Main profile changed; reconcile rather than overwrite it')
    core = ROOT / 'src/reserve_odometry/reserve_odometry/core.py'
    if hashlib.sha256(core.read_bytes()).hexdigest() != '6e2063666eea57a8065f405e0953797b3036cc0b7204b18bfafe5458bce5b1db':
        raise ValueError('PR11 core differs from reviewed version')
    (cfg / 'default.yaml').write_bytes((cfg / 'time_aligned_v6.yaml').read_bytes())
    profile = 'src/reserve_odometry/config/time_aligned_v6.json'
    config = json.loads((ROOT / profile).read_text())['config']
    protected = ['src/reserve_odometry/reserve_odometry/' + p for p in
                 ('core.py', 'node.py', 'timeline.py', 'route.py')]
    protected += ['src/reserve_odometry/config/' + p for p in
                  ('default.yaml', 'time_aligned_v6.json', 'time_aligned_v6.yaml',
                   'adaptive_v5.yaml', 'adaptive_v5.json')]
    record = dict(selected='time_aligned_v6', profile_json=profile, config=config,
        operational=dict(rate_hz=20., alignment_delay_s=0., clock_mode='input_stamp'),
        source_pr=11, source_pr_head='9d9bbf53ffe02520b98eaf78ae974e0864d75508',
        base_main='efc473e415795d64770ef9dfa4f1bc417078da32',
        decision='owner_directed_clean_distance_priority', automatic_previous_gate_passed=False,
        known_tradeoff='vs v5: clean group-macro RMSE -2.2722%; scalar span distance -1.1627%; fault-event RMSE +1.9585%. Not a Pareto improvement and not a pass of the historical 0.5% fault-regression gate.',
        fallback='src/reserve_odometry/config/adaptive_v5.yaml', independent_test_evaluated=False,
        evidence='reports/time_alignment_v6/REPORT.md', next_experiment='research/plan_v7.json',
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in protected},
        historical_v4_archive_sha256=hashlib.sha256((ROOT / 'submission/dist/reserve-odometry-v4.zip').read_bytes()).hexdigest())
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    replace('tests/ros_calibrated_smoke.py',
        "active = root / 'reports/research_v6/PROMOTION.json'",
        "active = root / 'submission/ACTIVE_PROFILE.json'\n    if not active.exists():\n        active = root / 'reports/research_v6/PROMOTION.json'")
    replace('tests/test_active_profile.py',
        "promotion=json.loads((ROOT/'reports/research_v6/PROMOTION.json').read_text())",
        "promotion=json.loads((ROOT/'submission/ACTIVE_PROFILE.json').read_text())")
    replace('tests/test_active_profile.py',
        "self.assertEqual(dict(actual,wheel_time_compensation=0.0),asdict(Config(**actual)))",
        "self.assertEqual(actual,asdict(Config(**actual)))\n        self.assertEqual(actual['wheel_time_compensation'],1.0)\n        self.assertFalse(promotion['automatic_previous_gate_passed'])\n        self.assertEqual(promotion['decision'],'owner_directed_clean_distance_priority')")
    replace('tests/test_active_profile.py',
        "raw = read_v4(path) if path.endswith('/core.py') else (ROOT/path).read_bytes()",
        "if path.endswith('/core.py'):\n                raw = read_v4(path)\n            elif path == 'src/reserve_odometry/config/default.yaml':\n                raw = (ROOT/'src/reserve_odometry/config/adaptive_v5.yaml').read_bytes()\n            else:\n                raw = (ROOT/path).read_bytes()")
    replace('tests/test_active_profile.py',
        '    def test_original_v4_default_is_retained_exactly(self):',
        """    def test_active_source_and_profile_hashes_match(self):
        active=json.loads((ROOT/'submission/ACTIVE_PROFILE.json').read_text())
        for path,digest in active['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
        self.assertEqual((ROOT/'src/reserve_odometry/config/default.yaml').read_bytes(),
                         (ROOT/'src/reserve_odometry/config/time_aligned_v6.yaml').read_bytes())

    def test_original_v4_default_is_retained_exactly(self):""")
    replace('tools/research_time_alignment/compare.py',
        'if ev.sha(ROOT / path) != expected:',
        "source = (ROOT / 'src/reserve_odometry/config/adaptive_v5.yaml'\n                  if path == 'src/reserve_odometry/config/default.yaml' else ROOT / path)\n        if ev.sha(source) != expected:")
    replace('tools/research_time_alignment/compare.py',
        '# main promoted the already measured v5 to default while this PR was open.\n    # Verify the actual active YAML, not the historical balanced-physics default.',
        "# Historical PR11 confirmation, not a declaration of today's default.\n    # Retained v5 fallback is byte-identical to the pinned original default.")
    replace('tools/research_time_alignment/compare.py',
        "for line in (cfg / 'default.yaml').read_text().splitlines():",
        "for line in (cfg / 'adaptive_v5.yaml').read_text().splitlines():")
    replace('tools/research_time_alignment/compare.py',
        'Active main profile differs from the paired v5 baseline',
        'Retained v5 profile differs from the pinned baseline')
    overview = """# Активный профиль: time_aligned_v6 (PR #11)

Обычный запуск теперь использует **time_aligned_v6**, без дополнительных аргументов. `default.yaml` побайтно совпадает с `time_aligned_v6.yaml`. Профиль компенсирует возраст принятых колёсных измерений ограниченным модельным ускорением и добавляет неопределённость переноса; адаптация остаётся 0.5 с.

| Тот же validation-набор | v5 | Активный v6 | Изменение |
|---|---:|---:|---:|
| Group-macro RMSE скорости, м/с | 0.117138274 | **0.114476684** | **-2.2722%** |
| Pooled RMSE скорости, м/с | 0.216723603 | **0.216396651** | -0.1509% |
| Scalar-span RMSE дистанции, м | 4.630977808 | **4.577133777** | **-1.1627%** |
| Group-macro fault-event RMSE, м/с | **0.538434411** | 0.548979449 | **+1.9585%** |

Выбор сделан по явному решению владельца в пользу clean-точности и дистанции. Это **не** прохождение прежнего автоматического порога 0.5% fault-регрессии. v6 не лучше по каждой метрике. Validation использовался повторно: нового независимого final test нет. 19 bag, 698891 сопоставленная точка, одинаковые timestamps и reference-маски. Scalar-span distance не равна xyz или полному терминальному дрейфу.

[Измерения PR11](reports/time_alignment_v6/REPORT.md) · [Активный профиль и хэши](submission/ACTIVE_PROFILE.json) · [Следующая задача: устойчивость](research/plan_v7.json) · [История отклонённых гипотез](reports/research_v6/REPORT.md).

## Сборка и запуск

В подготовленной Ubuntu 22.04 / ROS 2 Humble из корня checkout:

```bash
bash submission/build.sh
bash submission/run.sh
```

После сборки и source окружения также работает обычный `ros2 launch reserve_odometry odometry.launch.py`. Без дополнительных аргументов запускается v6. Для отката:

```bash
ros2 launch reserve_odometry odometry.launch.py \\
  params_file:="$PWD/src/reserve_odometry/config/adaptive_v5.yaml"
```

Голый `ros2 run` без params-file использует базовый Config(), не выбранный профиль. Три vehicle-входа, без GNSS/IMU/LLM/numpy/SciPy в runtime. Выходы VelocitySensor, Odometry и диагностика; 20 Гц, искусственная задержка 0 с. Физические коэффициенты не переобучались.

## Версии доказательств

Старые PROMOTION/отчёты v5 и `submission/dist/reserve-odometry-v4.zip` сохранены. Final test на 22 bag, FREEZE и 24-минутный ROS-прогон подтверждают **только v4**, не активный v6. Исторические хэши не переписаны, активные исходники проверяются отдельным ACTIVE_PROFILE.json. Старый evaluator намеренно не сертифицирует новый default старым freeze.

Новая задача: проверить три фиксированные гипотезы уменьшения fault-регрессии без потери clean-точности. План публикуется до вычислений; все результаты сохраняются. Патчи не включаются в runtime без отдельного сравнения и CI.

## Ограничения

Положение (s,0,0) в odom_path_1d — относительная дистанция, не ENU/xyz-траектория. Карта/origin/маршрут и единицы scale=1/3.6 требуют подтверждения организатора. Общая правдоподобная ошибка тележек может быть неразличима. При полном исчезновении inputs нужен продолжающийся /clock (`bash submission/run.sh --clock`); независимые bags требуют перезапуска.

[Инструкция](submission/JUDGE_GUIDE.md) · [Поля формы](submission/PLATFORM_FIELDS.md) · [Вопросы организаторам](docs/ORGANIZER_QUESTIONS.md). Приватность и отправка на платформу не менялись.
"""
    (ROOT / 'README.md').write_text(overview)
    guide = ROOT / 'submission/JUDGE_GUIDE.md'
    text = guide.read_text()
    position = text.index('## 1. Среда и сборка')
    guide.write_text("""# Запуск активного time_aligned_v6 и архива v4

## Выбор версии

Текущий main по решению владельца использует time_aligned_v6 из PR11. На повторно используемом validation он точнее v5 по обычной скорости на 2.2722% и scalar-span дистанции на 1.1627%, но хуже в fault-окнах на 1.9585%. Это компромисс, не pass прежнего автоматического gate и не независимый test. [ACTIVE_PROFILE.json](ACTIVE_PROFILE.json) содержит текущие параметры и хэши; [измерения PR11](../reports/time_alignment_v6/REPORT.md) — полные результаты.

Архив reserve-odometry-v4.zip остаётся историческим: его FREEZE/final-test/24-минутный runtime относятся только к v4. Для отката к v5 передать params_file с adaptive_v5.yaml.

""" + text[position:].replace('побайтно равный выбранному `adaptive_v5.yaml`', 'побайтно равный выбранному `time_aligned_v6.yaml`'))
    fields = ROOT / 'submission/PLATFORM_FIELDS.md'
    text = fields.read_text().replace('активный профиль v5','активный профиль time_aligned_v6').replace('checkout main с v5','checkout main с time_aligned_v6').replace('v5-код','v6-код').replace('Активная конфигурация adaptive_v5','Активная конфигурация time_aligned_v6')
    old = 'Базовые уравнения и runtime из v4 сохранены. Активный v5 меняет только постоянную времени адаптации неучтённого ускорения с 8 до 0.5 с; fitted-параметры тяги, мощности и торможения не переобучались. Пять экспериментальных вариантов v6 отклонены и не включены в ноду.'
    if old not in text:
        raise ValueError('Unexpected platform fields')
    text = text.replace(old, 'Базовая модель и адаптация v5 (0.5 с) дополнены компенсацией возраста принятых колесных измерений ограниченным модельным ускорением и неопределённостью переноса. Raw samples не меняются для gates, адаптации и остановки. Физические коэффициенты не переобучались; отклонённые исследовательские патчи не включены.')
    text = text.replace('reports/research_v6/REPORT.md', 'reports/time_alignment_v6/REPORT.md').replace('reports/research_v6/PROMOTION.json', 'submission/ACTIVE_PROFILE.json')
    begin = text.index('На одинаковом повторно используемом validation:')
    end = text.index('\n\n## 6.', begin)
    text = text[:begin] + 'На повторно используемом validation: group-macro RMSE скорости 0.114476684 м/с (v5: 0.117138274); pooled RMSE 0.216396651 м/с; scalar-span distance RMSE 4.577133777 м (v5: 4.630977808). Fault-event RMSE 0.548979449 м/с, хуже v5 на 1.9585%. 698891 сопоставленная точка, покрытие и число ложных остановок не ухудшились. Активация v6 — выбор владельца в пользу clean/distance, не pass прежнего 0.5% gate. Нового независимого final test нет. Новые runtime-измерения указываются отдельно по выполненным runs; старые числа v4/v5 не приписываются v6.' + text[end:]
    fields.write_text(text)
    print('Activation prepared; run unit/integrity/ROS checks before main promotion.')


if __name__ == '__main__':
    main()
