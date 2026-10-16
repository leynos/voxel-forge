# Provenance

This document records where the code in this repository comes from, so a reader
can determine the provenance of the format handling without reading Thai and
without taking any claim on trust.

## This repository is a soft fork

This repository, `leynos/voxel-forge`, is a soft fork of
[thanakon228/voxel-forge](https://github.com/thanakon228/voxel-forge), the
original VoxelForge by thanakon228. The fork exists to adapt VoxelForge as
content tooling for downstream projects; changes made here are published (see
[fork-and-interface-boundary.md](fork-and-interface-boundary.md)) and upstream
remains free to adopt them. The MIT licence and the upstream copyright notice
are retained unchanged.

## Relationship to Goxel

VoxelForge is inspired by [Goxel](https://github.com/guillaumechereau/goxel)
and interoperates with it, but it does not fork Goxel's C code. Goxel is
GPL-3.0; VoxelForge is an independent, MCP-first implementation written in
Python and TypeScript. What the two projects share is interchange formats, not
code:

- the MagicaVoxel `.vox` container, and
- the Wavefront `.obj` mesh format.

A file format is not itself copyrightable, and an independent implementation of
a format carries no obligation from another implementation's licence.

## Evidence for that claim

The claim rests on the repository's own history, which a reader can verify
without leaving this checkout:

1. **The upstream author states it.** Upstream's `README.md` describes
   VoxelForge as a new MCP-first implementation that does not fork Goxel's C
   code — a claim made by the author of the code, not by this fork.[^1]
2. **The repository's first commit is upstream's.** Running `git rev-list
   --max-parents=0 HEAD` yields `b2c8a9b`, and that commit is byte-identical to
   upstream's `main`: the same commit SHA and the same tree (`bd01083`). This
   repository's history therefore begins as upstream's published history and
   adds to it; no separately authored body of code is joined in.
3. **No C, C++, Rust, or Go source exists anywhere in that history.** Running
   `git ls-files | grep -Ei '\.(c|h|cpp|cc)$'` prints nothing, and the same
   holds across every commit reachable from any ref. A fork of Goxel would have
   to carry Goxel's C sources to be a fork; this repository never has.
4. **Every Goxel reference in this repository is descriptive.** "Goxel" appears
   only in format and attribution contexts — for example `vox_io.py`'s
   "Goxel-compatible format" and `__init__.py`'s "Goxel-inspired". None refers
   to translated code.

### What this evidence does not establish

This is a source-history audit, not a clean-room attestation. It shows that no
Goxel source is present and that upstream asserts independent authorship. It
cannot prove the absence of an undocumented translation, because no test and no
repository audit can establish which source material an author consulted. Treat
the claim as well-supported and author-asserted, not as independently
adjudicated.

## The format handling is written to published specifications

The `.vox` reader and writer live in
[`src/voxel_forge/vox_io.py`](../src/voxel_forge/vox_io.py) and implement the
published MagicaVoxel format specification, `MagicaVoxel-file-format-vox.txt`
(pinned here to the file's most recent revision),[^2] not Goxel's
implementation. The writer emits the version-150 chunk layout that
specification defines — `MAIN` containing `SIZE`, `XYZI`, and `RGBA` — and the
reader accepts the same. The `.obj` writer emits plain vertex (`v`) and face
(`f`) statements as described by the OBJ format's published documentation.[^3]

### The tests are format-conformance evidence

Contract tests in [`tests/`](../tests) pin the chunk ordering and round-trip
behaviour. `tests/test_model_readiness.py` asserts that the exported children
appear in `SIZE`, `XYZI`, `RGBA` order, and `tests/readiness_helpers.py` parses
the `MAIN` chunk's children by identifier, so a change to the layout fails the
suite rather than passing unnoticed.

These tests demonstrate that the implementation conforms to the specification
named above. They are **not** evidence of independent authorship: an
implementation translated from another codebase would satisfy them equally,
because they assert the format's observable contract and not the origin of the
code that produces it. The authorship claim rests on the source-history audit
above.

[^1]: Upstream `README.md`: "VoxelForge เป็น implementation ใหม่ที่ออกแบบ
    MCP-first ไม่ได้ fork โค้ด C ของ Goxel โดยตรง" — "VoxelForge is a new,
    MCP-first implementation that does not directly fork Goxel's C code."

[^2]: <https://github.com/ephtracy/voxel-model/blob/ee2216c28a78ebb68691dc6cfa9c4ba429117ea2/MagicaVoxel-file-format-vox.txt>

[^3]: The OBJ format originates in Appendix B1 of the Wavefront Advanced
    Visualizer 3.0 manual (c. 1992). The Library of Congress format
    description records the copies and their provenance:
    <https://www.loc.gov/preservation/digital/formats/fdd/fdd000507.shtml>
