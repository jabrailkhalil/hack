"""Single queue consumer; every job runs in a cancellable child process."""
import signal
import subprocess
import sys
import time
from .storage import Settings, Store


def main():
    settings = Settings.environment()
    store = Store(settings)
    store.recover()
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        job = store.claim()
        if not job:
            time.sleep(.5)
            continue
        with (settings.state / (job['id'] + '.log')).open('w', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, '-m', 'tram_lab.web.jobs', job['id']], stdout=log, stderr=subprocess.STDOUT)
            while child.poll() is None:
                cancelling = store.get(job['id'])['status'] == 'cancelling'
                if stopping or cancelling:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill(); child.wait()
                    store.update(job['id'], status='interrupted' if stopping else 'cancelled')
                    break
                time.sleep(.3)
        current = store.get(job['id'])
        if current['status'] == 'cancelling':
            store.update(job['id'], status='cancelled')
        elif current['status'] == 'running':
            store.update(job['id'], status='failed', error=f'Расчёт завершился с кодом {child.returncode}')


if __name__ == '__main__':
    main()
