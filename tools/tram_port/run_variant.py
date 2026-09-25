"""Execute this branch's selected port; do not change the active ROS champion."""
import argparse
import csv
import json
from pathlib import Path

import run_native as bench

ROOT = Path(__file__).resolve().parent


def route_check(output):
    import numpy as np
    from reserve_odometry.route import Route as HackRoute
    from tram_lab.hypotheses.concept_d import Route as OurRoute

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for route_id, points in enumerate(([(0, 0, 0), (10, 0, 0), (10, 10, 0)],
                                       [(0, 0, 0), (3, 4, 5), (8, 12, 7)])):
        native, ours = HackRoute(points), OurRoute(points)
        for s in np.linspace(0, native.arc[-1], 401):
            expected = np.asarray(native.at(float(s))[0])
            actual = ours.position(float(s))
            np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-14)
            rows.append((route_id, float(s), *actual.tolist(),
                         float(np.max(np.abs(actual - expected)))))
    with (output / 'route.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['route', 's_m', 'x_m', 'y_m', 'z_m', 'max_abs_difference_m'])
        writer.writerows(rows)
    result = {'points_checked': len(rows), 'max_coordinate_difference_m': max(r[-1] for r in rows),
              'real_map_evaluated': False, 'orientation_parity_evaluated': False}
    bench.dump(output / 'results.json', result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New output directory; never overwrite evidence.')
    parser.add_argument('--all', action='store_true', help='Run the original complete ten-method comparison.')
    args = parser.parse_args()
    selection = json.loads((ROOT / 'variant.json').read_text(encoding='utf-8'))
    method = selection['method']
    if method not in ('A', 'B', 'C', 'D', 'H1_10', 'H2_050'):
        raise ValueError('Unsupported branch variant: ' + str(method))
    if method == 'D' and not args.all:
        route_check(args.output)
        return
    if not args.all:
        bench.METHODS = ['mean', method, 'hack_v5', 'hack_v6', 'hack_v7', 'hack_v8']
    bench.run(args.output)
    bench.dump(Path(args.output) / 'selection.json', selection)


if __name__ == '__main__':
    main()
