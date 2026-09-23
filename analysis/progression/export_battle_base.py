"""Recover raw base wrappers needed by ordinary server-supplied fight heroes."""
import json
from pathlib import Path
from probe import read_tables

data, meta, missing = read_tables(('PlayerAttrib','IndexInfo','AttribType'))
assert not missing
hero = next(r for r in data['PlayerAttrib'] if r['ID'] == 1003)
types = {r['AttribId']:r for r in data['AttribType']}
rows = []
for mapping in data['IndexInfo']:
    name, attr = mapping['AttreName'], mapping['AttrID']
    assert attr in types
    rows.append({'name':name,'attrId':attr,'attrValue':hero.get(name,0),
                 'runtime_enum':types[attr].get('NameEnu',{'value':0,'enum':'E_ATK'})})
result = {'hero_id':1003,'sources':meta,'attributes':rows,
          'evidence': 'Unit.InitProperty 0x1CCA05C skips AddBaseProperty for non-null mOtherAttrs; ConvertHeroAttrAdd 0x16C37B0 always returns a list; IndexInfo maps raw PlayerAttrib fields to AttribType IDs. PropertyUpdate applies level/stage, so send raw base values, not grown totals.'}
path = Path(__file__).with_name('battle_base_1003.json')
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('exported',len(rows),'base wrappers')
