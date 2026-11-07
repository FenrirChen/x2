"""The resource assembler preserves compressed streams and aligns stored media."""
import json
import zipfile
import struct

import pytest

from tools.savemanager.client.supplement_reference_resources import assemble


@pytest.mark.parametrize('padding', range(4))
def test_archive_preserves_unrelated_entries_and_aligns_media(tmp_path, padding):
    baseline, result = tmp_path/'old.apk', tmp_path/'new.apk'
    unchanged = {'lib/example.so': b'unchanged code'*100,
                 'assets/'+'x'*padding+'image': b'stored image',
                 'classes.dex': bytes(range(256))}
    with zipfile.ZipFile(baseline, 'w') as z:
        for name, payload in unchanged.items():
            z.writestr(name, payload, compress_type=zipfile.ZIP_STORED)
        z.writestr('assets/ui', b'old resource', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('META-INF/OLD.SF', b'obsolete signature')
    image, movie = tmp_path/'image', tmp_path/'movie'
    image.write_bytes(b'new resource')
    movie.write_bytes(b'movie data'*100)
    manifest = tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'patches': {'assets/ui': str(image)},
        'additions': {'assets/Video/loop.mp4': str(movie)}}))
    assemble(baseline, manifest, result)
    with zipfile.ZipFile(result) as z, result.open('rb') as f:
        assert 'META-INF/OLD.SF' not in z.namelist()
        assert z.testzip() is None
        for name, payload in unchanged.items():
            assert z.read(name) == payload
        assert z.read('assets/ui') == b'new resource'
        assert z.read('assets/Video/loop.mp4') == movie.read_bytes()
        assert z.getinfo('assets/Video/loop.mp4').compress_type == zipfile.ZIP_STORED
        for info in z.infolist():
            if info.compress_type == 0:
                f.seek(info.header_offset)
                n, e = struct.unpack_from('<HH', f.read(30), 26)
                assert (info.header_offset+30+n+e) % 4 == 0


def test_assembler_rejects_added_entry_colliding_with_baseline(tmp_path):
    baseline=tmp_path/'old.apk'
    with zipfile.ZipFile(baseline,'w') as z:
        z.writestr('same',b'original')
    file=tmp_path/'payload';file.write_bytes(b'replacement')
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'patches':{},'additions':{'same':str(file)}}))
    with pytest.raises(AssertionError,match='already exists'):
        assemble(baseline,manifest,tmp_path/'out.apk')
