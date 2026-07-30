# Provenance

This document records where the code in this repository comes from, so a
reader can determine the provenance of the format handling without
reading Thai and without taking any claim on trust.

## This repository is a soft fork

This repository, `leynos/voxel-forge`, is a soft fork of
[thanakon228/voxel-forge](https://github.com/thanakon228/voxel-forge),
the original VoxelForge by thanakon228. The fork exists to adapt
VoxelForge as content tooling for downstream projects; changes made here
are published (see
[fork-and-interface-boundary.md](fork-and-interface-boundary.md)) and
upstream remains free to adopt them. The MIT licence and the upstream
copyright notice are retained unchanged.

## Relationship to Goxel

VoxelForge is inspired by [Goxel](https://github.com/guillaumechereau/goxel)
and interoperates with it, but it does not fork Goxel's C code. Goxel is
GPL-3.0; VoxelForge is an independent, MCP-first implementation written
in Python and TypeScript. What the two projects share is interchange
formats, not code:

- the MagicaVoxel `.vox` container, and
- the Wavefront `.obj` mesh format.

A file format is not itself copyrightable, and an independent
implementation of a format carries no obligation from another
implementation's licence.

## The format handling is written to published specifications

The `.vox` reader and writer live in
[`src/voxel_forge/vox_io.py`](../src/voxel_forge/vox_io.py) and were
written against the published MagicaVoxel format specification
(`MagicaVoxel-file-format-vox.txt`, distributed with MagicaVoxel and
mirrored widely), not by translating Goxel's implementation. The writer
emits the version-150 chunk layout — `MAIN` containing `SIZE`, `XYZI`,
and `RGBA` — and the reader accepts the same. The `.obj` writer emits
plain vertex and face statements as described by the format's public
documentation.

Contract tests in [`tests/`](../tests) pin the chunk ordering and
round-trip behaviour, so the claim above is checked by the test suite
rather than asserted only in prose.
