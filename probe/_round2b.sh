export PYTHONIOENCODING=utf-8 PYTHONPATH=.
PY=.venv/Scripts/python.exe
$PY -m pds probe-run 2 --max-rows 1000
$PY -c "
import asyncio,json,os
from pds.probe.files import run_files
t=json.load(open('knowledge/targets.json',encoding='utf-8'))
items=[(x['id'],x['url']) for x in t if x['round']=='2' and x['kind'] in ('STD','FILE') and not json.load(open(f'probe/runs/{x[\"id\"]}.json',encoding='utf-8')).get('ok_ops')] if True else []
print('retry files',len(items))
for r in asyncio.run(run_files(items)): print('FILE',r['id'],r.get('rows'),r.get('error','')[:120])
"
$PY -m pds probe-report 2
$PY -m pds.probe.synth 2
echo DONE
