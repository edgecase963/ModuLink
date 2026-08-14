# ModuLink

Portable **logic-only** module / blueprint / group runtime for host apps.

- No Qt / web UI — host apps provide their own front ends.
- Runtime depends only on the Python 3.10+ standard library (see `requirements.txt`).
- Install editable: `python3 install.py --dev` (or `pip install -e /path/to/ModuLink`)
- Import: `import modulink` or `from modulink import Blueprint, SimulationModule, ...`

## Package layout

| Module | Role |
|--------|------|
| `modulink.core` | Modules, ports, helpers, registry |
| `modulink.blueprint` | Blueprint runner, connections, groups |
| `modulink.python_outline` | Strategy script outline helper |
| `modulink.testing` | `StubEnvironment` / helpers for demos & host adapters |

## Demos & tests

```bash
cd /path/to/ModuLink
python3 install.py --dev                        # optional; then PYTHONPATH is not required
PYTHONPATH=. python demos/run_demos.py          # narrative demos (all)
PYTHONPATH=. python demos/run_demos.py math data simulation
PYTHONPATH=. python -m unittest tests.test_foundation -v
```

## Host environment hooks

Hosts implement a small environment/account surface that modules look up via `getattr`. Examples: `environment.start_modulink_simulation`, `get_modulink_simulation`, `request_modulink_ai`, `modulink_memory`, `account.modulink_secrets`, `account.load_data`, audio, drawings. See `modulink.core`. For local experiments, start from `modulink.testing.StubEnvironment` / `StubAccount`.

## Create wheel

```bash
python3 install.py --dev    # editable install + packaging tools (`build`)
python3 install.py          # write dist/modulink-*.whl
```

`python3 -m build --wheel` works after `--dev` as well. Prefer `python3 install.py` so a leftover `build/` directory cannot shadow the packaging tool.
