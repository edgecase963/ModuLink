# ModuLink usage guide

ModuLink is a **logic-only** module / blueprint / group runtime. Host apps supply their own UI and a small environment/account surface. This package does not include Qt, a web front end, or any third-party runtime dependencies (Python 3.10+ standard library only).

This guide assumes ModuLink is already installed and importable.

## Contents

- [Import](#import)
- [Mental model](#mental-model)
- [Minimal example](#minimal-example)
- [Package map](#package-map)
- [Blueprints](#blueprints)
- [Module catalog](#module-catalog)
- [Host environment and account](#host-environment-and-account)
- [Testing helpers](#testing-helpers)
- [Python outline](#python-outline)
- [JSON](#json)
- [Run state and status](#run-state-and-status)

## Import

The top-level package re-exports core types, blueprint types, and helpers:

```python
import modulink
from modulink import (
    Blueprint,
    Connection,
    Group,
    ConstantModule,
    MathModule,
    MODULE_TYPES,
    module_from_json,
)
```

Submodules when you want a narrower import:

```python
import modulink.core as core
from modulink.blueprint import Blueprint, Connection, Group
from modulink.testing import StubEnvironment, StubAccount, wire, run_blueprint
from modulink.python_outline import build_python_outline
```

`modulink.__version__` is the package version.

## Mental model

A **module** is a typed node with named **input** and **output** ports (`{name: type_hint}`). Type hints are strings (`str`, `int`, `float`, `bool`, `number`, `any`, `list`, `dict`, `dataframe`, …) used by hosts and coercers; they are not enforced by a type checker.

A **connection** is a wire from one module’s output port to another module’s input port.

A **blueprint** is a graph: placed module instances, wires, optional layout **groups**, and per-run state. `Blueprint.run(environment=...)` executes modules in topological order. Values move **only** along wires — there is no implicit global bus.

An **environment** is a host object modules look up with `getattr`. An optional **account** on that environment holds secrets, saved datasets, and similar durable data. Session memory and throttle timestamps live on the environment, not the account.

Gating: if a required input is unwired, or every inbound wire is missing / `None`, the module is **skipped** (status idle, empty outputs). Downstream modules then skip unless they treat that port as optional. Returning `{}` from `run()` (condition fail, throttle block, prompt not activated) has the same effect.

## Minimal example

```python
from modulink import Blueprint, ConstantModule, MathModule
from modulink.testing import StubEnvironment, run_blueprint, wire

bp = Blueprint(name="arith")
a = ConstantModule(outputs={"value": "float"}, values={"value": "4"})
b = ConstantModule(outputs={"value": "float"}, values={"value": "5"})
mul = MathModule(mode="mul")

bp.add_module(a)
bp.add_module(b)
bp.add_module(mul)
wire(bp, a, "value", mul, "a")
wire(bp, b, "value", mul, "b")

results, _ = run_blueprint(bp, StubEnvironment())
print(results[str(mul.module_id)]["result"])  # 20.0
```

You can also call `bp.run(environment=env)` directly. `results` is `{module_id: outputs_dict}`.

## Package map

| Location | Role |
|----------|------|
| `modulink` | Public re-exports |
| `modulink.core` | Module classes, ports, registry, helpers |
| `modulink.blueprint` | `Connection`, `Group`, `Blueprint` runner |
| `modulink.python_outline` | Structural index of Python source |
| `modulink.testing` | `StubEnvironment`, `StubAccount`, `wire`, `run_blueprint` |

`MODULE_TYPES` lists registry ids. `MODULE_TYPE_MAP` maps id → class. `module_from_json(data)` reconstructs a module from `to_json()`.

## Blueprints

```python
bp = Blueprint(name="My graph", description="")
bp.add_module(module, x=0.0, y=0.0)
bp.add_connection(Connection(
    source_module=str(src.module_id),
    source_port="result",
    target_module=str(dst.module_id),
    target_port="a",
))
bp.add_group(Group(title="Inputs", member_ids=[str(a.module_id), str(b.module_id)]))
results = bp.run(on_update=None, environment=env)
bp.request_stop()  # cooperative halt before the next pending module
```

`modulink.testing.wire(bp, source, source_port, target, target_port)` is the usual helper.

### Execution rules

- Order is topological. Cycles raise `ValueError`.
- **Fan-in:** most ports keep a single wire (a new wire to the same port replaces the old one). Modules that return `allows_input_fan_in() == True` keep multiple wires; `run()` then sees a **list** of values.
- **Optional ports:** `optional_input_names()` may be left unwired.
- **None** on a wire is treated as “no value” (gated), same as a withheld port.
- **Iterator** modules re-run every module reachable from their outputs once per item.
- **Memory write-back:** a wire into Memory from a module that is downstream of that Memory is a soft feedback edge. Memory publishes its stored value first; write-back runs after the main pass.
- **Groups** are layout-only. They are serialized with the blueprint but ignored by the runner.
- `on_update(module_id)` is called as status/outputs change (live UI). Poll-mode simulation publishes mid-run outputs here without advancing the graph until `run()` returns.

### JSON

```python
payload = bp.to_json()
bp2 = Blueprint()
bp2.from_json(payload)
```

`payload` includes `name`, `description`, `modules`, `positions`, `connections`, `groups`. Module ids and connection ids are strings.

## Module catalog

Every module has `name`, `description`, `module_id`, `inputs`, `outputs`, `module_type`, plus `run(inputs, environment=None)`, `to_json()`, `from_json()`, and `clone()`.

Construct with keyword args, or `Cls(json_data=...)`. Ports often **sync from settings** (mode, kind, source); do not fight that by passing mismatched `inputs=` unless you know the subclass keeps them.

### Constant (`constant`)

Fixed outputs. No inputs. `values` is `{port: stored_string}`; `outputs` is `{port: type_hint}` (`str`, `int`, `float`, `bool`). Values are coerced at run time.

### Math (`math`)

Modes: `add`, `sub`, `mul`, `div`, `mod`, `pow`, `abs`, `neg`, `round`, `floor`, `ceil`, `sqrt`, `log`, `log10`, `exp`, `min`, `max`, `clamp`, `pct_change`.

Binary modes use `a` / `b` → `result`. Unary modes use `value` → `result`. `clamp` uses `value`, `min`, `max`. `pct_change` uses `old`, `new`.

`add`, `mul`, `min`, `max` allow fan-in (`b` optional).

### String (`string`)

Modes: `concat`, `join`, `upper`, `lower`, `title`, `strip`, `replace`, `split`, `contains`, `starts_with`, `ends_with`, `length`, `slice`.

Settings: `separator`, `find`, `replace_with`, `case_sensitive`. `concat` / `join` allow fan-in.

### Compare (`compare`)

Modes: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `all_equal`, `any_equal`, `between`, `approx_eq`. Output is always `result: bool`.

Binary modes take `a` / `b` (`b` optional if `b_value` is set). `all_equal` / `any_equal` fan-in on `value`. `between` uses `value`, `min`, `max`. `approx_eq` uses `epsilon`.

### Condition (`condition`)

Modes: `if`, `not` (one condition port), `and`, `or` (several).

- Default (`output_result=False`): passthrough ports become outputs when the condition passes; otherwise outputs are withheld.
- `output_result=True`: always emits bool `result`; no passthrough.

### Filter (`filter`)

Input `value` → `filtered`, `count`. Modes include contains / equals / regex / keyword include-exclude / field compare / datetime range / `limit`.

Settings: `pattern`, `keywords`, `field`, `op` (`==`, `!=`, `<`, …), `compare_value`, `limit`, `case_sensitive`. `wire_pattern=True` adds a `pattern` input (and `end` for `between_datetimes`). Duck-types lists, dicts, and pandas DataFrame/Series without importing pandas.

### Exec (`exec`)

Runs Python. Declared **input names are locals**; after `exec`, declared **output names are read back** from that namespace. `environment` is always injected (not a graph port).

- `code_source="embedded"` uses `code`.
- `code_source="input"` reads source from the `code_input` port (default `"code"`).
- `expose_console=True` adds a console output (default `"console"`) with stdout/stderr. On failure with console exposed, `ExecModuleFailedWithConsole` still publishes partial outputs so the graph can continue.

Assign output names in the script (`items = ['a', 'b']`), do not use an `outputs` dict.

### Data source (`data_source`)

| `source` | Inputs | Outputs | Host lookup |
|----------|--------|---------|-------------|
| `working_data` | `symbol`, `timeframe` | `data` | `environment.working_data_dict[symbol][timeframe]` |
| `economic_events` | — | `events` | `environment.economic_events` (or `econ_events`) |
| `saved_data` | `dataset_name` (optional if `dataset_name` setting is set) | `data` package | `account.load_data(name)` |
| `list_saved_data` | — | `names`, `index`, `count` | `account.data_index` |

Saved package shape: `{data, economic_events, stream_prices}`.

### AI (`ai`)

Input `prompt` (fan-in concatenates) → `response`. Calls `environment.request_modulink_ai(prompt=, system_prompt=, llm_client=)`. Settings: `system_prompt`, `llm_client` (`"auto"` lets the host pick).

### Message (`message`)

Inputs `message`, `to` → `sent`.

- `medium="host"` (default): `environment.send_message({...})`. Empty / `broadcast` / `all` / `*` send a broadcast payload; otherwise a directed `to` payload. If `client_ready` exists, it must be true.
- `medium="discord_webhook"`: `account.send_webhook_message(text, url)` with `to` as the URL.

### Audio (`audio`)

Input `path` → `played`. Calls `environment.play_modulink_audio(path, volume=)`. Setting: `volume` in `[0, 1]`.

### Secret (`secret`)

No inputs. Outputs `value`, `exists`. Reads `account.modulink_secrets[secret_name]`. The secret value is **never** stored in module/blueprint JSON.

### Memory (`memory`)

Session slot at `environment.modulink_memory[module_id]`. Survives blueprint re-runs on the same environment; not written to the account.

| `kind` | Inputs | Outputs |
|--------|--------|---------|
| `single` | `value`, `clear` | `value` |
| `list` | `item`, `clear` | `items`, `count` |
| `dict` | each key in `keys`, plus `clear` | each key, plus `data` |

All inputs optional; fan-in allowed. `output_is_set=True` adds `is_set`. `allow_duplicates` applies to list kind. `clear` truthy resets the slot.

### Throttle (`throttle`)

Rate-limits passthrough using `environment.modulink_throttle`. If the key fired within `interval_sec`, returns `{}` (dependents skip). Optional `key` input; otherwise `default_key` or the module id. Passthrough map is configurable (default `value`).

### Wait (`wait`)

- `duration`: optional `seconds` → `done`, `elapsed`
- `until`: optional `until` (clock string) → `done`, `elapsed`

Interruptible via the blueprint stop checker. `require_activate=True` waits only when wired `activate` is true. Optional `value` is passed through after a successful wait.

### Prompt (`prompt`)

Host UI dialog via `environment.prompt_modulink_form(spec)`.

- `trigger_mode="message"`: opens when wired `message` text arrives (fan-in joins).
- `trigger_mode="activate"`: built-in `message` setting; opens when `activate` is true.

Not activated → `{}`. Cancel → `accepted=False` only (field values withheld). Accept → field outputs plus `accepted=True`. Field types: `str`, `int`, `float`, `bool`, `choice`.

The host callback should return `{"accepted": bool, "values": {field_name: value}}`.

### Iterator (`iterator`)

Input `items` → `item`, `index`, `count`. The **blueprint** re-runs every reachable downstream module once per item (cap `ITERATOR_MAX_ITEMS` = 10_000). Empty iterable: `count=0`, body skipped.

Fan-in: one sequence is walked; several scalars become one pass each; several sequences are zipped (truncated to the shortest). Strings are a single item, not character-iterated.

### Strategy (`strategy`)

Private script bundle. Inputs `params`, `ops` (optional). Outputs `strategies`, `names`, `default_params`, `params`, `outline`.

- `strategies`: `{name: source}`; output also embeds `__primary__` (meta, not a script).
- `primary`: which script is primary (module setting, not a port).
- `param_defs`: `[{name, type, default}, ...]`.
- `params_mode`: `merge` or `replace` for the `params` input.
- `ops`: structured edits (`set`, `delete`, `rename`, `replace`, `set_params`, `set_primary`). See `format_strategy_ops_reference()`. Ops mutate **this module only**; they do not write `account.strategies`.

`outline` is produced by `python_outline.build_strategies_outline`.

### Simulation (`simulation`)

Starts a host job with `environment.start_modulink_simulation(job)` and polls `get_modulink_simulation(sim_id)` until a terminal status (`Finished`, `Stopped`, `Terminated`, `Error`). Optional `stop_modulink_simulation`.

Does **not** step bars through the ModuLink graph.

- `completion_mode="wait"` (default): block until done; no `finished` port; downstream runs once with finals.
- `completion_mode="poll"`: same block, but every `poll_interval_sec` publishes live outputs on run state (`finished` is False until the end).

Always-available inputs: `data`, `strategy`, `params`, `start_time`, `stop_time`, `stop` (all optional). Optional exposed inputs: `symbol`, `timeframe`, `step_size`, `funds` (`expose_*` flags). Outputs: `status`, `sim_id`, `performance`, `params`, and `finished` in poll mode. `emit_full_result=True` adds `full_result`. `run_target` is `local` or `auxiliary` (host-defined).

### Sim batch (`sim_batch`)

Read / summarize saved batches via `account.get_meta_folder()`, `account.load_sim_batch(path, password)`, and `environment.password`. Modes: `list`, `cache`, `load`, `sims`, `performance`. Names input is optional (empty → all known). Cache may live on `account.sim_batch_performance_cache`. Metrics fall back to `environment.calculate_performance_metrics` or per-metric helpers (`get_sortino_ratio`, …).

### Drawing (`drawing`)

Calls `environment.update_modulink_drawing(data)` or `clear_modulink_drawings()`. Types: `dot`, `x`, `line`, `text`, `circle`, `rectangle`, `candle`, `clear`. Each type has geometry ports (`name` plus coordinates). Style settings (`color`, `size`, `style`, `anchor`, …) are module fields, not ports. `clear` requires a true `clear` input.

---

## Host environment and account

Modules never import a host package. They use `getattr(environment, ...)` and `environment.account`. Missing required hooks raise `ValueError` (“requires a host environment” or a more specific message).

Implement only what your graphs need. `modulink.testing.StubEnvironment` / `StubAccount` are the reference stubs.

### Environment

| Attribute / method | Used by |
|--------------------|---------|
| `account` | secrets, saved data, webhooks, sim batches |
| `working_data_dict` | data source `working_data` |
| `economic_events` (or `econ_events`) | data source `economic_events` |
| `tzinfo` | datetime filter / wait-until |
| `password` | sim batch decrypt |
| `modulink_memory` | Memory (created if missing) |
| `modulink_throttle` | Throttle (created if missing) |
| `request_modulink_ai(prompt, system_prompt, llm_client)` | AI |
| `send_message(payload)` | Message `host` |
| `client_ready()` | Message `host` (optional) |
| `play_modulink_audio(path, volume)` | Audio |
| `update_modulink_drawing(data, graph=, remember=)` | Drawing |
| `clear_modulink_drawings()` / `remove_modulink_drawing(name)` | Drawing |
| `prompt_modulink_form(spec)` → `{accepted, values}` | Prompt |
| `start_modulink_simulation(job)` → `sim_id` | Simulation |
| `get_modulink_simulation(sim_id)` → snapshot or `None` | Simulation |
| `stop_modulink_simulation(sim_id)` | Simulation |
| `status_message(text)` | Simulation progress log (optional) |
| `calculate_performance_metrics` / `get_*` ratio helpers | Sim batch |

Installed by the blueprint **during** a module `run()` (do not set these yourself unless you are the runner):

- `_modulink_should_stop()` — cooperative cancel
- `_modulink_progress(partial_outputs)` — live UI publishes (poll simulation, etc.)

Exec scripts also receive `environment` as a local.

### Account

| Attribute / method | Used by |
|--------------------|---------|
| `modulink_secrets` | Secret |
| `data_index` | list / resolve saved datasets |
| `load_data(name)` | data source `saved_data` |
| `send_webhook_message(message, url)` | Message Discord |
| `get_meta_folder()` | sim batch paths |
| `load_sim_batch(path, password)` | sim batch load |
| `sim_batch_performance_cache` | sim batch cache mode |

Hosts may also store `account.strategies`; StrategyModule does not write it automatically.

## Testing helpers

```python
from modulink.testing import (
    StubAccount,
    StubEnvironment,
    sample_market_package,
    wire,
    run_blueprint,
)
```

- **StubAccount** — in-memory secrets and datasets; `send_webhook_message` returns True.
- **StubEnvironment** — memory, throttle, drawings, fake AI replies (`ai_replies`), fake progressing simulations (`sim_duration_sec`), captured `sent_messages` / `played_audio` / `status_log`.
- **sample_market_package(symbol, timeframe, bars)** — tiny OHLC-ish dict matching saved-data / simulation expectations.
- **wire** — add a `Connection`.
- **run_blueprint(bp, env=None, collect_updates=False)** → `(results, updates)`. Updates are `(module_id, status, outputs)` when `collect_updates=True`.

`StubEnvironment` does **not** implement `prompt_modulink_form`; attach one if you exercise Prompt.

## Python outline

```python
from modulink.python_outline import (
    build_python_outline,
    build_strategies_outline,
    flatten_outline,
)

tree = build_python_outline(source, nested=True)
flat = build_python_outline(source, nested=False)  # or flatten_outline(tree)
by_script = build_strategies_outline({"Demo": source})
```

Entry kinds: `class`, `function`, `async_function`, `method`, `async_method`, `variable`, `constant`, `import`, `import_from`, `error`. Fields include `name`, `qualified`, `lineno`, `end_lineno`, `signature`, `decorators`, `bases`, `annotation`, `detail`, `children`.

Used by StrategyModule’s `outline` output and by host editors.

## JSON

Round-trip a single module:

```python
from modulink import MathModule, module_from_json

original = MathModule(name="Add", mode="add")
restored = module_from_json(original.to_json())
```

Unknown `module_type` raises `ValueError`. `MODULE_MIME` (`application/x-modulink-module`) is a clipboard/drag hint for hosts, not used by the runner.

Display helpers hosts can reuse: `module_type_label`, `MODULE_TYPE_ACCENT`, `STATUS_OUTLINE_COLORS`, `format_value`, `format_port_section`, `GROUP_COLOR_PALETTE`.

## Run state and status

`bp.get_run_state(module_id)` → `ModuleRunState`:

- `status`: `idle` | `waiting` | `running` | `success` | `failed`
- `inputs` / `outputs` — last resolved maps
- `console` — log lines (`state.log(...)`)
- `error` — failure message

`bp.reset_run_states()` clears them. Every `Blueprint.run()` starts from a clean slate (`waiting`, then running/success/failed/idle).
