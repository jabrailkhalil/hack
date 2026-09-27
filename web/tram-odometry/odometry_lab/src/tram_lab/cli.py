import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from .data import build_manifest, prepare_bag, make_split, write_json
from .experiments import load_config, run_experiment, select_records, msg_directory
from .reporting import compare_runs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tram-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "prepare", "split"):
        command = commands.add_parser(name)
        command.add_argument("--dataset", default="../dataset")
        command.add_argument("--cache", default=".cache")
        if name == "prepare":
            command.add_argument("--bags", nargs="+")
            command.add_argument("--msg-dir")
        if name == "split":
            command.add_argument("--strategy", choices=["chronological", "cross_vehicle"], default="chronological")
            command.add_argument("--train-vehicle", default="30618")
            command.add_argument("--output", default=".cache/split.json")
    run = commands.add_parser("run")
    run.add_argument("--config", required=True)
    for option in ("dataset", "cache", "output", "msg-dir"):
        run.add_argument("--" + option)
    run.add_argument("--bags", nargs="+")
    compare = commands.add_parser("compare")
    compare.add_argument("runs", nargs="+")
    compare.add_argument("--output", required=True)
    smoke = commands.add_parser("ros-smoke")
    smoke.add_argument("--dataset", default="../dataset")
    smoke.add_argument("--output", default="artifacts/ros-smoke")
    smoke.add_argument("--image", default="tram-odometry-lab:humble")
    smoke.add_argument("--build", action="store_true")
    smoke.add_argument("--project", default=".")
    args = parser.parse_args(argv)
    try:
        if args.command in {"inspect", "prepare", "split"}:
            manifest = build_manifest(args.dataset, args.cache)
            print(json.dumps(manifest["summary"], indent=2))
            if args.command == "prepare":
                config = {"dataset": args.dataset}
                if args.msg_dir: config["msg_dir"] = args.msg_dir
                for record in select_records(manifest, args.bags):
                    print(record["id"], prepare_bag(record, args.cache, msg_directory(config)))
            elif args.command == "split":
                result = make_split(manifest, args.strategy, args.train_vehicle)
                write_json(args.output, result)
                print({k: len(v) for k, v in result["splits"].items()})
        elif args.command == "run":
            config = load_config(args.config, {k: getattr(args, k) for k in ["dataset", "cache", "output", "msg_dir", "bags"]})
            if "output" not in config:
                config["output"] = str(Path("runs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
            run_experiment(config)
        elif args.command == "compare":
            compare_runs(args.runs, args.output)
            print(str(Path(args.output).resolve() / "report.html"))
        else:
            project, dataset, output = Path(args.project).resolve(), Path(args.dataset).resolve(), Path(args.output).resolve()
            if not (dataset / "tram_vehicle_msgs" / "msg").is_dir():
                raise ValueError("ros-smoke requires dataset root with tram_vehicle_msgs")
            if output.exists():
                raise FileExistsError(f"refusing to overwrite {output}")
            if args.build:
                subprocess.run(["docker", "build", "-f", str(project / "docker" / "Dockerfile"), "-t", args.image, str(project)], check=True)
            output.mkdir(parents=True)
            command = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "512m",
                       "--mount", f"type=bind,source={dataset},target=/dataset,readonly",
                       "--mount", f"type=bind,source={output},target=/artifacts", args.image, "smoke"]
            with (output / "runner.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                for line in process.stdout:
                    print(line, end="", flush=True)
                    log.write(line)
                code = process.wait()
            if code:
                if not (output / "smoke.json").exists():
                    write_json(output / "smoke.json", {"status": "failed", "stage": "container_build_or_startup", "exit_code": code, "log": "runner.log"})
                raise subprocess.CalledProcessError(code, command)
            print(output / "smoke.json")
    except (ValueError, FileNotFoundError, FileExistsError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
