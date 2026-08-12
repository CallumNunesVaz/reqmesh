"""Where reqmesh keeps its own state, as opposed to a project's data.

One resolution, used by every module that writes something the operator did not
author: accounts, the signing secret, reset tokens, admin settings overrides.

Split out because two modules had drifted apart. `auth.py` honoured
``RT_STATE_DIR``; `settings_store.py` hardcoded ``$HOME``. In the Docker
deployment ``HOME`` is ``/app`` on a read-only root filesystem, so the settings
file could not be written at all — the admin Settings UI silently failed to
persist anything, which is the same failure the auth files were moved off
``$HOME`` to fix.

Callers resolve this **once, into a module-level constant**. Two things depend on
that: `tests/conftest.py` monkeypatches those constants, and
`tests/test_auth_state_dir.py` proves the paths by reloading the module. A
per-call lookup would defeat both.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    """The state directory: ``RT_STATE_DIR``, else ``~/.reqmesh``.

    An empty ``RT_STATE_DIR`` falls back rather than resolving to the filesystem
    root — the `or` matters, and `test_auth_state_dir.py` pins it.
    """
    return Path(os.environ.get("RT_STATE_DIR") or (Path.home() / ".reqmesh"))
