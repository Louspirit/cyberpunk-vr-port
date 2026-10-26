"""Read-only installed shader inventory and RED4 archive collision audit.

Uses Python's standard library. Reads files; does not extract archives, load game
DLLs, alter settings, start the game, or make network requests. Archive layout:
https://github.com/WolvenKit/WolvenKit/blob/main/WolvenKit.RED4/Archive/IO/ArchiveReader.cs
Stored payloads are compared without decompression. Different compressed bytes
alone are not proof of different decompressed content; sizes are reported too.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct


GROUPS = ("asym", "asym_ssr", "asym_ao", "asym_particles", "asym_expo",
          "asym_shadow", "view_dir", "screen_fx")
DEFAULT_ARCHIVES = ("Velocity.archive", "ZVisualEffectsFixes.archive",
                    "PreemOptics.archive", "GeneralShadowsFix.archive")
PORT = "cyberpunkvrport.archive"


@dataclass
class Archive:
    path: Path
    entries: dict[int, tuple[int, int]]
    segments: list[tuple[int, int, int]]
    empty_sha1_count: int

    @classmethod
    def read(cls, path: Path) -> Archive:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(40)
            if len(header) != 40:
                raise ValueError(f"{path.name}: truncated header")
            magic, version, offset, length, _, _, _ = struct.unpack("<IIQIQIQ", header)
            if magic != 1380009042 or version != 12:
                raise ValueError(f"{path.name}: unsupported archive header/version")
            if offset + length > size or length < 28:
                raise ValueError(f"{path.name}: invalid index bounds")
            stream.seek(offset)
            _, _, _, count, segment_count, dependency_count = struct.unpack("<IIQIII", stream.read(28))
            if 28 + count * 56 + segment_count * 16 + dependency_count * 8 > length:
                raise ValueError(f"{path.name}: tables exceed index bounds")
            entries = {}
            empty_sha1_count = 0
            empty_sha1 = hashlib.sha1(b"").digest()
            for _ in range(count):
                row = stream.read(56)
                key = struct.unpack_from("<Q", row)[0]
                first, end = struct.unpack_from("<II", row, 20)
                if not 0 <= first <= end <= segment_count or key in entries:
                    raise ValueError(f"{path.name}: invalid/duplicate file entry")
                entries[key] = (first, end)
                empty_sha1_count += row[36:56] == empty_sha1
            segments = [struct.unpack("<QII", stream.read(16)) for _ in range(segment_count)]
            if any(start + packed > size for start, packed, _ in segments):
                raise ValueError(f"{path.name}: segment outside archive")
        return cls(path, entries, segments, empty_sha1_count)

    def payload(self, key: int) -> tuple[str, list[int]]:
        digest = hashlib.sha256()
        sizes = []
        first, end = self.entries[key]
        with self.path.open("rb") as stream:
            for offset, packed, unpacked in self.segments[first:end]:
                sizes.append(unpacked)
                digest.update(struct.pack("<II", packed, unpacked))
                stream.seek(offset)
                remaining = packed
                while remaining:
                    block = stream.read(min(remaining, 1024 * 1024))
                    if not block:
                        raise ValueError(f"{self.path.name}: truncated segment")
                    digest.update(block)
                    remaining -= len(block)
        return digest.hexdigest(), sizes


def path_hash(path: str) -> int:
    value = 14695981039346656037
    for byte in path.lower().replace("/", "\\").encode("utf-8"):
        value = ((value ^ byte) * 1099511628211) & 0xffffffffffffffff
    return value


def shader_inventory(repository: Path, game: Path) -> dict:
    result = {}
    for group in GROUPS:
        # build_dist.ps1 installs source asym_fog/ as plugin asym/.
        source = repository / "src/Shaders" / ("asym_fog" if group == "asym" else group)
        installed = game / "red4ext/plugins/CyberpunkVR_Stereo" / group
        a = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.dxil")}
        b = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in installed.glob("*.dxil")}
        result[group] = {"source_count": len(a), "installed_count": len(b),
                         "missing": sorted(a.keys() - b.keys()),
                         "extra": sorted(b.keys() - a.keys()),
                         "different": sorted(k for k in a.keys() & b.keys() if a[k] != b[k])}
    return result


def nova_inventory(game: Path) -> dict:
    folder = game / "bin/x64/plugins/cyber_engine_tweaks/mods/NovaOptics"
    settings = folder / "settings.json"
    result = {"installed": folder.is_dir(), "persisted_settings_present": settings.is_file(),
              "live_service_state_observed": False}
    init = folder / "init.lua"
    if init.is_file():
        text = init.read_text(encoding="utf-8", errors="replace")
        result["source_defaults"] = {
            key: match.group(1) == "true"
            for key in ("enable", "autoMode")
            if (match := re.search(r"^\s*" + key + r"\s*=\s*(true|false)\s*,", text, re.MULTILINE))
        }
    if settings.is_file():
        values = json.loads(settings.read_text(encoding="utf-8-sig"))
        keys = ("enable", "autoMode", "exposureOverrideEnabled", "exposureOverrideGlobeEnabled",
                "exposureOverrideCarEnabled", "bloomEnabled", "volFogEnabled", "colorGradingEnabled")
        result["persisted_values"] = {key: values[key] for key in keys if key in values}
    return result


def audit(repository: Path, game: Path, candidates: list[str]) -> dict:
    if not (repository / "src/Shaders/asym_fog").is_dir():
        raise ValueError("--repository does not contain the expected source shader groups")
    folder = game / "archive/pc/mod"
    port = Archive.read(folder / PORT)
    raw = repository / "mods/archive/source/raw"
    names = {path_hash(str(p.relative_to(raw))[:-5]): str(p.relative_to(raw))[:-5].replace("/", "\\")
             for p in raw.rglob("*.json")}
    port_payloads = {}
    collisions = {}
    modlist_present = (folder / "modlist.txt").is_file()
    for filename in candidates:
        # Names only: a candidate must stay directly inside the archive directory.
        if "/" in filename or "\\" in filename or Path(filename).name != filename or not filename.endswith(".archive"):
            raise ValueError("--archive requires a single .archive filename")
        path = folder / filename
        if not path.is_file():
            collisions[filename] = {"installed": False}
            continue
        other = Archive.read(path)
        rows = []
        for key in sorted(port.entries.keys() & other.entries.keys()):
            if key not in port_payloads:
                port_payloads[key] = port.payload(key)
            a, b = port_payloads[key], other.payload(key)
            rows.append({"hash": f"{key:016x}", "depot_path": names.get(key),
                         "stored_payload_equal": a == b,
                         "uncompressed_segment_sizes_equal": a[1] == b[1],
                         "port_uncompressed_sizes": a[1], "other_uncompressed_sizes": b[1]})
        collisions[filename] = {
            "installed": True, "entries": len(other.entries), "overlap_count": len(rows),
            "stored_payload_different_count": sum(not r["stored_payload_equal"] for r in rows),
            "different_uncompressed_size_count": sum(not r["uncompressed_segment_sizes_equal"] for r in rows),
            "empty_sha1_count": other.empty_sha1_count,
            "documented_ascii_expected_winner": None if modlist_present or not rows else
                min((PORT, filename), key=lambda value: value.encode("utf-8")),
            "runtime_resolver_winner_observed": False, "overlaps": rows}
    return {"read_only": True, "archive_version": 12, "port_entries": len(port.entries),
            "port_empty_sha1_count": port.empty_sha1_count, "modlist_present": modlist_present,
            "shaders": shader_inventory(repository, game), "nova_optics": nova_inventory(game),
            "archives": collisions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--archive", action="append", help="Candidate archive basename; repeat as needed")
    parser.add_argument("--json", action="store_true", help="Print the full inventory as JSON to stdout")
    args = parser.parse_args()
    result = audit(args.repository, args.game_root, args.archive or list(DEFAULT_ARCHIVES))
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"Read-only audit: port {result['port_entries']} entries; modlist present={result['modlist_present']}")
    for group, row in result["shaders"].items():
        print(f"{group}: source={row['source_count']} installed={row['installed_count']} "
              f"missing={len(row['missing'])} extra={len(row['extra'])} different={len(row['different'])}")
    print("Nova Optics:", json.dumps(result["nova_optics"]))
    for name, row in result["archives"].items():
        if not row["installed"]:
            print(f"{name}: absent")
            continue
        print(f"{name}: entries={row['entries']} overlaps={row['overlap_count']} "
              f"different_stored_payload={row['stored_payload_different_count']} "
              f"different_uncompressed_size={row['different_uncompressed_size_count']} "
              f"documented_expected_winner={row['documented_ascii_expected_winner']}")


if __name__ == "__main__":
    main()
