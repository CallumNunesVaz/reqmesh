# reqmesh — Security Review & Implementation Plan

**Version:** 1.0
**Date:** 25 July 2026
**Subject:** `CallumNunesVaz/reqmesh` — open-source requirements management tool (FastAPI + React + YAML/git, GPL-3.0-or-later)
**Author:** Prepared in consultation with Claude

---

## 0. Scope, method and caveats

This review was produced from the public `README.md` and the repository file listing. `AUDIT.md`, `DEPLOYMENT.md`, `ROADMAP.md` and the source tree itself were **not** readable at time of writing. Findings are therefore split into two classes:

| Class | Meaning |
| --- | --- |
| **Confirmed** | Directly evidenced by documented behaviour in the README. |
| **Verify** | A known failure mode for this architecture that must be checked against the code. Not an assertion that the defect exists. |

Every **Verify** item is written so it can be resolved in minutes by grepping the codebase. Where an item is already handled, close it out and record that — a closed verification is an assurance artefact in its own right, not wasted effort.

### 0.1 A note on "highest level security"

You asked whether serving all three audiences — defence/aerospace suppliers, general engineering teams, and personal use — means defaulting to the strictest posture. Not quite, and the distinction matters for a tool you maintain in evenings.

Uniformly maximal security makes reqmesh hostile to the casual user, and hostile tools get deployed with the controls switched off, which is worse than not having them. The correct pattern is:

> **Secure defaults, explicitly relaxable — never insecure defaults, optionally hardened.**

Concretely, introduce a deployment profile as a first-class concept:

```bash
RT_PROFILE=personal   # single user, localhost, convenience-oriented
RT_PROFILE=team       # default; authenticated, TLS assumed, sane limits
RT_PROFILE=hardened   # E8/DISP-oriented; MFA mandatory, no self-registration,
                      # no anonymous read, strict CSP, audit-everything
```

The profile sets defaults for a dozen individual switches which remain independently overridable. This gives you one thing to document, one thing to test, and one thing a customer's assessor can point at. It also means the *hardened* path can be added incrementally without regressing usability for anyone else.

Everything in this plan assumes that model.

---

## 1. Architecture summary as it bears on security

| Property | Security consequence |
| --- | --- |
| Python FastAPI backend, React SPA frontend | Conventional web attack surface; ASVS applies directly. |
| YAML file-per-entity on disk, no database | No SQL injection. Path traversal and YAML deserialisation become the primary storage risks. |
| Git auto-commit on every mutation, optional push | Subprocess handling, credential exposure, and **a second input path that bypasses the API**. |
| JWT auth, four roles, per-project permission map | Access control correctness is the highest-value test surface. No MFA, no SSO. |
| ReqIF / SysML / CSV / TSV / XLSX import | Untrusted structured input, including XML and zip containers. |
| HTML-bearing rich text (TipTap), published to HTML/LaTeX/PDF | Stored XSS and LaTeX injection. |
| Expression evaluator for parametrics | Sandbox escape and resource exhaustion. |
| SSE event stream + in-memory presence | Connection exhaustion; single-process state. |
| Docker, Caddy/nginx, Electron desktop | Three distinct hardening checklists. |
| Air-gapped operation supported (`RT_OFFLINE_MODE`) | No cloud dependencies permitted in any control you add. |
| GPL-3.0-or-later, public repository | Supply-chain transparency expected; source is available to attackers by design. |

---

## 2. Threat model

### 2.1 Assets, in priority order

1. **The requirements baseline.** For a defence or aerospace user this is the most sensitive artefact they hold, and may be export-controlled under ITAR/EAR or Australia's *Defence Trade Controls Act 2012*. Confidentiality is the dominant concern.
2. **Audit trail and review fingerprint integrity.** reqmesh's value proposition is that `reviewed` and `reviewed_fingerprint` are trustworthy. If they can be forged or silently desynchronised, the tool produces false assurance — arguably worse than producing none. Integrity is the dominant concern.
3. **Baseline availability.** A frozen baseline that can't be retrieved blocks a design review or a certification gate.
4. **Secrets.** `RT_SECRET`, SMTP credentials, git remote credentials.

### 2.2 Adversaries

| Actor | Capability | Primary concern |
| --- | --- | --- |
| Unauthenticated network attacker | Reaches port 8000 or the reverse proxy | Anonymous read; auth bypass |
| Authenticated `guest` / `contributor` | Valid low-tier credentials | Vertical privilege escalation; cross-project access |
| Malicious project data | Can commit YAML directly to the project repo | Bypasses **all** API-side validation |
| Malicious interchange file | Supplies a ReqIF/XLSX from a partner org | Parser exploitation, XXE, decompression bomb |
| Compromised dependency | Any transitive package | Supply chain |
| Local attacker (desktop) | User-level access to the workstation | Electron IPC abuse, token theft at rest |

### 2.3 The trust boundary most likely to be wrong

The README states that entity IDs are validated because they become filenames, "which also blocks path traversal **through the API**." That qualifier is the crux of the design.

A project directory is git-tracked and human-editable by intent — that is the product's headline feature. Therefore YAML arriving on disk has **at least three** paths in, only one of which passes through your validators:

1. The API (validated).
2. A developer editing files directly and committing (unvalidated).
3. `git pull` from a remote, including a remote controlled by someone else (unvalidated, and potentially attacker-controlled).

Path 3 is the dangerous one. Any invariant enforced only at the API layer is not an invariant. **Validation must be re-applied on read from the YAML store**, not solely on write. This single principle drives several findings below and is, in my assessment, the most important structural change in this document.

---

## 3. Findings

Severity uses a simple scale: **Critical** (exploitable by an unauthenticated attacker, or breaks the integrity guarantee), **High**, **Medium**, **Low**.

### 3.1 Identity and access control

**F-01 — No MFA and no SSO. [Confirmed | High]**
Authentication is username/password issuing a JWT. Essential Eight Maturity Level 2 — the mandated baseline for Defence Industry Security Program membership — requires phishing-resistant MFA. reqmesh cannot meet it. This is the single largest blocker to adoption by your most demanding audience.
*Fix:* OIDC delegation first, then WebAuthn, then TOTP. Detailed in §5, Phase 3.

**F-02 — Anonymous read access is the default. [Confirmed | Critical for internet-facing deployments]**
Unauthenticated users resolve to `guest`, which grants `view` on every project by default. On any deployment reachable from an untrusted network this exposes the entire requirements baseline — the crown-jewel asset — to anyone who finds the port.
*Fix:* `RT_REQUIRE_AUTH=true` by default in `team` and `hardened` profiles. Anonymous access becomes opt-in, per-project, and logged at startup with an explicit warning banner.

**F-03 — Self-registration is enabled by default and grants `propose`. [Confirmed | High]**
Combined with F-02, an attacker who reaches the service can create an account and write change requests, risks, comments and decisions into a customer's project. Even without escalation this is a defacement and denial-of-review vector.
*Fix:* Off by default outside the `personal` profile. When enabled, support an email-domain allowlist and an admin approval queue.

**F-04 — Bootstrap admin password is written to the log. [Confirmed | High]**
When `RT_ADMIN_PASSWORD` is unset, a random password is generated and logged. Container logs are routinely shipped to aggregators, retained, and readable by operators who are not entitled to administrative access.
*Fix:* Write the credential to a file at `RT_DATA_ROOT/.initial-admin` with mode `0600`, log only the path, and force a password change on first login. Delete the file on first successful login.

**F-05 — Rate limiting is per-IP and may see only the proxy address. [Confirmed design, Verify implementation | High]**
Login is limited to 5/min per IP. Behind Caddy or nginx, `request.client.host` is the proxy unless `X-Forwarded-For` is explicitly trusted and parsed. If that's not wired up, the limit is global rather than per-attacker — which is simultaneously trivially bypassed and a self-inflicted denial of service.
*Verify:* How the client IP is derived; whether `--proxy-headers` and `--forwarded-allow-ips` are set on uvicorn.
*Fix:* Trust `X-Forwarded-For` only from a configured proxy CIDR. Add per-account lockout with exponential backoff in addition to per-IP limits.

**F-06 — Access control test coverage per endpoint. [Verify | High]**
You have a four-tier role model plus a per-project permission map plus global-admin override. That is a matrix with real complexity, and broken access control is consistently the most common serious web vulnerability. 259 backend tests is a good number, but the question is whether there is a test asserting that *each* mutating endpoint rejects *each* insufficient role.
*Fix:* Generate the test matrix programmatically from the route table so a new endpoint added without a permission decorator fails CI by default. This is high-value and well suited to an evening's work.

**F-07 — JWT hardening. [Verify | High]**
*Verify:* algorithm is pinned server-side (reject `alg` from the token header); `exp` is present and short; `aud`/`iss` are validated; `RT_SECRET` persistence file has restrictive permissions and is excluded from any project git repo; token is not stored in `localStorage` where XSS can exfiltrate it.
*Fix:* If tokens live in `localStorage`, move to `HttpOnly` + `Secure` + `SameSite=Strict` cookies with CSRF protection on mutating routes. Your `token_version` design is sound and should be extended to bump on MFA enrolment/removal and role change.

**F-08 — User enumeration. [Verify | Medium]**
`/auth/register`, `/auth/forgot-password` and `/auth/verify-email` are classic oracles. Differing response bodies, status codes, or *timings* reveal which usernames and email addresses exist.
*Fix:* Identical responses and comparable timing regardless of existence. Perform a dummy hash on unknown users so login timing doesn't leak.

### 3.2 Storage, git and the second input path

**F-09 — Validation is applied on write but must also apply on read. [Confirmed by design | Critical for integrity]**
See §2.3. Entity IDs, relation targets, `references[].path`, and every field consumed by the evaluator or publisher must be re-validated when loaded from disk, because disk contents can originate from a git pull rather than the API.
*Fix:* A single `validate_on_load` gate in the YAML store service. Corrupt or non-conforming files are already logged and skipped — extend that same mechanism to files that are syntactically valid but semantically hostile (IDs containing `../`, absolute paths, oversized fields, unexpected keys).

**F-10 — YAML deserialisation. [Verify | Critical if wrong]**
Every load path must use `yaml.safe_load`. A single `yaml.load` without `SafeLoader` on a path reachable from a pulled project directory is remote code execution.
*Fix:* Grep for `yaml.load(`, `Loader=`, `FullLoader`, `UnsafeLoader`. Add a lint rule so it can't regress. Bandit's `B506` catches this — free once CI is in place.

**F-11 — Git subprocess argument injection. [Verify | High]**
Commit messages embed entity IDs (`rt: put requirements/SYST0001`), and `RT_GIT_REMOTE_URL` is operator-supplied. Values beginning with `-` can be interpreted as flags; `--upload-pack`/`--receive-pack` and `ext::` URLs are the classic escalation.
*Fix:* Always pass a `--` separator; never build commands through a shell (`shell=False`, list form); reject remote URLs not matching an `https://`/`ssh://` allowlist; reject `ext::`, `file://`, and anything containing a newline.

**F-12 — Git credential exposure in error paths. [Verify | Medium]**
Push failures commonly echo the remote URL, and URLs with embedded credentials then land in logs and API error responses.
*Fix:* Redact anything matching a credential pattern before logging. Prefer SSH keys or a credential helper over URL-embedded tokens, and document that in DEPLOYMENT.md.

**F-13 — `POST /scan` accepts a filesystem path. [Confirmed | High]**
The code-scanning endpoint takes a source directory. Unless containment is enforced, an authenticated user can enumerate and read arbitrary files readable by the server process — including other tenants' projects, `RT_SECRET`, and `/proc`.
*Fix:* Resolve the path, `os.path.realpath` it, and assert it is a descendant of a configured allowlist root. Reject symlinks that escape. Same treatment for `references[].path` and any import/export file path.

**F-14 — No integrity protection on the audit trail. [Confirmed | Medium, escalating to High for certification use]**
`history/` and the review fingerprints are plain files in the project directory. Anyone with write access to the directory or the git remote can rewrite history, and git alone does not prevent a force-push.
*Fix (staged):* Document that the project remote should be configured append-only with force-push disabled — that's a deployment control and costs nothing. Longer term, consider signed commits (`git commit -S`) and a hash-chained history file, which would meaningfully strengthen the DO-330 story in §4.2.

### 3.3 Untrusted content processing

**F-15 — XML external entity handling in the ReqIF importer. [Verify | Critical if wrong]**
ReqIF 1.2 is XML. Python's stdlib `xml.etree.ElementTree` and `lxml` are vulnerable to entity expansion ("billion laughs") and, depending on configuration, external entity resolution enabling file disclosure and SSRF.
*Fix:* Use `defusedxml` for all parsing. Add a hard cap on input size and parse depth.

**F-16 — Decompression bombs in XLSX import. [Verify | High]**
XLSX is a zip container. `openpyxl` will happily expand a 1 MB file into gigabytes.
*Fix:* Inspect the zip manifest before extraction; reject if the uncompressed total or the compression ratio exceeds a threshold. Cap sheet and cell counts.

**F-17 — Stored XSS via requirement descriptions. [Confirmed vector | Critical]**
Descriptions contain HTML (`"<p>The system shall authenticate users via OAuth2 within 500 ms.</p>"`). TipTap sanitises paste on the client, but client-side sanitisation is not a security control. Content also arrives via import, and via the git path described in §2.3. It is then rendered in the SPA *and* emitted into published HTML reports that get emailed around an organisation.
*Fix:* Sanitise server-side on write **and** on read, using `nh3` (Rust `ammonia` bindings — fast, maintained) or `bleach`. Define an explicit tag/attribute allowlist. Strip `javascript:` and `data:` URIs, all `on*` handlers, `<style>`, `<iframe>`, `<object>`, and SVG. Escape rather than sanitise in published output where formatting isn't required.

**F-18 — LaTeX injection in the PDF publish path. [Confirmed vector | High]**
User-controlled text is fed to tectonic. `\input{/etc/passwd}`, `\write18{...}` (if shell escape is enabled), `\csname`, and unbounded macro expansion are the concerns. Even without code execution, a crafted requirement can hang the compiler indefinitely.
*Fix:* Escape all user content for LaTeX; never interpolate raw. Run tectonic with shell escape explicitly disabled, in a temporary directory, with a wall-clock timeout and a memory cap. Treat compile failure as a normal error, not a stack trace.

**F-19 — Expression evaluator sandbox. [Verify | High]**
The README states expressions are parsed against a strict whitelist and cannot execute arbitrary code. That is the right design and deserves adversarial testing rather than assumption.
*Verify:* AST-walking with a node allowlist (not a blocklist); attribute access to dunders (`__class__`, `__globals__`, `__subclasses__`) is impossible; no access to builtins; and resource exhaustion is bounded — `10**10**10` will hang a process regardless of how good the whitelist is.
*Fix:* Add explicit bounds on numeric magnitude, expression length, and recursion depth. This is your highest-value fuzz target (§6.3).

### 3.4 Transport, headers and the SPA

**F-20 — Security headers and CSP. [Verify | Medium]**
Not mentioned in the README or the file listing.
*Fix:* In `Caddyfile`/`nginx.conf` **and** as FastAPI middleware (so the desktop and dev paths are covered too):

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
    img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
    form-action 'self'; object-src 'none'
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

A strict CSP is the single most effective mitigation for F-17 residual risk. Note that TipTap and Tailwind may require `'unsafe-inline'` for styles — acceptable — but must not require it for scripts.

**F-21 — CORS configuration divergence between dev and prod. [Verify | Medium]**
Development runs Vite on `:5173` against the API on `:8000`, which requires permissive CORS. Production is single-origin and requires none.
*Fix:* CORS origins must come from config with an empty default; a wildcard origin combined with credentials should raise at startup, not warn.

**F-22 — Image upload handling in the rich text editor. [Verify | Medium]**
TipTap supports images. Whether they are base64-embedded in YAML or stored as files determines the risk: unbounded YAML growth and DoS in the first case; content-type confusion, path traversal, and stored-XSS-via-SVG in the second.
*Fix:* Cap size, validate magic bytes rather than trusting the declared type, re-encode raster images, and refuse SVG outright.

**F-23 — SSE connection exhaustion. [Confirmed design | Medium]**
Every project exposes a long-lived SSE stream, and the event bus is in-memory single-process. An authenticated user can open connections until the worker pool is exhausted.
*Fix:* Per-user and global connection caps; idle timeout; heartbeat.

**F-24 — Expensive endpoints are unauthenticated-adjacent and unbounded. [Confirmed | Medium]**
`/evaluation`, `/evaluation/impact`, `/coverage`, `/trace`, `/scan`, `/publish` all perform substantial work. Only the three auth endpoints are rate-limited. With F-02 in play, some are reachable anonymously.
*Fix:* Global per-user rate limits with a lower budget for analysis and publishing endpoints. Cap project size for in-memory search.

### 3.5 Deployment, supply chain and desktop

**F-25 — Container hardening. [Verify | Medium]**
*Verify:* `Dockerfile.prod` creates and runs as a non-root user; no build secrets in layers; `docker-compose.prod.yml` sets `read_only: true` with explicit `tmpfs` mounts, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, and a pinned digest base image rather than a floating tag.

**F-26 — No SBOM, no advisory channel, no signed releases. [Confirmed | Medium]**
Essential Eight ML1 expects internet-facing applications patched within two weeks, or 48 hours where an exploit exists. That obligation is unmeetable for your users if they cannot tell what version they run or learn that a fix exists.
*Fix:* CycloneDX SBOM per release (your pinned `requirements.txt` and lockfile make this nearly free); GitHub Security Advisories; immutable semver Docker tags plus digests; `RT_VERSION` surfaced in `/api/health` so an operator can audit fleet-wide.

**F-27 — No `SECURITY.md`. [Confirmed | Low effort, disproportionate signal]**
Absent from the repository root. ISO/IEC 29147 asks for a published intake channel; every vendor security questionnaire asks for it; it takes fifteen minutes.

**F-28 — Electron hardening. [Verify | High for desktop users]**
*Verify:* `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, a narrow `contextBridge` surface rather than exposing `ipcRenderer`, `webSecurity` never disabled, navigation and `window.open` restricted to an allowlist, and no `shell.openExternal` on untrusted URLs. Also: where the JWT is persisted on disk and with what permissions.
*Fix:* Code signing on Windows and macOS. This is not optional for the defence audience — unsigned binaries will not execute under an Essential Eight ML2 application control policy, which makes the desktop build undeployable regardless of its actual security.

**F-29 — Air-gap discipline. [Confirmed feature, Verify completeness | Medium]**
`RT_OFFLINE_MODE` suppresses git push and SMTP. Any control added by this plan must not introduce a network dependency — that rules out hosted CAPTCHA, remote JWKS fetching without caching, WebAuthn attestation requiring a live MDS fetch, and CDN-hosted frontend assets.
*Verify:* the frontend bundles all fonts and assets locally; no telemetry; no external CDN references in `index.html`.

---

## 4. Standards positioning

### 4.1 What to pursue

| Standard | Rationale | Commitment |
| --- | --- | --- |
| **OWASP ASVS 5.0, Level 2** | The verification target. Maps to a checklist you can drive to completion and cite. Prioritise V1 (encoding/injection), V4 (access control), V5 (file handling), V8 (data protection). | Ongoing, self-assessed |
| **NIST SP 800-218 (SSDF)** + SBOM | The framing US and allied primes ask for in supply-chain attestations. | Low, mostly documentation |
| **OpenSSF Scorecard + Best Practices badge** | The open-source-native equivalent, automated, and visible on the repo. A concrete adoption signal. | One weekend |
| **ISO/IEC 29147 / 30111** | Disclosure intake and handling. | Hours |
| **CIS Docker Benchmark** | Directly applicable to `Dockerfile.prod`. | One evening |
| **ASD Essential Eight (→ Essentials for Enterprise IT)** | Not a control set for your software, but the framework your defence customers are assessed against. Publishing a mapping is a sales asset. | See §4.3 |

### 4.2 What to defer or decline

- **ISO/IEC 27001** — certifies an operating organisation. You don't run a service. Decline.
- **Common Criteria (ISO/IEC 15408)** — cost and recertification-per-release are incompatible with an actively developed solo project. Decline unless a specific programme mandates an evaluated product.
- **IEC 62443** — applies if reqmesh sits inside an OT environment. It doesn't. Decline.
- **DO-330 tool qualification** — *this is the significant one, and it is not a security standard.* Your demo project is a Cessna 172S and your example requirement carries a `DO-178C` attribute. If a customer holds certification-credible requirements in reqmesh, the tool is likely qualifiable at **TQL-5** (a development tool whose errors could insert an undetected error into the airborne software). The road-vehicle and industrial equivalents are ISO 26262-8 clause 11 and IEC 61508-3 clause 7.4.4 (T2 classification).

  Full qualification is out of scope for evenings and weekends. But the *preparatory* work overlaps almost entirely with things worth doing anyway: reqmesh's own requirements captured in reqmesh, structured test evidence traced to them, configuration management records, and a tamper-evident change history (F-14). **Recommendation:** don't chase TQL-5 now; do make the choices that keep it reachable, and say so publicly. "Designed with DO-330 TQL-5 qualification in mind; qualification data package not yet produced" is honest, differentiating, and costs you nothing.

### 4.3 Essential Eight status and what it means here

ASD confirmed on 24 June 2026 that the Essential Eight will be retired over approximately two years and replaced by a domain-based **Essentials series**, beginning with *Essentials for Enterprise IT* (consultation closed 12 July 2026). Both frameworks run in parallel; deprecation around mid-2027, retirement around mid-2028. Existing work carries across.

The practical consequence for reqmesh is *none* — the underlying controls (MFA, patching, application control, backups) are unchanged, and the Essential Eight remains what tenders and DISP obligations reference today. Build against it, but write your published mapping so it can be re-titled rather than rewritten.

Four of the eight land on reqmesh's side of the line:

| Control | reqmesh's position | Action |
| --- | --- | --- |
| **Multi-factor authentication** | **Fails.** No MFA of any kind. Phishing-resistant MFA required from ML2. | F-01 — Phase 3 |
| **Patch applications** | Weak. No advisory channel, no SBOM, no version endpoint. | F-26 — Phase 0/1 |
| **Restrict administrative privileges** | Reasonable. Role tiers and lockout guardrails are sound; the logged bootstrap password and default self-registration are findings. | F-03, F-04 — Phase 1 |
| **Regular backups** | **Strong — a genuine differentiator.** Git-native YAML is versioned, restorable, human-readable, diffable, and offsite via push. ML2+ requires tested restoration and that unprivileged accounts cannot modify or delete backups. | Document the append-only remote pattern in DEPLOYMENT.md |

Application control affects the Electron build only (F-28, code signing).

Be explicit in your documentation that the Essential Eight says essentially nothing about application security — it is IT hygiene, and ASD says so directly, pointing to the ISM, NIST CSF or ISO 27002 for comprehensive coverage. ASVS answers "is the code sound"; the Essential Eight answers "is the environment fit to run it". reqmesh needs an answer to both, and they are different documents.

---

## 5. Implementation plan

Sized for evenings and weekends, ongoing. Each phase is independently shippable and leaves the project better than it found it. Estimates assume roughly one weekend equals 8–10 focused hours.

### Phase 0 — Instrumentation and free wins
**Effort: 1 weekend. Do this first; it makes every later phase measurable.**

| # | Task | Notes |
| --- | --- | --- |
| 0.1 | `SECURITY.md` at repo root | Contact, scope, 90-day disclosure window, safe-harbour statement. Enable GitHub private vulnerability reporting. |
| 0.2 | CI security workflow | §6.1. CodeQL, Semgrep, Bandit, pip-audit, npm audit, gitleaks, Trivy. All free for a public repo. |
| 0.3 | Triage the initial CI output | Expect noise. Suppress with justification comments, not blanket ignores — the suppressions become review evidence. |
| 0.4 | Resolve the **Verify** items in §3 | Mostly grep. F-10, F-15, F-16, F-19, F-25, F-28 are the priorities. An evening's work that may close half this document. |
| 0.5 | OpenSSF Scorecard action + Best Practices badge | Publishes a security posture signal on the README. |

**Exit criterion:** CI green with a documented suppression list; every **Verify** item in §3 resolved to Confirmed-safe or promoted to a tracked issue.

### Phase 1 — Secure defaults
**Effort: 2–3 weekends. Highest risk reduction per hour in the entire plan.**

| # | Task | Findings |
| --- | --- | --- |
| 1.1 | Deployment profiles (`RT_PROFILE`) | §0.1. Implement first; subsequent switches hang off it. |
| 1.2 | `RT_REQUIRE_AUTH` defaulting true outside `personal` | F-02 |
| 1.3 | Self-registration off by default; domain allowlist; approval queue | F-03 |
| 1.4 | Bootstrap credential to a `0600` file, forced rotation on first login | F-04 |
| 1.5 | Correct client-IP derivation behind proxy; per-account lockout | F-05 |
| 1.6 | Security headers + CSP, in both proxy config and FastAPI middleware | F-20 |
| 1.7 | CORS from config, empty default, fail-fast on wildcard+credentials | F-21 |
| 1.8 | Container: non-root, read-only rootfs, dropped caps, pinned digest | F-25 |
| 1.9 | Startup self-check that logs a prominent warning for each insecure setting active | Cheap, and it makes misconfiguration visible in a support ticket |

**Exit criterion:** a default `docker compose -f docker-compose.prod.yml up` produces a deployment with no anonymous access, no self-registration, no logged credentials, and a strict CSP.

### Phase 2 — The input trust boundary
**Effort: 3–4 weekends. Addresses the structural issue in §2.3.**

| # | Task | Findings |
| --- | --- | --- |
| 2.1 | Server-side HTML sanitisation on write **and** on read (`nh3`) | F-17 |
| 2.2 | `validate_on_load` gate in the YAML store; treat disk as untrusted | F-09 |
| 2.3 | Path containment for `/scan`, `references[].path`, import/export | F-13 |
| 2.4 | `defusedxml` + size/depth caps for ReqIF | F-15 |
| 2.5 | Zip manifest inspection and ratio limits for XLSX | F-16 |
| 2.6 | LaTeX escaping, shell-escape disabled, timeout and memory cap | F-18 |
| 2.7 | Evaluator bounds: magnitude, length, recursion depth | F-19 |
| 2.8 | Git argument hardening: `--` separators, URL allowlist, no shell | F-11, F-12 |
| 2.9 | Image upload: magic-byte validation, size cap, SVG refused | F-22 |
| 2.10 | Rate limits on analysis/publish endpoints; SSE connection caps | F-23, F-24 |
| 2.11 | Access control test matrix generated from the route table | F-06 |

**Exit criterion:** a deliberately hostile project directory — crafted YAML, malicious ReqIF, XSS payloads in descriptions, LaTeX injection, path traversal in references — can be pulled into a running instance without compromise. Build that directory as a test fixture; it becomes a permanent regression suite and, incidentally, excellent demo material.

### Phase 3 — Identity
**Effort: 4–6 weekends. Unblocks the defence and aerospace audience.**

| # | Task | Notes |
| --- | --- | --- |
| 3.1 | **OIDC via Authlib (BSD-3)** | Do this first. Customers already run Entra ID, Keycloak or ADFS; delegating means you inherit their MFA, conditional access and offboarding in one integration, and you stop being an unmanaged identity store. Map IdP groups to existing role tiers — the per-project permission map needs no change. Test against Keycloak (Apache-2.0) and Authentik (MIT); both self-host and work air-gapped. |
| 3.2 | **WebAuthn / passkeys** via `py_webauthn` (BSD-3) + `@simplewebauthn/browser` (MIT) | For deployments with no IdP, which is most air-gapped and small-team users. Phishing-resistant, satisfies ML2. Skip attestation verification unless a customer requires vendor-pinned keys — it drags in an MDS blob you'd have to ship and update, which conflicts with F-29. |
| 3.3 | **TOTP** via `pyotp` (MIT) + `qrcode` (BSD) | The convenience tier. ~500 lines, no dependencies. Document honestly that it is **not** phishing-resistant and does not satisfy ML2. |
| 3.4 | Recovery codes | Mandatory whichever factors ship. Ten codes, hashed like passwords, single-use, regeneration is an audited event. |
| 3.5 | `mfa_required` at project permission level; `hardened` profile enforces globally | Lets a customer mandate MFA per project rather than all-or-nothing. |
| 3.6 | Extend `token_version` bump to MFA enrolment/removal and role change | Your existing design already does the hard part. |
| 3.7 | JWT storage and hardening remediation | F-07 |

All licences above are GPLv3-compatible. **privacyIDEA** (AGPL-3.0) is worth documenting as an integration option for classified networks with issued hardware tokens — integrated over its REST/RADIUS interface as a separate process, so no licence interaction.

**Exit criterion:** a deployment can be configured such that every account authenticates with a phishing-resistant factor, with no outbound network dependency.

### Phase 4 — Assurance artefacts
**Effort: ongoing, ~1 weekend per item. This is what converts engineering work into adoption.**

| # | Task |
| --- | --- |
| 4.1 | `docs/security/threat-model.md` — §2 of this document, maintained |
| 4.2 | `docs/security/asvs-l2.md` — ASVS Level 2 checklist with per-control status and evidence links |
| 4.3 | `docs/security/essential-eight.md` — the §4.3 mapping, written to survive the Essentials rename |
| 4.4 | DEPLOYMENT.md: hardened profile guide, append-only remote pattern, backup restoration test procedure, E8-aligned operational guidance |
| 4.5 | Release process: CycloneDX SBOM, immutable tags + digests, signed tags, published advisories, `RT_VERSION` in `/api/health` |
| 4.6 | Code signing for the Electron build (Windows + macOS) — F-28 |
| 4.7 | Fuzzing harnesses in CI (§6.3); consider OSS-Fuzz once adoption justifies it |
| 4.8 | Audit trail integrity: signed commits and hash-chained history — F-14, and the strongest single step toward §4.2's DO-330 posture |

### 5.1 Realistic timeline

Roughly 11–15 weekends of focused work to the end of Phase 3, so **five to seven months** at a sustainable evenings-and-weekends pace, with Phase 4 continuing indefinitely. Phases 0 and 1 alone — about a month — remove the majority of the acute risk and are worth treating as a single milestone.

---

## 6. CI/CD security pipeline

### 6.1 Baseline workflow

`.github/workflows/security.yml`. Everything here is free for a public repository.

```yaml
name: security

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 17 * * 0'   # Monday ~03:00 ACST

permissions:
  contents: read
  security-events: write

jobs:
  codeql:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        language: [python, javascript-typescript]
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          language: ${{ matrix.language }}
          queries: security-extended
      - uses: github/codeql-action/analyze@v3

  semgrep:
    runs-on: ubuntu-latest
    container: semgrep/semgrep
    steps:
      - uses: actions/checkout@v4
      - run: semgrep ci --config p/python --config p/react
                        --config p/secrets --config p/dockerfile
        env:
          SEMGREP_RULES: p/default

  python-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install bandit[toml] pip-audit
      - run: bandit -r backend/app -ll -f sarif -o bandit.sarif
      - run: pip-audit -r backend/requirements.txt
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: bandit.sarif }

  node-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci --prefix frontend
      - run: npm audit --prefix frontend --audit-level=high

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2

  container:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f Dockerfile.prod -t reqmesh:ci .
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: reqmesh:ci
          severity: HIGH,CRITICAL
          exit-code: '1'
          format: sarif
          output: trivy.sarif
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: trivy.sarif }
```

Add Dependabot (`.github/dependabot.yml`) for `pip`, `npm`, `docker` and `github-actions` ecosystems. Note the tension with your pinned-exact-versions policy — Dependabot PRs are how you keep pinning without stagnating, and the pinning is what makes the SBOM meaningful. Keep both.

### 6.2 Nightly dynamic scan

A ZAP baseline scan against a live instance catches header regressions, cookie flag mistakes and CORS drift that static analysis cannot. Roughly twenty lines: `docker compose up -d`, wait for `/api/health`, run `zaproxy/action-baseline` against `http://localhost:8000`, publish the report. Seed the demo project first so the scan has real content to crawl.

### 6.3 Fuzzing

Three targets, in descending order of value. All consume untrusted input and hold the most state.

1. **The expression evaluator** — Atheris or Hypothesis. Assert: no exception escapes as a 500, no execution exceeds a time bound, no attribute access reaches a dunder.
2. **The ReqIF importer** — Atheris with a seed corpus of valid ReqIF files. Assert: no unhandled exception, bounded memory, no filesystem or network access during parse.
3. **The YAML store loader** — Hypothesis generating structurally valid but semantically hostile entity files. This is the harness that proves F-09 is fixed.

Run in CI at a low iteration count per commit; longer campaigns on the weekly schedule.

---

## 7. Priority summary

If only a handful of things get done, do these, in this order:

1. **F-02 / F-03** — anonymous read and open self-registration are the acute exposure on any networked deployment. *One evening.*
2. **F-10 / F-15** — unsafe YAML or XML parsing would be remote code execution. Verification alone may close both. *One evening.*
3. **F-17** — server-side HTML sanitisation, plus CSP as defence in depth. *One weekend.*
4. **F-09** — re-validate on load; the git path is not the API path. *One to two weekends.*
5. **F-13** — path containment on `/scan` and references. *One evening.*
6. **F-04 / F-05** — logged credentials and ineffective rate limiting. *One evening.*
7. **Phase 0 CI** — so none of the above regresses. *One weekend.*
8. **F-01, OIDC** — the adoption blocker for your most demanding audience. *Two to three weekends.*

Items 1, 2, 5 and 6 total roughly one weekend between them and remove most of the acute risk. That is the highest-leverage weekend available to this project.

---

## 8. Open items requiring your input

1. `AUDIT.md` — unread. It may already close a substantial number of the **Verify** items above, and this document should be reconciled against it before any work starts.
2. `DEPLOYMENT.md` — unread. Determines how much of §4.3's operational guidance already exists.
3. Whether the desktop build is a supported distribution channel or a convenience. This decides whether code signing (F-28) is a Phase 4 item or a blocker.
4. Whether you intend to keep the DO-330 path open (§4.2). It changes the priority of F-14 considerably.
