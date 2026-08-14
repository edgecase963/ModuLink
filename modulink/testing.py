"""Host-agnostic test / demo harness for ModuLink.

Provides a minimal Environment + Account stand-in so blueprints and modules
can run without a host UI. Hosts can subclass StubEnvironment
when building their own adapters.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Callable
from uuid import uuid4

from .blueprint import Blueprint, Connection
from .core import Module


class StubAccount:
    """Minimal account surface: secrets, saved datasets, optional webhooks."""

    def __init__(self, datasets: dict | None = None, secrets: dict | None = None):
        self.modulink_secrets = dict(secrets or {})
        # name → on-disk package shape {data, economic_events, stream_prices}
        self._datasets = {
            str(k): copy.deepcopy(v) for k, v in (datasets or {}).items()
        }

    @property
    def data_index(self) -> dict:
        """Dataset index: name → metadata stub."""
        return {name: {"name": name} for name in self._datasets}

    def load_data(self, name: str) -> dict | None:
        package = self._datasets.get(str(name))
        if package is None:
            return None
        return copy.deepcopy(package)

    def list_datasets(self) -> list[str]:
        return sorted(self._datasets.keys())

    def put_dataset(self, name: str, package: dict) -> None:
        self._datasets[str(name)] = copy.deepcopy(package)

    def send_webhook_message(self, message: str, url: str) -> bool:
        # Demos/tests can override or inspect via environment.sent_messages.
        return True


class StubEnvironment:
    """
    Stand-in Environment for demos and automated tests.

    Implements the hooks modules look up via getattr (simulation, AI, memory,
    messaging, audio, drawings). Extend or monkeypatch for host-specific needs.
    """

    def __init__(
        self,
        *,
        account: StubAccount | None = None,
        working_data: dict | None = None,
        economic_events: dict | None = None,
        sim_duration_sec: float = 0.25,
        sim_tick_sec: float = 0.05,
    ):
        self.account = account or StubAccount()
        self.working_data_dict = working_data if working_data is not None else {}
        self.economic_events = economic_events if economic_events is not None else {}
        self.modulink_memory: dict = {}
        self.modulink_throttle: dict = {}
        self.modulink_drawings: dict = {}
        self._modulink_sims: dict[str, dict] = {}
        self.sim_duration_sec = float(sim_duration_sec)
        self.sim_tick_sec = float(sim_tick_sec)
        self.sent_messages: list[dict] = []
        self.status_log: list[str] = []
        self.ai_replies: list[str] = ["stub-ai-reply"]
        self._ai_index = 0
        self.played_audio: list[dict] = []
        self._connected = True

    # --- messaging / status -------------------------------------------------

    def client_ready(self) -> bool:
        return bool(self._connected)

    def send_message(self, payload: dict) -> None:
        self.sent_messages.append(dict(payload or {}))

    def status_message(self, text: str) -> None:
        self.status_log.append(str(text))

    # --- AI -----------------------------------------------------------------

    def request_modulink_ai(
        self, prompt, system_prompt="", llm_client="auto", timeout_ms=180000
    ):
        if self._ai_index < len(self.ai_replies):
            reply = self.ai_replies[self._ai_index]
            self._ai_index += 1
        else:
            reply = self.ai_replies[-1] if self.ai_replies else ""
        return str(reply)

    # --- audio / drawings ---------------------------------------------------

    def play_modulink_audio(self, path: str, volume: float = 1.0) -> bool:
        self.played_audio.append({"path": path, "volume": float(volume)})
        return True

    def update_modulink_drawing(self, drawing_data, graph=None, remember=True):
        name = (drawing_data or {}).get("name")
        if not name:
            raise ValueError("ModuLink drawing requires a 'name'.")
        if remember:
            self.modulink_drawings[str(name)] = dict(drawing_data)
        return True

    def remove_modulink_drawing(self, name):
        self.modulink_drawings.pop(str(name), None)

    def clear_modulink_drawings(self):
        self.modulink_drawings.clear()

    # --- simulation (fake progressing job) ----------------------------------

    def start_modulink_simulation(self, job: dict) -> str:
        sim_id = str(uuid4())
        self._modulink_sims[sim_id] = {
            "sim_id": sim_id,
            "sim_name": (job or {}).get("strategy_name") or "StubSim",
            "status": "Running",
            "percent_complete": 0.0,
            "stopped": False,
            "paused": False,
            "pnl": 0.0,
            "funds": float((job or {}).get("starting_funds") or 100000.0),
            "start_funds": float((job or {}).get("starting_funds") or 100000.0),
            "fees_paid": 0.0,
            "num_trades": 0,
            "num_wins": 0,
            "num_losses": 0,
            "selected_strategy": (job or {}).get("strategy_name") or "",
            "current_symbol": (job or {}).get("symbol") or "",
            "starting_timeframe": (job or {}).get("timeframe") or "",
            "_t0": time.monotonic(),
            "_job": copy.deepcopy(job or {}),
        }
        return sim_id

    def get_modulink_simulation(self, sim_id: str) -> dict | None:
        snap = self._modulink_sims.get(str(sim_id))
        if snap is None:
            return None
        if snap.get("stopped") or snap.get("status") in {
            "Finished",
            "Stopped",
            "Terminated",
            "Error",
        }:
            return dict(snap)

        elapsed = time.monotonic() - float(snap.get("_t0") or time.monotonic())
        duration = max(0.05, self.sim_duration_sec)
        pct = min(100.0, (elapsed / duration) * 100.0)
        snap["percent_complete"] = pct
        snap["pnl"] = round(pct * 0.1, 4)
        snap["num_trades"] = int(pct // 25)
        if pct >= 100.0:
            snap["status"] = "Finished"
            snap["percent_complete"] = 100.0
            snap["pnl"] = 42.0
        else:
            snap["status"] = "Running"
        # Return a shallow copy without private keys for callers that iterate.
        out = {k: v for k, v in snap.items() if not str(k).startswith("_")}
        return out

    def stop_modulink_simulation(self, sim_id: str) -> None:
        snap = self._modulink_sims.get(str(sim_id))
        if not snap:
            return
        snap["stopped"] = True
        snap["status"] = "Stopped"


def sample_market_package(
    symbol: str = "ES",
    timeframe: str = "5m",
    bars: int = 8,
) -> dict:
    """Tiny OHLC-ish package matching saved_data / Simulation expectations."""
    frame = {
        "open": [100.0 + i for i in range(bars)],
        "high": [101.0 + i for i in range(bars)],
        "low": [99.0 + i for i in range(bars)],
        "close": [100.5 + i for i in range(bars)],
        "volume": [1000 + i * 10 for i in range(bars)],
    }
    return {
        "data": {symbol: {timeframe: frame}},
        "economic_events": {},
        "stream_prices": {symbol: 100.0 + bars},
    }


def wire(
    blueprint: Blueprint,
    source: Module,
    source_port: str,
    target: Module,
    target_port: str,
) -> Connection:
    """Connect two modules already added to the blueprint."""
    conn = Connection(
        source_module=str(source.module_id),
        source_port=source_port,
        target_module=str(target.module_id),
        target_port=target_port,
    )
    blueprint.add_connection(conn)
    return conn


def run_blueprint(
    blueprint: Blueprint,
    environment: StubEnvironment | None = None,
    *,
    collect_updates: bool = False,
) -> tuple[dict, list[tuple[str, str, dict]]]:
    """
    Run a blueprint; optionally collect (module_id, status, outputs) on_update.

    Returns (results, updates).
    """
    env = environment if environment is not None else StubEnvironment()
    updates: list[tuple[str, str, dict]] = []

    def on_update(module_id):
        if not collect_updates:
            return
        state = blueprint.get_run_state(module_id)
        updates.append(
            (
                str(module_id),
                str(getattr(state, "status", "") or ""),
                dict(getattr(state, "outputs", None) or {}),
            )
        )

    results = blueprint.run(
        on_update=on_update if collect_updates else None,
        environment=env,
    )
    return results, updates
