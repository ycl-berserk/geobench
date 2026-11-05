"""Every text file in the repository must be valid UTF-8, and none may
contain the replacement character.

This is a regression gate for a failure that cost a whole afternoon: a bulk
rewrite through Windows PowerShell read the UTF-8 sources as GBK and wrote
them back mangled. The Chinese in the error messages and the geometry
symbols ``⊥`` / ``∥`` were destroyed, and the damage was silent wherever a
character sat inside a string literal rather than in code.

A syntax error would have been caught by the compiler. A wrong character in
a message would not have been caught by anything, so it is checked here
instead.

See ``tasks/T004-dsl-parser.failures.md`` (F10) and ``docs/ai-workflow.md``
section 11.1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yml", ".yaml", ".cfg", ".txt"}

SKIPPED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "examples",
}

# Spelled as a code point so that this file does not itself contain the
# character it is looking for.
REPLACEMENT_CHARACTER = chr(0xFFFD)


def _text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in SKIPPED_DIRECTORIES:
            continue
        files.append(path)
    return sorted(files)


TEXT_FILES = _text_files()


def test_the_scan_found_something() -> None:
    """Guard against a broken glob silently making the other tests vacuous."""
    assert len(TEXT_FILES) > 20, f"expected many text files, found {len(TEXT_FILES)}"


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_file_is_valid_utf8(path: Path) -> None:
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{path} is not valid UTF-8: {exc}")


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_file_has_no_replacement_character(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if REPLACEMENT_CHARACTER in text:
        line_number = text[: text.index(REPLACEMENT_CHARACTER)].count("\n") + 1
        pytest.fail(
            f"{path}:{line_number} contains U+FFFD, the replacement character -- "
            "the file was most likely re-encoded by a tool that did not "
            "honour UTF-8"
        )
