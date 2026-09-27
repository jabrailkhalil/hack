"""Real-data acceptance against a running Docker web stack. Creates new runs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8080')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    evidence = {}
    def api(path, body=None):
        request = urllib.request.Request(args.url+'/api/v1'+path, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)
    def job(kind, request, key):
        created = api('/jobs', dict(kind=kind, request=request))
        evidence[key] = created['id']
        (args.output/'progress.json').write_text(json.dumps(evidence, indent=2))
        previous = ''
        deadline = time.monotonic()+3600
        while time.monotonic()<deadline:
            result = api('/jobs/'+created['id'])
            message = result['status']+' '+(result['log'].splitlines()[-1] if result['log'] else '')
            if message != previous:
                print(key, message, flush=True); previous = message
            if result['status'] not in ('queued','running','cancelling'):
                assert result['status'] == 'succeeded', result
                (args.output/(key+'.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False))
                return result
            time.sleep(2)
        raise TimeoutError(key)

    data = api('/dataset'); by_id={b['id']:b for b in data['bags']}
    assert data['summary']['unique_bags'] == 97
    # Simultaneous first reads exercise cache coordination without modifying sources.
    old = api('/runs')
    old_run = next((r for r in old if r['id'] == 'validation_mean'), old[0])
    old_bag = old_run['metrics']['bags'][0]['id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(api, ['/geometry/'+old_bag,
                 '/series?'+urllib.parse.urlencode({'run':old_run['id'],'bag':old_bag}),
                 '/geometry/'+old_bag]))
    assert responses[1]['metrics'] == next(r['metrics'] for r in old_run['metrics']['bags'] if r['id']==old_bag)
    evidence['legacy_run_loaded'] = old_run['id']

    models = [m['id'] for m in api('/models')['models']]
    baseline = job('experiment',dict(name='Приёмка · все модели', models=[{'id':m} for m in models],
                   bags=['30618_0e41eac3'],seed=42), 'models_job')
    cross = job('experiment',dict(name='Приёмка · второй трамвай и без GNSS',models=[{'id':'mean'},{'id':'hack_v8'}],
                bags=['30639_0be558e2','30618_0a83c933'],seed=42), 'cross_vehicle')
    for run_id in cross['result']['runs']:
        series = api('/series?'+urllib.parse.urlencode({'run':run_id,'bag':'30618_0a83c933'}))
        assert all(v is None for v in series['error'])
        assert any(v is not None for v in series['velocity'])
        assert all(p[0] is None for p in series['actual_position'])

    split = api('/splits')
    def pick(subset):
        return [min((b for b in split['splits'][subset] if by_id[b]['vehicle']==vehicle and by_id[b]['has_gnss'] and by_id[b]['duration_s']>120),
                    key=lambda b:by_id[b]['duration_s']) for vehicle in ['30618','30639']]
    train_bags, validation_bags = pick('train'), pick('validation')
    training = job('train',dict(name='Приёмка · A train',models=[{'id':'A'}], train_bags=train_bags,
                   validation_bags=validation_bags,seed=42), 'training')
    artifact = api('/artifacts/'+training['result']['artifact'])
    assert artifact['weights']['training_ids'] == train_bags
    assert not artifact['test_used']
    assert not set(train_bags)&set(validation_bags)
    tuned = job('tune',dict(name='Приёмка · подбор A',models=[{'id':'A','artifact':artifact['id']}],
                train_bags=train_bags,validation_bags=validation_bags,seed=42,budget=3,
                coverage_floor=.95,ranges={'innovation_gate_mps':{'min':.5,'max':1.}}), 'tuning')
    learned = job('experiment',dict(name='Приёмка · обученная версия', models=[{'id':'mean'},
                  {'id':'A','artifact':tuned['result']['artifact']}],bags=['30618_0e41eac3'],seed=42), 'learned')
    downloaded = args.url+'/api/v1/download?'+urllib.parse.urlencode({'run':learned['result']['runs'][0],'file':'bags/30618_0e41eac3/predictions.csv'})
    with urllib.request.urlopen(downloaded) as response:
        assert b'time_ns,velocity_mps,distance_m' in response.read(100)
    created = api('/jobs',dict(kind='experiment',request=dict(name='Приёмка · отмена',models=[{'id':'H2'}],bags=['30618_0e41eac3'])))
    deadline=time.monotonic()+15
    while api('/jobs/'+created['id'])['status']=='queued' and time.monotonic()<deadline:
        time.sleep(.2)
    api('/jobs/'+created['id']+'/cancel',{})
    while api('/jobs/'+created['id'])['status']=='cancelling' and time.monotonic()<deadline:
        time.sleep(.2)
    assert api('/jobs/'+created['id'])['status']=='cancelled'
    evidence.update(cancelled_job=created['id'],training_ids=train_bags,validation_ids=validation_bags,
                    models=models,status='passed',download_csv=True)
    (args.output/'verification.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False))
    print('PASS', json.dumps(evidence,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
