"""Audit saved H39 train outputs without reading any measurement database or refitting q."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(root, split_path):
    root = Path(root)
    summary = json.loads((root / "SUMMARY.json").read_text())
    split = json.loads(Path(split_path).read_text())
    records = {r["bag"]: r for r in split["records"]}
    bags = json.loads((root / "per_bag.json").read_text())
    access = json.loads((root / "access.json").read_text())
    expected = {r["bag"] for r in split["records"] if r["split"] == "train"}
    assert len(expected) == len(bags) == len(access) == 64
    assert {r["bag"] for r in bags} == {r["bag"] for r in access} == expected
    topics = {"/vehicle/driver_position_cmd", "/vehicle/front_bogie_velocity",
              "/vehicle/rear_bogie_velocity"}
    for r in access:
        assert r["purpose"] == "train" and set(r["topics"]) == topics
        assert r["sha256"] == records[r["bag"]]["sha256"]
    hashes = json.loads((root / "HASHES.json").read_text())
    assert all(digest(root / k) == v for k, v in hashes.items())
    npz = np.load(root / "eligible_train.npz", allow_pickle=False)
    all_groups = sorted({records[b]["group"] for b in expected})
    role = {g: "check" if i % 3 == 2 else "fitting" for i, g in enumerate(all_groups)}
    seen = set()
    selected = []
    for r in bags:
        key = (r["group"], r["vehicle_wire_sha256"])
        assert r["duplicate_wire"] == (key in seen)
        seen.add(key)
        if not r["duplicate_wire"]:
            selected.append(r)
        for i, channel in enumerate(("front", "rear")):
            a = npz[r["bag"] + "_" + channel]
            assert a.shape == (r["channels"][i].get("eligible", 0), 3)
            assert np.isfinite(a).all() and np.all(np.diff(a[:, 0]) > 0)
    comparisons = 0
    independent_bounds = {}
    for channel in ("front", "rear"):
        cc = summary["channels"][channel]
        independent_bounds[channel] = {}
        for group in all_groups:
            aa = [npz[r["bag"]+"_"+channel] for r in selected if r["group"] == group]
            a = np.concatenate(aa) if aa else np.empty((0, 3))
            record = cc["per_group"][group]
            assert record["eligible"] == len(a)
            assert record["distinct_values"] == len(np.unique(a[:, 1]))
            qualifies = len(a) >= 1000 and len(np.unique(a[:, 1])) >= 100 and np.ptp(a[:, 1]) >= 1
            assert record["qualified"] == qualifies and record["role"] == role[group]
            pairs = [np.abs(x[:len(x)//2*2:2, 1] - x[1:len(x)//2*2:2, 1]) for x in aa]
            d = np.concatenate(pairs) if pairs else np.array([])
            if len(d):
                d = d[np.linspace(0, len(d)-1, min(512, len(d)), dtype=int)]
            bound = record["practical_pair_upper_bound"]
            assert bound["pairs"] == len(d)
            if not len(d):
                assert bound["max_fraction"] is None
                continue
            # Independent interval stabbing: directly test all unique interval
            # endpoints and interior midpoints in long-double precision.
            dd = d.astype(np.longdouble)
            lo, hi = np.longdouble(np.sqrt(.0012)), np.longdouble(.5)
            tol, eps = np.longdouble(.002), np.longdouble(2e-10)
            endpoints = [lo, hi]
            for value in dd:
                max_n = int(np.ceil((value + eps)/lo + tol))
                for n in range(max_n+1):
                    left = (value-eps)/tol if n == 0 else (value-eps)/(n+tol)
                    right = hi if n == 0 else (value+eps)/(n-tol)
                    left, right = max(lo, left), min(hi, right)
                    if left <= right:
                        endpoints.extend([left, right])
            ends = np.unique(endpoints)
            candidates = np.unique(np.r_[ends, (ends[1:]+ends[:-1])/2])
            maximum = 0
            for q in candidates:
                residual = np.abs(dd-np.rint(dd/q)*q)
                # Boundary roundoff allowance only for the independent audit.
                count = int(np.sum(residual <= tol*q + eps + np.longdouble(1e-17)))
                maximum = max(maximum, count)
            assert maximum == bound["max_pairs"], (group, channel, maximum, bound)
            independent_bounds[channel][group] = {
                "pairs": len(d), "independent_max_pairs": maximum,
                "maximum_fraction": maximum/len(d)}
            comparisons += 1
        fit_count = sum(r["qualified"] and r["role"] == "fitting" for r in cc["per_group"].values())
        check_count = sum(r["qualified"] and r["role"] == "check" for r in cc["per_group"].values())
        assert [fit_count, check_count] == [cc["qualified_fit_groups"], cc["qualified_check_groups"]]
        assert cc["selected"] is None and cc["coherent_proposals"] == 0
    assert summary["scientific_verdict"] == "INCONCLUSIVE"
    return {"passed": True, "train_databases_in_access": len(access),
            "unique_wire_streams": len(seen), "source_groups": len(all_groups),
            "hashes_verified": len(hashes), "saved_arrays_verified": len(npz.files),
            "independent_pair_bounds_verified": comparisons,
            "bounds": independent_bounds, "refitting_performed": False,
            "measurement_database_io": False,
            "audit_source_sha256": digest(Path(__file__))}

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", required=True, type=Path)
    p.add_argument("--split", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = audit(args.results, args.split)
    with args.output.open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "bounds"}, indent=2))
