"""Extract only canonical DP-related TextAssets selected by APK ResourceManager."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

TABLES = {"chapterinfo", "taskchapter", "taskcondition", "taskconditionline", "item", "language", "gift"}


def extract(apk, output):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".phase2_deps"))
    import UnityPy
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    with zipfile.ZipFile(apk) as archive:
        environment = UnityPy.load(archive.read("assets/bin/Data/globalgamemanagers"))
        serialized = next(iter(environment.files.values()))
        manager = next(o for o in environment.objects if o.type.name == "ResourceManager").read_typetree()
        for resource, pointer in manager["m_Container"]:
            if resource not in {"table/" + name for name in TABLES}:
                continue
            external = serialized.externals[pointer["m_FileID"] - 1].path
            asset = UnityPy.load(archive.read("assets/bin/Data/" + external))
            obj = next(o for o in asset.objects if o.path_id == pointer["m_PathID"])
            if obj.type.name != "TextAsset":
                raise ValueError("canonical table is not a TextAsset")
            data = obj.read()
            payload = data.m_Script
            if isinstance(payload, str):
                payload = payload.encode("utf-8", "surrogateescape")
            name = resource.split("/")[1]
            (output / (name + ".bytes")).write_bytes(payload)
            entries.append({"resource": resource, "external": external, "path_id": obj.path_id,
                "asset_name": data.m_Name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    if len(entries) != len(TABLES):
        raise ValueError("canonical DP resource missing")
    manifest = {"apk": str(apk.resolve()), "tables": entries}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, default=Path(__file__).resolve().parents[3] / "X2_Eclipse_v2_4.apk")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "analysis/dp_client/raw")
    args = parser.parse_args()
    print(json.dumps(extract(args.apk, args.output), ensure_ascii=False, indent=2))
