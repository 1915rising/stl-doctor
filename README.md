# stl-doctor

A small command-line health check for STL files. Point it at one file, a
list of files, or a whole folder, and it tells you whether each mesh is
actually safe to slice, print, or build on — before your slicer finds out
the hard way.

## What it reports

For every STL:

- **watertight** — is the mesh a closed solid?
- **components** — how many disconnected shells it contains
- **boundary edges** — edges used by only one face (holes in the surface)
- **non-manifold edges** — edges shared by 3 or more faces
- **degenerate faces** — zero-area triangles
- **duplicate faces** — identical triangles stacked on each other
- **tiny faces** — triangles with area below 1e-4 mm², including zero-area
  ones (reported, not by itself a failure)
- **dimensions** — bounding box (X × Y × Z, mm) and sole-to-crown height
- **triangle / vertex counts** and enclosed **volume** (when the mesh is a
  valid volume)

A file **fails** if it is not watertight, or has any boundary edges,
non-manifold edges, degenerate faces, or duplicate faces. The exit code is
`0` when everything passes, `1` when any file fails, and `2` on usage or
load errors — so it drops straight into scripts and CI.

## Usage

```bash
# one file, human-readable summary
python3 stl_doctor.py model.stl

# several files
python3 stl_doctor.py bracket.stl gear.stl housing.stl

# a whole folder (add -r to recurse into subfolders)
python3 stl_doctor.py ./prints/
python3 stl_doctor.py -r ./prints/

# machine-readable output
python3 stl_doctor.py --json model.stl
python3 stl_doctor.py ./prints/ -o report.json
```

Example output:

```text
[OK  ] bracket.stl
       triangles=12,480  components=1  watertight=yes
       size=40.0 x 40.0 x 57.2 mm  height=57.2 mm  volume=8.46 cm3
       boundary_edges=0  nonmanifold_edges=0  degenerate_faces=0  duplicate_faces=0  tiny_faces=10
[FAIL] gear.stl
       triangles=96,204  components=3  watertight=no
       size=52.0 x 52.0 x 18.0 mm  height=18.0 mm  volume=None cm3
       boundary_edges=1,204  nonmanifold_edges=0  degenerate_faces=2  duplicate_faces=0  tiny_faces=0
       ! not watertight
       ! 1204 boundary edges (holes)
       ! 2 degenerate (zero-area) faces

2 file(s) checked: 1 healthy, 1 failed, 0 unreadable.
```

## Requirements

- Python 3.9+
- [trimesh](https://trimsh.org/) and NumPy

```bash
pip install -r requirements.txt
```

## How it works

Vertices are welded first (`merge_vertices`), because raw STL stores three
unshared vertices per triangle — without welding, every edge looks like a
boundary edge and every triangle looks like its own component. All checks
run on the welded mesh: edge-sharing counts find holes and non-manifold
edges, face areas find degenerate triangles, and connected-component
splitting counts the shells.

## Tested on

Validated against a corpus of 46 miniature STL files (roughly 130k–5.4M
triangles each). Spot-checked files reproduce the reference audit numbers
exactly — triangle counts, dimensions, volumes, watertight verdicts,
component counts, boundary/non-manifold edge counts, degenerate-face
counts, and tiny-face counts — including a 5.4M-triangle plate with known
defects (2 non-manifold edges, 2 degenerate faces, 21 components) and the
same plate after repair (watertight, 0 defects, identical volume).

STL is a universal format and the checks are purely geometric, so the tool
should behave the same on any STL. That said, honestly: other corpora
(engineering CAD exports, scans, other slicers' output) have not been
tested yet. If you find a file it gets wrong, please open an issue with
the file attached if you can share it.

## License

MIT — see [LICENSE](LICENSE).
