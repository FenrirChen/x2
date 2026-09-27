"""Inventory external snapshots without modifying either source or current code."""

import hashlib
import json
from collections import Counter
from pathlib import Path


CURRENT = Path(__file__).resolve().parents[2]
PACKAGES = {
    "a": Path(r"D:\demo\x2\other\9.25 loadbyhoshi\9.25 loadbyhoshi"),
    "b": Path(r"D:\demo\x2\other\9.26 修复包\9.26 修复包"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_equivalent(relative):
    parts = relative.parts
    if parts[:3] == ("server", "src", "x2server"):
        return CURRENT.joinpath("src", "x2server", *parts[3:])
    if parts[:2] == ("server", "analysis"):
        return CURRENT.joinpath("analysis", *parts[2:])
    return None


def category(relative):
    parts = relative.parts
    if "save" in parts or any(p in ("runtime", "logs", "cache", "__pycache__") for p in parts):
        return "runtime_artifact"
    if relative.suffix.lower() in (".apk", ".dll", ".so", ".exe", ".sqlite3", ".db"):
        return "binary_or_database"
    if "test" in relative.name.lower():
        return "test"
    if relative.suffix == ".md" or "docs" in parts:
        return "document"
    if relative.suffix == ".json":
        return "data_or_config"
    if relative.suffix in (".py", ".sql"):
        return "code_or_schema"
    return "other"


for label, root in PACKAGES.items():
    if not root.is_dir():
        raise SystemExit(f"package absent: {root}")
    rows = []
    for source in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = source.relative_to(root)
        current = current_equivalent(rel)
        source_hash = digest(source)
        current_hash = digest(current) if current and current.is_file() else None
        rows.append({
            "path": rel.as_posix(), "size": source.stat().st_size,
            "sha256": source_hash, "category": category(rel),
            "current_equivalent": current.relative_to(CURRENT).as_posix() if current else None,
            "current_status": ("different" if current_hash and current_hash != source_hash else
                               "identical" if current_hash else "new_candidate" if current else
                               "no_direct_mapping"),
            "current_sha256": current_hash,
        })
    manifest = {"package": label.upper(), "root": str(root), "file_count": len(rows),
                "total_bytes": sum(row["size"] for row in rows), "files": rows,
                "deletion_intent": "not inferred from absent files in a snapshot"}
    output = Path(__file__).parent
    (output / f"package_{label}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_category = Counter(row["category"] for row in rows)
    by_status = Counter(row["current_status"] for row in rows)
    lines = [f"# Package {label.upper()} inventory", "",
             f"Source: `{root}`", "",
             f"Files inspected: {len(rows)}; bytes: {manifest['total_bytes']:,}.", "",
             "## Categories", ""]
    lines.extend(f"- {key}: {value}" for key, value in sorted(by_category.items()))
    lines.extend(["", "## Comparison with current workspace", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(by_status.items()))
    lines.extend(["", "Absence from this snapshot is not treated as a deletion request.",
                  "Runtime databases, logs, caches, binaries, and external documents are audit-only.",
                  "", "## Directly mapped code and data candidates", ""])
    lines.extend(f"- `{row['path']}` → `{row['current_equivalent']}` ({row['current_status']})"
                 for row in rows if row["current_equivalent"] and row["category"] not in
                 ("runtime_artifact", "binary_or_database"))
    (output / f"package_{label}_diff_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
