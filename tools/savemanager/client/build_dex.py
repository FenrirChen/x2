"""Compile the save-manager Java classes to classes5.dex.

javac (against android.jar + the UnityPlayer compile stub) -> d8. The Unity
stub is excluded from the dex: the real class ships in the game's dex.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
ANDROID_JAR = Path(r"D:\Android\android-sdk\platforms\android-33\android.jar")
D8_JAR = HERE.parents[2].parent / ".runtime" / "build-tools" / "r8.jar"


def main() -> None:
    sources = [
        HERE / "java" / "com" / "siva" / "project" / "x2" / "SaveManagerBridge.java",
        HERE / "java" / "com" / "siva" / "project" / "x2" / "SaveManagerDialogFragment.java",
        HERE / "stubs" / "com" / "unity3d" / "player" / "UnityPlayer.java",
    ]
    classes_dir = BUILD / "classes"
    classes_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["javac", "-source", "8", "-target", "8", "-nowarn", "-g:none",
                    "-bootclasspath", str(ANDROID_JAR),
                    "-d", str(classes_dir),
                    *[str(s) for s in sources]], check=True)
    game_classes = sorted((classes_dir / "com" / "siva" / "project" / "x2").glob("*.class"))
    output_dir = BUILD
    result = subprocess.run(["java", "-cp", str(D8_JAR), "com.android.tools.r8.D8",
                             "--release", "--lib", str(ANDROID_JAR), "--min-api", "21",
                             "--output", str(output_dir),
                             *[str(c) for c in game_classes]],
                            capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit("d8 failed")
    (output_dir / "classes.dex").rename(output_dir / "classes5.dex")
    dex = output_dir / "classes5.dex"
    print(f"built {dex} ({dex.stat().st_size} bytes)")
    assert b"SaveManagerDialogFragment" in dex.read_bytes()


if __name__ == "__main__":
    main()
