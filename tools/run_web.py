"""Serve the built web interface and its experiment worker on localhost."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from check_web_integration import verify, ROOT, LAB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'dataset/organizer')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    verify()
    frontend = LAB / 'frontend/dist'
    if not (frontend / 'index.html').is_file():
        parser.error('Build the frontend first: cd web/tram-odometry/odometry_lab/frontend && npm ci && npm run build')
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', args.port))
        except OSError:
            parser.error(f'Port {args.port} is in use; choose --port')
    env = dict(os.environ, PYTHONUTF8='1')
    paths = dict(DATASET=args.dataset.resolve(), FRONTEND=frontend,
                 CACHE=ROOT/'web/.cache', RUNS=ROOT/'web/runs',
                 MODELS=ROOT/'web/models', STATE=ROOT/'web/.state')
    env.update({'TRAM_'+key: str(value) for key, value in paths.items()})
    env['PYTHONPATH'] = str(LAB/'src') + (os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    if not args.dataset.is_dir():
        print('Dataset is absent. Models are available; load official data before running experiments.', flush=True)
    children = []
    try:
        for command in ([sys.executable, '-m', 'uvicorn', 'tram_lab.web.app:app',
                         '--host', '127.0.0.1', '--port', str(args.port)],
                        [sys.executable, '-m', 'tram_lab.web.worker']):
            children.append(subprocess.Popen(command, cwd=LAB, env=env))
        print(f'Web interface: http://127.0.0.1:{args.port}', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.5)
        raise SystemExit(next((p.returncode for p in children if p.returncode), 1))
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
