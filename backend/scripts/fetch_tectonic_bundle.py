#!/usr/bin/env python3
"""Fetch the tectonic TeX bundle files the report needs, into the cache.

tectonic compiles against a "bundle" of TeX support files that it normally
downloads on demand from ``relay.fullyjustified.net`` (a ~2.9 GB indexed tarball
— far too large to bake into the image). The old flow let that download happen
*inside* ``warm_tectonic.py`` at image-build time, so the build depended on a
third-party host and failed intermittently (the 3-attempt retry in the warmer
could not help: every attempt re-downloaded from the same host).

This script is the build-time half of the fix. It downloads, once, exactly the
bundle files the two warmed reports pull in, laying them out as the tectonic
*file cache* (the same layout a normal warm produces) keyed to the default
bundle URL. ``warm_tectonic.py`` then compiles entirely from local files, with
the network switched off.

The download itself is done by tectonic, not by curl: the bundle is served by a
CDN that drops connections and rejects plain range requests (403) on large
offsets, while tectonic's own HTTP client is what it expects to talk to. We hand
tectonic a prefetch manifest of the files we know the reports need and compile a
trivial document once; tectonic then fetches the whole working set concurrently
through its own client, with its own retries. An outer loop re-runs tectonic
until every file has landed, because a failed fetch leaves the warmer's retry
loop nothing to work with.

The file list below is not hand-written: it is the set of files tectonic
requested while warming the real report (normal + draft), recorded from an
actual ``warm_tectonic.py`` run against this tectonic version. If the publisher
preamble later pulls in a package that is not listed here, the offline warm will
fail — loudly — and this list must be regenerated, rather than the build
silently going back to the network.

The bundle is pinned the same way the tectonic binary is: a URL plus a recorded
SHA-256. The digest is the bundle's own ``SHA256SUM`` (the value tectonic itself
uses to identify a bundle), which the fetch verifies before trusting the cache
it just built.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Bundle files the two warmed reports need, recorded from a real warm run.
# Flat file names, matching the (flat) entries in the bundle index.
NEEDED_FILES = (
    "array.sty", "article.cls", "atbegshi-ltx.sty", "atbegshi.sty",
    "atveryend-ltx.sty", "atveryend.sty", "auxhook.sty", "bigintcalc.sty",
    "bitset.sty", "booktabs.sty", "CaseFolding.txt", "ckx.map",
    "cmex10.tfm", "cmmi10.pfb", "cmmi10.tfm", "cmmi5.tfm",
    "cmmi6.tfm", "cmmi7.tfm", "cmmi8.tfm", "cmr10.tfm",
    "cmr5.tfm", "cmr6.tfm", "cmr7.tfm", "cmr8.tfm",
    "cmsy10.pfb", "cmsy10.tfm", "cmsy5.tfm", "cmsy6.tfm",
    "cmsy7.pfb", "cmsy7.tfm", "cmsy8.pfb", "cmsy8.tfm",
    "color.cfg", "color.sty", "colortbl.sty", "dehyphn-x-2022-03-16.pat",
    "dehyphn-x-2022-03-16.tex", "dehypht-x-2022-03-16.pat", "dehypht-x-2022-03-16.tex", "draftwatermark.sty",
    "dumyhyph.tex", "enumitem.sty", "etexcmds.sty", "etoolbox.sty",
    "expl3-code.tex", "expl3.ltx", "expl3.sty", "fancyhdr.sty",
    "fontenc.sty", "fontmath.cfg", "fontmath.ltx", "fontspec.cfg",
    "fontspec.sty", "fontspec-xetex.sty", "fonttext.cfg", "fonttext.ltx",
    "geometry.sty", "gettitlestring.sty", "glyphlist.txt", "graphics.cfg",
    "graphics.sty", "graphicx.sty", "hxetex.def", "hycolor.sty",
    "hyperref.sty", "hyph-af.tex", "hyph-as.tex", "hyph-be.tex",
    "hyph-bg.tex", "hyph-bn.tex", "hyph-ca.tex", "hyph-cop.tex",
    "hyph-cs.tex", "hyph-cu.tex", "hyph-cy.tex", "hyph-da.tex",
    "hyph-de-1901.tex", "hyph-de-1996.tex", "hyph-de-ch-1901.tex", "hyph-el-monoton.tex",
    "hyph-el-polyton.tex", "hyphen.cfg", "hyph-en-gb.tex", "hyphen.tex",
    "hyph-en-us.tex", "hyph-eo.tex", "hyph-es.tex", "hyph-et.tex",
    "hyph-eu.tex", "hyph-fi.tex", "hyph-fi-x-school.tex", "hyph-fr.tex",
    "hyph-fur.tex", "hyph-ga.tex", "hyph-gl.tex", "hyph-grc.tex",
    "hyph-gu.tex", "hyph-hi.tex", "hyph-hr.tex", "hyph-hsb.tex",
    "hyph-hu.tex", "hyph-hy.tex", "hyph-ia.tex", "hyph-id.tex",
    "hyph-is.tex", "hyph-it.tex", "hyph-ka.tex", "hyph-kmr.tex",
    "hyph-kn.tex", "hyph-la.tex", "hyph-la-x-classic.tex", "hyph-la-x-liturgic.tex",
    "hyph-lt.tex", "hyph-lv.tex", "hyph-mk.tex", "hyph-ml.tex",
    "hyph-mn-cyrl.tex", "hyph-mn-cyrl-x-lmc.tex", "hyph-mr.tex", "hyph-mul-ethi.tex",
    "hyph-nb.tex", "hyph-nl.tex", "hyph-nn.tex", "hyph-no.tex",
    "hyph-oc.tex", "hyph-or.tex", "hyph-pa.tex", "hyph-pi.tex",
    "hyph-pl.tex", "hyph-pms.tex", "hyph-pt.tex", "hyph-quote-af.tex",
    "hyph-quote-be.tex", "hyph-quote-fr.tex", "hyph-quote-fur.tex", "hyph-quote-it.tex",
    "hyph-quote-oc.tex", "hyph-quote-pms.tex", "hyph-quote-rm.tex", "hyph-quote-uk.tex",
    "hyph-rm.tex", "hyph-ro.tex", "hyph-ru.tex", "hyph-sa.tex",
    "hyph-sh-cyrl.tex", "hyph-sh-latn.tex", "hyph-sk.tex", "hyph-sl.tex",
    "hyph-sv.tex", "hyph-ta.tex", "hyph-te.tex", "hyph-th.tex",
    "hyph-tk.tex", "hyph-tr.tex", "hyph-uk.tex", "hyph-zh-latn-pinyin.tex",
    "ibyhyph.tex", "ifluatex.sty", "iftex.sty", "ifthen.sty",
    "ifvtex.sty", "ifxetex.sty", "infwarerr.sty", "intcalc.sty",
    "Inter-BlackItalic.otf", "Inter-Black.otf", "Inter-BoldItalic.otf", "Inter-Bold.otf",
    "Inter-ExtraBoldItalic.otf", "Inter-ExtraBold.otf", "Inter-ExtraLightItalic.otf", "Inter-ExtraLight.otf",
    "Inter-Italic.otf", "Inter-LightItalic.otf", "Inter-Light.otf", "Inter-MediumItalic.otf",
    "Inter-Medium.otf", "Inter-Regular.otf", "Inter-SemiBoldItalic.otf", "Inter-SemiBold.otf",
    "inter.sty", "Inter-ThinItalic.otf", "Inter-Thin.otf", "kanjix.map",
    "keyval.sty", "keyval.tex", "kvdefinekeys.sty", "kvoptions.sty",
    "kvsetkeys.sty", "l3backend-xetex.def", "language.dat", "lastpage.sty",
    "latex2e-first-aid-for-external-files.ltx", "latex.ltx", "lcircle10.tfm", "lcirclew10.tfm",
    "letltxmacro.sty", "line10.tfm", "linew10.tfm", "lmroman10-bold.otf",
    "lmroman10-regular.otf", "lmroman5-regular.otf", "lmroman6-regular.otf", "lmroman7-regular.otf",
    "lmroman8-regular.otf", "loadhyph-af.tex", "loadhyph-as.tex", "loadhyph-be.tex",
    "loadhyph-bg.tex", "loadhyph-bn.tex", "loadhyph-ca.tex", "loadhyph-cop.tex",
    "loadhyph-cs.tex", "loadhyph-cu.tex", "loadhyph-cy.tex", "loadhyph-da.tex",
    "loadhyph-de-1901.tex", "loadhyph-de-1996.tex", "loadhyph-de-ch-1901.tex", "loadhyph-el-monoton.tex",
    "loadhyph-el-polyton.tex", "loadhyph-en-gb.tex", "loadhyph-en-us.tex", "loadhyph-eo.tex",
    "loadhyph-es.tex", "loadhyph-et.tex", "loadhyph-eu.tex", "loadhyph-fi.tex",
    "loadhyph-fi-x-school.tex", "loadhyph-fr.tex", "loadhyph-fur.tex", "loadhyph-ga.tex",
    "loadhyph-gl.tex", "loadhyph-grc.tex", "loadhyph-gu.tex", "loadhyph-hi.tex",
    "loadhyph-hr.tex", "loadhyph-hsb.tex", "loadhyph-hu.tex", "loadhyph-hy.tex",
    "loadhyph-ia.tex", "loadhyph-id.tex", "loadhyph-is.tex", "loadhyph-it.tex",
    "loadhyph-ka.tex", "loadhyph-kmr.tex", "loadhyph-kn.tex", "loadhyph-la.tex",
    "loadhyph-la-x-classic.tex", "loadhyph-la-x-liturgic.tex", "loadhyph-lt.tex", "loadhyph-lv.tex",
    "loadhyph-mk.tex", "loadhyph-ml.tex", "loadhyph-mn-cyrl.tex", "loadhyph-mn-cyrl-x-lmc.tex",
    "loadhyph-mr.tex", "loadhyph-mul-ethi.tex", "loadhyph-nb.tex", "loadhyph-nl.tex",
    "loadhyph-nn.tex", "loadhyph-oc.tex", "loadhyph-or.tex", "loadhyph-pa.tex",
    "loadhyph-pi.tex", "loadhyph-pl.tex", "loadhyph-pms.tex", "loadhyph-pt.tex",
    "loadhyph-rm.tex", "loadhyph-ro.tex", "loadhyph-ru.tex", "loadhyph-sa.tex",
    "loadhyph-sk.tex", "loadhyph-sl.tex", "loadhyph-sr-cyrl.tex", "loadhyph-sr-latn.tex",
    "loadhyph-sv.tex", "loadhyph-ta.tex", "loadhyph-te.tex", "loadhyph-th.tex",
    "loadhyph-tk.tex", "loadhyph-tr.tex", "loadhyph-uk.tex", "loadhyph-zh-latn-pinyin.tex",
    "load-unicode-data.tex", "longtable.sty", "ltxcmds.sty", "makecell.sty",
    "nameref.sty", "omlcmm.fd", "omlenc.def", "omscmsy.fd",
    "omsenc.def", "omxcmex.fd", "ot1cmr.fd", "ot1cmss.fd",
    "ot1cmtt.fd", "ot1enc.def", "parskip.sty", "pd1enc.def",
    "pdfescape.sty", "pdfglyphlist.txt", "pdftexcmds.sty", "pdftex.map",
    "pgf.cfg", "pgfcomp-version-0-65.sty", "pgfcomp-version-1-18.sty", "pgfcorearrows.code.tex",
    "pgfcore.code.tex", "pgfcoreexternal.code.tex", "pgfcoregraphicstate.code.tex", "pgfcoreimage.code.tex",
    "pgfcorelayers.code.tex", "pgfcoreobjects.code.tex", "pgfcorepathconstruct.code.tex", "pgfcorepathprocessing.code.tex",
    "pgfcorepathusage.code.tex", "pgfcorepatterns.code.tex", "pgfcorepoints.code.tex", "pgfcorequick.code.tex",
    "pgfcorerdf.code.tex", "pgfcorescopes.code.tex", "pgfcoreshade.code.tex", "pgfcore.sty",
    "pgfcoretransformations.code.tex", "pgfcoretransparency.code.tex", "pgffor.code.tex", "pgffor.sty",
    "pgfint.code.tex", "pgfkeys.code.tex", "pgfkeysfiltered.code.tex", "pgfkeys.sty",
    "pgflibraryplothandlers.code.tex", "pgfmathcalc.code.tex", "pgfmath.code.tex", "pgfmathfloat.code.tex",
    "pgfmathfunctions.base.code.tex", "pgfmathfunctions.basic.code.tex", "pgfmathfunctions.code.tex", "pgfmathfunctions.comparison.code.tex",
    "pgfmathfunctions.integerarithmetics.code.tex", "pgfmathfunctions.misc.code.tex", "pgfmathfunctions.random.code.tex", "pgfmathfunctions.round.code.tex",
    "pgfmathfunctions.trigonometric.code.tex", "pgfmathparser.code.tex", "pgfmath.sty", "pgfmathutil.code.tex",
    "pgfmodulematrix.code.tex", "pgfmoduleplot.code.tex", "pgfmoduleshapes.code.tex", "pgfrcs.code.tex",
    "pgfrcs.sty", "pgf.revision.tex", "pgf.sty", "pgfsys.code.tex",
    "pgfsys-common-pdf.def", "pgfsys-dvipdfmx.def", "pgfsysprotocol.code.tex", "pgfsyssoftpath.code.tex",
    "pgfsys.sty", "pgfsys-xetex.def", "pgfutil-common-lists.tex", "pgfutil-common.tex",
    "pgfutil-latex.def", "preload.cfg", "preload.ltx", "puenc.def",
    "pzdr.tfm", "ragged2e.sty", "refcount.sty", "rerunfilecheck.sty",
    "size11.clo", "SourceCodePro-BlackIt.otf", "SourceCodePro-Black.otf", "SourceCodePro-BoldIt.otf",
    "SourceCodePro-Bold.otf", "SourceCodePro-ExtraLightIt.otf", "SourceCodePro-ExtraLight.otf", "SourceCodePro-LightIt.otf",
    "SourceCodePro-Light.otf", "SourceCodePro-MediumIt.otf", "SourceCodePro-Medium.otf", "SourceCodePro-RegularIt.otf",
    "SourceCodePro-Regular.otf", "SourceCodePro-SemiboldIt.otf", "SourceCodePro-Semibold.otf", "sourcecodepro.sty",
    "SpecialCasing.txt", "stringenc.sty", "t1cmr.fd", "t1enc.def",
    "tabularx.sty", "tectonic-format-latex.tex", "texglyphlist.txt", "texsys.cfg",
    "textcomp.sty", "tex-text.tec", "tikz.code.tex", "tikzlibrarytopaths.code.tex",
    "tikz.sty", "titlesec.sty", "titletoc.sty", "trig.sty",
    "ts1cmr.fd", "ts1enc.def", "ts1lmr.fd", "tuenc.def",
    "tulmr.fd", "tulmss.fd", "tulmtt.fd", "ucmr.fd",
    "UnicodeData.txt", "uniquecounter.sty", "url.sty", "xcolor.sty",
    "xebabel.def", "xelatex.ini", "xetex.def", "xkeyval.sty",
    "xkeyval.tex", "xkvutils.tex", "xparse.sty", "xstring.sty",
    "xstring.tex", "zerohyph.tex",
)

# A document that is small enough to compile for free but forces tectonic to
# generate the format and touch its bundle, which is what triggers the prefetch
# of the manifest above. 11pt keeps it on size11.clo, which the report also
# uses, so no report-unrelated files leak into the cache.
TRIVIAL_DOC = (
    r"\documentclass[11pt]{article}" "\n"
    r"\begin{document}" "\n"
    r"reqmesh" "\n"
    r"\end{document}" "\n"
)


def _sanitize(url: str) -> str:
    # Mirror tectonic_bundles::app_dirs::sanitize: it turns the bundle URL into
    # the cache key under bundles/hashes/, so it must match byte-for-byte.
    out: list[str] = []
    for i, ch in enumerate(url):
        if ch.isascii() and (ch.isalnum() or ch in " -_" or (ch == "." and i != 0)):
            out.append(ch)
        else:
            out.append(f",{ord(ch)},")
    return "".join(out)


def _fetch_once(bundle_url: str, doc: Path, outdir: Path) -> str:
    # Each pass downloads whatever is still missing (tectonic skips files already
    # in the cache), so a flaky CDN only costs another pass. The timeout mirrors
    # the warmer's own per-attempt budget; a pass that is cut short keeps every
    # file it managed to fetch. Returns tectonic's stderr for diagnosis.
    proc = subprocess.run(
        ["tectonic", "--bundle", bundle_url, "--outdir", str(outdir),
         "--keep-logs", str(doc)],
        cwd=str(outdir), capture_output=True, timeout=600,
    )
    return proc.stderr.decode("utf-8", "replace")


def main() -> int:
    bundle_url = os.environ["TECTONIC_BUNDLE_URL"]
    digest = os.environ["TECTONIC_BUNDLE_SHA256"].strip().lower()
    cache_dir = Path(os.environ["TECTONIC_CACHE_DIR"])

    key = _sanitize(bundle_url)
    data_dir = cache_dir / "bundles" / "data"
    hashes_dir = cache_dir / "bundles" / "hashes"
    data_dir.mkdir(parents=True, exist_ok=True)
    hashes_dir.mkdir(parents=True, exist_ok=True)

    # The prefetch manifest is what turns one trivial compile into a download of
    # the whole working set: tectonic replays it concurrently on a cold cache.
    (data_dir / f"{key}.prefetch").write_text(
        "\n".join(NEEDED_FILES) + "\n", encoding="ascii")

    with tempfile.TemporaryDirectory(prefix="fetch-tectonic-") as tmp:
        doc = Path(tmp) / "doc.tex"
        doc.write_text(TRIVIAL_DOC, encoding="ascii")
        outdir = Path(tmp) / "out"
        outdir.mkdir()

        # Each pass downloads whatever is still missing (tectonic skips files
        # already in the cache), so a flaky CDN only costs another pass, not a
        # full re-download.
        for attempt in range(1, 11):
            last_stderr = ""
            try:
                last_stderr = _fetch_once(bundle_url, doc, outdir)
            except subprocess.TimeoutExpired:
                pass  # progress is preserved; fall through to the completeness check
            hash_file = hashes_dir / key
            if not hash_file.exists():
                print(f"fetch-tectonic-bundle: attempt {attempt}: no bundle digest yet; "
                      "retrying", file=sys.stderr)
            else:
                recorded = hash_file.read_text(encoding="ascii").strip().lower()
                if recorded != digest:
                    print(f"fetch-tectonic-bundle: bundle digest mismatch: expected "
                          f"{digest}, got {recorded}", file=sys.stderr)
                    return 1
                digest_dir = data_dir / digest
                missing = [n for n in NEEDED_FILES if not (digest_dir / n).is_file()]
                if not missing:
                    break
                print(f"fetch-tectonic-bundle: attempt {attempt}: {len(missing)} files "
                      f"still missing; retrying", file=sys.stderr)
            time.sleep(5)
        else:
            print("fetch-tectonic-bundle: bundle download incomplete after 10 attempts",
                  file=sys.stderr)
            if last_stderr.strip():
                print(f"--- tectonic stderr (last 2000 chars) ---\n"
                      f"{last_stderr.strip()[-2000:]}", file=sys.stderr)
            return 1

    digest_dir = data_dir / digest
    total = sum(f.stat().st_size for f in digest_dir.rglob("*") if f.is_file())
    print(f"fetch-tectonic-bundle: {len(NEEDED_FILES)} files, {total} bytes, "
          f"digest {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
