#!/usr/bin/env python3
"""
Build and release automation for Sims 4 Mod Manager.

Usage:
    python build.py build          # Build executable locally
    python build.py bump patch     # Bump version (patch/minor/major)
    python build.py bump 1.2.3     # Set specific version
    python build.py release        # Bump patch, commit, tag, and push
    python build.py release minor  # Bump minor, commit, tag, and push
    python build.py release 2.0.0  # Set version, commit, tag, and push
"""

import re
import sys
import subprocess
from pathlib import Path

SCRIPT_FILE = Path(__file__).parent / "sims4_mod_manager.py"
VERSION_PATTERN = re.compile(r'^__version__ = ["\']([^"\']+)["\']', re.MULTILINE)


def get_version() -> str:
    """Get current version from script."""
    content = SCRIPT_FILE.read_text(encoding='utf-8')
    match = VERSION_PATTERN.search(content)
    if match:
        return match.group(1)
    raise ValueError("Could not find __version__ in script")


def set_version(new_version: str) -> None:
    """Set version in script."""
    content = SCRIPT_FILE.read_text(encoding='utf-8')
    new_content = VERSION_PATTERN.sub(f'__version__ = "{new_version}"', content)
    SCRIPT_FILE.write_text(new_content, encoding='utf-8')
    print(f"Updated version to {new_version}")


def bump_version(bump_type: str) -> str:
    """Bump version and return new version string."""
    current = get_version()
    parts = [int(x) for x in current.split('.')]

    # Pad to 3 parts if needed
    while len(parts) < 3:
        parts.append(0)

    if bump_type == 'major':
        parts = [parts[0] + 1, 0, 0]
    elif bump_type == 'minor':
        parts = [parts[0], parts[1] + 1, 0]
    elif bump_type == 'patch':
        parts = [parts[0], parts[1], parts[2] + 1]
    elif re.match(r'^\d+\.\d+\.\d+$', bump_type):
        # Specific version provided
        return bump_type
    else:
        raise ValueError(f"Invalid bump type: {bump_type}. Use major/minor/patch or X.Y.Z")

    return '.'.join(str(p) for p in parts)


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and print it."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def cmd_build():
    """Build executable locally."""
    print("Building executable...")
    run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '-q'])
    run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements-dev.txt', '-q'])
    run(['pyinstaller', 'sims4_mod_manager.spec', '--noconfirm'])

    exe_path = Path('dist/Sims4ModManager.exe')
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful!")
        print(f"  Output: {exe_path.absolute()}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print("\nBuild failed - executable not found")
        sys.exit(1)


def cmd_bump(bump_type: str = 'patch'):
    """Bump version number."""
    current = get_version()
    new_version = bump_version(bump_type)

    print(f"Current version: {current}")
    print(f"New version: {new_version}")

    confirm = input("Apply this version? (y/n): ").strip().lower()
    if confirm == 'y':
        set_version(new_version)
    else:
        print("Cancelled")


def cmd_release(bump_type: str = 'patch'):
    """Create a release: bump version, commit, tag, and push."""
    # Check for uncommitted changes (excluding version bump we're about to make)
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    if result.stdout.strip():
        print("Warning: You have uncommitted changes:")
        print(result.stdout)
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled")
            return

    # Bump version
    current = get_version()
    new_version = bump_version(bump_type)

    print(f"\nRelease plan:")
    print(f"  Current version: {current}")
    print(f"  New version: {new_version}")
    print(f"  Tag: v{new_version}")
    print(f"\nThis will:")
    print(f"  1. Update __version__ in sims4_mod_manager.py")
    print(f"  2. Commit the change")
    print(f"  3. Create tag v{new_version}")
    print(f"  4. Push commit and tag to origin")
    print(f"  5. GitHub Actions will build and create the release")

    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled")
        return

    # Update version
    set_version(new_version)

    # Git operations
    run(['git', 'add', 'sims4_mod_manager.py'])
    run(['git', 'commit', '-m', f'Bump version to {new_version}'])
    run(['git', 'tag', '-a', f'v{new_version}', '-m', f'Release v{new_version}'])
    run(['git', 'push'])
    run(['git', 'push', 'origin', f'v{new_version}'])

    print(f"\nRelease v{new_version} initiated!")
    print("GitHub Actions will now build and publish the release.")
    print("Check progress at: https://github.com/<your-repo>/actions")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"\nCurrent version: {get_version()}")
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == 'build':
        cmd_build()
    elif command == 'bump':
        bump_type = sys.argv[2] if len(sys.argv) > 2 else 'patch'
        cmd_bump(bump_type)
    elif command == 'release':
        bump_type = sys.argv[2] if len(sys.argv) > 2 else 'patch'
        cmd_release(bump_type)
    elif command == 'version':
        print(get_version())
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
