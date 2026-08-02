#!/usr/bin/env python3
"""Pre-fetch every TeX package the real reports need, at image build time.

tectonic ships as a ~30MB binary and downloads its TeX packages on demand,
caching them under ``TECTONIC_CACHE_DIR``. Left to itself that download happens
during a user's *first* PDF export, inside the compile subprocess timeout, and
if it does not finish in time the export silently drops to the weasyprint
HTML->PDF fallback. Which means:

  * a fresh install's first report is worse than every later one, for no reason
    the operator can see;
  * an air-gapped install can never produce a LaTeX report at all;
  * the deployment's behaviour depends on the network at an arbitrary moment.

So the packages are fetched here, during ``docker build``, and baked into the
image. A container then starts with a warm cache and needs no network to render.

The document compiled is a *real report*, generated from the seeded demo
project through ``Publisher.build_latex`` — not a hand-written stand-in. A
stand-in would list the packages it thinks the preamble uses, and would silently
stop matching the day someone adds one; then the build would still pass and the
first real export would go back to downloading. Driving the actual generator
means the warm cache is correct by construction.

Exits non-zero if the compile fails, so a broken image cannot ship.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    cache = os.environ.get("TECTONIC_CACHE_DIR")
    print(f"warm-tectonic: cache dir = {cache or '(default, per-user)'}")
    if not cache:
        print("warm-tectonic: refusing to warm an unset cache dir — the result "
              "would land in $HOME and be lost or unreadable at runtime.",
              file=sys.stderr)
        return 2

    from app.services.demo_seed import seed_demo_project
    from app.services.publisher import Publisher, latex_engine_available
    from app.services.yaml_store import YamlStore

    engine = latex_engine_available()
    if engine is None:
        print("warm-tectonic: no LaTeX engine on PATH", file=sys.stderr)
        return 3
    print(f"warm-tectonic: engine = {engine}")

    with tempfile.TemporaryDirectory(prefix="warm-tectonic-") as tmp:
        root = Path(tmp) / "projects"
        root.mkdir(parents=True)
        seed_demo_project(root)
        project = next(p for p in root.iterdir() if p.is_dir())

        latex = Publisher(YamlStore(project), None).build_latex(None, "", "")
        print(f"warm-tectonic: generated {len(latex):,} chars of LaTeX")

        out = Path(tmp) / "warm.pdf"
        # Imported late so the module-level import cost is not paid when this
        # script is only being asked for its docstring.
        from app.services.publisher import compile_latex_to_pdf

        # tectonic downloads its TeX packages during this compile, so the step
        # depends on a third-party package server at image-build time. A single
        # failed fetch used to fail the whole build — observed once, then
        # succeeding unchanged on the next run. Retrying is cheap next to
        # rebuilding the image, and each attempt leaves the cache warmer than
        # it found it, so a later attempt has less to fetch.
        #
        # It still exits non-zero once the attempts are spent: the point of
        # warming is that a broken image cannot ship, and a retry loop that
        # gives up quietly would defeat it.
        attempts = max(1, int(os.environ.get("WARM_TECTONIC_ATTEMPTS", "3")))
        # Generous per attempt: warming *is* the cold-cache case, and a cold
        # fetch on a slow link has been seen to take ~120s.
        timeout = int(os.environ.get("WARM_TECTONIC_TIMEOUT", "600"))

        ok = False
        started = time.time()
        for attempt in range(1, attempts + 1):
            began = time.time()
            ok = compile_latex_to_pdf(latex, str(out), timeout=timeout)
            took = time.time() - began
            if ok and out.exists() and out.stat().st_size > 0:
                if attempt > 1:
                    print(f"warm-tectonic: attempt {attempt} succeeded after "
                          f"{attempt - 1} failure(s)")
                break
            ok = False
            print(f"warm-tectonic: attempt {attempt}/{attempts} failed after "
                  f"{took:.1f}s", file=sys.stderr)
            if attempt < attempts:
                backoff = 5 * attempt
                print(f"warm-tectonic: retrying in {backoff}s", file=sys.stderr)
                time.sleep(backoff)

        elapsed = time.time() - started

        if not ok:
            print(f"warm-tectonic: compile FAILED after {attempts} attempt(s), "
                  f"{elapsed:.1f}s total", file=sys.stderr)
            return 1

        size = out.stat().st_size
        cached = sum(f.stat().st_size for f in Path(cache).rglob("*") if f.is_file()) \
            if Path(cache).exists() else 0
        print(f"warm-tectonic: compiled {size:,} bytes of PDF in {elapsed:.1f}s")
        print(f"warm-tectonic: cache now {cached / 1e6:.0f} MB")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
