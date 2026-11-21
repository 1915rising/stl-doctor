#!/usr/bin/env python3
"""stl-doctor: a health check for STL files.

Reports, per file: watertightness, connected-component count, boundary
edges, non-manifold edges, degenerate (zero-area) faces, duplicate faces,
bounding-box dimensions, sole-to-crown height and triangle count.

Usage:
    python3 stl_doctor.py model.stl [more.stl ...]
    python3 stl_doctor.py ./models/                 # every .stl in a folder
    python3 stl_doctor.py -r ./models/ -o report.json

Exit status: 0 if every file passes, 1 if any file fails a health check,
2 on usage or load errors.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

TINY_FACE_AREA = 1e-4  # mm^2; faces smaller than this are reported as "tiny"


def count_components(faces, vertex_count):
    """Count connected shells (faces joined by shared vertices/edges)."""
    if len(faces) == 0 or vertex_count == 0:
        return 0
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components

        rows = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
        cols = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
        graph = coo_matrix(
            (np.ones(len(rows), dtype=np.int8), (rows, cols)),
            shape=(vertex_count, vertex_count),
        )
        n, labels = connected_components(graph, directed=False)
        used = np.zeros(vertex_count, dtype=bool)
        used[np.unique(faces)] = True
        return int(len(np.unique(labels[used])))
    except ImportError:
        pass
    # Fallback: union-find over shared vertices (no scipy available).
    parent = list(range(vertex_count))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in faces.tolist():
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    return len({find(v) for v in np.unique(faces).tolist()})


def check_file(path):
    """Run all health metrics on one STL file. Returns a report dict."""
    t0 = time.time()
    mesh = trimesh.load(path, process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError("no triangle mesh found")
    mesh.merge_vertices()

    faces = np.asarray(mesh.faces)
    verts = np.asarray(mesh.vertices)
    bounds = np.asarray(mesh.bounds)
    extents = bounds[1] - bounds[0]

    areas = mesh.area_faces
    degenerate = int(np.sum(areas <= 0))
    tiny = int(np.sum(areas < TINY_FACE_AREA))  # includes the degenerate ones

    # duplicate faces: identical sorted vertex triples
    sorted_faces = np.sort(faces, axis=1)
    _, face_counts = np.unique(sorted_faces, axis=0, return_counts=True)
    duplicates = int(np.sum(face_counts - 1))

    # edge sharing: an edge used once is a boundary (hole) edge; an edge
    # used by 3+ faces is non-manifold
    edges = np.sort(
        np.concatenate(
            [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]
        ).astype(np.int64),
        axis=1,
    )
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    boundary = int(np.sum(edge_counts == 1))
    nonmanifold = int(np.sum(edge_counts > 2))

    components = count_components(faces, len(verts))

    problems = []
    if not mesh.is_watertight:
        problems.append("not watertight")
    if boundary:
        problems.append(f"{boundary} boundary edges (holes)")
    if nonmanifold:
        problems.append(f"{nonmanifold} non-manifold edges (shared by 3+ faces)")
    if degenerate:
        problems.append(f"{degenerate} degenerate (zero-area) faces")
    if duplicates:
        problems.append(f"{duplicates} duplicate faces")

    return {
        "file": str(path),
        "triangles": int(len(faces)),
        "vertices": int(len(verts)),
        "dimensions_mm": [round(float(x), 3) for x in extents],
        "height_mm": round(float(extents[2]), 3),
        "z_min": round(float(bounds[0][2]), 4),
        "z_max": round(float(bounds[1][2]), 4),
        "volume_cm3": round(float(mesh.volume) / 1000.0, 4)
        if mesh.is_volume
        else None,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "components": components,
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "degenerate_faces": degenerate,
        "tiny_faces": tiny,
        "duplicate_faces": duplicates,
        "healthy": not problems,
        "problems": problems,
        "seconds": round(time.time() - t0, 2),
    }


def collect_inputs(paths, recursive):
    """Expand file/folder arguments into a sorted list of STL paths."""
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for pattern in ("*.stl", "*.STL"):
                full = f"**/{pattern}" if recursive else pattern
                files.extend(sorted(p.glob(full)))
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: no such file or folder: {raw}", file=sys.stderr)
    # de-duplicate while keeping order (glob is case-insensitive on some OSes)
    seen = set()
    unique = []
    for f in files:
        key = str(f)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def print_summary(reports, errors):
    for r in reports:
        dims = r["dimensions_mm"]
        status = "OK  " if r["healthy"] else "FAIL"
        print(f"[{status}] {r['file']}")
        print(
            f"       triangles={r['triangles']:,}  components={r['components']}  "
            f"watertight={'yes' if r['watertight'] else 'no'}"
        )
        print(
            f"       size={dims[0]} x {dims[1]} x {dims[2]} mm  "
            f"height={r['height_mm']} mm  volume={r['volume_cm3']} cm3"
        )
        print(
            f"       boundary_edges={r['boundary_edges']}  "
            f"nonmanifold_edges={r['nonmanifold_edges']}  "
            f"degenerate_faces={r['degenerate_faces']}  "
            f"duplicate_faces={r['duplicate_faces']}  tiny_faces={r['tiny_faces']}"
        )
        for problem in r["problems"]:
            print(f"       ! {problem}")
    for path, message in errors:
        print(f"[ERR ] {path}: {message}")
    ok = sum(1 for r in reports if r["healthy"])
    print(
        f"\n{len(reports)} file(s) checked: {ok} healthy, "
        f"{len(reports) - ok} failed, {len(errors)} unreadable."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="stl-doctor",
        description="Health check for STL files: watertightness, components, "
        "boundary edges, degenerate faces, dimensions and triangle count.",
    )
    parser.add_argument(
        "paths", nargs="+", help="STL files and/or folders containing STLs"
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="recurse into subfolders when a folder is given",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="also write the full JSON report to FILE",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the JSON report to stdout instead of the text summary",
    )
    args = parser.parse_args(argv)

    files = collect_inputs(args.paths, args.recursive)
    if not files:
        print("error: no STL files found in the given paths", file=sys.stderr)
        return 2

    reports = []
    errors = []
    for f in files:
        try:
            reports.append(check_file(f))
        except Exception as exc:  # unreadable / not a mesh: report, don't crash
            errors.append((str(f), str(exc)))

    if args.json:
        print(json.dumps(reports, indent=1))
    else:
        print_summary(reports, errors)

    if args.output:
        Path(args.output).write_text(json.dumps(reports, indent=1))

    if errors:
        return 2
    return 0 if all(r["healthy"] for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
