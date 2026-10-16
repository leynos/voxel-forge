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
3. **No file in that history carries a suffix associated with C, C++, Rust,
   or Go source.** This is checked by enumerating every filename suffix the
   history contains, rather than by naming the suffixes each language "usually"
   uses — a list that is easy to get subtly wrong. Running:

   ```sh
   git log --all --format= --name-only | sort -u | grep -oE '\.[^./]+$' | sort -u
   ```

   reports fifteen suffixes and no others:

   ```text
   .bat .gitignore .html .json .jsonc .lock .md .mjs .py .spec .toml .ts
   .txt .yaml .yml
   ```

   Those account for 126 of the 128 paths in history; the remainder are
   `LICENSE` and `Makefile`, which carry no suffix. The enumeration therefore
   leaves nothing over, so a `.c`, `.h`, `.cpp`, `.hpp`, `.cc`, `.rs`, `.go`,
   `.cxx`, `.hh`, or `.hxx` file would have to appear in that list to exist.

   **A suffix census reads names, not contents**, so it cannot see compiled
   source stored under an unrelated suffix — C in a `.txt`, or in the
   suffixless `LICENSE` or `Makefile`. That case is covered by scanning the
   contents of every blob the history reaches, which needs no assumption about
   naming at all:

   ```sh
   git rev-list --all --objects | awk 'NF > 1 { print $1 }' | sort -u |
     git cat-file --batch-check='%(objecttype) %(objectname)' |
     awk '$1 == "blob" { print $2 }' |
     git cat-file --batch --buffer |
     grep -acE '#include[[:space:]]*[<"]|(fn|func)[[:space:]]+main[[:space:]]*\(|^[[:space:]]*package[[:space:]]+main'
   ```

   This reads every blob in the repository — several hundred of them, a few
   megabytes — and prints `0`. No exact count is given, because the number
   changes with every commit that touches this file: the document is itself one
   of the blobs the scan reads. The result is what carries the finding, and it
   does not move with the count.

   Read that `0` as the absence of the marker forms the expression names, and
   no more: a C-family preprocessor include directive, in either its
   angle-bracket or its quoted form, plus the entry-point declarations Rust and
   Go conventionally carry and an unindented Go package clause naming `main`.
   It does **not** by itself detect a bare C or C++ `int main(void)`, which
   carries none of those, so it is not a general test for compiled source. Two
   further limits apply. It matches markers conventional sources happen to
   carry rather than source of any conceivable shape, and it is a content test
   rather than an authorship test: a translation of Goxel's algorithms into
   Python would contain none of these markers and would pass it. What it rules
   out is the specific escape the suffix census leaves open — compiled source
   stored under a name that does not advertise it — and it rules that out only
   for the marker forms listed.

   Note that this document is itself one of the blobs the scan reads, so the
   marker forms are described here in words rather than written out. Spelling
   one of them literally on this page would make the scan match this file and
   report a nonzero count, which is a property of the audit rather than of the
   repository.

   Both commands should run on a full (non-shallow) clone, because both derive
   their paths from the commits actually fetched; a full clone is still not a
   guarantee that every remote ref was fetched. `git ls-files` is not a
   substitute for either: it sees just the current index and would miss source
   deleted in an earlier commit. Read both results as findings about names and
   markers in the inspected history — not as a proof that no such source exists
   in any form.
4. **Every Goxel reference in this repository is descriptive.** "Goxel" appears
   only in format and attribution contexts — for example `vox_io.py`'s
   "Goxel-compatible format" and `__init__.py`'s "Goxel-inspired". None refers
   to translated code.

### What this evidence does not establish

This is a source-history audit, not a clean-room attestation. It reports that
no filename suffix in the history identifies conventional C, C++, Rust, or Go
source, that no reachable blob matches the marker expression in item 3, and
that upstream asserts independent authorship. It cannot prove the absence of an
undocumented translation, because no test and no repository audit can establish
which source material an author consulted. Treat the claim as well-supported
and author-asserted, not as independently adjudicated.

Two limits apply specifically to the path enumeration in item 3, because
`git log --all --format= --name-only` lists paths reported by commit diffs:

- **It does not, by default, report merge diffs.** A file introduced only while
  resolving a merge conflict could therefore escape the listing, and
  reconciling counts taken from that same listing would not reveal the gap. In
  this repository it cannot have done so: the history contains **no merge
  commits**, so no merge diff exists to be omitted. This was checked with
  `git rev-list --all --merges --count`, which returns `0`.

  That check disposes of the merge concern, but it does not on its own show
  that the path list is complete. An independent enumeration does, by reading
  the tree of every reachable commit rather than any diff:

  ```sh
  git rev-list --all | while read -r commit; do
    git ls-tree -r --name-only "$commit"
  done | sort -u
  ```

  This returns the same 128 paths as the diff-based census, so the two methods
  agree exactly. The tree walk is the stronger of the two and is the one that
  establishes coverage: it reports every entry of every reachable commit's tree
  and does not depend on which commit happened to introduce a path.

  The content scan above should **not** be used for this purpose. Deriving
  paths from `git rev-list --all --objects` undercounts them, because that
  listing reports each reachable object once: where the same content sits at
  two paths, it need only name one, so the other vanishes from the list. On a
  two-file fixture holding identical bytes at `a/one.c` and `b/two.c`, the
  object listing reports only `a/one.c`. It happens to yield 128 paths here,
  matching the tree walk, but that agreement is not what proves the census
  complete.
- **Git may quote unusual path names.** With `core.quotePath` at its default of
  true, a line-oriented census parses the quoted form, so a path ending in
  `.cxx` could be reported with a trailing quote and miss the pattern. This is
  live rather than hypothetical — quoting is enabled here — but nothing in this
  history triggers it: no path contains a non-ASCII or otherwise quotable
  character, and enumerating with NUL-delimited records (`git log --all
  --format= --name-only -z`) yields the same pathname records as the line-based
  form once both are split. The raw streams are of course not comparable
  directly — one separates records with NUL and the other with newline, so they
  differ by construction for any non-empty listing. The comparison is between
  the records, not the bytes.

Neither limit is discharged by argument above; both were checked against the
actual history, and the figures are given so a reader can check them again.

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
