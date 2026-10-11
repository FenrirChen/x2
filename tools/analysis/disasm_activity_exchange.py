"""Trace exchange rendering/purchase consumers before advertising new IDs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT.parent
sys.path.insert(0, str(ASSETS / '.phase3_deps'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

methods = json.loads((ASSETS / 'tools/Il2CppDumper-bin/script.json').read_text())['ScriptMethod']
names = {m['Address']: m['Name'] for m in methods}
addresses = sorted(names)
binary = (ASSETS / 'apk/lib/arm64-v8a/libil2cpp.so').read_bytes()
decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
selected = [m for m in methods if m['Name'] == 'ShopGood$$RefreshShopGoodData' or
            m['Name'].startswith('ShopModule$$') and any(w in m['Name'] for w in
                ('OnReceiveActivityShop', 'OnReceiveShopGoods', 'QurearyShopGood', 'BuyGood', 'OnChooseGood'))]
out, calls = [], {}
for m in selected:
    start = m['Address']
    end = next(v for v in addresses if v > start)
    out.append(f"\n=== {m['Name']} @ {start:#x} ===")
    called = []
    for op in decoder.disasm(binary[start:end], start):
        label = ''
        if op.mnemonic in ('bl', 'b') and op.op_str.startswith('#0x'):
            label = names.get(int(op.op_str[1:], 16), '')
            if label:
                called.append(label)
        out.append(f'{op.address:x} {op.mnemonic} {op.op_str} ; {label}')
    calls[m['Name']] = called
(ROOT / 'runtime/activity_exchange_disasm.txt').write_text('\n'.join(out), encoding='utf8')
print(json.dumps(calls, ensure_ascii=False, indent=2))
