"""Stage an attached checksum-identical organizer archive; no network, train only.

This transport adapter does not modify the preregistered foundation.py or PLAN.
The outer ZIP is hashed as bytes; only authorized train DB members are extracted.
"""
import argparse
import datetime
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from stage import ROOT, pinned, save, sha


def safe_inventory(z, limit):
    entries = z.infolist()
    seen = set()
    if sum(x.file_size for x in entries) > limit:
        raise ValueError("Uncompressed archive limit exceeded")
    for item in entries:
        p = PurePosixPath(item.filename)
        if (p.is_absolute() or ".." in p.parts or "\\" in item.filename
                or item.filename in seen or item.flag_bits & 1
                or stat.S_ISLNK(item.external_attr >> 16)):
            raise ValueError("Unsafe or duplicate ZIP member")
        seen.add(item.filename)
    return entries


def stage_local(archive, output):
    archive, output = Path(archive), Path(output)
    if output.exists():
        raise FileExistsError("Use a new output directory")
    if sha(archive) != pinned.SHA256:
        raise ValueError("Organizer archive SHA256 differs from the pinned dataset")
    plan = json.loads((ROOT / "research/plan_v3.json").read_text())
    split = ROOT / "research/split_v3.json"
    if sha(split) != plan["manifest_sha256"]:
        raise ValueError("Split SHA256 mismatch")
    records = {r["bag"]: r for r in json.loads(split.read_text())["records"]}
    bags = plan["splits"]["train"]
    if len(bags) != 64 or len(set(bags)) != 64 or any(records[b]["split"] != "train" for b in bags):
        raise PermissionError("Not the exact authorized train role")
    output.mkdir(parents=True)
    inner = output / "data.zip"
    with zipfile.ZipFile(archive) as z:
        safe_inventory(z, 400 * 1024 * 1024)
        members = [n for n in z.namelist() if PurePosixPath(n).name == "data.zip"]
        if len(members) != 1:
            raise ValueError("Expected exactly one nested data.zip")
        with z.open(members[0]) as inp, inner.open("xb") as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
    extracted = []
    with zipfile.ZipFile(inner) as z:
        entries = safe_inventory(z, 1500 * 1024 * 1024)
        for bag in bags:
            matches = [i for i in entries if PurePosixPath(i.filename).name == bag + "_0.db3"]
            if len(matches) != 1 or matches[0].file_size != records[bag]["bytes"]:
                raise ValueError("Missing/duplicate/size-mismatched bag: " + bag)
            dest = output / "data" / bag / (bag + "_0.db3")
            dest.parent.mkdir(parents=True)
            with z.open(matches[0]) as inp, dest.open("xb") as out:
                shutil.copyfileobj(inp, out, 1024 * 1024)
            digest = sha(dest)
            if digest != records[bag]["sha256"]:
                raise ValueError("Bag checksum mismatch: " + bag)
            extracted.append({"bag": bag, "role": "train", "sha256": digest,
                              "bytes": dest.stat().st_size})
    receipt = {"dataset_sha256": pinned.SHA256, "source_archive": str(archive.resolve()),
               "archive_bytes": archive.stat().st_size,
               "nested_archive_sha256": sha(inner), "split_sha256": sha(split),
               "staged_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "extracted": extracted, "network_used": False,
               "measurement_decode_performed": False, "train_gnss_decoded": False,
               "validation_extracted": False, "development_extracted": False, "test_extracted": False,
               "transport_adapter_sha256": sha(__file__)}
    save(output / "STAGING.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "extracted"}, indent=2))
    print("VERIFIED TRAIN DATABASES:", len(extracted))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    stage_local(args.archive, args.output)
