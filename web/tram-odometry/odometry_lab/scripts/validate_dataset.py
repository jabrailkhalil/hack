"""Reproducible dataset acceptance, independent of any pre-existing temp analyses."""
import argparse
import hashlib
from pathlib import Path
from tram_lab.data import build_manifest, make_split, write_json
from tram_lab.experiments import load_config, run_experiment
from tram_lab.reporting import compare_runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="../dataset")
    parser.add_argument("--cache", default=".cache")
    parser.add_argument("--output", default="artifacts/validation")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = build_manifest(args.dataset, args.cache)
    assert manifest["summary"] == {"bags": 122, "unique_bags": 97, "duplicates": 25, "messages": 8788325}
    split = make_split(manifest)
    hashes = [{split["bag_hashes"][b] for b in split["splits"][key]} for key in ["train", "validation", "test"]]
    assert all(not hashes[i] & hashes[j] for i in range(3) for j in range(i + 1, 3))
    write_json(output / "split.json", split)
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs/mean.yaml", {"dataset": args.dataset, "cache": args.cache,
        "bags": ["30618_0e41eac3", "30639_0be558e2", "30618_0a83c933"]})
    first = run_experiment({**config, "output": str(output / "mean")})
    second = run_experiment({**config, "output": str(output / "mean_repeat")})
    assert first == second, "numerical metrics are not reproducible"
    digests = {}
    for bag in config["bags"]:
        relative = Path("bags") / bag / "predictions.csv"
        a, b = (output / "mean" / relative).read_bytes(), (output / "mean_repeat" / relative).read_bytes()
        assert a == b, f"nondeterministic predictions: {bag}"
        digests[bag] = hashlib.sha256(a).hexdigest()
    assert first["aggregate"]["bags_without_velocity_reference"] == 1
    assert first["aggregate"]["prediction_coverage"] > .99
    compare_runs([output / "mean", output / "mean_repeat"], output / "comparison")
    write_json(output / "verification.json", {"status": "passed", "manifest": manifest["summary"],
        "split_sizes": {k: len(v) for k, v in split["splits"].items()}, "disjoint_duplicate_groups": True,
        "identical_metrics": True, "identical_prediction_csv": True, "prediction_sha256": digests})
    print(output / "verification.json")


if __name__ == "__main__":
    main()
