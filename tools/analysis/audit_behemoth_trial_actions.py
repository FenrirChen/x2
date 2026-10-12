"""Compare Behemoth ultimate transitions in the original APK action assets."""
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import ROOT as ASSETS, resources, UnityPy
from phase3_protobuf import parse_table_container, parse_message


def audit():
    dump = (ASSETS / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8')
    def numbers(name):
        block = re.search(r'public class ' + name + r' //[^\n]+\n\{(.*?)// Properties', dump, re.S)[1]
        return {name: index for index, (_, name) in enumerate(
            re.findall(r'private ([\w<>]+) <(\w+)>k__BackingField;', block), 1)}
    action, interrupt = numbers('Action'), numbers('ActionInterrupt')
    result = {}
    with zipfile.ZipFile(ASSETS / 'X2_Eclipse_v2_4.apk') as archive:
        for unit in (1303, 1003):
            source = resources[f'action/action_{unit}']['source_hash']
            env = UnityPy.load(archive.read('assets/bin/Data/' + source))
            asset = next(obj.read() for obj in env.objects if obj.type.name == 'TextAsset')
            plain = parse_table_container(asset.m_Script.encode('utf-8', 'surrogateescape'))['plain']
            # UnitActionInfo.ActionGroups (1), ActionGroup.ActionList (2).
            group = next(v.value for v in parse_message(plain)[0] if v.field == 1)
            transitions = []
            for entry in parse_message(group)[0]:
                if entry.field != 2:
                    continue
                fields = parse_message(entry.value)[0]
                from_id = next(v.value.decode('utf-8') for v in fields if v.field == action['ID'])
                for child in fields:
                    if child.field != action['ActionInterrupts']:
                        continue
                    values = {v.field: v.value for v in parse_message(child.value)[0]}
                    if values.get(interrupt['ActionID']) == b'W13000' and values.get(interrupt['CheckSkill']):
                        transitions.append({'from': from_id, 'to': 'W13000',
                                            'checked_skill': values.get(interrupt['SkillID'])})
            result[str(unit)] = {'source_hash': source, 'ultimate_transitions': transitions}
    assert any(t['checked_skill'] == 10057 for t in result['1303']['ultimate_transitions'])
    normal = {}
    for t in result['1003']['ultimate_transitions']:
        normal.setdefault(t['from'], set()).add(t['checked_skill'])
    corrected = [t['from'] for t in result['1303']['ultimate_transitions']
                 if t['checked_skill'] == 10057 and 10033 in normal.get(t['from'], set())]
    assert corrected, 'No matching ultimate transition correction found'
    result['corrected_call_sites'] = corrected
    target = ROOT / 'runtime/behemoth_trial_action_audit_20261012.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Ultimate transitions corrected from 10057 to 10033:', len(corrected))
    print('Evidence:', target)


if __name__ == '__main__':
    audit()
