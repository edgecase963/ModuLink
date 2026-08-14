#!/usr/bin/env python3
"""Assert-based foundation suite (stdlib unittest — no pytest required).

    PYTHONPATH=. python -m unittest tests.test_foundation -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modulink import (
    Blueprint,
    ConstantModule,
    MathModule,
    SimulationModule,
    StrategyModule,
    module_from_json,
)
from modulink.testing import (
    StubAccount,
    StubEnvironment,
    run_blueprint,
    sample_market_package,
    wire,
)


class TestModules(unittest.TestCase):
    def test_module_json_round_trip(self):
        m = MathModule(name="M", mode="mul")
        restored = module_from_json(m.to_json())
        self.assertEqual(restored.mode, "mul")
        self.assertEqual(restored.module_type, "math")

    def test_simulation_ports_by_mode(self):
        wait = SimulationModule(completion_mode="wait")
        poll = SimulationModule(completion_mode="poll")
        self.assertNotIn("finished", wait.outputs)
        self.assertIn("finished", poll.outputs)

    def test_strategy_primary_meta(self):
        s = StrategyModule(
            strategies={"A": "x = 1\n", "B": "y = 2\n"},
            primary="B",
        )
        out = s.run({})
        self.assertEqual(out["strategies"]["__primary__"], "B")
        self.assertIn("A", out["strategies"])
        self.assertIn("B", out["strategies"])


class TestBlueprint(unittest.TestCase):
    def test_constant_math_wire(self):
        bp = Blueprint(name="t")
        a = ConstantModule(
            outputs={"value": "float"}, values={"value": "4"}
        )
        b = ConstantModule(
            outputs={"value": "float"}, values={"value": "5"}
        )
        mul = MathModule(mode="mul")
        bp.add_module(a)
        bp.add_module(b)
        bp.add_module(mul)
        wire(bp, a, "value", mul, "a")
        wire(bp, b, "value", mul, "b")
        results, _ = run_blueprint(bp)
        self.assertEqual(results[str(mul.module_id)]["result"], 20.0)

    def test_blueprint_json_preserves_connections(self):
        bp = Blueprint(name="t")
        a = ConstantModule(
            outputs={"value": "float"}, values={"value": "2"}
        )
        b = ConstantModule(
            outputs={"value": "float"}, values={"value": "2"}
        )
        add = MathModule(mode="add")
        bp.add_module(a)
        bp.add_module(b)
        bp.add_module(add)
        wire(bp, a, "value", add, "a")
        wire(bp, b, "value", add, "b")
        payload = bp.to_json()
        bp2 = Blueprint()
        bp2.from_json(payload)
        self.assertEqual(len(bp2.connections), 2)
        results, _ = run_blueprint(bp2)
        math_id = next(
            mid for mid, m in bp2.modules.items() if m.module_type == "math"
        )
        self.assertEqual(results[math_id]["result"], 4.0)


class TestHarness(unittest.TestCase):
    def test_sample_package_and_saved_data(self):
        package = sample_market_package("NQ", "1m", bars=3)
        account = StubAccount(datasets={"nq1": package})
        self.assertIn("nq1", account.data_index)
        loaded = account.load_data("nq1")
        self.assertEqual(loaded["data"]["NQ"]["1m"]["close"][-1], 102.5)

    def test_stub_simulation_finishes(self):
        env = StubEnvironment(sim_duration_sec=0.15)
        sim = SimulationModule(completion_mode="wait")
        sim._build_job = lambda inputs: {"params": {}, "strategy_name": "T"}
        out = sim.run({}, environment=env)
        self.assertEqual(out["status"], "Finished")
        self.assertNotIn("finished", out)


if __name__ == "__main__":
    unittest.main()
