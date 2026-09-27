import json
import os
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from ..catalog import registry
from .service import manifest, split_for, runs, validate_request, artifact
from .series import load_series, geometry_for
from .storage import Settings, Store, safe_path

settings = Settings.environment()
store = Store(settings)
app = FastAPI(title='Tram Odometry Lab', version='1.0')


@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and urlparse(origin).netloc != request.headers.get('host'):
        return JSONResponse({'detail': 'Cross-origin mutations are disabled'}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.exception_handler(KeyError)
@app.exception_handler(FileNotFoundError)
def missing(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=404)


@app.get('/api/v1/health')
def health():
    return {'status': 'ok'}


@app.get('/api/v1/display')
def display():
    return {'tile_url': os.environ.get('TRAM_TILE_URL', 'https://tile.openstreetmap.org/{z}/{x}/{y}.png')}


@app.get('/api/v1/models')
def models():
    return dict(models=list(registry().values()), geometry=[dict(id='D', label='D · заданная геометрия маршрута', kind='geometry')],
                provenance=json.loads((Path(__file__).parents[1] / 'model_sources.json').read_text()))


@app.get('/api/v1/dataset')
def dataset():
    data = manifest(settings)
    return dict(summary=data['summary'], bags=[dict(id=r['id'], vehicle=r['vehicle'],
                duration_s=r['duration_ns']/1e9, has_gnss=r['has_gnss'], start_ns=str(r['start_ns']), sha256=r['sha256'])
                for r in data['bags'] if r['id'] == r['canonical_id']])


@app.get('/api/v1/splits')
def splits(strategy: str = 'chronological', train_vehicle: str = '30618'):
    return split_for(settings, dict(split=strategy, train_vehicle=train_vehicle))


class JobRequest(BaseModel):
    kind: str = 'experiment'
    request: dict = Field(default_factory=dict)


@app.get('/api/v1/jobs')
def jobs():
    return store.list()


@app.post('/api/v1/jobs', status_code=202)
def create_job(payload: JobRequest):
    validate_request(settings, payload.kind, payload.request)
    return store.create(payload.kind, payload.request)


@app.get('/api/v1/jobs/{identity}')
def get_job(identity: str):
    return store.get(identity)


@app.post('/api/v1/jobs/{identity}/cancel')
def cancel_job(identity: str):
    return store.cancel(identity)


@app.get('/api/v1/runs')
def get_runs():
    return runs(settings)


@app.get('/api/v1/series')
def series(run: str, bag: str, limit: int = 5000):
    return load_series(settings, run, bag, max(100, min(limit, 50000)))


@app.get('/api/v1/geometry/{bag}')
def geometry(bag: str):
    return geometry_for(settings, bag)


@app.get('/api/v1/artifacts')
def artifacts():
    items = [json.loads(p.read_text(encoding='utf-8')) for p in settings.models.glob('*/artifact.json')]
    return sorted([dict(id=a['id'], name=a['name'], model_id=a['model_id'], kind=a['kind'], created=a['created'], validation=a['validation']) for a in items], key=lambda a: a['created'], reverse=True)


@app.get('/api/v1/artifacts/{identity}')
def get_artifact(identity: str):
    return artifact(settings, identity)


@app.get('/api/v1/download')
def download(run: str, file: str):
    folder = safe_path(settings.runs, run)
    path = safe_path(folder, file)
    if not path.is_file() or path.suffix not in ('.csv', '.json', '.yaml', '.npz', '.html'):
        raise HTTPException(404, 'Артефакт не найден')
    return FileResponse(path, filename=path.name)


# Register before the root SPA mount; otherwise /research API can be swallowed.
from .research_api import router_for
app.include_router(router_for(settings, store))

static = Path(os.environ.get('TRAM_FRONTEND', Path(__file__).parents[3] / 'frontend/dist'))
if static.is_dir():
    app.mount('/', StaticFiles(directory=static, html=True), name='frontend')
