import hashlib,json,re,zipfile
from pathlib import Path
root=Path(__file__).resolve().parent
repo=Path('D:/demo/x2/x2_revive_workspace')
reviewed=['src/x2server/player/battle_entry.py','src/x2server/player/equipment.py',
          'src/x2server/player/battle_bonuses.py','src/x2server/player/drop_budget.py',
          'src/x2server/player/appearance.py','src/x2server/player/login.py',
          'src/x2server/messages/lobby.py']
source=json.loads((root/'source_manifest.json').read_text('utf8'))
source['server_source_sha256']={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in reviewed}
source['libil2cpp_sha256']=hashlib.sha256(Path('D:/demo/x2/apk/lib/arm64-v8a/libil2cpp.so').read_bytes()).hexdigest()
(root/'source_manifest.json').write_text(json.dumps(source,ensure_ascii=False,indent=2),'utf8')
links=re.findall(r'\]\(([^)]+)\)',(root/'REPORT.md').read_text('utf8'))
assert all((root/l).is_file() for l in links)
manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(root.rglob('*')) if p.is_file() and p.name!='FILE_SHA256.json'}
(root/'FILE_SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8')
archive=root.parent/'season-research-20261012.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(root.parent))
print('Verified report links:',len(links),'evidence files:',len(manifest)+1,'zip bytes:',archive.stat().st_size)
