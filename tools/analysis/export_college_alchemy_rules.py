"""Export official element currencies and global periods from the canonical APK."""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables, resources, UnityPy, ROOT as CLIENT_ROOT
from phase3_protobuf import convert_data_bytes, parse_message

tables, sources, missing = read_tables(['Item', 'CurrencyType'])
if missing:
    raise ValueError(missing)
items = [r for r in tables['Item'] if 1237991 <= r['ItemID'] <= 1237996]
entry = resources['table/globalparamstring']
with zipfile.ZipFile(CLIENT_ROOT / 'X2_Eclipse_v2_4.apk') as apk:
    env = UnityPy.load(apk.read('assets/bin/Data/' + entry['source_hash']))
    obj = next(o.read() for o in env.objects if o.type.name == 'TextAsset')
    blob = obj.m_Script
    if isinstance(blob, str):
        blob = blob.encode('utf8', 'surrogateescape')
    wrapper, _ = parse_message(convert_data_bytes(blob)[4:])
    rows = [parse_message(v.value)[0] for v in wrapper if v.field == 2]
    global_rows = [{('Key' if v.field == 1 else 'Value'): v.value.decode() for v in row}
                   for row in rows]
sources['GlobalParamString'] = {'source': 'assets/bin/Data/' + entry['source_hash']}
params = {r['Key']: r['Value'] for r in global_rows
          if r['Key'] in ('AlchemyNum', 'AlchemyCustomerNum', 'AlchemyExploreParam',
                         'AlchemyPriceNum', 'AlchemyPriceParam', 'AlchemyDiscountNum',
                         'AlchemyDiscountParam', 'AlchemyAdviceParam', 'AlchemySpeedConsume')
          or r['Key'] in [f'Element{i:02}' + suffix for i in range(1, 7)
                          for suffix in ('', 'Pay', 'Param')]}
result = {'sources': sources, 'items': items, 'params': params,
          'speed_cards': [r for r in tables['Item'] if r.get('FunctionEff', {}).get('value') == 8]}
(ROOT / 'src/x2server/data/college_alchemy_rules.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(params)
