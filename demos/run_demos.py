#!/usr/bin/env python3
"""ModuLink foundation demos — run from the ModuLink repo root:

    PYTHONPATH=. python demos/run_demos.py
    PYTHONPATH=. python demos/run_demos.py math memory simulation

Each demo prints a short narrative and raises on failure so CI / hosts can
reuse the same scenarios.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

# Allow running without an editable install.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modulink import (  # noqa: E402
    Blueprint,
    CompareModule,
    ConditionModule,
    ConstantModule,
    DataSourceModule,
    ExecModule,
    Group,
    IteratorModule,
    MathModule,
    MemoryModule,
    MODULE_TYPES,
    SecretModule,
    SimulationModule,
    StrategyModule,
    StringModule,
    WaitModule,
    module_from_json,
    python_outline,
)
from modulink.testing import (  # noqa: E402
    StubAccount,
    StubEnvironment,
    run_blueprint,
    sample_market_package,
    wire,
)


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def demo_registry() -> None:
    """Registered module types and JSON round-trip for a few modules."""
    _section("registry / JSON round-trip")
    assert "simulation" in MODULE_TYPES
    assert "strategy" in MODULE_TYPES
    print(f"MODULE_TYPES ({len(MODULE_TYPES)}): {', '.join(MODULE_TYPES)}")

    original = MathModule(name="Add", mode="add")
    payload = original.to_json()
    restored = module_from_json(payload)
    assert restored.module_type == "math"
    assert restored.mode == "add"
    assert restored.inputs == original.inputs
    print("MathModule JSON round-trip OK")

    sim = SimulationModule(name="Sim", completion_mode="poll", poll_interval_sec=0.2)
    sim2 = module_from_json(sim.to_json())
    assert sim2.completion_mode == "poll"
    assert "finished" in sim2.outputs
    wait = SimulationModule(completion_mode="wait")
    assert "finished" not in wait.outputs
    print("SimulationModule wait/poll ports OK")


def demo_math_string_compare() -> None:
    """Constant → Math / String / Compare graph."""
    _section("math / string / compare")
    bp = Blueprint(name="arith")
    a = ConstantModule(
        name="A",
        outputs={"value": "float"},
        values={"value": "10"},
    )
    b = ConstantModule(
        name="B",
        outputs={"value": "float"},
        values={"value": "3"},
    )
    add = MathModule(name="Add", mode="add")
    label = ConstantModule(
        name="Label",
        outputs={"value": "str"},
        values={"value": "sum="},
    )
    concat = StringModule(name="Concat", mode="concat")
    cmp_eq = CompareModule(name="EqZero", mode="eq")
    zero = ConstantModule(
        name="Zero",
        outputs={"value": "float"},
        values={"value": "0"},
    )

    for mod, x in (
        (a, 0),
        (b, 100),
        (add, 200),
        (label, 300),
        (concat, 400),
        (cmp_eq, 500),
        (zero, 600),
    ):
        bp.add_module(mod, x=x, y=0)

    wire(bp, a, "value", add, "a")
    wire(bp, b, "value", add, "b")
    wire(bp, label, "value", concat, "a")
    wire(bp, add, "result", concat, "b")
    wire(bp, add, "result", cmp_eq, "a")
    wire(bp, zero, "value", cmp_eq, "b")

    results, _ = run_blueprint(bp)
    assert results[str(add.module_id)]["result"] == 13.0
    text = results[str(concat.module_id)]["result"]
    assert "13" in str(text)
    assert results[str(cmp_eq.module_id)]["result"] is False
    print(f"add=13, concat={text!r}, eq_zero=False")


def demo_condition_gate() -> None:
    """Condition passthrough vs withhold."""
    _section("condition gate")
    bp = Blueprint(name="gate")
    flag = ConstantModule(
        name="Flag",
        outputs={"value": "bool"},
        values={"value": "true"},
    )
    payload = ConstantModule(
        name="Payload",
        outputs={"value": "str"},
        values={"value": "hello"},
    )
    gate = ConditionModule(
        name="Gate",
        mode="if",
        output_result=False,
        condition_inputs={"cond": "bool"},
        passthrough={"value": "any"},
    )
    for mod in (flag, payload, gate):
        bp.add_module(mod)
    wire(bp, flag, "value", gate, "cond")
    wire(bp, payload, "value", gate, "value")

    results, _ = run_blueprint(bp)
    assert results[str(gate.module_id)]["value"] == "hello"
    print("condition True → passthrough hello")

    flag.values["value"] = "false"
    results2, _ = run_blueprint(bp)
    # False → empty outputs (passthrough withheld); still recorded as success.
    gate_out = results2.get(str(gate.module_id), {})
    assert gate_out == {} or "value" not in gate_out
    print("condition False → withheld")


def demo_memory_session() -> None:
    """Memory survives across blueprint runs on the same environment."""
    _section("memory session")
    env = StubEnvironment()
    bp = Blueprint(name="mem")
    writer = ConstantModule(
        name="Write",
        outputs={"value": "str"},
        values={"value": "alpha"},
    )
    mem = MemoryModule(name="Slot", kind="single", output_is_set=True)
    bp.add_module(writer)
    bp.add_module(mem)
    wire(bp, writer, "value", mem, "value")

    results, _ = run_blueprint(bp, env)
    mid = str(mem.module_id)
    assert results[mid]["value"] == "alpha"
    assert results[mid].get("is_set") is True

    # Second run: no write wire change — still holds alpha unless cleared.
    reader_bp = Blueprint(name="mem2")
    # Re-attach same Memory module instance so module_id (slot key) matches.
    reader_bp.add_module(mem)
    results2, _ = run_blueprint(reader_bp, env)
    assert results2[mid]["value"] == "alpha"
    print(f"memory slot retained: {env.modulink_memory[mid]!r}")


def demo_iterator() -> None:
    """Iterator fans out downstream once per item."""
    _section("iterator")
    bp = Blueprint(name="iter")
    # Exec injects output names as locals — assign `items`, don't use outputs[].
    items = ExecModule(
        name="Items",
        code="items = ['a', 'b', 'c']",
        inputs={},
        outputs={"items": "list"},
    )
    it = IteratorModule(name="Each")
    upper = StringModule(name="Upper", mode="upper")
    mem = MemoryModule(name="Collected", kind="list", allow_duplicates=True)

    bp.add_module(items, x=0)
    bp.add_module(it, x=100)
    bp.add_module(upper, x=200)
    bp.add_module(mem, x=300)
    wire(bp, items, "items", it, "items")
    wire(bp, it, "item", upper, "value")
    wire(bp, upper, "result", mem, "item")

    env = StubEnvironment()
    results, _ = run_blueprint(bp, env)
    collected = results[str(mem.module_id)]["items"]
    assert collected == ["A", "B", "C"], collected
    print(f"iterator collected {collected}")


def demo_exec_and_secrets() -> None:
    """ExecModule + SecretModule."""
    _section("exec / secrets")
    env = StubEnvironment(
        account=StubAccount(secrets={"api_key": "demo-secret-99"})
    )
    bp = Blueprint(name="exec")
    secret = SecretModule(name="Key", secret_name="api_key")
    exec_mod = ExecModule(
        name="Mask",
        code="masked = (str(key)[:4] + '…') if key else ''\n",
        inputs={"key": "str"},
        outputs={"masked": "str"},
    )
    bp.add_module(secret)
    bp.add_module(exec_mod)
    wire(bp, secret, "value", exec_mod, "key")
    results, _ = run_blueprint(bp, env)
    masked = results[str(exec_mod.module_id)]["masked"]
    assert masked.startswith("demo"), masked
    print(f"secret → exec masked={masked!r}")


def demo_strategy_outline() -> None:
    """Strategy bundle + python_outline."""
    _section("strategy / outline")
    code = (
        "def on_bar(ctx):\n"
        "    x = 1\n"
        "    return x\n"
        "\n"
        "PARAM = 3\n"
    )
    strat = StrategyModule(
        name="Bundle",
        strategies={"Demo": code},
        primary="Demo",
        param_defs=[{"name": "size", "default": 1}],
    )
    out = strat.run({})
    assert "strategies" in out
    assert out["strategies"].get("__primary__") == "Demo"
    assert "Demo" in out["strategies"]
    outline = out.get("outline") or {}
    assert "Demo" in outline and outline["Demo"], outline
    built = python_outline.build_python_outline(code)
    assert built, built
    print(f"primary={out['strategies'].get('__primary__')}, outline={len(built)} entries")


def demo_data_source() -> None:
    """Working data + saved_data package."""
    _section("data source")
    package = sample_market_package("ES", "5m")
    env = StubEnvironment(
        working_data={"ES": {"5m": package["data"]["ES"]["5m"]}},
        account=StubAccount(datasets={"demo_es": package}),
    )

    bp = Blueprint(name="data")
    sym = ConstantModule(
        name="Sym", outputs={"value": "str"}, values={"value": "ES"}
    )
    tf = ConstantModule(
        name="Tf", outputs={"value": "str"}, values={"value": "5m"}
    )
    working = DataSourceModule(name="Working", source="working_data")
    saved = DataSourceModule(
        name="Saved", source="saved_data", dataset_name="demo_es"
    )
    listed = DataSourceModule(name="List", source="list_saved_data")

    for mod in (sym, tf, working, saved, listed):
        bp.add_module(mod)
    wire(bp, sym, "value", working, "symbol")
    wire(bp, tf, "value", working, "timeframe")

    results, _ = run_blueprint(bp, env)
    assert "close" in results[str(working.module_id)]["data"]
    saved_pkg = results[str(saved.module_id)]["data"]
    assert "data" in saved_pkg and "ES" in saved_pkg["data"]
    assert "demo_es" in results[str(listed.module_id)]["names"]
    print("working + saved_data + list_saved_data OK")


def demo_simulation_wait_poll() -> None:
    """Simulation wait vs poll with live progress updates."""
    _section("simulation wait / poll")
    package = sample_market_package()
    env = StubEnvironment(sim_duration_sec=0.3)

    # --- wait mode ---
    wait_sim = SimulationModule(
        name="WaitSim",
        completion_mode="wait",
        symbol="ES",
        timeframe="5m",
    )
    wait_sim._build_job = lambda inputs: {
        "params": {"x": 1},
        "strategy_name": "Demo",
        "starting_funds": 50_000,
        "symbol": "ES",
        "timeframe": "5m",
    }
    out_wait = wait_sim.run({}, environment=env)
    assert out_wait["status"] == "Finished"
    assert "finished" not in out_wait
    print(f"wait mode final status={out_wait['status']}, keys={sorted(out_wait)}")

    # --- poll mode via blueprint (live state.outputs) ---
    env2 = StubEnvironment(sim_duration_sec=0.35)
    bp = Blueprint(name="sim_poll")
    poll_sim = SimulationModule(
        name="PollSim",
        completion_mode="poll",
        poll_interval_sec=0.1,
        symbol="ES",
        timeframe="5m",
    )
    poll_sim._build_job = lambda inputs: {
        "params": {},
        "strategy_name": "Demo",
        "starting_funds": 50_000,
        "symbol": "ES",
        "timeframe": "5m",
        "data": package,
    }
    bp.add_module(poll_sim)
    results, updates = run_blueprint(bp, env2, collect_updates=True)
    final = results[str(poll_sim.module_id)]
    assert final["finished"] is True
    live = [
        u
        for u in updates
        if u[0] == str(poll_sim.module_id)
        and u[1] == "running"
        and u[2].get("status") == "Running"
    ]
    assert live, "expected mid-run progress publishes"
    assert all(u[2].get("finished") is False for u in live)
    print(f"poll mode: {len(live)} live updates, final finished=True")


def demo_blueprint_groups_json() -> None:
    """Groups + full blueprint JSON round-trip."""
    _section("blueprint groups / JSON")
    bp = Blueprint(name="grouped", description="demo")
    c1 = ConstantModule(
        name="One", outputs={"value": "float"}, values={"value": "1"}
    )
    c2 = ConstantModule(
        name="Two", outputs={"value": "float"}, values={"value": "2"}
    )
    add = MathModule(name="Sum", mode="add")
    bp.add_module(c1, x=0, y=0)
    bp.add_module(c2, x=0, y=80)
    bp.add_module(add, x=160, y=40)
    wire(bp, c1, "value", add, "a")
    wire(bp, c2, "value", add, "b")
    group = Group(title="Inputs", member_ids=[str(c1.module_id), str(c2.module_id)])
    bp.add_group(group)

    payload = bp.to_json()
    bp2 = Blueprint()
    bp2.from_json(payload)
    assert len(bp2.modules) == 3
    assert len(bp2.groups) == 1
    results, _ = run_blueprint(bp2)
    # Find math module by type
    math_id = next(
        mid for mid, m in bp2.modules.items() if m.module_type == "math"
    )
    assert results[math_id]["result"] == 3.0
    print("group + blueprint JSON round-trip → sum=3")


def demo_wait_interruptible() -> None:
    """Short WaitModule duration."""
    _section("wait module")
    bp = Blueprint(name="wait")
    wait = WaitModule(name="Pause", mode="duration", seconds=0.05)
    bp.add_module(wait)
    results, _ = run_blueprint(bp)
    # Wait typically passes through optional value or just completes
    assert str(wait.module_id) in results or bp.get_run_state(
        str(wait.module_id)
    ).status in {"success", "idle"}
    print(f"wait status={bp.get_run_state(str(wait.module_id)).status}")


DEMOS = {
    "registry": demo_registry,
    "math": demo_math_string_compare,
    "condition": demo_condition_gate,
    "memory": demo_memory_session,
    "iterator": demo_iterator,
    "exec": demo_exec_and_secrets,
    "strategy": demo_strategy_outline,
    "data": demo_data_source,
    "simulation": demo_simulation_wait_poll,
    "blueprint": demo_blueprint_groups_json,
    "wait": demo_wait_interruptible,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ModuLink foundation demos.")
    parser.add_argument(
        "names",
        nargs="*",
        help=f"Demo names (default: all). Choices: {', '.join(DEMOS)}",
    )
    args = parser.parse_args(argv)
    selected = args.names or list(DEMOS.keys())
    unknown = [n for n in selected if n not in DEMOS]
    if unknown:
        print(f"Unknown demos: {unknown}", file=sys.stderr)
        return 2

    failed = []
    for name in selected:
        try:
            DEMOS[name]()
            print(f"OK  {name}")
        except Exception as exc:
            failed.append(name)
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            traceback.print_exc()

    print()
    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}")
        return 1
    print(f"All {len(selected)} demos passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
