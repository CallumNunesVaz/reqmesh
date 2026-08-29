# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in reqmesh, please report it privately.

- **GitHub Security Advisories**: Use the
  [Report a vulnerability](https://github.com/CallumNunesVaz/reqmesh/security/advisories/new)
  form (preferred).
- **Email**: security@reqmesh.dev (monitored by the maintainer)

Please do **not** open a public issue.

## Scope

This policy covers the reqmesh application source code, official container images,
and the build/install infrastructure in this repository.

It does **not** cover:

- Vulnerabilities in third-party dependencies (report those upstream and we
  will update the pinned version)
- Vulnerabilities that require already-administrative access to the host
- Issues in the demo project (`seed_cessna.py`) or its output
- Theoretical attacks with no practical exploit path that are already
  mitigated by documented deployment controls

## Disclosure Window

We aim to acknowledge reports within **72 hours** and provide an initial
assessment within **7 days**. Fixes are targeted for release within **90 days**
of confirmation. We request that reporters maintain confidentiality until a
fix is published.

This is an evening/weekend project — response times respect that.

## Safe Harbour

We consider vulnerability research and coordinated disclosure to be
authorized conduct under the Computer Fraud and Abuse Act, the Digital
Millennium Copyright Act, and the Australian _Cybercrime Act 2001_.
If a third party brings a claim against you related to research conforming
to this policy, we will make clear that your actions were authorized.

## Accepted Threat Models

Before reporting, please understand reqmesh's documented threat model:

1. **Unauthenticated network attacker** — can reach the service port
2. **Authenticated low-privilege user** — valid `guest`/`contributor` credentials
3. **Malicious project data via git pull** — YAML arriving on disk through the
   shared git remote, bypassing the API
4. **Malicious interchange file** — uploaded ReqIF, SysML, XLSX, CSV
5. **Compromised dependency** — supply-chain attack on a transitive package

A project's git SSH deploy key is stored **unencrypted at rest** on disk
(`<data root>/.ssh/<project>/id_ed25519`). This is forced, not chosen: pushes
run unattended under `BatchMode=yes`, which admits no passphrase prompt, so a
passphrased key could never be used for an automated push. An attacker who
gains filesystem access to the data volume, or administrative access to the
application, can therefore read the key and gain push access to the project's
configured remote. Deploy keys should be scoped to a single repository and
revoked at the host when a project is decommissioned.

The project is GPL-3.0-or-later; source is openly available to attackers by
design. Threats that require source access to identify are acknowledged but
are assigned lower severity.

## Known Issues

A running list of known, accepted limitations is maintained internally and is
not published, because it records unfixed findings in enough detail to act on
them. If you want to know whether something you have found is already tracked,
raise it through the process above and you will be told.

## Permission tiers and the view gate

Each project's `_meta.yaml` carries a `permissions` map from role to one of five
tiers, lowest first: `none`, `view`, `propose`, `edit`, `admin`.

- `none` — no access at all; even reads are denied
- `view` — read-only
- `propose` — create change requests, risks, comments, decisions
- `edit` — edit requirements, components, specifications, baselines
- `admin` — everything, including project settings and the git remote

The **default** permissions map still grants `view` to every role, so the `view`
gate does not switch an instance to default-deny: it makes denial *possible*. A
project denies a role all access by setting that role's tier to `none` through
the project settings update. A global `admin` is never demoted by a project's
map.

At the time of writing the `view` gate is enforced on a single route
(`GET /projects/{project_id}/publish/download`); gating the rest of the read
surface is tracked follow-up work.

## Supported Versions

| Version | Supported |
|---|---|
| Latest tagged release | Yes |
| `main` branch | Yes (pre-release) |
| Older releases | No |

Container images are published with immutable semver tags and digests.
Check `/api/health` for the running version.
