#!/usr/bin/env python3
"""Smoke tests for stl_doctor: a clean cube must pass, a cube with a
missing face (a hole) must fail.

Run: python3 tests/test_stl_doctor.py
"""
import sys
import tempfile
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stl_doctor import check_file, main


def write_stl(mesh, folder, name):
    path = Path(folder) / name
    mesh.export(path)
    return str(path)


def run():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        cube = trimesh.creation.box(extents=[10.0, 20.0, 30.0])
        good = write_stl(cube, tmp, "cube.stl")
        report = check_file(good)
        if not report["healthy"]:
            failures.append(f"clean cube should be healthy: {report['problems']}")
        if not report["watertight"] or report["components"] != 1:
            failures.append("clean cube: expected watertight, 1 component")
        if report["triangles"] != 12:
            failures.append(f"clean cube: expected 12 triangles, got {report['triangles']}")
        if abs(report["height_mm"] - 30.0) > 1e-6:
            failures.append(f"clean cube: expected height 30.0, got {report['height_mm']}")

        broken = trimesh.creation.box(extents=[10.0, 10.0, 10.0])
        broken.faces = broken.faces[:-1]  # punch a hole in it
        bad = write_stl(broken, tmp, "cube_with_hole.stl")
        report = check_file(bad)
        if report["healthy"]:
            failures.append("cube with a hole should NOT be healthy")
        if report["watertight"]:
            failures.append("cube with a hole should not be watertight")
        if report["boundary_edges"] != 3:
            failures.append(
                f"cube with a hole: expected 3 boundary edges, got {report['boundary_edges']}"
            )

        if main([good]) != 0:
            failures.append("exit code for a healthy file should be 0")
        if main([bad]) != 1:
            failures.append("exit code for a broken file should be 1")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
