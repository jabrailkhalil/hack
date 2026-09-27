"""Read-only sources, content-addressed cache, explicit CDR schemas."""
import hashlib
import json
import math
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
import numpy as np
import yaml
from filelock import FileLock
from rosbags.typesys import Stores, get_typestore, get_types_from_msg
from .types import Event

PARSER_VERSION = 2  # Rebuild caches created before cross-process serialization.
TOPIC_FIELDS = {
    "tram_vehicle_msgs/msg/VelocitySensor": ("velocity",),
    "tram_vehicle_msgs/msg/DriverControllerCommand": ("position",),
    "geometry_msgs/msg/TwistStamped": ("x", "y", "z"),
    "sensor_msgs/msg/NavSatFix": ("latitude", "longitude", "altitude", "status", "covariance_type", *[f"cov_{i}" for i in range(9)]),
}


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    temporary.replace(path)


def hash_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _record(meta, bag_id, digest, locator):
    duration_ns = int(meta["duration"]["nanoseconds"])
    start_ns = int(meta["starting_time"]["nanoseconds_since_epoch"])
    return dict(id=bag_id, vehicle=bag_id.split("_", 1)[0], sha256=digest,
                start_ns=start_ns, duration_ns=duration_ns, end_ns=start_ns + duration_ns,
                message_count=int(meta["message_count"]), locator=locator,
                topics=[dict(name=t["topic_metadata"]["name"], type=t["topic_metadata"]["type"], count=int(t["message_count"])) for t in meta["topics_with_message_count"]])


def build_manifest(dataset, cache=None):
    dataset = Path(dataset).resolve()
    archive = dataset if dataset.suffix == ".zip" else dataset / "data.zip"
    records = []
    if archive.is_file():
        with zipfile.ZipFile(archive) as z:
            for name in sorted(n for n in z.namelist() if n.endswith("/metadata.yaml")):
                parts = PurePosixPath(name).parts
                if len(parts) != 2 or any(p in ("..", ".") for p in parts):
                    raise ValueError(f"unsupported or unsafe archive path: {name}")
                meta = yaml.safe_load(z.read(name))["rosbag2_bagfile_information"]
                paths = meta["relative_file_paths"]
                if len(paths) != 1 or PurePosixPath(paths[0]).name != paths[0] or "\\" in paths[0]:
                    raise ValueError("v1 expects one plain sqlite3 filename per bag")
                member = str(PurePosixPath(name).parent / paths[0])
                with z.open(member) as stream:
                    digest = hash_stream(stream)
                records.append(_record(meta, parts[0], digest, {"archive": str(archive), "member": member}))
    else:
        files = [dataset / "metadata.yaml"] if (dataset / "metadata.yaml").exists() else sorted(dataset.glob("*/metadata.yaml"))
        if not files:
            raise FileNotFoundError(f"No data.zip or bag directories at {dataset}")
        for file in files:
            meta = yaml.safe_load(file.read_text(encoding="utf-8"))["rosbag2_bagfile_information"]
            paths = meta["relative_file_paths"]
            if len(paths) != 1:
                raise ValueError("v1 supports one sqlite3 file per bag")
            db = (file.parent / paths[0]).resolve()
            if db.parent != file.parent.resolve():
                raise ValueError("unsafe bag database path")
            with db.open("rb") as stream:
                digest = hash_stream(stream)
            records.append(_record(meta, file.parent.name, digest, {"db": str(db)}))
    groups = {}
    for record in records:
        groups.setdefault(record["sha256"], []).append(record["id"])
    for record in records:
        record["canonical_id"] = min(groups[record["sha256"]])
        record["has_gnss"] = any(t["count"] > 0 and t["name"].startswith("/sensing/gnss/") for t in record["topics"])
    manifest = {"schema_version": 1, "source": str(dataset), "bags": records, "duplicate_groups": {h: sorted(ids) for h, ids in groups.items()},
                "summary": {"bags": len(records), "unique_bags": len(groups), "duplicates": len(records) - len(groups), "messages": sum(r["message_count"] for r in records)}}
    if cache:
        write_json(Path(cache) / "manifest.json", manifest)
    return manifest


def make_split(manifest, strategy="chronological", train_vehicle="30618"):
    unique = [r for r in manifest["bags"] if r["id"] == r["canonical_id"]]
    if strategy == "cross_vehicle" and train_vehicle not in {r["vehicle"] for r in unique}:
        raise ValueError("train_vehicle is absent from this manifest")
    splits = {"train": [], "validation": [], "test": []}
    for vehicle in sorted({r["vehicle"] for r in unique}):
        rows = sorted((r for r in unique if r["vehicle"] == vehicle), key=lambda r: (r["start_ns"], r["id"]))
        if strategy == "chronological":
            n_train, n_val = math.floor(.7 * len(rows)), math.floor(.15 * len(rows))
        elif strategy == "cross_vehicle":
            if vehicle != train_vehicle:
                splits["test"].extend(r["id"] for r in rows)
                continue
            n_train, n_val = math.floor(.85 * len(rows)), len(rows) - math.floor(.85 * len(rows))
        else:
            raise ValueError("unknown split strategy")
        splits["train"].extend(r["id"] for r in rows[:n_train])
        splits["validation"].extend(r["id"] for r in rows[n_train:n_train+n_val])
        splits["test"].extend(r["id"] for r in rows[n_train+n_val:])
    return {"strategy": strategy, "train_vehicle": train_vehicle if strategy == "cross_vehicle" else None, "splits": splits,
            "bag_hashes": {r["id"]: r["sha256"] for r in unique}}


def _types(msg_dir):
    store = get_typestore(Stores.ROS2_HUMBLE)
    digest = hashlib.sha256()
    for name in ("VelocitySensor", "DriverControllerCommand"):
        raw = (Path(msg_dir) / f"{name}.msg").read_bytes()
        digest.update(raw)
        store.register(get_types_from_msg(raw.decode("utf-8"), f"tram_vehicle_msgs/msg/{name}"))
    return store, digest.hexdigest()[:16]


def materialize_bag(record, cache):
    """Extract only this bag, using fixed output filenames rather than ZIP paths."""
    dest = Path(cache) / "bags" / record["sha256"]
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "data_0.db3"
    if target.exists():
        with target.open("rb") as stream:
            if hash_stream(stream) != record["sha256"]:
                raise ValueError(f"corrupt extracted database: {target}")
    else:
        loc = record["locator"]
        with target.with_suffix(".tmp").open("wb") as output:
            if "archive" in loc:
                with zipfile.ZipFile(loc["archive"]) as z, z.open(loc["member"]) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        output.write(block)
            else:
                with Path(loc["db"]).open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        output.write(block)
        with target.with_suffix(".tmp").open("rb") as stream:
            if hash_stream(stream) != record["sha256"]:
                raise ValueError("source changed since manifest creation")
        target.with_suffix(".tmp").replace(target)
    # Preserve original rosbag metadata, changing only filenames. QoS is retained.
    loc = record["locator"]
    if "archive" in loc:
        with zipfile.ZipFile(loc["archive"]) as z:
            raw_meta = yaml.safe_load(z.read(str(PurePosixPath(loc["member"]).parent / "metadata.yaml")))
    else:
        raw_meta = yaml.safe_load((Path(loc["db"]).parent / "metadata.yaml").read_text(encoding="utf-8"))
    info = raw_meta["rosbag2_bagfile_information"]
    info["relative_file_paths"] = ["data_0.db3"]
    for item in info.get("files", []):
        item["path"] = "data_0.db3"
    (dest / "metadata.yaml").write_text(yaml.safe_dump(raw_meta, sort_keys=False), encoding="utf-8")
    return dest


def prepare_bag(record, cache, msg_dir):
    """Serialize cache creation across web requests and the worker process."""
    lock_dir = Path(cache) / 'locks'
    lock_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock_dir / (record['sha256'] + '.lock')), timeout=300):
        return _prepare_bag(record, cache, msg_dir)


def _prepare_bag(record, cache, msg_dir):
    store, schema_hash = _types(msg_dir)
    dest = Path(cache) / "decoded" / f"v{PARSER_VERSION}-{schema_hash}-{record['sha256']}"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "events.npz"
    if target.exists() and (dest / "schema.json").exists():
        return dest
    folder = materialize_bag(record, cache)
    con = sqlite3.connect((folder / "data_0.db3").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        topics = [{"id": i, "name": n, "type": t} for i, n, t in con.execute("SELECT id,name,type FROM topics ORDER BY id")]
        by_id = {t["id"]: (i, t) for i, t in enumerate(topics)}
        count = con.execute("SELECT count(*) FROM messages").fetchone()[0]
        if count != record["message_count"]:
            raise ValueError("metadata and SQLite message counts disagree")
        received = np.empty(count, dtype=np.int64)
        stamps = np.empty(count, dtype=np.int64)
        sequence = np.empty(count, dtype=np.int64)
        topic_index = np.empty(count, dtype=np.int16)
        frames = []
        values = np.full((count, 14), np.nan, dtype=np.float64)
        for row, (seq, topic_id, timestamp, raw) in enumerate(con.execute("SELECT id,topic_id,timestamp,data FROM messages ORDER BY timestamp,id")):
            ix, topic = by_id[topic_id]
            msg = store.deserialize_cdr(raw, topic["type"])
            received[row], sequence[row], topic_index[row] = timestamp, seq, ix
            stamps[row] = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
            frames.append(msg.header.frame_id)
            if topic["type"].endswith("/VelocitySensor"):
                numbers = [msg.velocity]
            elif topic["type"].endswith("/DriverControllerCommand"):
                numbers = [msg.position]
            elif topic["type"].endswith("/TwistStamped"):
                numbers = [msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z]
            elif topic["type"].endswith("/NavSatFix"):
                numbers = [msg.latitude, msg.longitude, msg.altitude, msg.status.status, msg.position_covariance_type, *msg.position_covariance]
            else:
                raise ValueError(f"unsupported type: {topic['type']}")
            values[row, :len(numbers)] = numbers
        with target.with_suffix(".tmp").open("wb") as stream:
            np.savez_compressed(stream, received_ns=received, stamp_ns=stamps, sequence=sequence, topic_index=topic_index, values=values, frame_id=np.asarray(frames))
        target.with_suffix(".tmp").replace(target)
        write_json(dest / "schema.json", {"parser_version": PARSER_VERSION, "schema_hash": schema_hash, "sha256": record["sha256"], "topics": topics})
        diagnostics = {}
        for ix, topic in enumerate(topics):
            mask = topic_index == ix
            h, r = stamps[mask], received[mask]
            diagnostics[topic["name"]] = {"count": int(mask.sum()), "backward_headers": int(np.sum(np.diff(h) < 0)),
                "future_headers": int(np.sum(h > r)), "max_receipt_gap_s": float(np.max(np.diff(r)) / 1e9) if len(r) > 1 else None}
        write_json(dest / "diagnostics.json", diagnostics)
    finally:
        con.close()
    return dest


def read_bag(record, cache, msg_dir):
    folder = prepare_bag(record, cache, msg_dir)
    schema = json.loads((folder / "schema.json").read_text(encoding="utf-8"))
    with np.load(folder / "events.npz", allow_pickle=False) as archive:
        arrays = {k: archive[k] for k in archive.files}
    for row in range(len(arrays["received_ns"])):
        topic = schema["topics"][int(arrays["topic_index"][row])]
        fields = TOPIC_FIELDS[topic["type"]]
        data = {name: float(arrays["values"][row, i]) for i, name in enumerate(fields)}
        if "position" in data:
            data["position"] = int(data["position"])
        yield Event(topic["name"], int(arrays["stamp_ns"][row]), int(arrays["received_ns"][row]), int(arrays["sequence"][row]), data, str(arrays["frame_id"][row]))
