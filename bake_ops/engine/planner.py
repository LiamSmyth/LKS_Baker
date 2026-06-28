"""Compile enabled bake maps into ordered mesh/derive steps (engine planner)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lks_baker.bake_ops.engine.catalog_bridge import (
    BAKE_MAP_CATALOG,
    LKS_BakeMapSpec,
    get_bake_map_spec,
    resolve_map_enabled,
)
from lks_baker.bake_ops.static_utilities.bake_export_helpers import ensure_export_directory
from lks_baker.bake_ops.static_utilities.bake_low_material_helpers import bake_image_file_extension

def _bake_output_filepath(project, group_name: str, output_suffix: str) -> Path:
    ext = bake_image_file_extension(project)
    root = ensure_export_directory(project.output_dir)
    group_dir = root / group_name
    return group_dir / f'{group_name}_{output_suffix}.{ext}'


_PASS_GROUP_ORDER: dict[str, int] = {
    'raycast': 10,
    'shader_height': 20,
    'shader_curvature': 30,
    'shader_convexity': 31,
    'shader_cavity': 32,
    'shader_thickness': 33,
    'lighting': 40,
    'shader_id': 50,
    'id_mask': 51,
    'shader_mask': 52,
    'shader_pbr': 60,
    'shader_vcol': 70,
}

# Internal prerequisite mesh/derive steps injected for derive chains.
_DERIVE_PREREQUISITES: dict[str, tuple[str, ...]] = {
    'normal_object': ('normal',),
    'bent_normal': ('normal_object', 'position'),
    'bent_normal_object': ('normal_object', 'position'),
    'curvature': ('normal_object', 'position'),
    'convexity': ('curvature',),
    'cavity': ('curvature',),
    'alpha_mask': ('transparency',),
}

# Derive input availability: any fully-satisfied group is enough (OR between groups).
_DERIVE_INPUT_OR_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {}


@dataclass(frozen=True)
class LKS_BakeJobStep:
    """One compiled bake/derive step."""

    map_id: str
    spec: LKS_BakeMapSpec
    backend: str  # 'mesh' | 'derive' | 'engine'
    internal_prerequisite: bool = False


def _spec_sort_key(spec: LKS_BakeMapSpec) -> tuple[int, int]:
    return (_PASS_GROUP_ORDER.get(spec.pass_group, 99), spec.sort_order)


def _map_entry_for(project, map_id: str):
    for entry in project.map_entries:
        if entry.map_id == map_id:
            return entry
    return None


def resolve_map_backend_preference(map_entry) -> str:
    """Resolve map backend preference from the gear-menu Method selection."""
    if map_entry is None:
        return 'AUTO'
    from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
        resolve_map_backend_preference_from_method,
    )

    return resolve_map_backend_preference_from_method(map_entry)


def map_has_derive_path(spec: LKS_BakeMapSpec) -> bool:
    """Map has derive path.

    Args:
        spec: ``LKS_BakeMapSpec`` value.

    Returns:
        ``bool`` result.
    """
    return spec.derive_method is not None


def _input_available(
    project,
    group_name: str,
    map_id: str,
    *,
    scheduled: set[str],
    available_on_disk: set[str],
) -> bool:
    if map_id in scheduled or map_id in available_on_disk:
        return True
    spec = get_bake_map_spec(map_id)
    if spec is None:
        return False
    path = _bake_output_filepath(project, group_name, spec.output_suffix)
    return path.is_file()


def _is_or_group_alternative_satisfied(
    project,
    group_name: str,
    map_id: str,
    *,
    scheduled: set[str],
    available_on_disk: set[str],
) -> bool:
    """True when another OR prerequisite branch is already fully available."""
    for or_groups in _DERIVE_INPUT_OR_GROUPS.values():
        branch_with_map: tuple[str, ...] | None = None
        for group in or_groups:
            if map_id in group:
                branch_with_map = group
                break
        if branch_with_map is None:
            continue
        for group in or_groups:
            if group is branch_with_map:
                continue
            if all(
                _input_available(
                    project,
                    group_name,
                    alt_id,
                    scheduled=scheduled,
                    available_on_disk=available_on_disk,
                )
                for alt_id in group
            ):
                return True
    return False


def _can_reuse_existing_prerequisite(
    project,
    group_name: str,
    map_id: str,
    *,
    scheduled: set[str],
    available_on_disk: set[str],
) -> bool:
    """True when an internal prerequisite step can be skipped (file or OR alternative)."""
    if _input_available(
        project,
        group_name,
        map_id,
        scheduled=scheduled,
        available_on_disk=available_on_disk,
    ):
        return True
    return _is_or_group_alternative_satisfied(
        project,
        group_name,
        map_id,
        scheduled=scheduled,
        available_on_disk=available_on_disk,
    )


def _derive_inputs_ok(
    spec: LKS_BakeMapSpec,
    *,
    project,
    group_name: str,
    scheduled: set[str],
    available_on_disk: set[str],
) -> bool:
    or_groups = _DERIVE_INPUT_OR_GROUPS.get(spec.map_id)
    if or_groups:
        return any(
            all(
                _input_available(
                    project,
                    group_name,
                    parent_id,
                    scheduled=scheduled,
                    available_on_disk=available_on_disk,
                )
                for parent_id in group
            )
            for group in or_groups
        )
    parents = spec.derive_from or _DERIVE_PREREQUISITES.get(spec.map_id, ())
    return all(
        _input_available(
            project,
            group_name,
            parent_id,
            scheduled=scheduled,
            available_on_disk=available_on_disk,
        )
        for parent_id in parents
    ) if parents else True


def _prerequisite_map_ids(map_id: str, map_entry) -> tuple[str, ...]:
    from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
        engine_method_prerequisites,
        resolve_map_entry_bake_method,
    )

    method = resolve_map_entry_bake_method(map_entry, map_id=map_id) if map_entry else ''
    engine_parents = engine_method_prerequisites(map_id, method)
    if engine_parents:
        return engine_parents
    return _DERIVE_PREREQUISITES.get(map_id, ())


def select_map_backend(
    map_entry,
    spec: LKS_BakeMapSpec,
    *,
    project,
    group_name: str,
    scheduled: set[str],
    available_on_disk: set[str],
) -> str:
    """Return ``mesh``, ``derive``, or ``engine`` for one map at compile/execute time."""
    from lks_baker.bake_ops.static_utilities.bake_method_catalog import (
        is_registered_engine_method,
        resolve_map_entry_bake_method,
    )

    method = (
        resolve_map_entry_bake_method(map_entry, map_id=spec.map_id)
        if map_entry is not None
        else ''
    )
    map_type = spec.map_id
    if method and method != 'blender' and is_registered_engine_method(map_type, method):
        if map_has_derive_path(spec):
            inputs_ok = _derive_inputs_ok(
                spec,
                project=project,
                group_name=group_name,
                scheduled=scheduled,
                available_on_disk=available_on_disk,
            )
            return 'derive'
        return 'engine'

    pref = resolve_map_backend_preference(map_entry)
    eligible = map_has_derive_path(spec)

    inputs_ok = _derive_inputs_ok(
        spec,
        project=project,
        group_name=group_name,
        scheduled=scheduled,
        available_on_disk=available_on_disk,
    )

    if pref == 'MESH_ONLY' or not eligible:
        return 'mesh'
    if pref == 'DERIVE_ONLY':
        return 'derive' if inputs_ok else 'mesh'
    if eligible and inputs_ok:
        return 'derive'
    return 'mesh'


def _collect_requested_map_ids(
    project,
    map_ids: list[str] | None,
    *,
    require_enabled: bool,
) -> set[str]:
    if map_ids is not None:
        return set(map_ids)

    requested: set[str] = set()
    for entry in project.map_entries:
        if require_enabled and not entry.enabled:
            continue
        spec = get_bake_map_spec(entry.map_id)
        if spec is None or not spec.implemented:
            continue
        requested.add(entry.map_id)

    if require_enabled:
        for map_id, spec in BAKE_MAP_CATALOG.items():
            if not spec.implemented:
                continue
            if resolve_map_enabled(project, map_id):
                requested.add(map_id)
        return requested

    if requested:
        return requested

    return {map_id for map_id, spec in BAKE_MAP_CATALOG.items() if spec.implemented}


def _inject_prerequisites(requested: set[str], project=None) -> set[str]:
    expanded = set(requested)
    changed = True
    while changed:
        changed = False
        for map_id in list(expanded):
            map_entry = _map_entry_for(project, map_id) if project is not None else None
            for parent in _prerequisite_map_ids(map_id, map_entry):
                parent_spec = get_bake_map_spec(parent)
                if parent_spec is None or not parent_spec.implemented:
                    continue
                if parent not in expanded:
                    expanded.add(parent)
                    changed = True
    return expanded


def expand_bake_map_prerequisites(map_ids: set[str]) -> set[str]:
    """Return ``map_ids`` plus injected derive prerequisite map ids."""
    return _inject_prerequisites(map_ids)


def _topological_sort_steps(
    steps: list[LKS_BakeJobStep],
    project,
) -> list[LKS_BakeJobStep]:
    by_id = {step.map_id: step for step in steps}
    deps: dict[str, set[str]] = {}
    for step in steps:
        spec = step.spec
        map_entry = _map_entry_for(project, step.map_id)
        parents = set(spec.derive_from or _prerequisite_map_ids(step.map_id, map_entry))
        deps[step.map_id] = {p for p in parents if p in by_id}

    ordered: list[LKS_BakeJobStep] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(map_id: str) -> None:
        if map_id in visited:
            return
        if map_id in temp:
            return
        temp.add(map_id)
        for parent in deps.get(map_id, ()):
            visit(parent)
        temp.discard(map_id)
        visited.add(map_id)
        ordered.append(by_id[map_id])

    for step in sorted(steps, key=lambda s: _spec_sort_key(s.spec)):
        visit(step.map_id)

    return ordered


def compile_bake_job_steps(
    project,
    group_name: str,
    *,
    map_ids: list[str] | None = None,
    require_enabled: bool = True,
    reuse_existing_dependencies: bool = False,
) -> list[LKS_BakeJobStep]:
    """Enabled maps → prerequisite injection → backend selection → topo sort."""
    requested = _collect_requested_map_ids(project, map_ids, require_enabled=require_enabled)
    if not requested:
        return []

    expanded = _inject_prerequisites(requested, project)
    available_on_disk: set[str] = set()
    for map_id in expanded:
        spec = get_bake_map_spec(map_id)
        if spec is None:
            continue
        if _bake_output_filepath(project, group_name, spec.output_suffix).is_file():
            available_on_disk.add(map_id)

    scheduled: set[str] = set()
    steps: list[LKS_BakeJobStep] = []

    for map_id in sorted(expanded, key=lambda mid: _spec_sort_key(get_bake_map_spec(mid))):  # type: ignore[arg-type]
        spec = get_bake_map_spec(map_id)
        if spec is None or not spec.implemented:
            continue
        if map_id not in requested:
            needed = any(
                map_id in _prerequisite_map_ids(req, _map_entry_for(project, req))
                for req in requested
            )
            if not needed:
                continue
            if reuse_existing_dependencies and _can_reuse_existing_prerequisite(
                project,
                group_name,
                map_id,
                scheduled=scheduled,
                available_on_disk=available_on_disk,
            ):
                continue

        map_entry = _map_entry_for(project, map_id)
        backend = select_map_backend(
            map_entry,
            spec,
            project=project,
            group_name=group_name,
            scheduled=scheduled,
            available_on_disk=available_on_disk,
        )
        internal = map_id not in requested
        steps.append(
            LKS_BakeJobStep(
                map_id=map_id,
                spec=spec,
                backend=backend,
                internal_prerequisite=internal,
            ),
        )
        scheduled.add(map_id)

    return _topological_sort_steps(steps, project)
