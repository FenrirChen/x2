"""Layer covenant and jewel patches onto a current APK, retaining prior changes.

The small intermediate ZIP is a build input for the jewel patch, never an APK
for installation. Final signing and installation are separate actions.
"""
import argparse
from collections import Counter
import hashlib
import json
import zipfile
from pathlib import Path

import patch_contract_chujiu as contract
import patch_jewel_pool_702 as jewel
from savemanager.client.supplement_reference_resources import assemble


def prepare(baseline, output):
    output.mkdir(parents=True, exist_ok=True)
    patches = contract.patch(baseline, contract.DEFAULT_ASSETS, output / 'contract')
    overlay = output / 'jewel_input.zip'
    entries = [jewel.GLOBAL, jewel.DRAW_PARAM, jewel.DRAW_RULES, jewel.GIFT]
    entries += [piece.entry for piece in jewel.PIECES]
    with zipfile.ZipFile(baseline) as original, zipfile.ZipFile(
            overlay, 'w', compression=zipfile.ZIP_DEFLATED) as derived:
        for entry in entries:
            name = jewel.DATA_PREFIX + entry
            derived.writestr(name, Path(patches[name]).read_bytes()
                             if name in patches else original.read(name))
        original_names = set(original.namelist())
    patches.update(jewel.patch(overlay, jewel.DEFAULT_ART_DIR, output / 'jewel'))
    plan = {'baseline': str(baseline.resolve()), 'images': [],
            'patches': {name: path for name, path in patches.items() if name in original_names},
            'additions': {name: path for name, path in patches.items() if name not in original_names}}
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(plan, indent=2), encoding='utf-8')
    return manifest


def validate(baseline, manifest, release, report):
    """Verify allowed native edits and retain every unrelated resource binding."""
    import UnityPy
    plan = json.loads(manifest.read_text(encoding='utf-8'))
    expected = {**plan['patches'], **plan['additions']}
    with zipfile.ZipFile(baseline) as old, zipfile.ZipFile(release) as new:
        original = {i.filename: i for i in old.infolist() if not i.filename.startswith('META-INF/')}
        current = {i.filename: i for i in new.infolist() if not i.filename.startswith('META-INF/')}
        assert len(new.namelist()) == len(set(new.namelist()))
        assert set(current) == set(original) | set(plan['additions'])
        for name, info in original.items():
            if name not in expected:
                assert (info.CRC, info.file_size) == (current[name].CRC, current[name].file_size), name
        for name, path in expected.items():
            assert new.read(name) == Path(path).read_bytes(), name
        before, after = old.read(contract.NATIVE), new.read(contract.NATIVE)
        assert len(before) == len(after)
        allowed = sorted([(contract.HOOK, contract.HOOK + 4),
                          (contract.PCT_SITE, contract.PCT_SITE + 4),
                          *[(p, p + 4) for p in contract.MARRIED_SITES],
                          (contract.NEW_CAVE, contract.ZERO_END)])
        assert before[contract.NEW_CAVE:contract.ZERO_END] == bytes(contract.ZERO_END - contract.NEW_CAVE)
        start = 0
        for lo, hi in allowed:
            assert before[start:lo] == after[start:lo], hex(lo)
            start = hi
        assert before[start:] == after[start:]
        a = next(iter(UnityPy.load(old.read(jewel.DATA_PREFIX + jewel.GLOBAL)).files.values()))
        b = next(iter(UnityPy.load(new.read(jewel.DATA_PREFIX + jewel.GLOBAL)).files.values()))
        for pid, obj in a.objects.items():
            if obj.type.name != 'ResourceManager':
                assert obj.get_raw_data() == b.objects[pid].get_raw_data(), pid
        def bindings(sf):
            tree = next(o for o in sf.objects.values() if o.type.name == 'ResourceManager').read_typetree()
            rows = tree['m_Container']
            return rows, Counter((key, value['m_FileID'], value['m_PathID']) for key, value in rows)
        _, prior = bindings(a)
        rows, now = bindings(b)
        assert [key for key, _ in rows] == sorted(key for key, _ in rows)
        assert [x.path for x in b.externals[:len(a.externals)]] == [x.path for x in a.externals]
        rebound = {'uialtas/altas/marryhead01', 'uialtas/heroicon_h/hero_icon_101004_h',
                   'uialtas/marrydrawing/marrydrawing_1221004', 'uialtas/drawing/jewel/baoshiji_2'}
        assert all(now[key] >= count for key, count in prior.items() if key[0] not in rebound)
        assert new.testzip() is None
    digest = hashlib.sha256()
    with release.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 << 20), b''):
            digest.update(chunk)
    result = {'apk': str(release), 'bytes': release.stat().st_size, 'sha256': digest.hexdigest(),
              'full_crc': 'passed', 'prior_native_patches_preserved': True,
              'unrelated_entries_and_bindings_preserved': True,
              'modified_entries': len(plan['patches']), 'new_entries': len(plan['additions'])}
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if args.baseline.resolve() == args.output.resolve():
        parser.error('output must differ from baseline')
    if args.validate_only:
        validate(args.baseline, args.work / 'manifest.json', args.output,
                 args.work / 'release_validation.json')
    else:
        plan = prepare(args.baseline, args.work)
        assemble(args.baseline, plan, args.output)
