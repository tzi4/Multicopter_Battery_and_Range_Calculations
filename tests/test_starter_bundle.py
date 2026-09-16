"""The small download must contain current runnable sources and honest hashes."""

import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from examples.build_starter_bundle import (
    ARCHIVE_ROOT, MANIFEST_PATH, OUTPUT_PATH, SOURCE_FILES, ZIP_TIMESTAMP,
    build_bundle, check_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_tree(tmp_path):
    for source in SOURCE_FILES.values():
        path = tmp_path / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"A fixture for {source}\n", encoding="utf-8")
    # Unlisted files must not accidentally inflate or alter the download.
    extra = tmp_path / "data/calibration/original-flight.BIN"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(b"not a starter input")
    return tmp_path


def rewrite_archive(path, replacement=None, extra=None):
    with zipfile.ZipFile(path) as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    if replacement is not None:
        payloads[replacement] = b"changed after publication"
    if extra is not None:
        payloads[extra] = b"unexpected file"
    # Deliberately use ZIP_STORED: --check must compare contents, not zlib bytes.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in payloads.items():
            archive.writestr(name, content)


def test_bundle_has_complete_current_payload_and_manifest():
    path = check_bundle(ROOT)
    assert path.stat().st_size < 1_000_000
    with zipfile.ZipFile(path) as archive:
        required = {
            "README.md", "LICENSE", "pyproject.toml", "multicopter_range.py",
            "flight_workflow.py", "examples/csv_starter.py",
            "examples/aircraft_inputs.py", "data/starter/flight.csv",
            "data/starter/README.md", "data/starter/provenance.json",
            "data/starter/expected-results.json", "bundle-manifest.json",
        }
        assert set(archive.namelist()) == {f"{ARCHIVE_ROOT}/{name}" for name in required}
        manifest = json.loads(archive.read(MANIFEST_PATH))
        assert manifest["format_version"] == 1
        assert set(manifest["files"]) == set(archive.namelist()) - {MANIFEST_PATH}
        for name, metadata in manifest["files"].items():
            content = archive.read(name)
            assert content == (ROOT / metadata["source"]).read_bytes()
            assert metadata["sha256"] == hashlib.sha256(content).hexdigest()
            assert metadata["size_bytes"] == len(content)


def test_builder_is_deterministic_and_excludes_unlisted_files(source_tree):
    path = build_bundle(source_tree)
    first = path.read_bytes()
    build_bundle(source_tree)
    assert path.read_bytes() == first
    assert check_bundle(source_tree) == source_tree / OUTPUT_PATH
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        for member in archive.infolist():
            assert member.date_time == ZIP_TIMESTAMP
            assert member.create_system == 3
            assert member.external_attr >> 16 == stat.S_IFREG | 0o644
            assert not member.filename.endswith((".BIN", ".zip"))
    rewrite_archive(path)
    assert check_bundle(source_tree) == path


@pytest.mark.parametrize("changed", ["archive", "source", "manifest", "extra", "missing"])
def test_check_rejects_stale_or_tampered_download(source_tree, changed):
    path = build_bundle(source_tree)
    member = f"{ARCHIVE_ROOT}/flight_workflow.py"
    if changed == "source":
        (source_tree / "flight_workflow.py").write_text("new source\n")
    elif changed == "archive":
        rewrite_archive(path, replacement=member)
    elif changed == "manifest":
        rewrite_archive(path, replacement=MANIFEST_PATH)
    elif changed == "extra":
        rewrite_archive(path, extra=f"{ARCHIVE_ROOT}/data/full-flight.BIN")
    else:
        with zipfile.ZipFile(path, "w"):
            pass
    with pytest.raises(ValueError, match="Starter ZIP"):
        check_bundle(source_tree)
