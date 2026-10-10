"""Read native PE import tables to identify runtime dependencies in the bundle."""

import json
import struct
from pathlib import Path


def imports(path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe : pe + 4] != b"PE\0\0":
        return []
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directory = optional + (112 if magic == 0x20B else 96)
    import_rva = struct.unpack_from("<I", data, directory + 8)[0]
    sections = []
    for index in range(count):
        section = optional + optional_size + index * 40
        virtual_size, address, raw_size, raw_offset = struct.unpack_from("<IIII", data, section + 8)
        sections.append((address, max(virtual_size, raw_size), raw_offset))

    def offset(rva):
        for address, size, raw in sections:
            if address <= rva < address + size:
                return raw + rva - address
        return rva

    if not import_rva:
        return []
    table, result = offset(import_rva), []
    while any(data[table : table + 20]):
        name = offset(struct.unpack_from("<I", data, table + 12)[0])
        result.append(data[name : data.index(b"\0", name)].decode("ascii").lower())
        table += 20
    return result


def main():
    bundle = Path("data/windows-build/bundle")
    dependencies = {}
    for path in bundle.rglob("*"):
        if path.suffix.lower() in {".exe", ".dll", ".pyd"}:
            for name in imports(path):
                if name.startswith(("msvcp", "msvcr", "vcruntime", "concrt")):
                    dependencies.setdefault(name, []).append(str(path.relative_to(bundle)))
    report = {
        name: {"referenced_by": len(paths), "bundled": any(bundle.rglob(name))}
        for name, paths in dependencies.items()
    }
    Path("data/windows-build/runtime-dependencies.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
