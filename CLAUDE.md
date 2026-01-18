# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Sims 4 Mod Manager is a Python CLI application for managing The Sims 4 mods. It provides mod scanning, update checking, backup creation, and metadata tracking.

## Commands

```bash
# Run the application (uses default Sims 4 Mods path)
python sims4_mod_manager.py

# Run with custom mods path
python sims4_mod_manager.py /path/to/Mods

# Install dependencies
pip install -r requirements.txt
```

## Architecture

Single-file architecture (`sims4_mod_manager.py`) with four main classes:

- **ModDatabase**: Manages persistent JSON database (`_mod_manager_data.json`) for tracking mod metadata (hash, source URL, creator, notes, timestamps)
- **ModScanner**: Recursively scans Mods folder for `.package` and `.ts4script` files, extracts metadata, calculates MD5 hashes, and extracts version info from filenames and .ts4script contents (which are ZIP archives)
- **UpdateChecker**: Checks any URL for mod updates using requests + BeautifulSoup. Has site-specific checkers (ModTheSims) and a generic checker that looks for version numbers, update dates, and download links on any page. Includes version comparison logic.
- **SimsModManager**: Main orchestrator that combines all components and provides high-level operations

Entry point is `main()` which runs an interactive menu-driven CLI loop with 9 options.

## Key Patterns

- Uses `pathlib.Path` throughout for cross-platform compatibility
- Mods identified by MD5 hash (not filename)
- Optional BeautifulSoup with graceful degradation if not installed
- Cross-platform mods path detection (Windows, macOS, Linux/Wine/Proton)
- JSON database with `default=str` for datetime serialization
- Wildcard support (`*`, `?`) in mod name patterns using `fnmatch`

## Version Detection

**Local version extraction** (in order of priority):
1. From filename patterns (e.g., `ModName_v1.2.3.ts4script`)
2. For `.ts4script` files (ZIP archives): looks inside for `version.txt`, `__version__` in Python files, or `version` key in JSON manifests

**Remote version detection** (multiple strategies):
1. HTML elements with version-related classes/IDs
2. Elements containing version keywords
3. Meta tags with version info
4. Changelog/release note sections
5. Full page text scan (fallback)

## Dependencies

- `requests` - HTTP client for web scraping
- `beautifulsoup4` - HTML parsing (optional, graceful degradation)
