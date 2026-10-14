"""Build native macOS .app, .pkg and .dmg, then perform a small-sample check."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "CausalStudio"
IDENTIFIER = "io.causalstudio.desktop"
MINIMUM_MACOS = "15.0"
METADATA = ("numpy", "pandas", "scipy", "causal-learn", "tigramite", "lingam",
            "PySide6-Essentials", "shiboken6", "openpyxl", "numba", "dcor", "scikit-learn", "array-api-compat")


def command(args, **kwargs):
    print("Running:", " ".join(str(x) for x in args), flush=True)
    return subprocess.run([str(x) for x in args], check=True, cwd=ROOT, **kwargs)


def build(arch):
    if sys.platform != "darwin":
        raise SystemExit("A real macOS host is required to build the application and installer.")
    if platform.machine() != arch:
        raise SystemExit(f"Use a native {arch} macOS runner; current interpreter is {platform.machine()}.")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12 to match the pinned scientific dependencies.")
    for tool in ("codesign", "pkgbuild", "hdiutil", "ditto", "lipo"):
        if not shutil.which(tool):
            raise SystemExit(f"Required macOS tool missing: {tool}")
    version = (ROOT / "causal_studio/__init__.py").read_text().split('"')[1]
    dist = ROOT / "dist/macos" / arch
    work = ROOT / "build/macos" / arch
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(work / "cache")
    env["MPLCONFIGDIR"] = str(work / "matplotlib")
    env["MACOSX_DEPLOYMENT_TARGET"] = MINIMUM_MACOS
    args = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--noupx",
            "--windowed", "--onedir", "--name", APP_NAME, "--distpath", dist,
            "--workpath", work / "work", "--specpath", work,
            "--target-architecture", arch, "--osx-bundle-identifier", IDENTIFIER,
            "--additional-hooks-dir", ROOT / "packaging/hooks",
            "--runtime-hook", ROOT / "packaging/runtime_macos.py"]
    for module in ("causallearn", "tigramite", "lingam", "dcor"):
        args += ["--collect-all", module]
    for name in METADATA:
        args += ["--copy-metadata", name]
    for module in ("PySide6.QtQml", "PySide6.QtQuick", "IPython", "pytest", "__main__"):
        args += ["--exclude-module", module]
    identity = os.environ.get("MACOS_CODESIGN_IDENTITY")
    if identity:
        args += ["--codesign-identity", identity]
    args += [str(ROOT / "launch.py")]
    command(args, env=env)
    app = dist / (APP_NAME + ".app")
    resources = app / "Contents/Resources"
    executable = app / "Contents/MacOS" / APP_NAME
    if not executable.is_file():
        raise SystemExit("PyInstaller did not produce the expected macOS executable.")
    actual = subprocess.check_output(["lipo", "-archs", str(executable)], text=True).strip().split()
    if actual != [arch]:
        raise SystemExit(f"Unexpected binary architecture: {actual}")
    info_path = app / "Contents/Info.plist"
    with info_path.open("rb") as handle:
        info = plistlib.load(handle)
    info.update(CFBundleName="Causal Studio", CFBundleDisplayName="Causal Studio",
                CFBundleShortVersionString=version, CFBundleVersion=version,
                LSMinimumSystemVersion=MINIMUM_MACOS, NSHighResolutionCapable=True)
    with info_path.open("wb") as handle:
        plistlib.dump(info, handle)
    shutil.copy2(ROOT / "MACOS.md", resources / "MACOS.md")
    shutil.copy2(ROOT / "README.md", resources / "README.md")
    shutil.copytree(ROOT / "examples", resources / "examples", dirs_exist_ok=True)
    sign = ["codesign", "--force", "--sign", identity or "-"]
    if identity:
        sign += ["--options", "runtime", "--timestamp"]
    command(sign + [app])
    command(["codesign", "--verify", "--deep", "--strict", app])
    smoke_output = ROOT / "output/macos-smoke" / arch
    smoke_env = env.copy()
    smoke_env["QT_QPA_PLATFORM"] = "offscreen"
    command([executable, "--smoke-test", smoke_output], env=smoke_env, timeout=300)
    smoke = json.loads((smoke_output / "smoke.json").read_text(encoding="utf-8"))
    if not smoke["ok"] or smoke["rows"] != 100 or smoke["variables"] != 5:
        raise SystemExit("The packaged small-sample desktop check failed.")
    prefix = f"CausalStudio-{version}-macOS-{arch}"
    installer = dist / (prefix + ".pkg")
    installer_identity = os.environ.get("MACOS_INSTALLER_IDENTITY")
    with tempfile.TemporaryDirectory(prefix="installer-", dir=work) as temporary:
        temporary = Path(temporary)
        components = temporary / "components.plist"
        # Analyze an isolated root containing only the .app (not PyInstaller's
        # duplicate onedir output) to keep installer metadata unambiguous.
        staging = temporary / "pkg-root/Applications"
        staging.mkdir(parents=True)
        command(["ditto", app, staging / app.name])
        command(["pkgbuild", "--analyze", "--root", temporary / "pkg-root", components])
        with components.open("rb") as handle:
            entries = plistlib.load(handle)
        for entry in entries:
            entry["BundleIsRelocatable"] = False
            entry["BundleIsVersionChecked"] = True
        with components.open("wb") as handle:
            plistlib.dump(entries, handle)
        pkg = ["pkgbuild", "--root", temporary / "pkg-root", "--component-plist", components,
               "--identifier", IDENTIFIER, "--version", version, "--install-location", "/",
               "--ownership", "recommended"]
        if installer_identity:
            pkg += ["--sign", installer_identity, "--timestamp"]
        command(pkg + [installer])
        dmg_root = temporary / "dmg-root"
        dmg_root.mkdir()
        command(["ditto", app, dmg_root / app.name])
        (dmg_root / "Applications").symlink_to("/Applications")
        shutil.copy2(ROOT / "MACOS.md", dmg_root / "安装说明.md")
        disk_image = dist / (prefix + ".dmg")
        command(["hdiutil", "create", "-ov", "-format", "UDZO", "-fs", "HFS+",
                 "-volname", "Causal Studio", "-srcfolder", dmg_root, disk_image])
    profile = os.environ.get("MACOS_NOTARY_PROFILE")
    if profile:
        if not identity or not installer_identity:
            raise SystemExit("Notarization requires Developer ID application and installer identities.")
        for artifact in (installer, disk_image):
            command(["xcrun", "notarytool", "submit", artifact, "--keychain-profile", profile, "--wait"])
            command(["xcrun", "stapler", "staple", artifact])
    manifest = {"version": version, "architecture": arch, "minimum_macos": MINIMUM_MACOS,
                "signed_with_developer_id": bool(identity), "notarized": bool(profile),
                "small_sample_check": smoke, "files": {}}
    for artifact in (installer, disk_image):
        digest = hashlib.sha256()
        with artifact.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        manifest["files"][artifact.name] = {"bytes": artifact.stat().st_size, "sha256": digest.hexdigest()}
    (dist / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("macOS installers ready:", installer, disk_image, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", choices=("arm64", "x86_64"), default=platform.machine())
    options = parser.parse_args()
    build(options.arch)
