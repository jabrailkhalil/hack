"""Materialize this agent's checksummed source bundle, never canonical files."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = '21616b8d6024bd499c167e9a29896f1bdfc77cd96ac008367c463857dc56efe7'
NAMES = {'BASELINE.json','README.md','SOURCES.md','algorithm.patch','execute.sh','factory.py','run.py','stage_data.py','tests/test_h20.py','wolfram-output.json','wolfram.wl'}
parts = [(HERE/'transport'/f'{i}.b64').read_text().strip() for i in range(4)]
raw = base64.b64decode(''.join(parts), validate=True)
if hashlib.sha256(raw).hexdigest() != EXPECTED:
    raise ValueError('Transport checksum mismatch; no source was applied or data opened')
text = gzip.decompress(raw)
if len(text) > 200000:
    raise ValueError('Unexpected source bundle size')
files = json.loads(text)
if set(files) != NAMES:
    raise ValueError('Unexpected bundle paths')
for name, content in files.items():
    path = HERE/name
    if path.exists() and path.read_text() != content:
        raise FileExistsError('Refuse to overwrite a different implementation: '+name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
print('Verified H20 source transport:', EXPECTED, 'files:', len(files))
