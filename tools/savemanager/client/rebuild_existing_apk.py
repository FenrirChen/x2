"""Apply explicit native/resource patches to an existing SaveManager APK.

Do not append the bridge or DEX again, and do not depend on an old release
baseline being present. Signing remains a separate release-signing step.
"""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('native', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    assert args.baseline.resolve() != args.output.resolve()
    sys.argv = [sys.argv[0], str(args.native), str(args.output), str(args.manifest)]
    import build_apk_savemanager as build
    build.TARGET_BASELINE = str(args.baseline)
    build.NEW_ENTRIES = []
    build.TEXT_PATCHES = {}
    build.main()


if __name__ == '__main__':
    main()
