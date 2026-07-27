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

### Tectonic

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

## Bundled binaries (desktop build)

The Electron desktop build (`desktop/`, packaged by electron-builder) ships a
complete application runtime inside the installer. Unlike tectonic above, this is
not mere aggregation: reqmesh's frontend is loaded and executed *by* that runtime.
The combination is nonetheless sound, because every component is under a
permissive, GPL-compatible license — recording them here is a notice obligation,
not a conflict.

### Electron

- **Used for:** the desktop shell — it starts the reqmesh backend as a child
  process and renders the existing web UI in a native window (`desktop/main.js`).
- **License:** MIT License.
- **Copyright:** © Electron contributors; © 2013–2020 GitHub Inc.
- **Homepage:** https://www.electronjs.org/
- **Source:** https://github.com/electron/electron

Electron in turn embeds two large runtimes, which are redistributed as part of
the packaged application:

- **Chromium** — BSD-3-Clause for Chromium's own source, plus a substantial set
  of third-party licenses for its bundled components.
- **Node.js** — MIT License, itself bundling components under MIT, BSD and
  similar terms.

Electron ships the authoritative, version-specific text for both as
`LICENSES.chromium.html` in its distribution, and its own terms as `LICENSE`.
Those files are the correct reference rather than a list transcribed here, which
would drift out of date at every Electron upgrade. Both are present in the
unpacked application directory of a built installer.

`electron-builder` is a build-time tool only (MIT) and is not redistributed.

The desktop build's own code is licensed GPL-3.0-or-later along with the rest of
reqmesh; see `desktop/package.json`.
