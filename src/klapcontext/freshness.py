"""Single source of truth for KlapContext index freshness."""
from __future__ import annotations

import json
from pathlib import Path

from .git import commit, dirty_files
from .scope import IndexScope, RULES_VERSION


VALID_STATES = {"CURRENT", "STALE", "UNINITIALIZED", "UNKNOWN"}


def evaluate_freshness(root: Path, scope: IndexScope | None = None) -> dict:
    root = root.resolve()
    state_file = root / ".klap" / "state.json"
    if not state_file.exists():
        return {"status": "UNINITIALIZED", "reason": "No existe un snapshot de KlapContext.", "causes": ["missing_state"], "irrelevant_changes": []}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "UNKNOWN", "reason": "state.json no es válido o no puede leerse.", "causes": ["invalid_state"], "irrelevant_changes": []}
    scope = scope or IndexScope.load(root, write_default=False)
    current_commit = commit(root)
    recorded_commit = state.get("git_commit")
    recorded_scope = state.get("scope", {}) if isinstance(state.get("scope"), dict) else {}
    causes = []
    if recorded_commit != current_commit:
        causes.append("head_changed")
    if recorded_scope.get("rules_version") != RULES_VERSION:
        causes.append("scope_rules_changed")
    current_hash = scope.snapshot_hash()
    if recorded_scope.get("hash") != current_hash:
        causes.append("eligible_files_changed")
    relevant = scope.relevant_paths
    changed = [path.replace("\\", "/") for path in dirty_files(root)]
    irrelevant = sorted(path for path in changed if path not in relevant and not any(path.startswith(prefix + "/") for prefix in relevant if "." not in Path(prefix).name))
    if causes:
        explanations = {
            "head_changed": "HEAD no coincide con el commit analizado",
            "scope_rules_changed": "cambió la versión de reglas de alcance",
            "eligible_files_changed": "cambió código, metadata o configuración incluida en el alcance",
        }
        return {"status": "STALE", "reason": "; ".join(explanations[item] for item in causes) + ".", "causes": causes, "scope_hash": current_hash, "irrelevant_changes": irrelevant}
    reason = "El commit, los archivos elegibles y la configuración de alcance coinciden con el snapshot."
    if irrelevant:
        reason += f" {len(irrelevant)} cambio(s) fuera del alcance no afectan el índice."
    return {"status": "CURRENT", "reason": reason, "causes": [], "scope_hash": current_hash, "irrelevant_changes": irrelevant}
