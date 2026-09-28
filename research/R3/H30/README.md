# R3-H30

Один кандидат по PLAN.md. Обычный checkout/ROS launch H30 не включает.

```python
import sys
sys.path.insert(0, 'research/R3/H30')
from factory import candidate
observer = candidate(enabled=True)
# observer.step(t, command, front, rear) -> Estimate
```

factory.py создаёт приватную копию core/readout; joint.py хранит совместную covariance. Все canonical src, profiles и evaluator остаются побайтно прежними. Hook-патч выводится командой `python research/R3/H30/factory.py` и сохраняется workflow как algorithm.patch; сам патч требует factory.py и joint.py, он не самостоятельная ROS-интеграция.

```bash
python -m pip install -r requirements-research.txt
PYTHONPATH=src/reserve_odometry python -m unittest discover -s tests -v
python -m unittest discover -s research/tests -v
python -m unittest discover -s research/R3/H30/tests -v
python research/R3/H30/oracle.py
python research/R3/H30/stage_data.py --stage development --journal /tmp/H30-stage.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 python research/R3/H30/run.py --stage development --output /tmp/H30-fresh --workers 2
```

Output directory должен быть новым. Validation/test стадий в этом driver нет. Положительный development требует отдельного опубликованного freeze. Тесты с отключённым H30 не сертифицируют installed enabled ROS. История: <=32 state slots/32x32 covariance и суммарно <=64 event/ledger records; при нехватке истории/ёмкости conservative fallback, counters saturating. d не replay; прошлые выданные Estimate и накопленная дистанция не переписываются.
