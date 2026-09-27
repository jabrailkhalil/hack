import json
import sqlite3
import zipfile
from pathlib import Path
import numpy as np
import pytest
import yaml
from rosbags.typesys import Stores, get_typestore, get_types_from_msg
from tram_lab.data import build_manifest, make_split, read_bag, prepare_bag
from tram_lab.experiments import select_records, run_experiment
from tram_lab.types import FRONT, COMMAND


@pytest.fixture
def fixture_dataset(tmp_path):
    root = tmp_path / "dataset"
    msg_dir = root / "tram_vehicle_msgs" / "msg"
    msg_dir.mkdir(parents=True)
    store = get_typestore(Stores.ROS2_HUMBLE)
    definitions = {"VelocitySensor": "std_msgs/Header header\nfloat64 velocity\n", "DriverControllerCommand": "std_msgs/Header header\nint8 position\n"}
    for name, definition in definitions.items():
        (msg_dir / f"{name}.msg").write_text(definition)
        store.register(get_types_from_msg(definition, f"tram_vehicle_msgs/msg/{name}"))
    t = 1_786_353_518_961_320_453
    msg_time = store.types["builtin_interfaces/msg/Time"]
    header = store.types["std_msgs/msg/Header"]
    raw_bases = []
    for n in range(2):
        db = tmp_path / f"source{n}.db3"
        con = sqlite3.connect(db)
        con.executescript("CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT,type TEXT); CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB);")
        vel_type, cmd_type = "tram_vehicle_msgs/msg/VelocitySensor", "tram_vehicle_msgs/msg/DriverControllerCommand"
        con.executemany("INSERT INTO topics VALUES(?,?,?)", [(1, FRONT, vel_type), (2, COMMAND, cmd_type)])
        h = header(msg_time(*divmod(t, 10**9)), "base_link")
        vel = store.types[vel_type](h, 36.+n)
        cmd = store.types[cmd_type](header(msg_time(*divmod(t+1, 10**9)), ""), -15)
        con.executemany("INSERT INTO messages VALUES(?,?,?,?)", [(1, 1, t, store.serialize_cdr(vel, vel_type)), (2, 2, t+100_000_000, store.serialize_cdr(cmd, cmd_type))])
        con.commit(); con.close()
        raw_bases.append(db.read_bytes())
    with zipfile.ZipFile(root / "data.zip", "w") as z:
        for i, name in enumerate(["100_a", "100_b", "200_c"]):
            z.writestr(f"{name}/{name}_0.db3", raw_bases[0 if i < 2 else 1])
            info = {"version": 5, "storage_identifier": "sqlite3", "duration": {"nanoseconds": 100_000_000},
                    "starting_time": {"nanoseconds_since_epoch": t}, "message_count": 2,
                    "relative_file_paths": [f"{name}_0.db3"], "topics_with_message_count": [
                        {"topic_metadata": {"name": FRONT, "type": vel_type, "serialization_format": "cdr", "offered_qos_profiles": ""}, "message_count": 1},
                        {"topic_metadata": {"name": COMMAND, "type": cmd_type, "serialization_format": "cdr", "offered_qos_profiles": ""}, "message_count": 1}]}
            z.writestr(f"{name}/metadata.yaml", yaml.safe_dump({"rosbag2_bagfile_information": info}))
    return root, msg_dir, t


def test_manifest_hashes_types_cache_and_precision(fixture_dataset, tmp_path):
    dataset, msg_dir, base = fixture_dataset
    cache = tmp_path / "cache"
    manifest = build_manifest(dataset, cache)
    assert manifest["summary"] == {"bags": 3, "unique_bags": 2, "duplicates": 1, "messages": 6}
    record = manifest["bags"][0]
    a = list(read_bag(record, cache, msg_dir))
    assert a[0].received_ns == base and a[1].stamp_ns == base+1
    assert a[0].data["velocity"] == 36 and a[1].data["position"] == -15
    assert a[0].frame_id == "base_link"
    assert a == list(read_bag(record, cache, msg_dir))
    folder = prepare_bag(record, cache, msg_dir)
    with np.load(folder / "events.npz", allow_pickle=False) as arrays:
        assert arrays["stamp_ns"].dtype == np.int64
    duplicate_folder = prepare_bag(manifest["bags"][1], cache, msg_dir)
    assert folder == duplicate_folder
    with pytest.raises(ValueError): select_records(manifest, ["100_a", "100_b"])


def test_split_disjoint_hashes_and_temporal_order():
    records = [{"id": f"{v}_{i:02d}", "canonical_id": f"{v}_{i:02d}", "vehicle": v, "start_ns": i, "sha256": f"hash{v}{i}"} for v in ["a", "b"] for i in range(20)]
    records += [{**records[0], "id": "duplicate"}]
    split = make_split({"bags": records})
    assert [len(split["splits"][s]) for s in ["train", "validation", "test"]] == [28, 6, 6]
    groups = [set(split["splits"][s]) for s in ["train", "validation", "test"]]
    assert not groups[0] & groups[1] and not groups[1] & groups[2] and not groups[0] & groups[2]
    cross = make_split({"bags": records}, "cross_vehicle", "a")
    assert all(b.startswith("b_") for b in cross["splits"]["test"])


def test_concurrent_first_decode_is_atomic(fixture_dataset, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    dataset, msg_dir, _ = fixture_dataset
    record = build_manifest(dataset)['bags'][0]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: list(read_bag(record, tmp_path / 'shared-cache', msg_dir)), range(12)))
    assert all(rows == results[0] for rows in results)


def test_full_run_repeatable_without_reference(fixture_dataset, tmp_path):
    dataset, msg_dir, _ = fixture_dataset
    config = {"dataset": str(dataset), "cache": str(tmp_path / "cache"), "msg_dir": str(msg_dir), "bags": ["100_a"],
              "estimator": {"name": "front"}, "period_ms": 50, "seed": 42, "faults": [], "quality": {}, "tolerance_ms": 50, "plots": False}
    a = run_experiment({**config, "output": str(tmp_path / "run_a")}, progress=lambda _: None)
    b = run_experiment({**config, "output": str(tmp_path / "run_b")}, progress=lambda _: None)
    assert a == b and a["aggregate"]["bags_without_velocity_reference"] == 1
    for relative in ["metrics.json", "bags/100_a/predictions.csv"]:
        assert (tmp_path / "run_a" / relative).read_bytes() == (tmp_path / "run_b" / relative).read_bytes()
    with pytest.raises(FileExistsError): run_experiment({**config, "output": str(tmp_path / "run_a")})


def test_web_job_matches_cli_predictions(fixture_dataset, tmp_path):
    from tram_lab.web.storage import Settings, Store
    from tram_lab.web.jobs import execute
    from tram_lab.web.service import run_config
    dataset, _, _ = fixture_dataset
    settings = Settings(dataset, tmp_path/'cache', tmp_path/'runs', tmp_path/'models', tmp_path/'state')
    store = Store(settings)
    request = {'models':[{'id':'front'}], 'bags':['100_a'], 'seed':42}
    job = store.create('experiment', request)
    result = execute(settings, store, job)
    output = tmp_path/'cli'
    config = run_config(settings, request, {'id':'front'}, output)
    run_experiment(config, progress=lambda _: None)
    web = settings.runs / result['runs'][0]
    for relative in ['metrics.json', 'bags/100_a/predictions.csv']:
        assert (web/relative).read_bytes() == (output/relative).read_bytes()
