"""Export activity fields and cross-check their tags against native Serialize."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT.parent
sys.path.insert(0, str(ASSETS / '.phase3_deps'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

OPERATIONS = (
    'SceneGlobalParam',
    'ExtraDropData',
    'QueryActivity', 'UpdateActivity', 'UpdateActivityConfig', 'QueryActivityMissionRecord',
    'ActivityMissionRecordSave', 'QueryShuangHanActivity', 'PlayShuangHanPV',
    'ActivityDialogue', 'ActivityDialogReciveInfo', 'ActivityShop', 'ActivityPreNoticInfo',
    'ActivityPreNotic', 'ActivityReissue', 'ActivityReissueState', 'ActivityRewardPoolInfo',
    'ActivityRewardPoolDraw', 'CafeStoreInfo', 'CafeStoreUnLock', 'CafeStorePositionSet',
    'CafeStoreCooking', 'CafeStoreLevelUp', 'CafeStoreReceiveRevenue', 'CafeStoreUpdate',
    'LanternShowQuestion', 'LanternShowAnswerQuestion', 'LanternShowPaper',
    'LanternShowQueryData', 'LanternShowRecBox', 'ActivityMissionData',
    'ActivityMissionSelBranch', 'QueryFoodMissionReward', 'ReceiveFoodMissionReward',
    'ActivityPassRecord', 'QueryActivityTower', 'ActivityTowerLevelUp',
    'ActivityTowerPassive', 'ActivityBuilding', 'ActivityBuildingUpgrade',
)


def main():
    dump = (ASSETS / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8')
    blocks = {m[1]: m[2] for m in re.finditer(
        r'// Namespace: CommandX2\npublic class (\w+) : IMessage[^\n]*\n\{(.*?)\n\}', dump, re.S)}
    ids = {m[1][1:]: int(m[2]) for m in re.finditer(
        r'public const ERequestTypes (E(?:C2L|L2C)_\w+) = (\d+);', dump)}
    methods = json.loads((ASSETS / 'tools/Il2CppDumper-bin/script.json').read_text())['ScriptMethod']
    by_name = {}
    for m in methods:
        by_name.setdefault(m['Name'], []).append(m['Address'])
    addresses = sorted({m['Address'] for m in methods})
    binary = (ASSETS / 'apk/lib/arm64-v8a/libil2cpp.so').read_bytes()
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    pending = [p + n for n in OPERATIONS for p in ('C2L_', 'L2C_') if p + n in blocks]
    schemas = {}
    while pending:
        name = pending.pop()
        if name in schemas:
            continue
        declared = re.findall(r'public ([\w<>., ]+) (\w+); // (0x\w+)', blocks[name])
        candidates = by_name.get('CommandX2.' + name + '$$Serialize', [])
        if not candidates:
            raise ValueError('Missing native serializer: ' + name)
        # Instance Serialize is a tiny trampoline; the larger overload is static.
        start = max(candidates, key=lambda a: next(v for v in addresses if v > a) - a)
        end = next(v for v in addresses if v > start)
        ins = list(decoder.disasm(binary[start:end], start))
        tags = []
        for i, op in enumerate(ins):
            if op.mnemonic != 'blr':
                continue
            window = ins[max(0, i - 10):i]
            if not any('#0x270]' in x.op_str for x in window):
                continue
            tag = next((int(m[1], 0) for x in reversed(window)
                        if (m := re.fullmatch(r'w1, #(0x[0-9a-f]+|\d+)', x.op_str))
                        and x.mnemonic == 'mov'), None)
            if tag is not None and tag >= 8 and tag not in tags:
                tags.append(tag)
        fields = []
        # All selected messages fit one-byte tags except ActivityData, whose
        # native contract is already independently maintained in lobby.py.
        expected = [(i << 3) | (2 if t == 'string'
                               or (t[5:-1] if t.startswith('List<') else t) in blocks else 0)
                    for i, (t, _, _) in enumerate(declared, 1)]
        verified = tags == expected
        if not verified and name != 'ActivityData' and declared:
            raise ValueError(f'Native tag order differs: {name}: {tags} vs {expected}')
        for i, (kind, field, offset) in enumerate(declared, 1):
            repeated = kind.startswith('List<')
            inner = kind[5:-1] if repeated else kind
            if inner in blocks:
                pending.append(inner)
            fields.append({'number': i, 'name': field, 'type': inner,
                           'repeated': repeated, 'native_offset': offset})
        schemas[name] = {'fields': fields, 'native_serialize': start,
                         'native_tags': tags, 'verified': verified or name == 'ActivityData'}
    target = ROOT / 'src/x2server/data/activity_wire.json'
    target.write_text(json.dumps({'ids': {n: ids[n] for n in schemas if n in ids},
                                 'schemas': schemas}, indent=2), encoding='utf-8')
    print('Verified schemas', len(schemas))


if __name__ == '__main__':
    main()
