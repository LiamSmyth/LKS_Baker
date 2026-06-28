# _template_addon

Blender Python addon scaffolding template — a complete, production-ready skeleton for Blender 4.2+ extension addons. This template is instantiated by the `addon_tools/generate.py` script, which copies it and replaces `LKS Baker`, `lks_baker`, and `LKS Baker` placeholder tokens with real values.

## What the Template Provides

- **Modular code architecture** — separate files for operators (`ops/`), utilities (`util/`), UI panels (`ui.py`), scene properties (`properties.py`), and a central registration orchestrator (`register_addon.py`)
- **Submodule (junction) support** — `submodules/` directory for Windows directory junctions that link in shared code from the parent `blender_utils/submodules/`
- **Dev-only module** — optional `dev/` package for local scaffolding (mock keymaps, test operators, debug panels) that is auto-excluded from published builds
- **Headless testing** — `unittest`-based test suite that runs inside Blender in `--background` mode
- **Batch launchers** — `.bat` scripts for launching Blender, running tests, building extension zips, and publishing to GitHub
- **AI-assisted development** — pre-configured `.cursor/` rules and agents, plus `.github/instructions/` for LLM context

## Registration Order

Properties → Ops → UI → Submodules (each with `parent_panel_id`) → Dev

Unregistration is strict reverse order. The `__init__.py` performs a deep-reload of all submodules before every registration cycle for hot-reload support.

## Submodule Contract

Shared modules linked into `submodules/` must expose three functions:

```python
def register(parent_panel_id: str | None = None) -> None: ...
def unregister() -> None: ...
def reload() -> None: ...
```

Submodules are standalone — they never import from the consuming addon.

## Publishing Filters

Files pass through three gates before reaching end users:

| Gate | Config | Controls |
|---|---|---|
| Extension zip | `blender_manifest.toml` `paths_exclude_pattern` | What goes into the `.zip` |
| Remote `main` branch | `.remoteignore` + `.gitignore` | What gets pushed to GitHub |
| Release build | Both of the above | Release builds from remote clone |
