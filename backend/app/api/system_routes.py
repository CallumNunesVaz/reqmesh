"""Admin-only system endpoints: version/update checking and supervised update.

All routes require the admin role. The actual container swap is performed by the
updater sidecar (see app.services.updater); these endpoints check for updates,
trigger a supervised update, and report its progress.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import require_admin
from app.services import updater

router = APIRouter(prefix="/system", tags=["system"])


class UpdateRequest(BaseModel):
    target_version: str | None = None


class TestEmailRequest(BaseModel):
    to: str


# ── Application settings (runtime, admin-editable) ────────────────────────────

@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    """Effective values for every admin-editable setting (secrets redacted)."""
    from app.core.settings_store import effective_settings
    return effective_settings()


@router.patch("/settings")
async def patch_settings(patch: dict, admin: dict = Depends(require_admin)):
    """Update runtime settings. Env-locked and blank-secret keys are ignored."""
    from app.core.settings_store import set_overrides
    return set_overrides(patch)


@router.post("/settings/test-email")
async def test_email(body: TestEmailRequest, admin: dict = Depends(require_admin)):
    """Send a test email using the current SMTP settings and report the result."""
    from app.services.email_service import send_test_email
    return await asyncio.to_thread(send_test_email, body.to)


@router.get("/public-config")
async def public_config():
    """Non-sensitive instance info for the login/registration UI (no auth)."""
    from app.core.config import settings
    return {
        "instance_name": settings.instance_name,
        "support_email": settings.support_email,
        "allow_self_registration": settings.allow_self_registration,
        "require_email_verification": settings.require_email_verification,
    }


@router.get("/latex-status")
async def latex_status():
    """Whether a LaTeX engine is available for PDF report generation."""
    from app.services.publisher import latex_engine_available
    engine = latex_engine_available()
    return {"available": engine is not None, "engine": engine}


@router.get("/info")
async def system_info(admin: dict = Depends(require_admin)):
    """Runtime facts the admin UI uses to decide what update UX to show."""
    import os as _os
    import platform
    import socket
    import sys
    import time as _time

    info = updater.runtime_info()

    # Host identity
    info["hostname"] = socket.gethostname()
    try:
        info["fqdn"] = socket.getfqdn()
    except Exception:
        info["fqdn"] = socket.gethostname()

    # IP addresses — internal (LAN) and a best-effort public IP
    internal_ips: list[str] = []
    try:
        from socket import AF_INET
        for iface in ([l[4][0] for l in socket.getaddrinfo(socket.gethostname(), None) if l[0] == AF_INET]):
            if iface not in internal_ips and not iface.startswith("127."):
                internal_ips.append(iface)
    except Exception:
        pass
    info["internal_ips"] = internal_ips or ["unknown"]

    # OS info
    info["os"] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
    }

    # Uptime — how long PID 1 (this app in-container) has been running.
    # /proc/1/stat field 22 is starttime *since boot* in clock ticks, so the
    # elapsed uptime is system-uptime minus that offset.
    try:
        with open("/proc/uptime") as f:
            system_uptime = float(f.read().split()[0])
        with open("/proc/1/stat") as f:
            starttime_ticks = int(f.read().split()[21])
        clk_tck = _os.sysconf(_os.sysconf_names["SC_CLK_TCK"])
        info["process_uptime_seconds"] = max(0, int(system_uptime - starttime_ticks / clk_tck))
    except Exception:
        info["process_uptime_seconds"] = 0

    # Working directory and user
    info["working_directory"] = _os.getcwd()
    try:
        import pwd
        info["running_user"] = pwd.getpwuid(_os.getuid()).pw_name
    except Exception:
        info["running_user"] = str(_os.getuid())

    return info


@router.get("/update/check")
async def check_update(force: bool = False, admin: dict = Depends(require_admin)):
    """Latest GitHub release vs the running version. Cached; force to bypass."""
    return await asyncio.to_thread(updater.check_for_update, force)


@router.get("/update/status")
async def update_status(admin: dict = Depends(require_admin)):
    return updater.get_update_status()


@router.post("/update")
async def start_update(body: UpdateRequest, admin: dict = Depends(require_admin)):
    """Back up data and signal the updater to move to the target version.

    Uses the latest available release when target_version is omitted.
    """
    if not updater.self_update_supported():
        raise HTTPException(
            status_code=409,
            detail="Self-update is not available in this deployment. Update manually (see docs).",
        )

    target = body.target_version
    if not target:
        check = await asyncio.to_thread(updater.check_for_update, True)
        if check.get("error"):
            raise HTTPException(status_code=502, detail=check["error"])
        if not check.get("update_available"):
            raise HTTPException(status_code=409, detail="Already running the latest version.")
        target = check["latest"]

    try:
        result = await asyncio.to_thread(
            updater.request_update, target, admin.get("username", "admin")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return result


@router.post("/update/upload")
async def upload_update(
    file: UploadFile = File(...),
    target_version: str = Form(""),
    admin: dict = Depends(require_admin),
):
    """Update from an uploaded Docker image archive (offline / air-gapped).

    The archive (e.g. reqmesh-vX.Y.Z-image.tar.gz from a release) is streamed to
    the control volume; the sidecar then `docker load`s it and recreates the app.
    """
    if not updater.file_update_supported():
        raise HTTPException(
            status_code=409,
            detail="File-based update requires a Docker deployment with the updater sidecar.",
        )

    dest = updater.staged_image_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    limit = settings.max_update_upload_mb * 1024 * 1024

    def _stream_to_disk() -> int:
        written = 0
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError("too_large")
                out.write(chunk)
        return written

    try:
        size = await asyncio.to_thread(_stream_to_disk)
    except ValueError:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_update_upload_mb} MB limit.")

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await asyncio.to_thread(
            updater.request_file_update, target_version.strip(), admin.get("username", "admin")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {**result, "archive_bytes": size}


@router.post("/update/bundle")
async def upload_bundle(
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    """Stage an uploaded release bundle for a bare-metal (non-Docker) install.

    The bundle (reqmesh-vX.Y.Z.tar.gz from a release) is streamed to the
    instance, validated, and staged. It's applied on the next restart — the
    admin can trigger that immediately via POST /system/restart. Works offline.
    """
    from app.services import bundle_update

    if not bundle_update.bundle_update_supported():
        raise HTTPException(
            status_code=409,
            detail="Bundle-based update is not available in this deployment.",
        )

    dest = bundle_update.incoming_path()
    limit = settings.max_update_upload_mb * 1024 * 1024

    def _stream_to_disk() -> int:
        written = 0
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError("too_large")
                out.write(chunk)
        return written

    try:
        size = await asyncio.to_thread(_stream_to_disk)
    except ValueError:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_update_upload_mb} MB limit.")

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await asyncio.to_thread(
            bundle_update.stage_from_archive, dest, admin.get("username", "admin")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {**result, "archive_bytes": size}


@router.post("/restart")
async def restart_app(admin: dict = Depends(require_admin)):
    """Restart the app in place (re-exec). Applies any staged bundle update on
    the way back up. Bare-metal only — Docker manages its own lifecycle."""
    from app.services import bundle_update

    if not bundle_update.can_restart():
        raise HTTPException(
            status_code=409,
            detail="In-place restart is not available in this deployment.",
        )
    bundle_update.schedule_restart()
    return {"ok": True, "restarting": True}


@router.post("/update/dismiss")
async def dismiss_update(admin: dict = Depends(require_admin)):
    """Clear a completed/failed update's control files (and any staged archive)."""
    updater.clear_update_state()
    return {"ok": True}


# ── System Dependencies ───────────────────────────────────────────────────────

DEPENDENCY_CHECKERS: dict[str, callable] = {}


def _register(name: str):
    def deco(fn):
        DEPENDENCY_CHECKERS[name] = fn
        return fn
    return deco


@_register("git")
def _check_git():
    import shutil, subprocess
    if not shutil.which("git"):
        return {"ok": False, "error": "git not found on PATH"}
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        version = r.stdout.strip() or r.stderr.strip()
        return {"ok": True, "version": version}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_register("git-e2e")
def _test_git_e2e():
    import shutil, subprocess, tempfile
    from pathlib import Path
    if not shutil.which("git"):
        return {"ok": False, "error": "git not found"}
    tmp = tempfile.mkdtemp(prefix="rm-dep-git-")
    try:
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, timeout=10, check=True)
        (Path(tmp) / "test.txt").write_text("hello")
        subprocess.run(["git", "config", "user.email", "test@reqmesh.local"], cwd=tmp, capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "reqmesh-test"], cwd=tmp, capture_output=True, timeout=10)
        subprocess.run(["git", "add", "test.txt"], cwd=tmp, capture_output=True, timeout=10, check=True)
        subprocess.run(["git", "commit", "-m", "test"], cwd=tmp, capture_output=True, timeout=10, check=True)
        return {"ok": True, "detail": "init + add + commit succeeded"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"{e.stderr.strip() if e.stderr else str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@_register("weasyprint")
def _check_weasyprint():
    try:
        import weasyprint
        return {"ok": True, "version": getattr(weasyprint, "__version__", "installed")}
    except ImportError:
        return {"ok": False, "error": "weasyprint not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_register("weasyprint-e2e")
def _test_weasyprint_e2e():
    try:
        from weasyprint import HTML as WHTML
    except ImportError:
        return {"ok": False, "error": "weasyprint not installed"}
    try:
        WHTML(string="<html><body><h1>re</h1></body></html>").write_pdf()
        return {"ok": True, "detail": "HTML→PDF render succeeded"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_register("tectonic")
def _check_tectonic():
    _, result = _detect_latex("tectonic")
    return result


@_register("tectonic-e2e")
def _test_tectonic_e2e():
    return _test_latex_compile("tectonic")


@_register("pdflatex")
def _check_pdflatex():
    _, result = _detect_latex("pdflatex")
    return result


@_register("pdflatex-e2e")
def _test_pdflatex_e2e():
    return _test_latex_compile("pdflatex")


@_register("lualatex")
def _check_lualatex():
    _, result = _detect_latex("lualatex")
    return result


@_register("lualatex-e2e")
def _test_lualatex_e2e():
    return _test_latex_compile("lualatex")


@_register("xelatex")
def _check_xelatex():
    _, result = _detect_latex("xelatex")
    return result


@_register("xelatex-e2e")
def _test_xelatex_e2e():
    return _test_latex_compile("xelatex")


@_register("openpyxl")
def _check_openpyxl():
    try:
        import openpyxl
        return {"ok": True, "version": getattr(openpyxl, "__version__", "installed")}
    except ImportError:
        return {"ok": False, "error": "openpyxl not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_register("openpyxl-e2e")
def _test_openpyxl_e2e():
    try:
        import openpyxl
    except ImportError:
        return {"ok": False, "error": "openpyxl not installed"}
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "test"
        ws["A1"] = "hello"
        wb.save("/dev/null" if __import__("os").name != "nt" else "NUL")
        return {"ok": True, "detail": "workbook create + save succeeded"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_register("rst2pdf")
def _check_rst2pdf():
    import shutil
    if not shutil.which("rst2pdf"):
        return {"ok": False, "error": "rst2pdf not found on PATH"}
    try:
        r = __import__("subprocess").run(["rst2pdf", "--version"], capture_output=True, text=True, timeout=10)
        return {"ok": True, "version": (r.stdout or r.stderr).strip().splitlines()[0]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Internal helpers ────────────────────────────────────────────────────────────

def _detect_latex(engine: str) -> tuple[bool, dict]:
    import shutil
    if not shutil.which(engine):
        return False, {"ok": False, "error": f"{engine} not found on PATH"}
    return True, {"ok": True, "version": engine}


def _test_latex_compile(engine: str) -> dict:
    import shutil, subprocess, tempfile, os
    from pathlib import Path as P
    if not shutil.which(engine):
        return {"ok": False, "error": f"{engine} not found"}

    # Minimal LaTeX doc exercising common font & class requirements
    tex = r"""
\documentclass{article}
\usepackage{lmodern}
\usepackage{fontenc}
\begin{document}
\section{Smoke Test}
This is a minimal reqmesh dependency test.
\end{document}
"""
    tmp = tempfile.mkdtemp(prefix=f"rm-dep-{engine}-")
    tex_path = P(tmp) / "smoke.tex"
    try:
        tex_path.write_text(tex)
        if engine == "tectonic":
            r = subprocess.run(
                [engine, "--outdir", tmp, str(tex_path)],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
        else:
            r = subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error",
                 f"-output-directory={tmp}", str(tex_path)],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                # Classic engines need a second pass for TOC/refs
                subprocess.run(
                    [engine, "-interaction=nonstopmode", "-halt-on-error",
                     f"-output-directory={tmp}", str(tex_path)],
                    cwd=tmp, capture_output=True, text=True, timeout=60,
                )

        pdf = P(tmp) / "smoke.pdf"
        if pdf.exists() and pdf.stat().st_size > 100:
            stderr_tail = ""
            if r.returncode != 0 and getattr(r, "stderr", None):
                stderr_tail = "; " + r.stderr.strip()[-200:]
            return {"ok": True, "detail": f"PDF compiled ({pdf.stat().st_size} bytes){stderr_tail}"}
        else:
            msg = (getattr(r, "stderr", None) or getattr(r, "stdout", None) or "").strip()
            return {"ok": False, "error": f"no PDF produced (rc={r.returncode}): {msg[:500]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _collect_deps() -> list[dict]:
    import shutil, platform
    results = []

    _INSTALL_GUIDES: dict[str, str] = {
        "git": "sudo apt install git  # Debian/Ubuntu\nbrew install git    # macOS",
        "weasyprint": "pip install weasyprint\n# Also needs system fonts: sudo apt install fonts-dejavu-core",
        "tectonic": 'curl -L https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/bin',
        "pdflatex": "sudo apt install texlive-latex-base  # Debian/Ubuntu\nbrew install --cask mactex  # macOS (installs pdfLaTeX)",
        "lualatex": "sudo apt install texlive-latex-base  # Debian/Ubuntu\nbrew install --cask mactex  # macOS",
        "xelatex": "sudo apt install texlive-xetex     # Debian/Ubuntu\nbrew install --cask mactex  # macOS",
        "openpyxl": "pip install openpyxl",
        "rst2pdf": "pip install rst2pdf",
    }

    def _append(name: str, label: str, category: str, *, has_e2e: bool = True):
        checker = DEPENDENCY_CHECKERS.get(name)
        status = "unknown"
        detail = ""
        if checker:
            r = checker()
            status = "ok" if r.get("ok") else "missing"
            detail = r.get("version") or r.get("error") or r.get("detail") or ""
        results.append({
            "id": name,
            "label": label,
            "category": category,
            "status": status,
            "detail": detail,
            "has_e2e": has_e2e,
            "install_guide": _INSTALL_GUIDES.get(name, ""),
        })

    _append("git", "Git", "Core", has_e2e=True)
    _append("weasyprint", "WeasyPrint", "PDF Engine")
    _append("tectonic", "Tectonic", "LaTeX Engines")
    _append("pdflatex", "pdfLaTeX", "LaTeX Engines")
    _append("lualatex", "LuaLaTeX", "LaTeX Engines")
    _append("xelatex", "XeLaTeX", "LaTeX Engines")
    _append("openpyxl", "OpenPyXL", "Exports")
    _append("rst2pdf", "rst2pdf", "PDF Engine", has_e2e=False)

    return results


@router.get("/dependencies")
async def list_dependencies(admin: dict = Depends(require_admin)):
    import asyncio
    return await asyncio.to_thread(_collect_deps)


@router.post("/dependencies/{dep_id}/test")
async def test_dependency(dep_id: str, admin: dict = Depends(require_admin)):
    e2e_name = f"{dep_id}-e2e"
    checker = DEPENDENCY_CHECKERS.get(e2e_name)
    if checker is None:
        raise HTTPException(status_code=404, detail=f"No E2E test for '{dep_id}'")
    import asyncio
    return await asyncio.to_thread(checker)
