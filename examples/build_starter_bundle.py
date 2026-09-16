"""Build or check the small, self-contained CSV starter source download.

Run this from a repository checkout after updating its source files:
    python examples/build_starter_bundle.py
    python examples/build_starter_bundle.py --check

The ZIP contains the Python sources and one small CSV, not installed packages
or the original flight archive. Its README describes dependency installation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = "multicopter-csv-starter"
OUTPUT_PATH = Path("docs/downloads/csv-starter.zip")
MANIFEST_PATH = f"{ARCHIVE_ROOT}/bundle-manifest.json"
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
# Archive-relative destination: repository source. This explicit allowlist keeps
# full flight logs, generated plots, and the ZIP itself out of the download.
SOURCE_FILES = {
    "README.md": "docs/CSV_STARTER.md",
    "LICENSE": "LICENSE",
    "pyproject.toml": "pyproject.toml",
    "multicopter_range.py": "multicopter_range.py",
    "flight_workflow.py": "flight_workflow.py",
    "examples/csv_starter.py": "examples/csv_starter.py",
    "examples/aircraft_inputs.py": "examples/aircraft_inputs.py",
    "data/starter/flight.csv": "data/starter/flight.csv",
    "data/starter/README.md": "data/starter/README.md",
    "data/starter/provenance.json": "data/starter/provenance.json",
    "data/starter/expected-results.json": "data/starter/expected-results.json",
}


def _payloads(root):
    payloads = {}
    manifest = {"format_version": 1, "files": {}}
    for destination, source in sorted(SOURCE_FILES.items()):
        source_path = Path(root) / source
        try:
            content = source_path.read_bytes()
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Starter source is missing: {source_path}") from exc
        archive_path = f"{ARCHIVE_ROOT}/{destination}"
        payloads[archive_path] = content
        manifest["files"][archive_path] = {
            "source": source,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    payloads[MANIFEST_PATH] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return payloads


def build_bundle(root=ROOT, output_path=None):
    """Write the allowlisted current sources with stable ZIP member metadata."""
    root = Path(root)
    output_path = Path(output_path) if output_path is not None else root / OUTPUT_PATH
    payloads = _payloads(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, content in sorted(payloads.items()):
            member = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, content, compresslevel=9)
    return output_path


def check_bundle(root=ROOT, output_path=None):
    """Verify exact uncompressed payloads, including the generated manifest.

    Comparing payloads rather than compressed ZIP bytes tolerates differences
    between zlib versions while detecting changed, extra or missing sources.
    """
    root = Path(root)
    output_path = Path(output_path) if output_path is not None else root / OUTPUT_PATH
    expected = _payloads(root)
    with zipfile.ZipFile(output_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Starter ZIP contains duplicate member paths")
        missing = sorted(set(expected) - set(names))
        extra = sorted(set(names) - set(expected))
        if missing or extra:
            raise ValueError(f"Starter ZIP membership differs: missing={missing}, extra={extra}")
        for name, content in sorted(expected.items()):
            if archive.read(name) != content:
                raise ValueError(f"Starter ZIP payload differs from current source: {name}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Check that the existing ZIP matches current sources")
    args = parser.parse_args()
    try:
        path = check_bundle() if args.check else build_bundle()
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Starter bundle error: {exc}\n")
    verb = "Verified" if args.check else "Built"
    print(f"{verb}: {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
