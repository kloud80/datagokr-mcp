set -x
export PYTHONIOENCODING=utf-8 PYTHONPATH=.
PY=.venv/Scripts/python.exe
IDS=$($PY -c "
import json; t={x['id'] for x in json.load(open('knowledge/targets.json',encoding='utf-8')) if x['round']=='2'}
import glob
print(' '.join(json.load(open(p,encoding='utf-8'))['id'] for p in glob.glob('probe/specs/*.json') if json.load(open(p,encoding='utf-8'))['id'] in t and not json.load(open(p,encoding='utf-8')).get('swagger') and 'openapi.do' in json.load(open(p,encoding='utf-8'))['url']))")
$PY -m pds.probe.spec_old $IDS
$PY -m pds probe-apply 2
$PY -m pds probe-run 2 --max-rows 1000
$PY -c "
import asyncio,json
from pds.probe.files import run_files
t=json.load(open('knowledge/targets.json',encoding='utf-8'))
items=[(x['id'],x['url']) for x in t if x['round']=='2' and x['kind'] in ('STD','FILE')]
for r in asyncio.run(run_files(items)): print('FILE',r['id'],r.get('rows'),r.get('error','')[:120])
"
$PY -m pds probe-report 2
$PY -m pds.probe.synth 2
echo DONE
