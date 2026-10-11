"""Repair async entry hitboxes and retained anniversary room display geometry.

The APK omits the six tower room models, but retains their Detour navigation
tiles. Generate display-only floor meshes from those polygons; never replace
navigation, collisions, spawn positions, routes, or section configuration.
"""
import copy
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import UnityPy
from phase3_protobuf import parse_message
from tools.savemanager.client.patch_activity_ui import branch, adrp, ldr
from tools.savemanager.client.patch_treasure_activity import entries, text_asset


def nav_floor(blob):
    """Read retained dtMeshHeader/vertices/dtPoly; ignore off-mesh connections."""
    assert blob[:4] == b'VAND' and struct.unpack_from('<i', blob, 4)[0] == 7
    poly_count, vertex_count = struct.unpack_from('<ii', blob, 24)
    vertices = [struct.unpack_from('<fff', blob, 100 + i * 12)
                for i in range(vertex_count)]
    triangles = []
    for i in range(poly_count):
        offset = 100 + vertex_count * 12 + i * 32
        count, area_type = struct.unpack_from('<BB', blob, offset + 30)
        if area_type >> 6:
            continue
        assert 3 <= count <= 6
        indices = struct.unpack_from('<6H', blob, offset + 4)[:count]
        assert max(indices) < vertex_count
        for j in range(1, count - 1):
            a, b, c = indices[0], indices[j], indices[j + 1]
            va, vb, vc = vertices[a], vertices[b], vertices[c]
            normal_y = ((vb[2] - va[2]) * (vc[0] - va[0])
                        - (vb[0] - va[0]) * (vc[2] - va[2]))
            triangles.extend((a, b, c) if normal_y >= 0 else (a, c, b))
    assert triangles
    return vertices, triangles


def clone(sf, source, tree):
    obj = copy.copy(source)
    obj.assets_file = sf
    obj.path_id = max(sf.objects) + 1
    # Objects copied from another file need their own serialized type.
    if source.assets_file is not sf:
        obj.serialized_type = copy.deepcopy(source.serialized_type)
        sf.types.append(obj.serialized_type)
        obj.type_id = len(sf.types) - 1
    obj.set_raw_data(source.get_raw_data())
    sf.objects[obj.path_id] = obj
    obj.save_typetree(tree)
    return obj


def pointer(pid):
    return {'m_FileID': 0, 'm_PathID': pid}


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    index = json.loads((ROOT / 'tools/savemanager/client/activity_resource_index.json').read_text())
    manifest, audit = {}, []
    with zipfile.ZipFile(apk) as z:
        native = bytearray(z.read('lib/arm64-v8a/libil2cpp.so'))
        # OnHandleActivitySync finishes by initializing fireworks. Preserve
        # that call and then recompute all world-space entry hitboxes.
        cave, hook = 0x42B0A00, 0x13DBC80
        assert native[hook:hook + 4] == struct.pack('<I', branch(hook, 0x13D97D0))
        words = [0xA9BF7BF3, 0xAA0003F3,
                 branch(cave + 8, 0x13D97D0, True), 0xAA1303E0,
                 0xA8C17BF3, branch(cave + 20, 0x13D45E0)]
        payload = struct.pack('<6I', *words)
        assert native[cave:cave + len(payload)] == bytes(len(payload))
        native[cave:cave + len(payload)] = payload
        native[hook:hook + 4] = struct.pack('<I', branch(hook, cave))
        # Decorative UI shaders use _A_tex and intentionally lack _MainTex.
        # Image's no-sprite path unconditionally reads Material.mainTexture;
        # guard just that read, allowing its existing white-texture fallback.
        texture_cave, texture_hook = 0x42B0A40, 0x2A56350
        assert native[texture_hook:texture_hook + 4] == struct.pack('<I', branch(texture_hook, 0x2B91F48, True))
        tw = [0xA9BF7BF3, 0xAA0003F3,
              adrp(8, texture_cave + 8, 0x5222310), ldr(8, 8, 0x310),
              0xB9400100, branch(texture_cave + 20, 0x3F2AED0, True),
              adrp(8, texture_cave + 24, 0x530FAB8), ldr(8, 8, 0xAB8), ldr(1, 8),
              0xAA1303E0, 0xAA1F03E2,
              branch(texture_cave + 44, 0x2B92B6C, True),
              0x340000C0,  # cbz w0, missing (instruction 18)
              0xAA1303E0, 0xAA1F03E1,
              branch(texture_cave + 60, 0x2B91F48, True),
              0xA8C17BF3, 0xD65F03C0,
              0xAA1F03E0, 0xA8C17BF3, 0xD65F03C0]
        texture_payload = struct.pack('<' + 'I' * len(tw), *tw)
        assert native[texture_cave:texture_cave + len(texture_payload)] == bytes(len(texture_payload))
        native[texture_cave:texture_cave + len(texture_payload)] = texture_payload
        native[texture_hook:texture_hook + 4] = struct.pack('<I', branch(texture_hook, texture_cave, True))
        target = output / 'libil2cpp.followup.so'
        target.write_bytes(native)
        audit.append({'hook': hex(hook), 'purpose': 'reposition hitboxes after async activity visibility update'})
        audit.append({'hook': hex(texture_hook), 'purpose': 'Image respects custom shader without _MainTex; keep normal textures unchanged'})

        for page, images in {'ui_anniversary_main': [652, 841],
                             'ui_anniversary_section': [386, 403],
                             'ui_anniversary_task': [843],
                             'ui_anniversary_poolshop': [962, 1144],
                             'ui_anniversary_tower_section': [490, 589]}.items():
            filename, _ = index['ui/' + page]
            sf = UnityPy.load(z.read('assets/bin/Data/' + filename)).file
            for pid in images:
                obj = sf.objects[pid]
                raw = bytearray(obj.get_raw_data())
                assert len(raw) == 292
                # Image.Type = Simple, and AdvancedImage.useSpriteMesh = false.
                # The retained CG sprite has zero UVs in its custom mesh;
                # simple rendering computes UVs from its texture rectangle.
                struct.pack_into('<i', raw, 208, 0)
                raw[244] = 0
                obj.set_raw_data(raw)
                go = struct.unpack_from('<q', raw, 4)[0]
                rect_obj = next(o for o in sf.objects.values() if o.type.name == 'RectTransform'
                                and o.read_typetree()['m_GameObject']['m_PathID'] == go)
                rect = rect_obj.read_typetree()
                if rect['m_AnchorMin'] == rect['m_AnchorMax']:
                    width, height = rect['m_SizeDelta']['x'], rect['m_SizeDelta']['y']
                    if width <= 0 or height <= 0:
                        width = width if width > 0 else 1336.
                        rect['m_SizeDelta'] = {'x': width, 'y': width * 752 / 1336}
                        rect_obj.save_typetree(rect)
                        audit.append({'page': page, 'image': pid, 'rect': rect['m_SizeDelta']})
            target = output / filename
            target.write_bytes(sf.save())
            manifest['assets/bin/Data/' + filename] = str(target.resolve())

        sf = UnityPy.load(z.read('assets/bin/Data/level5')).file
        original = {pid: o.get_raw_data() for pid, o in sf.objects.items()}
        shared = b''.join(z.read(f'assets/bin/Data/sharedassets5.assets.split{i}') for i in range(27))
        mesh_source = UnityPy.load(shared).file.objects[88]
        mesh_template = mesh_source.read_typetree()
        root_tid = 1004  # StandardCell: original visual room template root.
        root = sf.objects[root_tid].read_typetree()
        assert sf.objects[root['m_GameObject']['m_PathID']].read_typetree()['m_Name'] == 'StandardCell'
        logic = entries(text_asset(UnityPy.load(z.read('assets/bin/Data/7470463322250fa4092ed34864a317fe')))[2])
        for key, entry in logic.items():
            if not key.startswith(b'X2_byxy_tafang_'):
                continue
            name = key.decode()
            fields, _ = parse_message(entry)
            fields, _ = parse_message(next(f.value for f in fields if f.field == 2))
            vertices, triangles = nav_floor(next(f.value for f in fields if f.field == 9))
            mesh = copy.deepcopy(mesh_template)
            mesh['m_Name'] = name + '_nav_floor'
            mesh['m_IsReadable'] = mesh['m_KeepVertices'] = mesh['m_KeepIndices'] = True
            mesh['m_IndexBuffer'] = list(struct.pack('<' + 'H' * len(triangles), *triangles))
            vd = mesh['m_VertexData']
            vd['m_VertexCount'], vd['m_CurrentChannels'] = len(vertices), 155
            vd['m_DataSize'] = b''.join(struct.pack('<14f', x, y - .02, zz, 0, 1, 0,
                                                  x / 10, zz / 10, 0, 0, 1, 0, 0, -1)
                                        for x, y, zz in vertices)
            low = [min(v[i] for v in vertices) for i in range(3)]
            high = [max(v[i] for v in vertices) for i in range(3)]
            bounds = {'m_Center': dict(zip('xyz', [(a + b) / 2 for a, b in zip(low, high)])),
                      'm_Extent': dict(zip('xyz', [max((b - a) / 2, .1) for a, b in zip(low, high)]))}
            mesh['m_LocalAABB'] = bounds
            mesh['m_SubMeshes'] = [{'firstByte': 0, 'indexCount': len(triangles), 'topology': 0,
                                    'baseVertex': 0, 'firstVertex': 0, 'vertexCount': len(vertices),
                                    'localAABB': bounds}]
            mesh['m_BakedConvexCollisionMesh'] = []
            mesh['m_BakedTriangleCollisionMesh'] = []
            mesh_obj = clone(sf, mesh_source, mesh)
            go_tree = copy.deepcopy(sf.objects[10].read_typetree())
            go_tree['m_Name'], go_tree['m_IsActive'] = name, True
            go_tree['m_Component'] = []
            go = clone(sf, sf.objects[10], go_tree)
            transform = copy.deepcopy(sf.objects[765].read_typetree())
            transform['m_GameObject'] = pointer(go.path_id)
            transform['m_Father'] = pointer(root_tid)
            transform['m_LocalPosition'] = {'x': 2000., 'y': 0., 'z': 0.}
            tf = clone(sf, sf.objects[765], transform)
            renderer = copy.deepcopy(sf.objects[1712].read_typetree())
            renderer['m_GameObject'] = pointer(go.path_id)
            renderer['m_LightmapIndex'] = 65535
            renderer['m_LightmapTilingOffset'] = {'x': 1., 'y': 1., 'z': 0., 'w': 0.}
            renderer['m_CastShadows'] = 0
            mr = clone(sf, sf.objects[1712], renderer)
            mf = clone(sf, sf.objects[1734], {'m_GameObject': pointer(go.path_id), 'm_Mesh': pointer(mesh_obj.path_id)})
            go_tree['m_Component'] = [{'component': pointer(o.path_id)} for o in [tf, mf, mr]]
            go.save_typetree(go_tree)
            root['m_Children'].append(pointer(tf.path_id))
            audit.append({'room': name, 'vertices': len(vertices), 'triangles': len(triangles) // 3,
                          'display_only': True, 'source': 'original Detour navigation polygons'})
        sf.objects[root_tid].save_typetree(root)
        target = output / 'level5'
        target.write_bytes(sf.save())
        verify = UnityPy.load(target.read_bytes()).file
        for pid, raw in original.items():
            if pid != root_tid:
                assert verify.objects[pid].get_raw_data() == raw
        assert sum(o.type.name == 'GameObject' and o.read_typetree()['m_Name'].startswith('X2_byxy_tafang_')
                   for o in verify.objects.values()) == 6
        manifest['assets/bin/Data/level5'] = str(target.resolve())
    (output / 'patches.json').write_text(json.dumps(manifest, indent=2))
    (output / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Generated', len(manifest), 'resource fixes:', output)


if __name__ == '__main__':
    patch(sys.argv[1], Path(sys.argv[2]))
