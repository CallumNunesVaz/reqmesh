# Third-Party Notices

reqmesh is distributed under the GNU General Public License v3.0 or later
(GPL-3.0-or-later, see `LICENSE`). This section records third-party software and
the basis on which it is combined with reqmesh.

## Dependency license compatibility

reqmesh's own code combines, at distribution time, with its dependencies. The
GPL-3.0-or-later choice keeps that combination compatible:

- **elkjs** (graph layout) is offered under `EPL-2.0 OR GPL-3.0-or-later`;
  reqmesh uses it under the **GPL-3.0-or-later** option.
- **bcrypt** and **python-multipart** are Apache-2.0, which is compatible with
  GPLv3 (but not with GPLv2 — the reason reqmesh is GPLv3-or-later rather than v2).
- All remaining dependencies are permissive (MIT, BSD, ISC) and impose no
  combination restrictions.

## Bundled binaries (Docker images)

The Docker images additionally bundle third-party software, invoked as separate
programs (mere aggregation — not linked into reqmesh). Their own licenses apply
to those components:

## Tectonic

- **Used for:** typesetting the LaTeX PDF report (primary PDF export path). When
  tectonic is unavailable, reqmesh falls back to the weasyprint HTML→PDF renderer.
- **License:** MIT License.
- **Copyright:** © The Tectonic Project.
- **Homepage:** https://tectonic-typesetting.github.io/
- **Source:** https://github.com/tectonic-typesetting/tectonic

The MIT License permits redistribution provided the copyright and permission
notice are retained. The full text is available in the tectonic repository at
`LICENSE`.

At runtime, tectonic downloads a bundle of TeX Live packages on demand (cached
under `TECTONIC_CACHE_DIR`). Those packages are **not** shipped inside the
reqmesh image; they are individually licensed under the free/redistributable
terms of the TeX Live distribution (predominantly the LaTeX Project Public
License, LPPL).
