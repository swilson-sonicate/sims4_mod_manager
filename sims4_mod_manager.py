#!/usr/bin/env python3
"""
Sims 4 Mod Manager & Update Checker
====================================
A tool to help manage, track, and check for updates to your Sims 4 mods.

Features:
- Scans your Mods folder and catalogs all mods
- Tracks mod metadata (source, version, date added)
- Detects potentially broken mods after game updates
- Checks ModTheSims for updates (for mods from that site)
- Simple command-line interface
- Automatic self-updates from GitHub Releases

Usage:
    python sims4_mod_manager.py

Requirements:
    pip install requests beautifulsoup4
"""

__version__ = "1.0.0"

import os
import sys
import json
import hashlib
import fnmatch
import zipfile
import marshal
import requests
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import re
import shutil
import tempfile
import subprocess

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("Note: Install beautifulsoup4 for web scraping features: pip install beautifulsoup4")


# ============================================================================
# AUTO UPDATER
# ============================================================================

class AutoUpdater:
    """Handles automatic updates from GitHub Releases."""

    # TODO: Set this to your GitHub repository (e.g., "username/sims4_mod_manager")
    GITHUB_REPO = "shawnplusplus/sims4_mod_manager"
    GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"
    UPDATE_CHECK_TIMEOUT = 5  # seconds

    def __init__(self):
        self.is_frozen = getattr(sys, 'frozen', False)
        self.executable_path = Path(sys.executable if self.is_frozen else __file__).resolve()

    def check_for_update(self) -> Optional[dict]:
        """Check GitHub for a newer release.

        Returns release info dict if update available, None otherwise.
        """
        try:
            import requests
            url = self.GITHUB_API_URL.format(repo=self.GITHUB_REPO)
            response = requests.get(url, timeout=self.UPDATE_CHECK_TIMEOUT)
            response.raise_for_status()

            release = response.json()
            remote_version = release.get('tag_name', '').lstrip('v')

            if self._is_newer_version(remote_version, __version__):
                return {
                    'version': remote_version,
                    'tag_name': release.get('tag_name'),
                    'name': release.get('name'),
                    'body': release.get('body', ''),
                    'html_url': release.get('html_url'),
                    'assets': release.get('assets', []),
                    'published_at': release.get('published_at')
                }
            return None
        except Exception as e:
            # Silently fail - don't interrupt startup for update check failures
            return None

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings. Returns True if remote is newer."""
        try:
            def parse_version(v: str) -> list:
                return [int(x) for x in v.split('.')]

            remote_parts = parse_version(remote)
            local_parts = parse_version(local)

            # Pad to same length
            max_len = max(len(remote_parts), len(local_parts))
            remote_parts += [0] * (max_len - len(remote_parts))
            local_parts += [0] * (max_len - len(local_parts))

            return remote_parts > local_parts
        except (ValueError, AttributeError):
            return False

    def download_and_update(self, release_info: dict) -> bool:
        """Download new version and schedule update.

        Returns True if update was scheduled successfully.
        """
        if not self.is_frozen:
            print("Auto-update is only available for the compiled executable.")
            print(f"Please download the new version manually from:")
            print(f"  {release_info.get('html_url', 'GitHub Releases')}")
            return False

        # Find the .exe asset
        exe_asset = None
        for asset in release_info.get('assets', []):
            if asset.get('name', '').endswith('.exe'):
                exe_asset = asset
                break

        if not exe_asset:
            print("Could not find executable in release assets.")
            print(f"Please download manually from: {release_info.get('html_url')}")
            return False

        try:
            import requests
            download_url = exe_asset.get('browser_download_url')
            asset_name = exe_asset.get('name')

            print(f"\nDownloading {asset_name}...")

            # Download to temp file with progress
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            # Create temp file in same directory as executable (to ensure same filesystem)
            temp_path = self.executable_path.parent / f"_update_{asset_name}"

            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        print(f"\rDownloading: {pct:.1f}%", end='', flush=True)

            print("\nDownload complete!")

            # Create batch script to replace executable after this process exits
            batch_path = self.executable_path.parent / "_updater.bat"
            with open(batch_path, 'w') as f:
                f.write('@echo off\n')
                f.write('echo Updating Sims 4 Mod Manager...\n')
                f.write('timeout /t 2 /nobreak >nul\n')  # Wait for process to exit
                f.write(f'del "{self.executable_path}"\n')
                f.write(f'move "{temp_path}" "{self.executable_path}"\n')
                f.write(f'echo Update complete! Starting new version...\n')
                f.write(f'start "" "{self.executable_path}"\n')
                f.write(f'del "%~f0"\n')  # Delete the batch file itself

            print("Update scheduled. The application will restart with the new version.")

            # Launch the batch script and exit
            subprocess.Popen(
                ['cmd', '/c', str(batch_path)],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )

            return True

        except Exception as e:
            print(f"\nUpdate failed: {e}")
            print(f"Please download manually from: {release_info.get('html_url')}")
            return False

    def prompt_and_update(self) -> bool:
        """Check for updates and prompt user to install.

        Returns True if user chose to update (app should exit).
        """
        print(f"Sims 4 Mod Manager v{__version__}")
        print("Checking for updates...", end=' ', flush=True)

        release_info = self.check_for_update()

        if release_info is None:
            print("You have the latest version.")
            return False

        print(f"\n\n🎉 New version available: v{release_info['version']}")
        if release_info.get('name'):
            print(f"   {release_info['name']}")

        # Show brief changelog if available
        body = release_info.get('body', '').strip()
        if body:
            # Show first few lines of changelog
            lines = body.split('\n')[:5]
            print("\nChangelog:")
            for line in lines:
                print(f"   {line}")
            if len(body.split('\n')) > 5:
                print("   ...")

        print()
        choice = input("Update now? (y/n): ").strip().lower()

        if choice == 'y':
            if self.download_and_update(release_info):
                return True  # Signal to exit
        else:
            print("Update skipped. Continuing with current version.\n")

        return False


# ============================================================================
# CONFIGURATION - Edit these paths if needed!
# ============================================================================

def get_default_mods_path() -> Path:
    """Get the default Sims 4 Mods folder path based on OS."""
    home = Path.home()
    
    # Windows
    if sys.platform == 'win32':
        return home / "Documents" / "Electronic Arts" / "The Sims 4" / "Mods"
    # macOS
    elif sys.platform == 'darwin':
        return home / "Documents" / "Electronic Arts" / "The Sims 4" / "Mods"
    # Linux (with Wine/Proton)
    else:
        # Common Wine path
        wine_path = home / ".wine" / "drive_c" / "users" / os.getlogin() / "Documents" / "Electronic Arts" / "The Sims 4" / "Mods"
        if wine_path.exists():
            return wine_path
        # Proton path (Steam)
        return home / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / "1222670" / "pfx" / "drive_c" / "users" / "steamuser" / "Documents" / "Electronic Arts" / "The Sims 4" / "Mods"


# ============================================================================
# MOD DATABASE
# ============================================================================

class ModDatabase:
    """Manages the local database of tracked mods."""
    
    def __init__(self, mods_path: Path):
        self.mods_path = mods_path
        self.db_path = mods_path / "_mod_manager_data.json"
        self.data = self._load()
    
    def _load(self) -> dict:
        """Load the database from disk."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("Warning: Database corrupted, creating new one.")
        
        return {
            "mods": {},
            "last_game_update": None,
            "settings": {
                "auto_backup": True,
                "check_interval_days": 7
            }
        }
    
    def save(self):
        """Save the database to disk."""
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, default=str)
    
    def get_mod(self, file_hash: str) -> Optional[dict]:
        """Get mod info by file hash."""
        return self.data["mods"].get(file_hash)
    
    def add_mod(self, file_hash: str, mod_info: dict):
        """Add or update a mod in the database."""
        self.data["mods"][file_hash] = mod_info
        self.save()
    
    def remove_mod(self, file_hash: str):
        """Remove a mod from the database."""
        if file_hash in self.data["mods"]:
            del self.data["mods"][file_hash]
            self.save()
    
    def mark_game_updated(self):
        """Mark that the game was recently updated."""
        self.data["last_game_update"] = datetime.now().isoformat()
        self.save()


# ============================================================================
# MOD SCANNER
# ============================================================================

class ModScanner:
    """Scans the Mods folder and identifies mod files."""

    MOD_EXTENSIONS = {'.package', '.ts4script'}

    # Patterns to find version in filename or content
    VERSION_PATTERNS = [
        # Year-based versioning: "_2025_7_0" or "_2025.7.0" (MCCC style)
        re.compile(r'[_\-\s](20\d{2}[_\.]\d+[_\.]\d+)(?:[_\-\s\.]|$)'),
        # Semantic versioning: "_1.2.3" or "_v1.2.3"
        re.compile(r'[_\-\s][Vv]?(\d+\.\d+(?:\.\d+)*[a-zA-Z]?)(?:[_\-\s\.]|$)'),
        # Simple v + number: "_v58" or " v58" (WonderfulWhims style)
        re.compile(r'[_\-\s][Vv](\d+)(?:[_\-\s\.]|$)'),
        # Just numbers with dots
        re.compile(r'[_\-\s](\d+\.\d+(?:\.\d+)*)(?:[_\-\s\.]|$)'),
    ]

    # Patterns to find version in Python/text content (binary patterns for searching in files)
    CONTENT_VERSION_PATTERNS = [
        re.compile(rb'__version__\s*=\s*["\']([^"\']+)["\']'),
        re.compile(rb'VERSION\s*=\s*["\']([^"\']+)["\']'),
        re.compile(rb'MOD_VERSION\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(rb'mod_version\s*=\s*["\']([^"\']+)["\']'),
        re.compile(rb'current_version\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(rb'version\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
        re.compile(rb'["\']version["\']\s*:\s*["\']([^"\']+)["\']'),  # JSON style
        # Version in comments or docstrings
        re.compile(rb'[Vv]ersion[:\s]+(\d+(?:\.\d+)*(?:[a-zA-Z])?)'),
        re.compile(rb'[Vv](\d+)[\s\r\n]'),  # Simple "v58" style
        # Year-based version
        re.compile(rb'(20\d{2}\.\d+\.\d+)'),
    ]

    # Simple patterns for raw binary search (version numbers as string literals in bytecode)
    # In .pyc files, short strings are stored with a length prefix like \xda\x02 for 2-char ASCII
    RAW_VERSION_PATTERNS = [
        # Short ASCII string in marshal format: \xda + length + string
        re.compile(rb'\xda\x02(\d\d)'),  # 2-digit version like "58"
        re.compile(rb'\xda\x03(\d\d\d)'),  # 3-digit version
        re.compile(rb'\xda[\x05-\x0b](\d+\.\d+\.\d+)'),  # Semantic version like "1.2.3"
        re.compile(rb'\xda[\x08-\x0c](20\d{2}\.\d+\.\d+)'),  # Year-based like "2025.7.0"
        # Unicode string format: \xf5 + length bytes
        re.compile(rb'\xf5.{1,2}(\d\d)\x00'),  # 2-digit in unicode
        # Just raw string occurrences
        re.compile(rb'(?:version|VERSION|Version).{0,10}?(\d+\.\d+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(rb'(?:version|VERSION|Version).{0,10}?["\'](\d+)["\']', re.IGNORECASE),
    ]
    
    def __init__(self, mods_path: Path):
        self.mods_path = mods_path
    
    def scan(self) -> list[dict]:
        """Scan the mods folder and return info about all mods."""
        mods = []
        
        if not self.mods_path.exists():
            print(f"Error: Mods folder not found at {self.mods_path}")
            return mods
        
        for file_path in self.mods_path.rglob('*'):
            if file_path.suffix.lower() in self.MOD_EXTENSIONS:
                # Skip the database file
                if file_path.name.startswith('_mod_manager'):
                    continue
                
                mod_info = self._get_mod_info(file_path)
                mods.append(mod_info)
        
        return mods
    
    def _get_mod_info(self, file_path: Path) -> dict:
        """Extract information about a mod file."""
        stat = file_path.stat()
        is_script = file_path.suffix.lower() == '.ts4script'

        # Try to extract version
        version = self._extract_version(file_path, is_script)

        return {
            "name": file_path.stem,
            "filename": file_path.name,
            "path": str(file_path.relative_to(self.mods_path)),
            "full_path": str(file_path),
            "extension": file_path.suffix.lower(),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified_date": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "hash": self._get_file_hash(file_path),
            "is_script": is_script,
            "subfolder": str(file_path.parent.relative_to(self.mods_path)) if file_path.parent != self.mods_path else None,
            "local_version": version
        }

    def _extract_version(self, file_path: Path, is_script: bool) -> Optional[str]:
        """Try to extract version from a mod file."""
        # First try filename
        version = self._version_from_filename(file_path.stem)
        if version:
            return version

        # For script mods, try to look inside the ZIP
        if is_script:
            version = self._version_from_ts4script(file_path)
            if version:
                return version

        return None

    def _version_from_filename(self, filename: str) -> Optional[str]:
        """Extract version number from filename."""
        for pattern in self.VERSION_PATTERNS:
            match = pattern.search(filename)
            if match:
                return match.group(1)
        return None

    def _version_from_pyc(self, pyc_data: bytes) -> Optional[str]:
        """Extract version from compiled Python (.pyc) file by reading constants."""
        try:
            # .pyc files have a header (size varies by Python version)
            # Try different header sizes (16 bytes for Python 3.7+, 12 for 3.6, 8 for older)
            for header_size in [16, 12, 8]:
                if len(pyc_data) <= header_size:
                    continue
                try:
                    code = marshal.loads(pyc_data[header_size:])
                    version = self._find_version_in_code(code)
                    if version:
                        return version
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _version_from_pyc_aggressive(self, pyc_data: bytes) -> Optional[str]:
        """Extract version from .pyc file more aggressively, including integer constants.

        Used specifically for files with 'version' in their name where we're more
        confident that integer constants represent version numbers.
        """
        try:
            for header_size in [16, 12, 8]:
                if len(pyc_data) <= header_size:
                    continue
                try:
                    code = marshal.loads(pyc_data[header_size:])
                    version = self._find_version_in_code_aggressive(code)
                    if version:
                        return version
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _find_version_in_code_aggressive(self, code: Any, depth: int = 0) -> Optional[str]:
        """Search code object for version, including integer constants.

        More aggressive than _find_version_in_code - used for files specifically
        named with 'version' where integers are more likely to be version numbers.
        """
        if depth > 3:
            return None

        try:
            if hasattr(code, 'co_consts'):
                # Collect ALL candidates first, then pick the best one
                string_candidates = []
                int_candidates = []
                year_based_candidates = []  # Like "2025.7.0"

                for const in code.co_consts:
                    if isinstance(const, str):
                        # Year-based version like "2025.7.0" - highest priority
                        if re.match(r'^20\d{2}\.\d+\.\d+$', const):
                            year_based_candidates.append(const)
                        # Simple digit string like "58"
                        elif re.match(r'^\d+$', const) and 2 <= len(const) <= 3:
                            num = int(const)
                            # Exclude common non-version numbers
                            excluded = {16, 32, 64, 128, 100, 200, 255, 256, 512, 24, 48, 96, 192, 384, 768}
                            if 10 <= num <= 999 and num not in excluded:
                                string_candidates.append(const)
                        # Semantic version like "1.2.3"
                        elif re.match(r'^\d+\.\d+\.\d+$', const):
                            string_candidates.append(const)

                    # Collect integer candidates
                    elif isinstance(const, int) and 10 <= const <= 999:
                        # Exclude common non-version numbers (powers of 2, alignment values, etc.)
                        excluded = {16, 32, 64, 128, 100, 200, 255, 256, 512, 24, 48, 96, 192, 384, 768}
                        if const not in excluded:
                            int_candidates.append(const)

                    # Recurse into nested code objects
                    elif hasattr(const, 'co_consts'):
                        result = self._find_version_in_code_aggressive(const, depth + 1)
                        if result:
                            # Check if it's year-based
                            if re.match(r'^20\d{2}\.\d+\.\d+$', result):
                                year_based_candidates.append(result)
                            else:
                                string_candidates.append(result)

                # Priority 1: Year-based versions (MCCC style) - return highest
                if year_based_candidates:
                    year_based_candidates.sort(reverse=True)
                    return year_based_candidates[0]

                # Priority 2: Check for version variable names and associated values
                if hasattr(code, 'co_names'):
                    names = list(code.co_names) if hasattr(code.co_names, '__iter__') else []
                    version_var_found = False
                    for name in names:
                        name_lower = name.lower() if isinstance(name, str) else ''
                        if 'version' in name_lower:
                            version_var_found = True
                            break

                    # If version variable exists, prefer 2-digit numbers, then highest in range
                    if version_var_found and int_candidates:
                        # Separate 2-digit and 3-digit candidates
                        two_digit = [n for n in int_candidates if 10 <= n <= 99]
                        three_digit = [n for n in int_candidates if 100 <= n <= 999]
                        if two_digit:
                            return str(max(two_digit))
                        elif three_digit:
                            return str(max(three_digit))

                # Priority 3: String versions that look like numbers
                # Prefer 2-digit numbers (10-99) over 3-digit, as most mods don't reach v100+
                if string_candidates:
                    def sort_key(s):
                        try:
                            num = int(s)
                            # 2-digit numbers are most likely version numbers
                            if 10 <= num <= 99:
                                return (0, -num)  # Highest 2-digit first
                            elif 100 <= num <= 999:
                                return (1, -num)  # Then 3-digit
                            else:
                                return (2, -num)
                        except ValueError:
                            return (3, 0)
                    string_candidates.sort(key=sort_key)
                    return string_candidates[0]

                # Priority 4: Integer candidates (prefer 2-digit over 3-digit)
                if int_candidates:
                    def version_score(n: int) -> tuple:
                        if 10 <= n <= 99:
                            return (0, -n)  # Most likely, higher is better
                        elif 100 <= n <= 999:
                            return (1, -n)
                        else:
                            return (2, -n)

                    int_candidates.sort(key=version_score)
                    return str(int_candidates[0])

        except Exception:
            pass

        return None

    def _debug_pyc_extraction(self, pyc_data: bytes):
        """Debug helper to show what version candidates are found in a .pyc file."""
        print(f"      --- Debug .pyc extraction ---")
        try:
            for header_size in [16, 12, 8]:
                if len(pyc_data) <= header_size:
                    continue
                try:
                    code = marshal.loads(pyc_data[header_size:])
                    self._debug_code_constants(code, depth=0)
                    break
                except Exception as e:
                    print(f"      Header {header_size}: marshal failed - {e}")
        except Exception as e:
            print(f"      Debug failed: {e}")

    def _debug_code_constants(self, code: Any, depth: int = 0):
        """Debug helper to show constants in a code object."""
        if depth > 2:
            return

        prefix = "      " + "  " * depth

        if hasattr(code, 'co_consts'):
            year_based = []
            string_nums = []
            int_nums = []

            excluded = {16, 32, 64, 128, 100, 200, 255, 256, 512, 24, 48, 96, 192, 384, 768}

            for const in code.co_consts:
                if isinstance(const, str):
                    if re.match(r'^20\d{2}\.\d+\.\d+$', const):
                        year_based.append(const)
                    elif re.match(r'^\d+$', const) and 2 <= len(const) <= 3:
                        num = int(const)
                        if 10 <= num <= 999 and num not in excluded:
                            string_nums.append(const)
                elif isinstance(const, int) and 10 <= const <= 999:
                    if const not in excluded:
                        int_nums.append(const)
                elif hasattr(const, 'co_consts'):
                    self._debug_code_constants(const, depth + 1)

            if year_based:
                print(f"{prefix}Year-based strings: {year_based}")
            if string_nums:
                print(f"{prefix}Numeric strings: {sorted(string_nums, key=lambda x: int(x))}")
            if int_nums:
                print(f"{prefix}Integer constants: {sorted(int_nums)}")

            # Check for version variable names
            if hasattr(code, 'co_names'):
                version_names = [n for n in code.co_names if isinstance(n, str) and 'version' in n.lower()]
                if version_names:
                    print(f"{prefix}Version-related names: {version_names}")

    def _find_version_in_code(self, code: Any, depth: int = 0) -> Optional[str]:
        """Recursively search code object constants for version info."""
        if depth > 3:  # Limit recursion depth
            return None

        try:
            # Check if it's a code object with constants
            if hasattr(code, 'co_consts'):
                for const in code.co_consts:
                    # Check string constants that look like versions
                    if isinstance(const, str):
                        # Simple version number like "58" or "2025.7.0"
                        if re.match(r'^\d+$', const) and 1 <= len(const) <= 4:
                            return const
                        if re.match(r'^\d+\.\d+(\.\d+)?$', const):
                            return const
                        if re.match(r'^20\d{2}\.\d+\.\d+$', const):
                            return const
                        if re.match(r'^v?\d+(\.\d+)*[a-zA-Z]?$', const.lower()) and len(const) < 20:
                            return const

                    # Check integer constants (some mods store version as int)
                    elif isinstance(const, int) and 1 <= const <= 9999:
                        # Could be a simple version number, but be careful
                        # Only return if it's in a reasonable range for version numbers
                        # This is a heuristic - version numbers like 58 are common
                        pass  # Skip for now, too many false positives

                    # Recurse into nested code objects
                    elif hasattr(const, 'co_consts'):
                        result = self._find_version_in_code(const, depth + 1)
                        if result:
                            return result

                # Also check co_names for version-related variable names
                if hasattr(code, 'co_names') and hasattr(code, 'co_consts'):
                    names = code.co_names
                    consts = code.co_consts
                    for i, name in enumerate(names):
                        name_lower = name.lower() if isinstance(name, str) else ''
                        if name_lower in ['version', '__version__', 'mod_version', 'current_version']:
                            # Found a version variable, look for nearby string constants
                            for const in consts:
                                if isinstance(const, str) and re.match(r'^[\dv][\d\.]*[a-zA-Z]?$', const.lower()):
                                    return const
                                if isinstance(const, int) and 1 <= const <= 999:
                                    return str(const)
        except Exception:
            pass

        return None

    def _version_from_ts4script(self, file_path: Path) -> Optional[str]:
        """Extract version from a .ts4script file (which is a ZIP archive)."""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                file_list = zf.namelist()

                # Look for dedicated version files first
                version_files = ['version.txt', 'VERSION', 'version', '__version__', 'mod_version.txt']
                for vf in version_files:
                    for name in file_list:
                        basename = name.split('/')[-1].lower()
                        if basename == vf.lower() or basename.endswith(vf.lower()):
                            try:
                                content = zf.read(name).decode('utf-8', errors='ignore').strip()
                                version = content.split('\n')[0].strip()
                                if version and len(version) < 50:
                                    return version
                            except Exception:
                                pass

                # Look for version in JSON files (mod info/manifest)
                for name in file_list:
                    if name.endswith('.json'):
                        try:
                            content = zf.read(name).decode('utf-8', errors='ignore')
                            data = json.loads(content)
                            if isinstance(data, dict):
                                for key in ['version', 'Version', 'VERSION', 'mod_version', 'modversion', 'ver']:
                                    if key in data:
                                        return str(data[key])
                        except Exception:
                            pass

                # Look for version in XML files
                for name in file_list:
                    if name.endswith('.xml'):
                        try:
                            content = zf.read(name).decode('utf-8', errors='ignore')
                            # Simple regex search for version in XML
                            for pattern in self.CONTENT_VERSION_PATTERNS:
                                match = pattern.search(content.encode())
                                if match:
                                    return match.group(1).decode('utf-8', errors='ignore')
                        except Exception:
                            pass

                # PRIORITY: Search for version in files with "version" in the name FIRST
                # These are most likely to contain the actual mod version
                version_named_files = [n for n in file_list if 'version' in n.lower()]

                # Sort to prioritize "registry" files over "control" files
                # (version_registry.pyc is more likely to have the actual version than version_control.pyc)
                def version_file_priority(name: str) -> int:
                    name_lower = name.lower()
                    if 'registry' in name_lower:
                        return 0
                    elif 'info' in name_lower or 'config' in name_lower:
                        return 1
                    elif 'control' in name_lower or 'check' in name_lower:
                        return 3
                    else:
                        return 2
                version_named_files.sort(key=version_file_priority)

                for name in version_named_files:
                    try:
                        content = zf.read(name)

                        # For .pyc files with "version" in name, try aggressive extraction FIRST
                        # This handles mods like WonderfulWhims that store version as integer
                        if name.endswith('.pyc'):
                            version = self._version_from_pyc_aggressive(content)
                            if version:
                                return version

                        # Try text-based version files
                        if name.endswith(('.txt', '.py', '.json')):
                            text_content = content.decode('utf-8', errors='ignore')
                            # Look for simple version number on its own line
                            for line in text_content.split('\n')[:10]:
                                line = line.strip()
                                if re.match(r'^v?\d+(\.\d+)*[a-zA-Z]?$', line) and len(line) < 20:
                                    return line.lstrip('v')
                            # Try content patterns
                            for pattern in self.CONTENT_VERSION_PATTERNS:
                                match = pattern.search(content)
                                if match:
                                    result = match.group(1).decode('utf-8', errors='ignore')
                                    if re.match(r'^[\d\.]+[a-zA-Z]?$|^20\d{2}[\._]\d+[\._]\d+$', result):
                                        return result

                        # Fallback 1: search for year-based versions (e.g., 2025.7.0) - highest priority
                        year_matches = re.findall(rb'(20\d{2}\.\d+\.\d+)', content)
                        if year_matches:
                            # Return the highest year-based version found
                            versions = sorted(set(m.decode('utf-8', errors='ignore') for m in year_matches), reverse=True)
                            if versions:
                                return versions[0]

                        # Fallback 2: search for year_underscore versions (e.g., 2025_7_0)
                        year_underscore_matches = re.findall(rb'(20\d{2}_\d+_\d+)', content)
                        if year_underscore_matches:
                            versions = sorted(set(m.decode('utf-8', errors='ignore').replace('_', '.') for m in year_underscore_matches), reverse=True)
                            if versions:
                                return versions[0]

                        # Fallback 3: search for 2-3 digit numbers in version-named files
                        digit_matches = re.findall(rb'[^\d](\d{2,3})[^\d]', content)
                        if digit_matches:
                            candidates = []
                            # Exclude common non-version numbers
                            excluded = {16, 32, 64, 128, 100, 200, 255, 256, 512, 24, 48, 96, 192, 384, 768}
                            for d in digit_matches:
                                try:
                                    num = int(d)
                                    if 10 <= num <= 999 and num not in excluded:
                                        candidates.append(num)
                                except ValueError:
                                    pass
                            if candidates:
                                counts = Counter(candidates)
                                # Sort: prefer 2-digit (10-99) over 3-digit, then by count, then by value (higher)
                                def candidate_sort_key(x):
                                    is_two_digit = 0 if 10 <= x <= 99 else 1
                                    return (is_two_digit, -counts[x], -x)
                                sorted_candidates = sorted(counts.keys(), key=candidate_sort_key)
                                if sorted_candidates:
                                    return str(sorted_candidates[0])
                    except Exception:
                        pass

                # Last resort: search raw content of first few files for version patterns
                for name in file_list[:20]:
                    try:
                        content = zf.read(name)[:4000]  # First 4KB
                        for pattern in self.RAW_VERSION_PATTERNS:
                            match = pattern.search(content)
                            if match:
                                result = match.group(1).decode('utf-8', errors='ignore')
                                if re.match(r'^[\d\.]+[a-zA-Z]?$|^20\d{2}[\._]\d+[\._]\d+$', result):
                                    return result
                        for pattern in self.CONTENT_VERSION_PATTERNS:
                            match = pattern.search(content)
                            if match:
                                result = match.group(1).decode('utf-8', errors='ignore')
                                if re.match(r'^[\d\.]+[a-zA-Z]?$|^20\d{2}[\._]\d+[\._]\d+$', result):
                                    return result
                    except Exception:
                        pass

        except (zipfile.BadZipFile, Exception):
            pass

        return None
    
    @staticmethod
    def _get_file_hash(file_path: Path) -> str:
        """Calculate MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()


# ============================================================================
# UPDATE CHECKER
# ============================================================================

class UpdateChecker:
    """Checks various sources for mod updates."""

    MODTHESIMS_PATTERN = re.compile(r'modthesims\.info/d(?:ownload)?/(\d+)')

    # Common version patterns (ordered by specificity - more specific first)
    VERSION_PATTERNS = [
        # Year-based versioning: "2025.7.0" (MCCC style) - must have year + 2 more parts
        re.compile(r'\b(20\d{2}\.\d+\.\d+)\b'),
        # Semantic versioning with "version" prefix: "Version 1.2.3" or "version: 1.2.3a"
        re.compile(r'[Vv]ersion[:\s]*(\d+(?:\.\d+)+(?:[a-zA-Z])?)', re.IGNORECASE),
        # "Current/Latest Version" prefix
        re.compile(r'(?:Current|Latest)\s+[Vv]ersion[:\s]*(\d+(?:\.\d+)+)', re.IGNORECASE),
        # Semantic versioning with v prefix: "v1.2.3" or "v1.2.3a" (check BEFORE simple v+number)
        re.compile(r'\b[Vv](\d+\.\d+(?:\.\d+)*[a-zA-Z]?)(?:[^\d\.]|$)'),
        # "ModName v58" style (WonderfulWhims) - must NOT be followed by dot (to avoid matching v1 from v1.2.3)
        re.compile(r'\bv(\d+)(?:[^\d\.]|$)', re.IGNORECASE),
        # Release/build prefix
        re.compile(r'(?:release|build)[:\s]*(\d+\.\d+(?:\.\d+)*)', re.IGNORECASE),
        # Standalone semantic version (3 parts minimum to avoid matching dates)
        re.compile(r'\b(\d+\.\d+\.\d+)\b'),
    ]

    # Version keywords to search near
    VERSION_KEYWORDS = ['version', 'current version', 'latest version', 'release', 'build', 'v.', 'v ']

    # Common date patterns
    DATE_PATTERNS = [
        re.compile(r'(?:Updated|Modified|Released)[:\s]*(.+?)(?:<|$)', re.IGNORECASE),
        re.compile(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'),
        re.compile(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})'),
        re.compile(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})', re.IGNORECASE),
        re.compile(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})', re.IGNORECASE),
    ]

    # Download button/link indicators (ordered by priority - "download" first)
    DOWNLOAD_KEYWORDS_PRIMARY = ['download', 'direct link']
    DOWNLOAD_KEYWORDS_SECONDARY = ['get it', 'grab', 'install']

    @staticmethod
    def compare_versions(local: Optional[str], remote: Optional[str]) -> Optional[str]:
        """Compare two version strings. Returns 'update', 'current', 'newer', or None if can't compare."""
        if not local or not remote:
            return None

        def parse_version(v: str) -> list:
            """Parse version string into comparable parts."""
            # Remove common prefixes
            v = v.lower().strip()
            for prefix in ['v', 'version ', 'ver ', 'ver.']:
                if v.startswith(prefix):
                    v = v[len(prefix):]

            # Split by dots and convert to integers where possible
            parts = []
            for part in re.split(r'[.\-_]', v):
                # Try to extract number from part
                num_match = re.match(r'(\d+)', part)
                if num_match:
                    parts.append(int(num_match.group(1)))
                    # Handle suffix like "1a" -> (1, 'a')
                    suffix = part[len(num_match.group(1)):]
                    if suffix:
                        parts.append(suffix)
                elif part:
                    parts.append(part)
            return parts

        try:
            local_parts = parse_version(local)
            remote_parts = parse_version(remote)

            if not local_parts or not remote_parts:
                return None

            # Check for incompatible versioning schemes
            # A single number (like "119") shouldn't be compared to semantic version (like "6.6.0")
            local_is_single = len(local_parts) == 1 and isinstance(local_parts[0], int)
            remote_is_semantic = len(remote_parts) >= 2

            if local_is_single and remote_is_semantic:
                # Single number vs semantic version - can't reliably compare
                # Exception: if single number is clearly a year (2020-2030), might be year-based
                if not (2020 <= local_parts[0] <= 2030):
                    return None

            # Also check if remote is single and local is semantic
            remote_is_single = len(remote_parts) == 1 and isinstance(remote_parts[0], int)
            local_is_semantic = len(local_parts) >= 2

            if remote_is_single and local_is_semantic:
                if not (2020 <= remote_parts[0] <= 2030):
                    return None

            # Compare part by part
            for i in range(max(len(local_parts), len(remote_parts))):
                l_part = local_parts[i] if i < len(local_parts) else 0
                r_part = remote_parts[i] if i < len(remote_parts) else 0

                # Normalize to same type for comparison
                if isinstance(l_part, int) and isinstance(r_part, int):
                    if l_part < r_part:
                        return 'update'
                    elif l_part > r_part:
                        return 'newer'
                else:
                    # Compare as strings
                    l_str = str(l_part)
                    r_str = str(r_part)
                    if l_str < r_str:
                        return 'update'
                    elif l_str > r_str:
                        return 'newer'

            return 'current'
        except Exception:
            return None

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def check_modthesims(self, mod_url: str) -> Optional[dict]:
        """Check ModTheSims for mod update info."""
        if not BS4_AVAILABLE:
            return None
        
        try:
            # Extract mod ID from URL
            match = self.MODTHESIMS_PATTERN.search(mod_url)
            if not match:
                return None
            
            mod_id = match.group(1)
            url = f"https://modthesims.info/d/{mod_id}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Try to find update date
            update_info = {}
            
            # Look for last updated date
            date_elem = soup.find('time', {'class': 'updated'})
            if not date_elem:
                for span in soup.find_all('span'):
                    span_text = span.get_text()
                    if span_text and 'Updated' in span_text:
                        date_elem = span
                        break
            if date_elem:
                update_info['last_updated'] = date_elem.get_text(strip=True)
            
            # Look for version info
            version_elem = soup.find(string=re.compile(r'Version:?\s*[\d.]+'))
            if version_elem:
                version_match = re.search(r'Version:?\s*([\d.]+)', str(version_elem))
                if version_match:
                    update_info['version'] = version_match.group(1)
            
            # Get mod title
            title_elem = soup.find('h1', {'class': 'title'}) or soup.find('h1')
            if title_elem:
                update_info['title'] = title_elem.get_text(strip=True)
            
            update_info['url'] = url
            update_info['checked_at'] = datetime.now().isoformat()
            
            return update_info if update_info else None
            
        except Exception as e:
            print(f"Error checking ModTheSims: {e}")
            return None
    
    def check_curseforge(self, mod_url: str) -> Optional[dict]:
        """Check CurseForge for mod updates (limited without API key)."""
        # CurseForge requires API key for full access
        # This is a placeholder for future implementation
        return None

    def check_generic(self, mod_url: str) -> Optional[dict]:
        """Check any URL for mod update info using generic patterns."""
        if not BS4_AVAILABLE:
            return None

        try:
            response = self.session.get(mod_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            update_info: dict[str, str] = {}

            # Get page title
            title_elem = soup.find('title')
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                # Clean up common title suffixes
                for suffix in [' - Patreon', ' | Patreon', ' - itch.io', ' by ', ' on ']:
                    if suffix in title_text:
                        title_text = title_text.split(suffix)[0]
                update_info['title'] = title_text

            # Look for h1 as better title
            h1_elem = soup.find('h1')
            if h1_elem:
                h1_text = h1_elem.get_text(strip=True)
                if h1_text and len(h1_text) < 200:
                    update_info['title'] = h1_text

            # Search for version info on main page
            version = self._find_version(soup)
            if version:
                update_info['version'] = version

            # Search for update/release date
            found_date = self._find_date(soup)
            if found_date:
                update_info['last_updated'] = found_date

            # Look for download button/link
            download_info = self._find_download_link(soup, mod_url)
            if download_info:
                update_info['download_url'] = download_info.get('url', '')
                update_info['download_text'] = download_info.get('text', '')

            # If no version found on main page, try following download link
            if not update_info.get('version') and download_info and download_info.get('url'):
                download_url = download_info['url']
                print(f"      DEBUG: Following download link: {download_url}")
                # Only follow if it's on the same domain or a known mod hosting site
                if self._should_follow_link(mod_url, download_url):
                    try:
                        dl_response = self.session.get(download_url, timeout=15)
                        dl_response.raise_for_status()
                        dl_soup = BeautifulSoup(dl_response.text, 'html.parser')

                        # Search for version on download page
                        dl_version = self._find_version(dl_soup)
                        print(f"      DEBUG: Version from download page: {dl_version}")
                        if dl_version:
                            update_info['version'] = dl_version

                        # Also check for date if not found
                        if not update_info.get('last_updated'):
                            dl_date = self._find_date(dl_soup)
                            if dl_date:
                                update_info['last_updated'] = dl_date
                    except Exception:
                        pass  # Failed to fetch download page, continue with what we have

            # If still no version, try common download page paths
            if not update_info.get('version'):
                from urllib.parse import urlparse, urljoin
                parsed = urlparse(mod_url)
                base = f"{parsed.scheme}://{parsed.netloc}"

                # Common download page paths to try
                download_paths = [
                    '/download', '/downloads', '/downloads.html', '/download.html',
                    '/releases', '/release', '/#/releases', '/#/downloads'
                ]

                print(f"      DEBUG: Trying common download paths...")
                for path in download_paths:
                    try:
                        test_url = urljoin(base, path)
                        if test_url == mod_url:
                            continue  # Skip if same as original URL

                        test_response = self.session.get(test_url, timeout=10)
                        if test_response.status_code == 200:
                            test_soup = BeautifulSoup(test_response.text, 'html.parser')
                            test_version = self._find_version(test_soup)
                            print(f"      DEBUG: {path} -> {test_version}")
                            if test_version:
                                update_info['version'] = test_version
                                # Update download URL if we found version on a download page
                                if 'download' in path.lower():
                                    update_info['download_url'] = test_url
                                break
                    except Exception:
                        continue

            update_info['url'] = mod_url
            update_info['checked_at'] = datetime.now().isoformat()

            # Only return if we found something useful
            if update_info.get('version') or update_info.get('last_updated') or update_info.get('download_url'):
                return update_info

            # Return basic info even if we didn't find update-specific info
            if update_info.get('title'):
                return update_info

            return None

        except Exception as e:
            print(f"Error checking URL: {e}")
            return None

    def _should_follow_link(self, base_url: str, link_url: str) -> bool:
        """Determine if we should follow a link to check for version info."""
        from urllib.parse import urlparse

        base_domain = urlparse(base_url).netloc.lower()
        link_domain = urlparse(link_url).netloc.lower()

        # Always follow links on same domain
        if base_domain == link_domain:
            return True

        # Follow links to known mod hosting domains
        known_domains = [
            'wonderfulwhims.com', 'deaderpool-mccc.com', 'modthesims.info',
            'patreon.com', 'simfileshare.net', 'mediafire.com',
            'mega.nz', 'github.com', 'curseforge.com'
        ]
        for domain in known_domains:
            if domain in link_domain:
                return True

        return False

    def _find_version(self, soup: "BeautifulSoup") -> Optional[str]:
        """Find version number on the page using multiple strategies."""
        version_pattern = re.compile(r'version', re.IGNORECASE)
        year_based_pattern = re.compile(r'^20\d{2}\.\d+\.\d+$')

        # Collect all found versions, then pick the best one
        found_versions: list[tuple[int, str]] = []  # (priority, version)

        def add_version(version: str, priority: int):
            """Add a version with priority (lower is better)."""
            # Year-based versions get highest priority (0)
            if year_based_pattern.match(version):
                found_versions.append((0, version))
            else:
                found_versions.append((priority, version))

        # Elements to search for version info
        version_elements = ['span', 'div', 'p', 'td', 'dd', 'strong', 'h1', 'h2', 'h3', 'h4', 'a', 'b', 'em']

        # Strategy 0: Early scan for year-based versions in page text (priority 0)
        # This ensures MCCC-style versions like "2025.7.0" are always found
        page_text = soup.get_text()[:8000]
        year_version_pattern = re.compile(r'\b(20\d{2}\.\d+\.\d+)\b')
        year_matches = year_version_pattern.findall(page_text)
        for version in set(year_matches):
            add_version(version, 0)

        # Strategy 1: Look for elements with version-related classes or IDs (priority 1)
        for elem in soup.find_all(version_elements):
            class_attr = elem.get('class')
            class_str = ' '.join(class_attr) if isinstance(class_attr, list) else ''
            id_attr = elem.get('id')
            id_str = str(id_attr) if id_attr else ''

            if version_pattern.search(class_str) or version_pattern.search(id_str):
                text = elem.get_text(strip=True)
                if text and len(text) < 50:
                    for pattern in self.VERSION_PATTERNS:
                        match = pattern.search(text)
                        if match:
                            add_version(match.group(1), 1)
                            break

        # Strategy 2: Look for headings (priority 2)
        for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
            text = elem.get_text(strip=True)
            if text and len(text) < 100:
                for pattern in self.VERSION_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        add_version(match.group(1), 2)
                        break

        # Strategy 3: Look for elements containing version keywords (priority 3)
        for elem in soup.find_all(version_elements + ['li', 'dt']):
            text = elem.get_text(strip=True)
            text_lower = text.lower()
            for keyword in self.VERSION_KEYWORDS:
                if keyword in text_lower and len(text) < 100:
                    for pattern in self.VERSION_PATTERNS:
                        match = pattern.search(text)
                        if match:
                            add_version(match.group(1), 3)
                            break
                    break

        # Strategy 4: Look in meta tags (priority 2)
        for meta in soup.find_all('meta'):
            name = str(meta.get('name', '')).lower()
            prop = str(meta.get('property', '')).lower()
            if 'version' in name or 'version' in prop:
                content = meta.get('content')
                if content:
                    add_version(str(content), 2)

        # Strategy 5: Search changelog/release sections (priority 1 - reliable source)
        changelog_keywords = ['changelog', 'release notes', 'what\'s new', 'updates', 'history', 'releases']
        for elem in soup.find_all(['section', 'div', 'article']):
            elem_id = str(elem.get('id', '')).lower()
            class_attr = elem.get('class')
            elem_class = ' '.join(class_attr).lower() if isinstance(class_attr, list) else ''
            header = elem.find(['h1', 'h2', 'h3', 'h4'])
            header_text = header.get_text(strip=True).lower() if header else ''

            if any(kw in elem_id or kw in elem_class or kw in header_text for kw in changelog_keywords):
                text = elem.get_text()[:500]
                for pattern in self.VERSION_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        add_version(match.group(1), 1)
                        break

        # If we found versions, return the best one
        if found_versions:
            # Sort by priority (lower is better), then prefer year-based, then higher version numbers
            def version_sort_key(item: tuple[int, str]) -> tuple:
                priority, version = item
                # Year-based versions: sort by version number descending
                if year_based_pattern.match(version):
                    try:
                        parts = [int(p) for p in version.split('.')]
                        return (priority, 0, tuple(-p for p in parts))
                    except ValueError:
                        return (priority, 0, (0,))
                # Other versions: try to parse as number
                try:
                    num = int(version)
                    return (priority, 1, -num)
                except ValueError:
                    return (priority, 2, version)

            found_versions.sort(key=version_sort_key)

            # Debug: show what versions were found (always show if more than 1 version)
            if len(found_versions) > 1:
                unique_versions = list(dict.fromkeys([v for _, v in found_versions]))[:10]
                print(f"      DEBUG versions found: {unique_versions}")

            return found_versions[0][1]

        # Strategy 6: Fall back to scanning full page text (priority 5)
        page_text = soup.get_text()[:5000]
        for pattern in self.VERSION_PATTERNS:
            match = pattern.search(page_text)
            if match:
                return match.group(1)

        return None

    def _find_date(self, soup: "BeautifulSoup") -> Optional[str]:
        """Find update/release date on the page."""
        # Check for time elements first (semantic HTML)
        time_elems = soup.find_all('time')
        for time_elem in time_elems:
            datetime_attr = time_elem.get('datetime')
            if datetime_attr:
                return str(datetime_attr)
            time_text = time_elem.get_text(strip=True)
            if time_text:
                return time_text

        # Look for elements containing update-related keywords
        update_keywords = ['updated', 'modified', 'released', 'published', 'last update']
        for elem in soup.find_all(['span', 'div', 'p', 'td', 'li']):
            elem_text = elem.get_text(strip=True).lower()
            for keyword in update_keywords:
                if keyword in elem_text and len(elem_text) < 100:
                    # Try to extract a date from this element
                    for pattern in self.DATE_PATTERNS[1:]:  # Skip first pattern (used differently)
                        match = pattern.search(elem.get_text())
                        if match:
                            return match.group(1)
                    # Return the whole text if it's short enough
                    if len(elem_text) < 50:
                        return elem.get_text(strip=True)

        return None

    def _find_download_link(self, soup: "BeautifulSoup", base_url: str) -> Optional[dict]:
        """Find download button or link on the page."""
        from urllib.parse import urljoin

        def check_element(elem, keywords: list[str]) -> Optional[dict]:
            """Check if element matches any keyword and return download info."""
            elem_text = elem.get_text(strip=True).lower()
            class_attr = elem.get('class')
            elem_class = ' '.join(class_attr).lower() if isinstance(class_attr, list) else ''
            id_attr = elem.get('id')
            elem_id = str(id_attr).lower() if id_attr else ''
            href_attr = elem.get('href')
            href_lower = str(href_attr).lower() if href_attr else ''

            for keyword in keywords:
                if keyword in elem_text or keyword in elem_class or keyword in elem_id or keyword in href_lower:
                    if href_attr:
                        return {
                            'url': urljoin(base_url, str(href_attr)),
                            'text': elem.get_text(strip=True)
                        }
            return None

        # First pass: look for primary keywords (download, direct link)
        for elem in soup.find_all(['a', 'button']):
            result = check_element(elem, self.DOWNLOAD_KEYWORDS_PRIMARY)
            if result:
                return result

        # Second pass: look for secondary keywords (get it, grab, install)
        for elem in soup.find_all(['a', 'button']):
            result = check_element(elem, self.DOWNLOAD_KEYWORDS_SECONDARY)
            if result:
                return result

        # Last resort: look for links to common download file types
        download_extensions = ['.zip', '.rar', '.7z', '.package', '.ts4script']
        for link in soup.find_all('a', href=True):
            href_attr = link.get('href')
            href = str(href_attr).lower() if href_attr else ''
            for ext in download_extensions:
                if href.endswith(ext):
                    return {
                        'url': urljoin(base_url, str(link['href'])),
                        'text': link.get_text(strip=True) or f'Download {ext}'
                    }

        return None

    def check_url(self, mod_url: str) -> Optional[dict]:
        """Check any URL for mod info, using site-specific checker if available."""
        url_lower = mod_url.lower()

        # Use site-specific checkers when available
        if 'modthesims' in url_lower:
            result = self.check_modthesims(mod_url)
            if result:
                return result

        if 'curseforge' in url_lower:
            result = self.check_curseforge(mod_url)
            if result:
                return result

        # Fall back to generic checker
        return self.check_generic(mod_url)


# ============================================================================
# MOD MANAGER
# ============================================================================

class SimsModManager:
    """Main mod manager class that ties everything together."""
    
    def __init__(self, mods_path: Optional[Path] = None):
        self.mods_path = mods_path or get_default_mods_path()
        self.db = ModDatabase(self.mods_path)
        self.scanner = ModScanner(self.mods_path)
        self.update_checker = UpdateChecker()
        
        print(f"Sims 4 Mod Manager initialized")
        print(f"Mods folder: {self.mods_path}")
        print(f"Folder exists: {self.mods_path.exists()}")
        print()
    
    def scan_mods(self) -> list[dict]:
        """Scan all mods and update the database."""
        print("Scanning mods folder...")
        mods = self.scanner.scan()
        
        # Update database with scanned mods
        current_hashes = set()
        for mod in mods:
            current_hashes.add(mod['hash'])
            existing = self.db.get_mod(mod['hash'])
            
            if existing:
                # Preserve user-added metadata
                mod['source_url'] = existing.get('source_url')
                mod['notes'] = existing.get('notes')
                mod['creator'] = existing.get('creator')
                mod['added_date'] = existing.get('added_date', mod['modified_date'])
                mod['last_checked'] = existing.get('last_checked')
            else:
                mod['added_date'] = datetime.now().isoformat()
            
            self.db.add_mod(mod['hash'], mod)
        
        # Remove mods that no longer exist
        removed = []
        for file_hash in list(self.db.data["mods"].keys()):
            if file_hash not in current_hashes:
                removed.append(self.db.data["mods"][file_hash]['name'])
                self.db.remove_mod(file_hash)
        
        print(f"Found {len(mods)} mods")
        if removed:
            print(f"Removed {len(removed)} deleted mods from database")

        # Show version detection summary
        with_versions = [m for m in mods if m.get('local_version')]
        print(f"Detected versions for {len(with_versions)}/{len(mods)} mods")

        return mods

    def debug_mod_version(self, mod_name: str):
        """Debug version detection for a specific mod."""
        # Find mod by name
        found = None
        for file_hash, mod in self.db.data["mods"].items():
            if mod_name.lower() in mod['name'].lower():
                found = mod
                break

        if not found:
            print(f"Mod '{mod_name}' not found. Run a scan first.")
            return

        print(f"\n{'='*60}")
        print(f"DEBUG: {found['name']}")
        print(f"{'='*60}")
        print(f"Filename: {found['filename']}")
        print(f"Path: {found['path']}")
        print(f"Is Script: {found['is_script']}")
        print(f"Current local_version: {found.get('local_version', 'None')}")

        file_path = Path(found['full_path'])
        if not file_path.exists():
            print(f"File not found at {file_path}")
            return

        # Try to extract version from filename
        print(f"\n--- Filename Analysis ---")
        version = self.scanner._version_from_filename(file_path.stem)
        print(f"Version from filename: {version or 'Not found'}")

        # If it's a script mod, analyze the contents
        if found['is_script']:
            print(f"\n--- Script Contents Analysis ---")
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    file_list = zf.namelist()
                    print(f"Files in archive ({len(file_list)} total):")
                    for name in file_list[:30]:  # Show first 30 files
                        print(f"  - {name}")
                    if len(file_list) > 30:
                        print(f"  ... and {len(file_list) - 30} more")

                    # Look for version files
                    print(f"\n--- Searching for version info ---")
                    version_files = ['version.txt', 'VERSION', '__version__', 'mod_version.txt']
                    for name in file_list:
                        basename = name.split('/')[-1].lower()
                        for vf in version_files:
                            if vf.lower() in basename:
                                print(f"Found potential version file: {name}")
                                try:
                                    content = zf.read(name).decode('utf-8', errors='ignore')[:200]
                                    print(f"  Content: {repr(content)}")
                                except Exception as e:
                                    print(f"  Error reading: {e}")

                    # Search for version patterns in Python source files
                    print(f"\n--- Searching Python source files (.py) ---")
                    py_found = False
                    for name in file_list:
                        if name.endswith('.py'):
                            try:
                                content = zf.read(name)[:1000]
                                for pattern in self.scanner.CONTENT_VERSION_PATTERNS[:5]:
                                    match = pattern.search(content)
                                    if match:
                                        result = match.group(1).decode('utf-8', errors='ignore')
                                        print(f"  Found in {name}: {result}")
                                        py_found = True
                                        break
                            except Exception:
                                pass
                    if not py_found:
                        print("  No version patterns found in .py files")

                    # Search files with "version" in the name
                    print(f"\n--- Searching files with 'version' in name ---")
                    version_files_found = [n for n in file_list if 'version' in n.lower()]
                    for name in version_files_found:
                        print(f"  Found: {name}")
                        try:
                            content = zf.read(name)
                            # Search for raw ASCII digit sequences that could be versions
                            # Look for 2-digit numbers that aren't likely to be other things
                            digit_matches = re.findall(rb'[^\d](\d{2,3})[^\d]', content)
                            if digit_matches:
                                unique_digits = list(set(d.decode() for d in digit_matches if 10 <= int(d) <= 999))
                                if unique_digits:
                                    print(f"    2-3 digit numbers found: {unique_digits[:15]}")

                            # Look for version-like strings
                            version_matches = re.findall(rb'(\d+\.\d+(?:\.\d+)?)', content)
                            if version_matches:
                                unique_versions = list(set(v.decode() for v in version_matches))
                                print(f"    Version-like strings: {unique_versions[:10]}")

                            # Try RAW_VERSION_PATTERNS
                            for pattern in self.scanner.RAW_VERSION_PATTERNS:
                                match = pattern.search(content)
                                if match:
                                    print(f"    RAW pattern match: {match.group(1).decode('utf-8', errors='ignore')}")

                            # Try aggressive .pyc extraction for version-named files
                            if name.endswith('.pyc'):
                                aggressive_version = self.scanner._version_from_pyc_aggressive(content)
                                if aggressive_version:
                                    print(f"    AGGRESSIVE .pyc extraction: {aggressive_version}")
                                else:
                                    print(f"    AGGRESSIVE .pyc extraction: No version found")

                                # Show detailed debug info
                                self.scanner._debug_pyc_extraction(content)

                        except Exception as e:
                            print(f"    Error: {e}")

                    # Search compiled Python files (.pyc)
                    print(f"\n--- Searching compiled Python files (.pyc) ---")
                    pyc_files = [n for n in file_list if n.endswith('.pyc')]
                    print(f"  Found {len(pyc_files)} .pyc files")

                    pyc_found = False
                    for name in pyc_files[:5]:  # Check first 5 .pyc files
                        try:
                            pyc_data = zf.read(name)
                            version = self.scanner._version_from_pyc(pyc_data)
                            if version:
                                print(f"  Found version in {name}: {version}")
                                pyc_found = True
                        except Exception as e:
                            print(f"  Error reading {name}: {e}")

                    if not pyc_found:
                        print("  No version extracted from .pyc files via marshal")

            except zipfile.BadZipFile:
                print("Error: Not a valid ZIP file")
            except Exception as e:
                print(f"Error: {e}")
    
    def list_mods(self, show_details: bool = False):
        """List all tracked mods."""
        mods = list(self.db.data["mods"].values())
        
        if not mods:
            print("No mods found. Run a scan first!")
            return
        
        # Sort by name
        mods.sort(key=lambda m: m['name'].lower())
        
        print(f"\n{'='*60}")
        print(f"INSTALLED MODS ({len(mods)} total)")
        print(f"{'='*60}\n")
        
        # Group by subfolder
        by_folder = {}
        for mod in mods:
            folder = mod.get('subfolder') or 'Root'
            if folder not in by_folder:
                by_folder[folder] = []
            by_folder[folder].append(mod)
        
        for folder in sorted(by_folder.keys()):
            print(f"📁 {folder}/")
            for mod in by_folder[folder]:
                icon = "📜" if mod['is_script'] else "📦"
                version_str = f" (v{mod['local_version']})" if mod.get('local_version') else ""
                print(f"   {icon} {mod['name']}{version_str}")
                if show_details:
                    print(f"      Size: {mod['size_mb']} MB")
                    print(f"      Modified: {mod['modified_date'][:10]}")
                    if mod.get('local_version'):
                        print(f"      Version: {mod['local_version']}")
                    if mod.get('source_url'):
                        print(f"      Source: {mod['source_url']}")
            print()
    
    def add_mod_source(self, mod_name: str, source_url: str, creator: Optional[str] = None, notes: Optional[str] = None):
        """Add source URL and metadata to a mod.

        Supports wildcards (* and ?) in mod_name to match multiple mods.
        Examples: 'WonderfulWhims*', '*MCCC*', 'Basemental*'
        """
        # Check if pattern contains wildcards
        has_wildcard = '*' in mod_name or '?' in mod_name

        # Find matching mods
        matches: list[tuple[str, dict]] = []
        pattern = mod_name.lower()

        for file_hash, mod in self.db.data["mods"].items():
            mod_name_lower = mod['name'].lower()
            if has_wildcard:
                if fnmatch.fnmatch(mod_name_lower, pattern):
                    matches.append((file_hash, mod))
            else:
                # Partial match for non-wildcard searches
                if pattern in mod_name_lower:
                    matches.append((file_hash, mod))

        if not matches:
            print(f"No mods found matching '{mod_name}'")
            return

        # Update all matching mods
        print(f"Found {len(matches)} mod(s) matching '{mod_name}':")
        for file_hash, mod in matches:
            mod['source_url'] = source_url
            if creator:
                mod['creator'] = creator
            if notes:
                mod['notes'] = notes
            self.db.add_mod(file_hash, mod)
            print(f"  ✓ {mod['name']}")
    
    def check_for_updates(self):
        """Check all mods with source URLs for updates."""
        print("\nChecking for updates...")

        mods_with_sources = [
            (h, m) for h, m in self.db.data["mods"].items()
            if m.get('source_url')
        ]

        if not mods_with_sources:
            print("No mods have source URLs configured.")
            print("Add source URLs with: manager.add_mod_source('mod_name', 'url')")
            return

        print(f"Checking {len(mods_with_sources)} mods with source URLs...\n")

        needs_update = []
        up_to_date = []
        unknown_status = []

        for file_hash, mod in mods_with_sources:
            source_url = mod['source_url']
            print(f"Checking: {mod['name']}...")

            update_info = self.update_checker.check_url(source_url)

            if update_info:
                mod['last_checked'] = update_info['checked_at']
                mod['remote_info'] = update_info
                self.db.add_mod(file_hash, mod)

                local_version = mod.get('local_version')
                remote_version = update_info.get('version')

                # Compare versions
                comparison = UpdateChecker.compare_versions(local_version, remote_version)

                # Show what we found
                if update_info.get('title'):
                    print(f"   Title: {update_info.get('title')}")

                if local_version or remote_version:
                    local_str = local_version or 'unknown'
                    remote_str = remote_version or 'unknown'
                    print(f"   Local version:  {local_str}")
                    print(f"   Remote version: {remote_str}")

                    if comparison == 'update':
                        print(f"   ⚠️  UPDATE AVAILABLE!")
                        needs_update.append({
                            'name': mod['name'],
                            'url': source_url,
                            'local_version': local_version,
                            'remote_version': remote_version,
                            'remote_info': update_info
                        })
                    elif comparison == 'current':
                        print(f"   ✅ Up to date")
                        up_to_date.append(mod['name'])
                    elif comparison == 'newer':
                        print(f"   ℹ️  Local version is newer than remote")
                        up_to_date.append(mod['name'])
                    else:
                        unknown_status.append({
                            'name': mod['name'],
                            'url': source_url,
                            'remote_info': update_info
                        })
                else:
                    unknown_status.append({
                        'name': mod['name'],
                        'url': source_url,
                        'remote_info': update_info
                    })

                if update_info.get('last_updated'):
                    print(f"   Last updated on site: {update_info.get('last_updated')}")
                if update_info.get('download_url'):
                    dl_text = update_info.get('download_text', 'Download')
                    dl_url = update_info.get('download_url')
                    print(f"   Download: {dl_text} - {dl_url}")
            else:
                print(f"   Could not retrieve update info")
                unknown_status.append({
                    'name': mod['name'],
                    'url': source_url,
                    'remote_info': None
                })

        # Summary
        print(f"\n{'='*60}")
        print("UPDATE CHECK SUMMARY")
        print(f"{'='*60}")

        if needs_update:
            print(f"\n🔴 UPDATES AVAILABLE ({len(needs_update)}):")
            for item in needs_update:
                print(f"   📦 {item['name']}")
                print(f"      {item.get('local_version', '?')} → {item.get('remote_version', '?')}")
                print(f"      URL: {item['url']}")
                if item['remote_info'] and item['remote_info'].get('download_url'):
                    print(f"      Download: {item['remote_info']['download_url']}")

        if up_to_date:
            print(f"\n🟢 UP TO DATE ({len(up_to_date)}):")
            for name in up_to_date:
                print(f"   ✓ {name}")

        if unknown_status:
            print(f"\n🟡 UNKNOWN STATUS ({len(unknown_status)}):")
            print("   (Could not compare versions)")
            for item in unknown_status:
                print(f"   ? {item['name']}")
    
    def find_potentially_broken(self) -> list[dict]:
        """Find mods that might be broken after a game update."""
        print("\nAnalyzing mods for potential issues...\n")
        
        issues = []
        mods = list(self.db.data["mods"].values())
        
        # Check for script mods (most likely to break)
        script_mods = [m for m in mods if m['is_script']]
        if script_mods:
            print(f"⚠️  Found {len(script_mods)} script mods (most likely to break after updates):")
            for mod in script_mods:
                print(f"   - {mod['name']}")
                issues.append({
                    'mod': mod,
                    'reason': 'Script mod - verify compatibility after game updates',
                    'severity': 'high'
                })
        
        # Check for very old mods
        old_threshold = datetime.now() - timedelta(days=180)
        old_mods = []
        for mod in mods:
            try:
                mod_date = datetime.fromisoformat(mod['modified_date'])
                if mod_date < old_threshold:
                    old_mods.append(mod)
            except (ValueError, KeyError):
                pass
        
        if old_mods:
            print(f"\n⚠️  Found {len(old_mods)} mods not updated in 6+ months:")
            for mod in old_mods:
                print(f"   - {mod['name']} (modified: {mod['modified_date'][:10]})")
                issues.append({
                    'mod': mod,
                    'reason': 'Not updated in 6+ months',
                    'severity': 'medium'
                })
        
        if not issues:
            print("✅ No obvious issues detected!")
        
        return issues
    
    def backup_mods(self, backup_path: Optional[Path] = None):
        """Create a backup of all mods."""
        if backup_path is None:
            backup_path = self.mods_path.parent / f"Mods_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"Creating backup at: {backup_path}")
        shutil.copytree(self.mods_path, backup_path)
        print("Backup complete!")
        return backup_path
    
    def generate_report(self) -> str:
        """Generate a summary report of all mods."""
        mods = list(self.db.data["mods"].values())
        
        total_size = sum(m['size_bytes'] for m in mods)
        script_count = sum(1 for m in mods if m['is_script'])
        package_count = len(mods) - script_count
        with_sources = sum(1 for m in mods if m.get('source_url'))
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║                  SIMS 4 MOD MANAGER REPORT                   ║
║                  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                       ║
╠══════════════════════════════════════════════════════════════╣
║  Mods Folder: {str(self.mods_path)[:45]:<45} ║
╠══════════════════════════════════════════════════════════════╣
║  STATISTICS                                                  ║
║  ─────────────────────────────────────────────────────────── ║
║  Total Mods:        {len(mods):<40} ║
║  Package Files:     {package_count:<40} ║
║  Script Mods:       {script_count:<40} ║
║  Total Size:        {total_size / (1024*1024):.2f} MB{' ':<33} ║
║  With Source URLs:  {with_sources:<40} ║
╚══════════════════════════════════════════════════════════════╝
"""
        return report


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main CLI interface."""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║           🎮 SIMS 4 MOD MANAGER & UPDATE CHECKER 🎮       ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    # Check for updates on startup
    updater = AutoUpdater()
    if updater.prompt_and_update():
        # User chose to update - exit to allow update to proceed
        sys.exit(0)

    print()  # Add spacing after update check

    # Check for custom path argument
    mods_path = None
    if len(sys.argv) > 1:
        mods_path = Path(sys.argv[1])

    manager = SimsModManager(mods_path)
    
    if not manager.mods_path.exists():
        print(f"\n❌ Mods folder not found at: {manager.mods_path}")
        print("\nPlease either:")
        print("  1. Run this script with the correct path:")
        print("     python sims4_mod_manager.py /path/to/your/Mods")
        print("  2. Or edit the script to set your custom path")
        return

    # Automatically scan mods folder on startup
    manager.scan_mods()

    while True:
        print("\n" + "="*50)
        print("MAIN MENU")
        print("="*50)
        print("1. Scan mods folder")
        print("2. List all mods")
        print("3. List mods (detailed)")
        print("4. Check for updates")
        print("5. Find potentially broken mods")
        print("6. Add source URL to mod")
        print("7. Backup mods folder")
        print("8. Generate report")
        print("9. Debug mod version detection")
        print("0. Exit")
        print()

        choice = input("Enter choice (1-9, 0 to exit): ").strip()
        
        if choice == '1':
            manager.scan_mods()
        
        elif choice == '2':
            manager.list_mods(show_details=False)
        
        elif choice == '3':
            manager.list_mods(show_details=True)
        
        elif choice == '4':
            manager.check_for_updates()
        
        elif choice == '5':
            manager.find_potentially_broken()
        
        elif choice == '6':
            print("\nAdd source URL to a mod")
            print("(This helps track updates from ModTheSims and other sites)")
            print("Tip: Use wildcards to match multiple mods (e.g., 'WonderfulWhims*', '*MCCC*')")
            mod_name = input("Enter mod name or pattern: ").strip()
            source_url = input("Enter source URL: ").strip()
            creator = input("Enter creator name (optional): ").strip() or None
            notes = input("Enter notes (optional): ").strip() or None
            manager.add_mod_source(mod_name, source_url, creator, notes)
        
        elif choice == '7':
            confirm = input("Create backup? This may take a while for large mod folders (y/n): ")
            if confirm.lower() == 'y':
                manager.backup_mods()
        
        elif choice == '8':
            print(manager.generate_report())

        elif choice == '9':
            print("\nDebug mod version detection")
            mod_name = input("Enter mod name (partial match OK): ").strip()
            manager.debug_mod_version(mod_name)

        elif choice == '0':
            print("\nGoodbye! Happy Simming! 🎮")
            break

        else:
            print("Invalid choice. Please enter 0-9.")


if __name__ == "__main__":
    main()
