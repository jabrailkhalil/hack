#!/usr/bin/env python3
"""R7 input preflight. Stdlib only; does not read SQL contents or run estimators."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, sys, zipfile
from pathlib import Path
from datetime import datetime, timezone

EXPECTED = {
    "canonical_source": {
        "sha256": "4823fbdbbb979d7b561841e2831e68f2f7d9d8ec0d14e970f09a38cd51dff4c4",
    },
    "dataset": {
        "sha256": "d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52",
        "db_count": 122,
    },
    "teacher_h42": {
        "sha256": "2ee08edb32343350bf6ae6202836644de4fb309640f2d140a1eb9d5791af28b8",
        "file_count": 85,
    },
    "atlas_h43": {
        "sha256": "6a759f4bafe4ece014e9dd4f25b201549e317f2ca9db7b47b6c15d4443d9b011",
        "file_count": 53,
    },
    "h44_completed": {
        "sha256": "f95dac3fdb10ce720800a39fe7a7444c25b27e2d72f06157d3f61f5386fd47ea",
        "file_count": 216,
    },
    "h54_completed": {
        "sha256": "e1d9a1816eb64cde78a077391a19295299d360662d74a0505a0cef747d9fac0b",
        "file_count": 194,
    },
}

REQUIRED = {
    "A0": ("canonical_source", "dataset", "h44_completed", "h54_completed"),
    "A1": ("canonical_source", "dataset", "teacher_h42", "h44_completed"),
}

BASELINE_COMMIT = "b2783206000091ab11a1c11ac3ff79082188a4fb"
BASELINE_TREE = "973d50d288e050325ee1c71a90fa8d81f2a099af"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()

def inspect_zip(path: Path):
    with zipfile.ZipFile(path) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        dbs = [i for i in files if i.filename.lower().endswith((".db", ".sqlite", ".sqlite3"))]
        bad = z.testzip()
    return len(files), len(dbs), bad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=("A0", "A1"), required=True)
    ap.add_argument("--inputs", required=True, help="JSON object mapping dependency keys to local paths")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    mapping = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
    out = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "task": args.task,
        "baseline_commit": BASELINE_COMMIT,
        "baseline_tree": BASELINE_TREE,
        "python": sys.version,
        "platform": platform.platform(),
        "artifacts": {},
        "status": "PASS",
    }

    for key in REQUIRED[args.task]:
        if key not in mapping:
            raise SystemExit(f"missing required input key: {key}")
        path = Path(mapping[key]).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"not a file: {key} -> {path}")
        exp = EXPECTED[key]
        digest = sha256(path)
        rec = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": digest,
            "expected_sha256": exp["sha256"],
            "sha256_ok": digest == exp["sha256"],
        }
        if not rec["sha256_ok"]:
            raise SystemExit(f"sha256 mismatch for {key}: {digest}")
        if zipfile.is_zipfile(path):
            count, db_count, bad = inspect_zip(path)
            rec.update(zip_file_count=count, zip_db_count=db_count, zip_crc_bad_member=bad)
            if bad is not None:
                raise SystemExit(f"CRC failure in {key}: {bad}")
            if "file_count" in exp and count != exp["file_count"]:
                raise SystemExit(f"member count mismatch for {key}: {count} != {exp['file_count']}")
            if "db_count" in exp and db_count != exp["db_count"]:
                raise SystemExit(f"DB count mismatch for {key}: {db_count} != {exp['db_count']}")
        out["artifacts"][key] = rec

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing lock: {output}")
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "task": args.task, "output": str(output)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
