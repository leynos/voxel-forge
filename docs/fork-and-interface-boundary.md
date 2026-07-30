# Fork and interface boundary

This document records the contract between VoxelForge and any game or
pipeline that consumes its output, and the licence position that applies
to changes made in this repository. It exists so a contributor can tell,
from the repository alone, which changes are in scope for the shared
format and which are not.

## The interface is a format, never a library

The interface between VoxelForge and a consuming project is a file
format plus a command-line contract:

- VoxelForge reads and writes files — its own scene JSON, MagicaVoxel
  `.vox`, Wavefront `.obj`, and any consumer scene format it learns to
  emit — and exposes command-line and MCP entry points to do so.
- VoxelForge takes no dependency on a consuming project. Where a
  consumer publishes a machine-readable specification (such as a JSON
  Schema for its scene document), VoxelForge consumes that specification
  as data, pinned by version and vendored, rather than importing the
  consumer's code.
- A consuming project vendors no VoxelForge code. It invokes the
  installed tool and reads the files the tool produces.

The boundary is deliberate and architectural: VoxelForge is content
tooling, not runtime. A code boundary that is never crossed is the
cheapest way to keep that true. Changes that would turn the interface
into a shared library — in either direction — are out of scope.

## What is in scope

- Changes that improve VoxelForge as a stand-alone tool.
- Changes that let VoxelForge read or write a format a consumer
  publishes, driven by that format's published specification.
- Fixes and tests that keep the published formats round-tripping
  faithfully.

## Licence position

VoxelForge is MIT-licensed (see [LICENSE](../LICENSE), copyright
thanakon228). The MIT licence imposes no obligation to publish
downstream changes.

This repository nevertheless publishes the changes it makes as a matter
of policy, not licence compliance: downstream projects that depend on
VoxelForge as content tooling benefit from a public, reviewable history,
and the upstream project remains free to take or ignore any of it.

The repository's provenance — its relationship to the upstream
VoxelForge repository and to Goxel — is recorded in
[provenance.md](provenance.md).
