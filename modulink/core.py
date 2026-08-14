"""Portable ModuLink core: constants, helpers, modules, and registry.

Qt-free by design — host apps supply their own UI; this package is logic-only.
"""

from __future__ import annotations

import datetime
import json
import math as mathlib
import os
import re
import time
import traceback
from uuid import uuid4

from . import python_outline


MODULE_TYPES = (
    "exec",
    "data_source",
    "ai",
    "message",
    "constant",
    "condition",
    "filter",
    "math",
    "string",
    "compare",
    "wait",
    "prompt",
    "secret",
    "throttle",
    "sim_batch",
    "simulation",
    "memory",
    "drawing",
    "audio",
    "iterator",
    "strategy",
)
MODULE_MIME = "application/x-modulink-module"

# Display labels for library category headers (ids stay snake_case).
MODULE_TYPE_LABELS = {
    "exec": "Exec",
    "data_source": "Data Source",
    "ai": "AI",
    "message": "Message",
    "constant": "Constant",
    "condition": "Condition",
    "filter": "Filter",
    "math": "Math",
    "string": "String",
    "compare": "Compare",
    "wait": "Wait",
    "prompt": "Prompt",
    "secret": "Secret",
    "throttle": "Throttle",
    "sim_batch": "Sim Batch",
    "simulation": "Simulation",
    "memory": "Memory",
    "drawing": "Drawing",
    "audio": "Audio",
    "iterator": "Iterator",
    "strategy": "Strategy",
}


def module_type_label(module_type: str) -> str:
    key = str(module_type or "").strip()
    if key in MODULE_TYPE_LABELS:
        return MODULE_TYPE_LABELS[key]
    return key.replace("_", " ").title() or "Module"

EXEC_CODE_SOURCE_OPTIONS = (
    ("embedded", "Embedded script"),
    ("input", "From input"),
)
EXEC_DEFAULT_CODE_INPUT = "code"
EXEC_DEFAULT_CONSOLE_OUTPUT = "console"


class ExecModuleFailedWithConsole(Exception):
    """Exec failed, but console (and any partial outputs) are still available downstream."""

    def __init__(self, message: str, outputs: dict):
        super().__init__(message)
        self.outputs = dict(outputs or {})


DATA_SOURCE_OPTIONS = (
    ("working_data", "Working Data"),
    ("economic_events", "Econ Events"),
    ("saved_data", "Saved Data"),
    ("list_saved_data", "List Saved Data"),
)

DATA_SOURCE_DEFAULT_INPUTS = {"symbol": "str", "timeframe": "str"}
DATA_SOURCE_DEFAULT_OUTPUTS = {"data": "dataframe"}
DATA_SOURCE_PORTS = {
    "working_data": {
        "inputs": {"symbol": "str", "timeframe": "str"},
        "outputs": {"data": "dataframe"},
    },
    "economic_events": {
        "inputs": {},
        "outputs": {"events": "dict"},
    },
    "saved_data": {
        "inputs": {"dataset_name": "str"},
        # Single package matching account.save_data / load_data shape:
        # {"data": {...}, "economic_events": {...}, "stream_prices": {...}}
        "outputs": {"data": "dict"},
    },
    "list_saved_data": {
        "inputs": {},
        "outputs": {"names": "list", "index": "dict", "count": "int"},
    },
}

AI_DEFAULT_INPUTS = {"prompt": "str"}
AI_DEFAULT_OUTPUTS = {"response": "str"}
AI_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer clearly and directly."
)
# Empty / "auto" → server picks the least-busy LLM client.
AI_LLM_CLIENT_AUTO = "auto"

MESSAGE_MEDIUM_HOST = "host"
MESSAGE_MEDIUM_OPTIONS = (
    (MESSAGE_MEDIUM_HOST, "Host"),
    ("discord_webhook", "Discord Webhook"),
)
MESSAGE_DEFAULT_INPUTS = {"message": "str", "to": "str"}
MESSAGE_DEFAULT_OUTPUTS = {"sent": "bool"}
MESSAGE_BROADCAST_TARGETS = frozenset({"", "broadcast", "all", "*"})

AUDIO_DEFAULT_INPUTS = {"path": "str"}
AUDIO_DEFAULT_OUTPUTS = {"played": "bool"}
AUDIO_DEFAULT_VOLUME = 1.0

CONSTANT_VALUE_TYPES = ("str", "int", "float", "bool")
CONSTANT_DEFAULT_OUTPUTS = {"value": "str"}
CONSTANT_DEFAULT_VALUES = {"value": ""}

CONDITION_MODE_OPTIONS = (
    ("if", "If"),
    ("not", "Not"),
    ("and", "And"),
    ("or", "Or"),
)
CONDITION_DEFAULT_MODE = "if"
CONDITION_DEFAULT_CONDITION_INPUTS = {"cond": "bool"}
CONDITION_DEFAULT_PASSTHROUGH = {"value": "any"}
CONDITION_RESULT_PORT = "result"
CONDITION_SINGLE_MODES = frozenset({"if", "not"})
CONDITION_MULTI_MODES = frozenset({"and", "or"})

FILTER_MODE_OPTIONS = (
    ("contains", "Contains (dict keys / text)"),
    ("not_contains", "Does not contain"),
    ("equals", "Equals (dict keys / text)"),
    ("not_equals", "Not equals"),
    ("regex", "Regex"),
    ("include_any", "Include any keyword"),
    ("exclude_any", "Exclude any keyword"),
    ("key_equals", "Field equals"),
    ("key_contains", "Field contains"),
    ("where_compare", "Where compare"),
    ("before", "Before datetime"),
    ("after", "After datetime"),
    ("on_or_before", "On or before datetime"),
    ("on_or_after", "On or after datetime"),
    ("between_datetimes", "Between datetimes"),
    ("limit", "Limit"),
)
FILTER_DEFAULT_MODE = "contains"
FILTER_COMPARE_OPS = ("==", "!=", "<", "<=", ">", ">=")
FILTER_DEFAULT_INPUTS = {"value": "any"}
FILTER_DEFAULT_OUTPUTS = {"filtered": "any", "count": "int"}
FILTER_PATTERN_PORT = "pattern"
FILTER_END_PORT = "end"
FILTER_TEXT_MODES = frozenset(
    {"contains", "not_contains", "equals", "not_equals", "regex"}
)
FILTER_KEYWORD_MODES = frozenset({"include_any", "exclude_any"})
# Match a named field/column *inside* each record (econ events, sims, DataFrames).
FILTER_KEY_MODES = frozenset({"key_equals", "key_contains", "where_compare"})
FILTER_DATETIME_MODES = frozenset(
    {"before", "after", "on_or_before", "on_or_after", "between_datetimes"}
)

MATH_MODE_OPTIONS = (
    ("add", "Add"),
    ("sub", "Subtract"),
    ("mul", "Multiply"),
    ("div", "Divide"),
    ("mod", "Modulo"),
    ("pow", "Power"),
    ("abs", "Absolute"),
    ("neg", "Negate"),
    ("round", "Round"),
    ("floor", "Floor"),
    ("ceil", "Ceil"),
    ("sqrt", "Square root"),
    ("log", "Natural log"),
    ("log10", "Log base 10"),
    ("exp", "Exponential"),
    ("min", "Minimum"),
    ("max", "Maximum"),
    ("clamp", "Clamp"),
    ("pct_change", "Percent change"),
)
MATH_DEFAULT_MODE = "add"
MATH_PORTS = {
    "add": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "sub": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "mul": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "div": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "mod": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "pow": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "abs": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "neg": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "round": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "floor": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "ceil": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "sqrt": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "log": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "log10": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "exp": {"inputs": {"value": "number"}, "outputs": {"result": "number"}},
    "min": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "max": {"inputs": {"a": "number", "b": "number"}, "outputs": {"result": "number"}},
    "clamp": {
        "inputs": {"value": "number", "min": "number", "max": "number"},
        "outputs": {"result": "number"},
    },
    "pct_change": {
        "inputs": {"old": "number", "new": "number"},
        "outputs": {"result": "number"},
    },
}
MATH_FAN_IN_MODES = frozenset({"add", "mul", "min", "max"})

STRING_MODE_OPTIONS = (
    ("concat", "Concatenate"),
    ("join", "Join"),
    ("upper", "Uppercase"),
    ("lower", "Lowercase"),
    ("title", "Title case"),
    ("strip", "Strip"),
    ("replace", "Replace"),
    ("split", "Split"),
    ("contains", "Contains"),
    ("starts_with", "Starts with"),
    ("ends_with", "Ends with"),
    ("length", "Length"),
    ("slice", "Slice"),
)
STRING_DEFAULT_MODE = "concat"
STRING_PORTS = {
    "concat": {"inputs": {"a": "str", "b": "str"}, "outputs": {"result": "str"}},
    "join": {"inputs": {"value": "any"}, "outputs": {"result": "str"}},
    "upper": {"inputs": {"value": "str"}, "outputs": {"result": "str"}},
    "lower": {"inputs": {"value": "str"}, "outputs": {"result": "str"}},
    "title": {"inputs": {"value": "str"}, "outputs": {"result": "str"}},
    "strip": {"inputs": {"value": "str"}, "outputs": {"result": "str"}},
    "replace": {"inputs": {"value": "str"}, "outputs": {"result": "str"}},
    "split": {"inputs": {"value": "str"}, "outputs": {"parts": "list", "count": "int"}},
    "contains": {"inputs": {"value": "str"}, "outputs": {"result": "bool"}},
    "starts_with": {"inputs": {"value": "str"}, "outputs": {"result": "bool"}},
    "ends_with": {"inputs": {"value": "str"}, "outputs": {"result": "bool"}},
    "length": {"inputs": {"value": "str"}, "outputs": {"result": "int"}},
    "slice": {
        "inputs": {"value": "str", "start": "int", "end": "int"},
        "outputs": {"result": "str"},
    },
}
STRING_FAN_IN_MODES = frozenset({"concat", "join"})
STRING_PARAM_MODES = frozenset(
    {"join", "replace", "split", "contains", "starts_with", "ends_with"}
)

COMPARE_MODE_OPTIONS = (
    ("eq", "Equal (==)"),
    ("ne", "Not equal (!=)"),
    ("lt", "Less than (<)"),
    ("le", "Less or equal (<=)"),
    ("gt", "Greater than (>)"),
    ("ge", "Greater or equal (>=)"),
    ("all_equal", "All equal"),
    ("any_equal", "Any equal"),
    ("between", "Between (inclusive)"),
    ("approx_eq", "Approx equal"),
)
COMPARE_DEFAULT_MODE = "eq"
COMPARE_DEFAULT_EPSILON = 1e-9
COMPARE_DEFAULT_B_VALUE = ""
COMPARE_OUTPUTS = {"result": "bool"}
COMPARE_PORTS = {
    "eq": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "ne": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "lt": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "le": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "gt": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "ge": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "all_equal": {"inputs": {"value": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "any_equal": {"inputs": {"value": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
    "between": {
        "inputs": {"value": "any", "min": "any", "max": "any"},
        "outputs": dict(COMPARE_OUTPUTS),
    },
    "approx_eq": {"inputs": {"a": "any", "b": "any"}, "outputs": dict(COMPARE_OUTPUTS)},
}
COMPARE_FAN_IN_MODES = frozenset({"all_equal", "any_equal"})
COMPARE_BINARY_MODES = frozenset({"eq", "ne", "lt", "le", "gt", "ge", "approx_eq"})
COMPARE_MODE_OPS = {
    "eq": "==",
    "ne": "!=",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
}

SIM_BATCH_MODE_OPTIONS = (
    ("list", "List available batches"),
    ("cache", "Cached metrics"),
    ("load", "Load batches"),
    ("sims", "Load simulations"),
    ("performance", "Compute performance"),
)
SIM_BATCH_DEFAULT_MODE = "list"
SIM_BATCH_METRIC_KEYS = (
    "Sortino Ratio",
    "Calmar Ratio",
    "MAR Ratio",
    "Stability",
    "Win Rate",
    "Net PnL",
    "Max Drawdown",
)
SIM_BATCH_PORTS = {
    "list": {
        "inputs": {},
        "outputs": {"names": "list", "cache": "dict", "count": "int"},
    },
    "cache": {
        "inputs": {"names": "any"},
        "outputs": {"names": "list", "metrics": "dict", "count": "int"},
    },
    "load": {
        "inputs": {"names": "any"},
        "outputs": {"names": "list", "batches": "dict", "count": "int"},
    },
    "sims": {
        "inputs": {"names": "any"},
        "outputs": {"names": "list", "sims": "dict", "count": "int"},
    },
    "performance": {
        "inputs": {"names": "any"},
        "outputs": {
            "names": "list",
            "metrics": "dict",
            "combined": "dict",
            "count": "int",
        },
    },
}

MEMORY_KIND_OPTIONS = (
    ("single", "Single value"),
    ("list", "List"),
    ("dict", "Dictionary"),
)
MEMORY_DEFAULT_KIND = "single"
MEMORY_CLEAR_PORT = "clear"
MEMORY_DATA_PORT = "data"
MEMORY_IS_SET_PORT = "is_set"
MEMORY_RESERVED_PORTS = frozenset(
    {MEMORY_CLEAR_PORT, MEMORY_DATA_PORT, MEMORY_IS_SET_PORT}
)
MEMORY_DEFAULT_DICT_KEYS = ("key_a", "key_b")

THROTTLE_KEY_PORT = "key"
THROTTLE_DEFAULT_INTERVAL_SEC = 60.0
THROTTLE_DEFAULT_PASSTHROUGH = {"value": "any"}
THROTTLE_RESERVED_PORTS = frozenset({THROTTLE_KEY_PORT})

WAIT_MODE_OPTIONS = (
    ("duration", "Wait duration"),
    ("until", "Wait until time"),
)
WAIT_DEFAULT_MODE = "duration"
WAIT_DEFAULT_SECONDS = 5.0
WAIT_ACTIVATE_PORT = "activate"
WAIT_VALUE_PORT = "value"
WAIT_PORTS = {
    "duration": {
        "inputs": {"seconds": "number"},
        "outputs": {"done": "bool", "elapsed": "number"},
    },
    "until": {
        "inputs": {"until": "str"},
        "outputs": {"done": "bool", "elapsed": "number"},
    },
}

PROMPT_FIELD_TYPES = ("str", "int", "float", "bool", "choice")
PROMPT_DEFAULT_FIELDS = (
    {"name": "confirm", "type": "bool", "password": False, "label": "Confirm", "choices": ""},
)
PROMPT_ACCEPTED_PORT = "accepted"
PROMPT_MESSAGE_PORT = "message"
PROMPT_ACTIVATE_PORT = "activate"
PROMPT_TRIGGER_MODE_OPTIONS = (
    ("message", "Prompt when Message arrives"),
    ("activate", "Built-in message + Activate gate"),
)
PROMPT_DEFAULT_TRIGGER_MODE = "message"
PROMPT_RESERVED_PORTS = frozenset(
    {PROMPT_ACCEPTED_PORT, PROMPT_MESSAGE_PORT, PROMPT_ACTIVATE_PORT}
)

SECRET_DEFAULT_NAME = ""
SECRET_OUTPUTS = {"value": "str", "exists": "bool"}

ITERATOR_ITEMS_PORT = "items"
ITERATOR_ITEM_PORT = "item"
ITERATOR_INDEX_PORT = "index"
ITERATOR_COUNT_PORT = "count"
ITERATOR_DEFAULT_INPUTS = {ITERATOR_ITEMS_PORT: "any"}
ITERATOR_DEFAULT_OUTPUTS = {
    ITERATOR_ITEM_PORT: "any",
    ITERATOR_INDEX_PORT: "int",
    ITERATOR_COUNT_PORT: "int",
}
ITERATOR_MAX_ITEMS = 10_000

STRATEGY_PARAMS_PORT = "params"
STRATEGY_OPS_PORT = "ops"
# Reserved key embedded in StrategyModule.strategies output (not a real script).
# Stripped on account import/export/restore and ignored by Simulation resolve.
STRATEGY_PRIMARY_META_KEY = "__primary__"
STRATEGY_META_KEYS = frozenset({STRATEGY_PRIMARY_META_KEY})
STRATEGY_DEFAULT_INPUTS = {
    STRATEGY_PARAMS_PORT: "dict",
    STRATEGY_OPS_PORT: "list",
}
STRATEGY_DEFAULT_OUTPUTS = {
    "strategies": "dict",
    "names": "list",
    "default_params": "dict",
    "params": "dict",
    "outline": "dict",
}
STRATEGY_PARAMS_MODE_OPTIONS = (
    ("merge", "Merge overrides into defaults"),
    ("replace", "Replace defaults with overrides"),
)
STRATEGY_DEFAULT_PARAMS_MODE = "merge"


def is_strategy_meta_key(name) -> bool:
    """True for reserved strategies-dict keys (e.g. __primary__)."""
    text = str(name or "")
    return text in STRATEGY_META_KEYS or (
        len(text) >= 4 and text.startswith("__") and text.endswith("__")
    )


def strategy_scripts_only(strategies) -> dict:
    """Return {name: code} with meta keys (e.g. __primary__) removed."""
    if not isinstance(strategies, dict):
        return {}
    out = {}
    for key, code in strategies.items():
        name = str(key)
        if is_strategy_meta_key(name):
            continue
        out[name] = "" if code is None else str(code)
    return out


def strategy_primary_from_payload(strategies, fallback: str = "") -> str:
    """Read primary from strategies payload meta, else fallback."""
    if isinstance(strategies, dict) and STRATEGY_PRIMARY_META_KEY in strategies:
        raw = strategies.get(STRATEGY_PRIMARY_META_KEY)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return str(fallback or "").strip()


def with_strategy_primary(strategies, primary: str) -> dict:
    """Scripts dict plus __primary__ meta for StrategyModule.strategies output."""
    out = strategy_scripts_only(strategies)
    name = str(primary or "").strip()
    if name:
        out[STRATEGY_PRIMARY_META_KEY] = name
    return out


SIMULATION_RUN_TARGET_OPTIONS = (
    ("local", "Local"),
    ("auxiliary", "Auxiliary"),
)
SIMULATION_COMPLETION_MODE_OPTIONS = (
    ("wait", "Wait until done"),
    ("poll", "Poll while running"),
)
SIMULATION_DEFAULT_RUN_TARGET = "local"
SIMULATION_DEFAULT_COMPLETION_MODE = "wait"
SIMULATION_DEFAULT_TIMEFRAME = "5m"
SIMULATION_DEFAULT_STEP_SIZE = 60
SIMULATION_DEFAULT_FUNDS = 100000.0
# Internal cooperative-wait loop sleep (stop responsiveness).
SIMULATION_POLL_INTERVAL_SEC = 0.1
# How often poll-mode publishes live outputs (UI / state.outputs only).
SIMULATION_DEFAULT_POLL_INTERVAL_SEC = 1.0
SIMULATION_TERMINAL_STATUSES = frozenset(
    {"Finished", "Stopped", "Terminated", "Error"}
)
# Always-visible ports. Settings-backed overrides are optional (expose_* flags).
SIMULATION_CORE_INPUTS = {
    "data": "dict",
    "strategy": "any",
    "params": "dict",
    "start_time": "any",
    "stop_time": "any",
    "stop": "bool",
}
SIMULATION_EXPOSABLE_INPUTS = {
    "symbol": "str",
    "timeframe": "str",
    "step_size": "float",
    "funds": "float",
}
# Back-compat alias: full set when every optional port is exposed.
SIMULATION_DEFAULT_INPUTS = {
    **SIMULATION_CORE_INPUTS,
    **SIMULATION_EXPOSABLE_INPUTS,
}
SIMULATION_DEFAULT_OUTPUTS = {
    "status": "str",
    "sim_id": "str",
    "performance": "dict",
    "params": "dict",
    "finished": "bool",
}
SIMULATION_FULL_RESULT_OUTPUT = {"full_result": "dict"}

# Structured catalog for UI / AI discoverability. Keep in sync with StrategyModule.apply_ops.
STRATEGY_OPS_CATALOG = (
    {
        "op": "set",
        "summary": "Create or overwrite a strategy script.",
        "fields": (
            ("name", "str", "Script name (required)"),
            ("code", "str", "Full script source (missing → empty string)"),
        ),
        "example": {"op": "set", "name": "MyStrat", "code": "def on_bar(bar):\n    pass\n"},
    },
    {
        "op": "delete",
        "summary": "Remove a strategy script by name.",
        "fields": (("name", "str", "Script name to delete"),),
        "example": {"op": "delete", "name": "MyStrat"},
    },
    {
        "op": "rename",
        "summary": "Rename a script. Updates primary if it pointed at the old name.",
        "fields": (
            ("name", "str", "Current script name"),
            ("new_name", "str", "New script name"),
        ),
        "example": {"op": "rename", "name": "OldName", "new_name": "NewName"},
    },
    {
        "op": "replace",
        "summary": "Find/replace text inside one script. Exact match; fails if count ≠ 1 unless replace_all.",
        "fields": (
            ("name", "str", "Script name"),
            ("old", "str", "Text to find (required)"),
            ("new", "str", "Replacement text (missing → empty)"),
            ("replace_all", "bool", "If true, replace every match (default false)"),
        ),
        "example": {
            "op": "replace",
            "name": "MyStrat",
            "old": "THRESHOLD = 10",
            "new": "THRESHOLD = 12",
            "replace_all": False,
        },
    },
    {
        "op": "set_params",
        "summary": "Update param defaults. Dict of name→default merges; otherwise replaces full param_defs list.",
        "fields": (
            ("params", "dict|list", "name→default dict to merge, or list of {name,type,default}"),
            ("param_defs", "list", "Alias of params when sending a full defs list"),
        ),
        "example": {"op": "set_params", "params": {"risk": 1.5, "symbol": "ES"}},
    },
    {
        "op": "set_primary",
        "summary": "Choose which script is the module primary (must already exist, or empty to clear).",
        "fields": (("name", "str", "Existing script name, or \"\" to clear"),),
        "example": {"op": "set_primary", "name": "MyStrat"},
    },
)


def format_strategy_ops_reference(*, include_examples: bool = True) -> str:
    """Human-readable reference for StrategyModule ops input."""
    lines = [
        "Strategy Module — ops reference",
        "",
        "Wire a list (or a single dict / {\"ops\": [...]}) into the `ops` input.",
        "Ops run in order at module run time and mutate this module's private scripts.",
        "They do not auto-write account.strategies (hosts may import/restore explicitly).",
        f"The strategies output also embeds {STRATEGY_PRIMARY_META_KEY!r} (meta, not a script).",
        "Primary is a module setting (and set_primary op), not a separate output port.",
        "Host account import / restore / export should strip meta keys.",
        "",
    ]
    for entry in STRATEGY_OPS_CATALOG:
        op = entry["op"]
        lines.append(f"• {op}")
        lines.append(f"  {entry['summary']}")
        for field, typ, desc in entry.get("fields") or ():
            lines.append(f"  - {field} ({typ}): {desc}")
        if include_examples and entry.get("example") is not None:
            try:
                example = json.dumps(entry["example"], indent=2, ensure_ascii=False)
            except Exception:
                example = str(entry["example"])
            for example_line in example.splitlines():
                lines.append(f"  {example_line}")
        lines.append("")
    lines.append("Example batch:")
    batch = [
        STRATEGY_OPS_CATALOG[0]["example"],
        STRATEGY_OPS_CATALOG[5]["example"],
    ]
    try:
        lines.append(json.dumps(batch, indent=2, ensure_ascii=False))
    except Exception:
        lines.append(str(batch))
    return "\n".join(lines).rstrip() + "\n"



DRAWING_TYPE_OPTIONS = (
    ("dot", "Dot"),
    ("x", "X Marker"),
    ("line", "Line"),
    ("text", "Text"),
    ("circle", "Circle"),
    ("rectangle", "Rectangle"),
    ("candle", "Candle"),
    ("clear", "Clear All ModuLink Drawings"),
)
DRAWING_DEFAULT_TYPE = "dot"
DRAWING_LINE_STYLES = ("solid", "dotted", "dashed", "dashdot", "dashdotdot")
DRAWING_TYPE_INPUTS = {
    "x": {"name": "str", "x": "float", "y": "float"},
    "dot": {"name": "str", "x": "float", "y": "float"},
    "circle": {"name": "str", "x": "float", "y": "float"},
    "line": {"name": "str", "x1": "float", "y1": "float", "x2": "float", "y2": "float"},
    "rectangle": {"name": "str", "x1": "float", "y1": "float", "x2": "float", "y2": "float"},
    "text": {"name": "str", "x": "float", "y": "float", "text": "str"},
    "candle": {
        "name": "str",
        "x": "float",
        "open_val": "float",
        "close_val": "float",
        "high_val": "float",
        "low_val": "float",
    },
    "clear": {"clear": "bool"},
}
DRAWING_DEFAULT_STYLE = {
    "color": "Blue",
    "size": 10,
    "style": "solid",
    "anchor": (0.5, 0.5),
    "border_color": "Blue",
    "filled": False,
    "glow": False,
    "glow_color": (255, 255, 255, 100),
    "glow_width": 6,
    "timeframe": "1m",
}

def coerce_constant_value(raw, type_hint: str):
    """Convert a stored constant to the declared port type."""
    hint = (type_hint or "str").strip().lower()
    if hint in ("str", "string", "text"):
        return "" if raw is None else str(raw)
    if hint in ("int", "integer"):
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            raise ValueError("Integer constant requires a value.")
        return int(raw)
    if hint in ("float", "number", "double"):
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            raise ValueError("Float constant requires a value.")
        return float(raw)
    if hint in ("bool", "boolean"):
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off", ""):
            return False
        raise ValueError(f"Cannot convert {raw!r} to bool.")
    # Unknown hint — pass through as-is.
    return raw


def coerce_condition_bool(raw) -> bool:
    """Truthiness helper for condition ports (bools, 0/1, yes/no, etc.)."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if raw is None:
        return False
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off", ""):
        return False
    return bool(raw)


def coerce_number(raw) -> float:
    """Convert a scalar to float for Math modules."""
    if isinstance(raw, bool):
        return float(int(raw))
    if isinstance(raw, (int, float)):
        return float(raw)
    if raw is None:
        raise ValueError("Expected a number, got None.")
    text = str(raw).strip()
    if not text:
        raise ValueError("Expected a number, got an empty string.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Cannot convert {raw!r} to a number.") from exc


def flatten_input_values(raw) -> list:
    """Flatten fan-in lists (and nested lists) into a flat value list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = []
        for part in raw:
            items.extend(flatten_input_values(part))
        return items
    return [raw]


def parse_filter_keywords(raw) -> list[str]:
    """Split a keyword blob on commas / newlines; drop empties."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).replace(",", "\n")
    return [part.strip() for part in text.splitlines() if part.strip()]


def parse_filter_datetime(raw, environment=None) -> datetime.datetime:
    """
    Parse a datetime from common ModuLink / host shapes.
    Accepts datetime/date, pandas Timestamp, unix seconds, and ISO-ish strings.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError("Expected a datetime value.")

    tz = getattr(environment, "tzinfo", None) if environment is not None else None

    if isinstance(raw, datetime.datetime):
        dt = raw
        if tz is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt

    if isinstance(raw, datetime.date) and not isinstance(raw, datetime.datetime):
        dt = datetime.datetime(raw.year, raw.month, raw.day)
        if tz is not None:
            dt = dt.replace(tzinfo=tz)
        return dt

    # pandas.Timestamp / numpy datetime64-like
    if hasattr(raw, "to_pydatetime"):
        try:
            dt = raw.to_pydatetime()
            if isinstance(dt, datetime.datetime):
                if tz is not None and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                return dt
        except Exception:
            pass

    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        # Heuristic: ms vs seconds
        ts = float(raw)
        if ts > 1e12:
            ts = ts / 1000.0
        dt = datetime.datetime.fromtimestamp(ts, tz=tz) if tz is not None else (
            datetime.datetime.fromtimestamp(ts)
        )
        return dt

    text = str(raw).strip()
    for parser in (
        lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00")),
        lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S"),
        lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M"),
        lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S"),
        lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M"),
        lambda s: datetime.datetime.strptime(s, "%Y-%m-%d"),
        lambda s: datetime.datetime.strptime(s, "%m/%d/%Y %H:%M:%S"),
        lambda s: datetime.datetime.strptime(s, "%m/%d/%Y %H:%M"),
        lambda s: datetime.datetime.strptime(s, "%m/%d/%Y"),
    ):
        try:
            dt = parser(text)
            if tz is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt
        except Exception:
            pass

    # Time-of-day → today (or tomorrow if already past), matching Wait semantics.
    now = datetime.datetime.now(tz) if tz is not None else datetime.datetime.now()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.datetime.strptime(text, fmt)
            dt = now.replace(
                hour=parsed.hour,
                minute=parsed.minute,
                second=parsed.second if fmt.endswith("%S") else 0,
                microsecond=0,
            )
            return dt
        except Exception:
            pass

    raise ValueError(
        f"Unrecognized datetime '{text}'. "
        "Use ISO, YYYY-MM-DD [HH:MM[:SS]], or unix timestamp."
    )


def filter_datetime_compare(left: datetime.datetime, mode: str, right: datetime.datetime, end=None) -> bool:
    """Compare two datetimes for Filter datetime modes (align aware/naive)."""
    # Normalize tz mismatch: drop tz if only one side is aware.
    if (left.tzinfo is None) != (right.tzinfo is None):
        left = left.replace(tzinfo=None) if left.tzinfo is not None else left
        right = right.replace(tzinfo=None) if right.tzinfo is not None else right
    if end is not None and (left.tzinfo is None) != (end.tzinfo is None):
        end = end.replace(tzinfo=None) if end.tzinfo is not None else end
        left = left.replace(tzinfo=None) if left.tzinfo is not None else left

    if mode == "before":
        return left < right
    if mode == "after":
        return left > right
    if mode == "on_or_before":
        return left <= right
    if mode == "on_or_after":
        return left >= right
    if mode == "between_datetimes":
        if end is None:
            raise ValueError("Between datetimes requires a start and end.")
        lo, hi = right, end
        if lo > hi:
            lo, hi = hi, lo
        return lo <= left <= hi
    raise ValueError(f"Unsupported datetime filter mode: {mode}")


def filter_norm_text(value, case_sensitive: bool) -> str:
    text = "" if value is None else str(value)
    return text if case_sensitive else text.lower()


def filter_compare_values(left, op: str, right) -> bool:
    """Compare two values, preferring numeric when both sides look numeric."""
    if op not in FILTER_COMPARE_OPS:
        raise ValueError(f"Unsupported compare op: {op}")

    left_num = right_num = None
    try:
        if left is not None and str(left).strip() != "":
            left_num = float(left)
        if right is not None and str(right).strip() != "":
            right_num = float(right)
    except (TypeError, ValueError):
        left_num = right_num = None

    if left_num is not None and right_num is not None:
        a, b = left_num, right_num
    else:
        a = "" if left is None else str(left)
        b = "" if right is None else str(right)

    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    return False


def filter_get_field(item, field: str):
    """Read a named field from a dict-like item (or mapping key for plain values)."""
    field = (field or "").strip()
    if not field:
        return None
    if isinstance(item, dict):
        if field in item:
            return item.get(field)
        # Case-insensitive key fallback for event-style dicts.
        lower = field.lower()
        for key, value in item.items():
            if str(key).lower() == lower:
                return value
        return None
    if hasattr(item, "get"):
        try:
            return item.get(field)
        except Exception:
            pass
    return None


def filter_count_value(value) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return 0 if value == "" else 1
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if type(value).__name__ == "DataFrame" and hasattr(value, "__len__"):
        try:
            return int(len(value))
        except Exception:
            return 0
    return 1


def normalize_batch_names(raw) -> list[str]:
    """
    Accept a batch name string, list/tuple of names, or a dict whose keys are names
    (so Filter outputs can be wired straight into Sim Batch modules).
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        names = []
        for key in raw.keys():
            text = str(key).strip()
            if text:
                names.append(text)
        return names
    if isinstance(raw, (list, tuple, set)):
        names = []
        for item in raw:
            names.extend(normalize_batch_names(item))
        # Preserve order, drop dupes.
        seen = set()
        ordered = []
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        return ordered
    text = str(raw).strip()
    if not text:
        return []
    # Multi-name blob (comma / newline) or a single literal name.
    parts = parse_filter_keywords(text)
    if len(parts) > 1:
        return parts
    if parts:
        return parts
    return [text]


def sim_batch_folder(environment) -> str:
    account = getattr(environment, "account", None)
    if account is None or not hasattr(account, "get_meta_folder"):
        raise ValueError("Environment account has no get_meta_folder().")
    return os.path.join(account.get_meta_folder(), "simulation_batches")


def list_sim_batch_names(environment) -> list[str]:
    folder = sim_batch_folder(environment)
    if not os.path.isdir(folder):
        return []
    names = []
    for filename in sorted(os.listdir(folder)):
        if filename.lower().endswith(".json"):
            names.append(filename[:-5])
    return names


def get_account_data_index(account_or_env) -> dict:
    """Return account.data_index, or {} when unavailable."""
    account = account_or_env
    if account is not None and not hasattr(account, "data_index"):
        account = getattr(account_or_env, "account", None)
    index = getattr(account, "data_index", None) if account is not None else None
    return index if isinstance(index, dict) else {}


def list_saved_dataset_names(account_or_env) -> list[str]:
    """Sorted dataset names from account.data_index (newest-style reverse sort)."""
    return sorted(get_account_data_index(account_or_env).keys(), reverse=True)


def format_saved_dataset_info(name: str, meta: dict | None) -> str:
    """Short human-readable summary of a data_index entry."""
    if not meta or not isinstance(meta, dict):
        return f"{name}: not in data index"
    symbols = meta.get("symbols") or []
    if isinstance(symbols, (list, tuple)):
        markets = ", ".join(str(s) for s in symbols) or "—"
    else:
        markets = str(symbols)
    date = meta.get("date") or "—"
    start = meta.get("start_date", "—")
    end = meta.get("end_date", "—")
    if hasattr(start, "strftime"):
        start = start.strftime("%Y-%m-%d %H:%M")
    if hasattr(end, "strftime"):
        end = end.strftime("%Y-%m-%d %H:%M")
    recorded = meta.get("recorded_prices", 0)
    return (
        f"Date: {date}\n"
        f"Markets: {markets}\n"
        f"Range: {start} → {end}\n"
        f"Recorded prices: {recorded}"
    )


def serialize_data_index_entry(meta: dict | None) -> dict:
    """Copy a data_index entry with datetimes as ISO strings (graph-friendly)."""
    if not isinstance(meta, dict):
        return {}
    out = {}
    for key, value in meta.items():
        if hasattr(value, "isoformat"):
            try:
                out[key] = value.isoformat()
                continue
            except Exception:
                pass
        out[key] = value
    return out


def build_saved_data_index_output(account_or_env) -> tuple[list[str], dict]:
    """Return (names, index) from account.data_index for graph outputs."""
    names = list_saved_dataset_names(account_or_env)
    raw = get_account_data_index(account_or_env)
    index = {name: serialize_data_index_entry(raw.get(name)) for name in names}
    return names, index


def load_sim_batch_by_name(environment, batch_name: str) -> dict:
    name = (batch_name or "").strip()
    if not name:
        raise ValueError("Batch name is empty.")
    if name.lower().endswith(".json"):
        name = name[:-5]
    folder = sim_batch_folder(environment)
    path = os.path.join(folder, f"{name}.json")
    if not os.path.isfile(path):
        raise ValueError(f"Simulation batch '{name}' was not found.")
    account = environment.account
    password = getattr(environment, "password", None)
    if not password:
        raise ValueError("Environment has no password for decrypting simulation batches.")
    batch = account.load_sim_batch(path, password)
    if batch is None:
        raise ValueError(f"Failed to load simulation batch '{name}'.")
    if not isinstance(batch, dict):
        raise ValueError(f"Simulation batch '{name}' is not a dictionary.")
    return batch


def compute_sim_batch_metrics(environment, data_dicts: dict) -> dict:
    """Prefer Environment helpers; fall back to lightweight local totals."""
    if hasattr(environment, "calculate_performance_metrics"):
        try:
            return dict(environment.calculate_performance_metrics(data_dicts))
        except Exception:
            pass

    metrics = {}
    for key, method_name in (
        ("Sortino Ratio", "get_sortino_ratio"),
        ("Calmar Ratio", "get_calmar_ratio"),
        ("MAR Ratio", "get_mar_ratio"),
        ("Stability", "get_stability_ratio"),
        ("Win Rate", "get_win_rate"),
        ("Net PnL", "get_net_pnl"),
        ("Max Drawdown", "get_max_drawdown"),
    ):
        fn = getattr(environment, method_name, None)
        if callable(fn):
            try:
                metrics[key] = fn(data_dicts)
                continue
            except Exception:
                pass
        metrics[key] = 0

    # Always provide a usable Net PnL even without Environment helpers.
    if metrics.get("Net PnL") in (0, 0.0) and data_dicts:
        metrics["Net PnL"] = sum(
            float(sim.get("pnl", 0) or 0) for sim in data_dicts.values() if isinstance(sim, dict)
        )
        wins = sum(int(sim.get("num_wins", 0) or 0) for sim in data_dicts.values() if isinstance(sim, dict))
        losses = sum(int(sim.get("num_losses", 0) or 0) for sim in data_dicts.values() if isinstance(sim, dict))
        total = wins + losses
        metrics["Win Rate"] = (wins / total * 100.0) if total else 0.0
    return metrics


def get_modulink_memory_root(environment) -> dict:
    """
    Session-only ModuLink memory root on the Environment.
    Survives blueprint re-runs; not written to the account file.
    Keys are Memory module_ids → stored values.
    """
    if environment is None:
        raise ValueError("Memory requires a host environment.")
    root = getattr(environment, "modulink_memory", None)
    if not isinstance(root, dict):
        root = {}
        environment.modulink_memory = root
    return root


def get_modulink_memory_slot(environment, module_id) -> dict:
    """
    Per-module slot: {"kind": str, "value": ...}.
    Created on first access; value initialized by the caller/kind.
    """
    root = get_modulink_memory_root(environment)
    key = str(module_id)
    slot = root.get(key)
    if not isinstance(slot, dict) or "value" not in slot:
        slot = {"kind": MEMORY_DEFAULT_KIND, "value": None}
        root[key] = slot
    return slot


def get_modulink_throttle_root(environment) -> dict:
    """
    Session-only throttle timestamps: {key: last_fire_unix_time}.
    Survives blueprint re-runs; not written to the account file.
    """
    if environment is None:
        raise ValueError("Throttle requires a host environment.")
    root = getattr(environment, "modulink_throttle", None)
    if not isinstance(root, dict):
        root = {}
        environment.modulink_throttle = root
    return root


def modulink_should_stop(environment) -> bool:
    """True when the active blueprint run has been asked to stop."""
    if environment is None:
        return False
    checker = getattr(environment, "_modulink_should_stop", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return bool(getattr(environment, "_modulink_stop_requested", False))


def modulink_publish_progress(environment, outputs: dict | None) -> None:
    """
    Publish mid-run module outputs for live UI / inspectors.

    Does not advance the graph: downstream modules still wait until run()
    returns. Blueprint installs _modulink_progress during module execution.
    """
    if environment is None:
        return
    callback = getattr(environment, "_modulink_progress", None)
    if not callable(callback):
        return
    try:
        callback(dict(outputs or {}))
    except Exception:
        pass


def get_modulink_secrets(environment) -> dict:
    """Account-level ModuLink secrets dict (name → value)."""
    if environment is None:
        raise ValueError("Secret requires a host environment.")
    account = getattr(environment, "account", None)
    if account is None:
        raise ValueError("Environment has no account for secrets.")
    secrets = getattr(account, "modulink_secrets", None)
    if not isinstance(secrets, dict):
        secrets = {}
        account.modulink_secrets = secrets
    return secrets


STATUS_IDLE = "idle"
STATUS_WAITING = "waiting"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

STATUS_OUTLINE_COLORS = {
    STATUS_IDLE: "#CFD8DC",
    STATUS_WAITING: "#FFC107",
    STATUS_RUNNING: "#FFC107",
    STATUS_SUCCESS: "#4CAF50",
    STATUS_FAILED: "#F44336",
}

# Muted left-accent colors for module cards (idle state).
MODULE_TYPE_ACCENT = {
    "exec": "#78909C",
    "data_source": "#4FC3F7",
    "ai": "#BA68C8",
    "message": "#4DB6AC",
    "constant": "#AED581",
    "condition": "#FFB74D",
    "filter": "#64B5F6",
    "math": "#4DD0E1",
    "string": "#FFCC80",
    "compare": "#A5D6A7",
    "wait": "#80CBC4",
    "prompt": "#CE93D8",
    "secret": "#EF9A9A",
    "throttle": "#FFD54F",
    "sim_batch": "#81C784",
    "simulation": "#66BB6A",
    "memory": "#F06292",
    "drawing": "#FF8A65",
    "audio": "#9575CD",
    "iterator": "#26C6DA",
    "strategy": "#8D6E63",
}
MODULE_TYPE_ACCENT_FALLBACK = "#607D8B"
NODE_SELECTION_BORDER = "#90CAF9"
NODE_SUMMARY_MAX_LEN = 36


def format_memory_summary(kind: str, value, max_len: int = NODE_SUMMARY_MAX_LEN) -> str:
    """Compact one-line summary for a Memory slot value."""
    kind = kind or MEMORY_DEFAULT_KIND
    if kind == "list":
        if not isinstance(value, list):
            return "[]"
        n = len(value)
        if n == 0:
            return "[] · 0"
        if n <= 3:
            parts = [format_value(v, max_len=12) for v in value]
            text = "[" + ", ".join(parts) + f"] · {n}"
            if len(text) > max_len:
                return f"[{n} items]"
            return text
        return f"[{n} items]"
    if kind == "dict":
        if not isinstance(value, dict):
            return "{}"
        n = len(value)
        if n == 0:
            return "{} · 0"
        if n <= 2:
            parts = [f"{k}={format_value(v, max_len=10)}" for k, v in list(value.items())[:2]]
            text = ", ".join(parts)
            if len(text) > max_len:
                return f"{{{n} keys}}"
            return text
        return f"{{{n} keys}}"
    return format_value(value, max_len=max_len)


def infer_port_renames(old_names, new_names) -> dict:
    """
    Infer old→new port renames from two ordered name lists.
    Prefers index pairing when lengths match; otherwise pairs removed→added in order.
    """
    old = [str(n) for n in (old_names or [])]
    new = [str(n) for n in (new_names or [])]
    if old == new:
        return {}
    if len(old) == len(new):
        return {a: b for a, b in zip(old, new) if a != b}
    old_set, new_set = set(old), set(new)
    removed = [n for n in old if n not in new_set]
    added = [n for n in new if n not in old_set]
    if removed and len(removed) == len(added):
        return dict(zip(removed, added))
    return {}


def format_value(value, max_len: int | None = 160, multiline: bool = False) -> str:
    """Readable single-value formatting for the properties/console panels.

    Containers are summarized (never full repr) so large sim batches stay cheap.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if multiline:
            text = value
        else:
            text = value if "\n" not in value else value.replace("\n", "\\n")
        if max_len is not None and len(text) > max_len:
            return f'"{text[: max_len - 3]}..."'
        if multiline and "\n" in text:
            return text
        return f'"{text}"'
    if isinstance(value, dict):
        return f"{{dict with {len(value)} keys}}"
    if isinstance(value, (list, tuple, set)):
        return f"[list with {len(value)} items]"
    # Avoid importing pandas just for display; duck-type DataFrame/Series.
    if type(value).__name__ == "DataFrame" and hasattr(value, "shape"):
        rows, cols = value.shape
        return f"DataFrame {rows} rows × {cols} cols"
    if type(value).__name__ == "Series" and hasattr(value, "__len__"):
        try:
            return f"Series with {len(value)} items"
        except Exception:
            return "Series"
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return str(value)
    # Last resort — never build an unbounded repr of unknown large objects.
    type_name = type(value).__name__
    text = f"<{type_name}>"
    try:
        size = len(value)  # type: ignore[arg-type]
        text = f"<{type_name} len={size}>"
    except Exception:
        pass
    if max_len is not None and len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def format_port_values(
    values: dict | None,
    empty: str = "—",
    indent: str = "",
    max_len: int | None = 160,
    multiline: bool = False,
    max_items: int | None = 40,
) -> str:
    """Format input/output maps as one `name: value` line each."""
    if not values:
        return empty
    lines = []
    items = list(values.items())
    truncated = 0
    if max_items is not None and len(items) > max_items:
        truncated = len(items) - max_items
        items = items[:max_items]
    for name, value in items:
        rendered = format_value(value, max_len=max_len, multiline=multiline)
        if (
            multiline
            and isinstance(value, str)
            and "\n" in value
            and (max_len is None or len(value) <= max_len)
        ):
            nested = "\n".join(f"{indent}  {line}" for line in value.splitlines())
            lines.append(f"{indent}{name}:\n{nested}")
        else:
            lines.append(f"{indent}{name}: {rendered}")
    if truncated:
        lines.append(f"{indent}… ({truncated} more)")
    return "\n".join(lines)


def format_port_section(title: str, values: dict | None, *, compact: bool = False) -> str:
    """Format Inputs/Outputs blocks for the Module Console (full string text).

    Containers stay summarized (dict/list/DataFrame size) so huge objects do not
    dump into the console; string values are never ellipsized.
    `compact` is accepted for call-site compatibility and ignored.
    """
    del compact
    body = format_port_values(
        values,
        empty="(none)",
        indent="  ",
        max_len=None,
        multiline=True,
        max_items=None,
    )
    return f"{title}\n{body}"


class ModuleRunState:
    """Temporary per-module run info for the current/last blueprint execution."""

    def __init__(self):
        self.status = STATUS_IDLE
        self.console: list[str] = []
        self.inputs: dict = {}
        self.outputs: dict = {}
        self.error: str | None = None

    def reset(self, status: str = STATUS_IDLE):
        self.status = status
        self.console.clear()
        self.inputs = {}
        self.outputs = {}
        self.error = None

    def log(self, message: str):
        self.console.append(str(message))


class Module:
    """Base reusable building block. Type-specific subclasses hold unique fields."""

    module_type = "base"

    def __init__(
        self,
        name="Module",
        description="",
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.name = name
        self.description = description
        self.module_id = uuid4()

        # {name: type} — type is a string hint like 'int', 'float', 'any'
        self.inputs = dict(inputs or {})
        self.outputs = dict(outputs or {})

        if json_data is not None:
            self.from_json(json_data)

    def from_json(self, json_data):
        self.name = json_data.get("name", self.name)
        self.description = json_data.get("description", self.description)
        module_id = json_data.get("module_id", self.module_id)
        self.module_id = module_id
        self.inputs = dict(json_data.get("inputs", self.inputs))
        self.outputs = dict(json_data.get("outputs", self.outputs))

    def to_json(self):
        return {
            "name": self.name,
            "description": self.description,
            "module_type": self.module_type,
            "module_id": str(self.module_id),
            "inputs": self.inputs,
            "outputs": self.outputs,
        }

    def randomize_id(self):
        self.module_id = uuid4()

    def clone(self) -> Module:
        clone = module_from_json(self.to_json())
        clone.randomize_id()
        return clone

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        raise NotImplementedError(f"run() is not implemented for {self.module_type}")

    def allows_input_fan_in(self) -> bool:
        """If True, multiple wires may target the same input port."""
        return False

    def optional_input_names(self) -> set:
        """Input port names that may be left unwired without failing the run."""
        return set()

    def node_meta(self) -> str:
        """Short muted subtitle shown on the graph node (under the name)."""
        return str(self.module_type or "")

    def node_summary(self, *, environment=None, run_state=None) -> str:
        """
        Optional one-line peek for the graph node.
        Default: compact primary output from the last run state.
        """
        if run_state is None:
            return ""
        outputs = getattr(run_state, "outputs", None) or {}
        if not outputs:
            return ""
        for key in ("value", "items", "data", "kept", "result", "message", "events"):
            if key in outputs:
                return format_value(outputs[key], max_len=NODE_SUMMARY_MAX_LEN)
        first_key = next(iter(outputs))
        return format_value(outputs[first_key], max_len=NODE_SUMMARY_MAX_LEN)


class ExecModule(Module):
    """Python exec module: inputs inject variables; outputs read variables after run.

    `environment` is always injected into the script namespace (not as a graph port).
    Code can come from the embedded script or from a wired input (e.g. AI response).
    Optionally expose captured console text (prints + errors) as a pluggable output.
    """

    module_type = "exec"

    def __init__(
        self,
        name="Module",
        description="",
        code="",
        code_source="embedded",
        code_input=EXEC_DEFAULT_CODE_INPUT,
        expose_console=False,
        console_output=EXEC_DEFAULT_CONSOLE_OUTPUT,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.code = code or ""
        self.code_source = code_source or "embedded"
        self.code_input = (code_input or EXEC_DEFAULT_CODE_INPUT).strip() or EXEC_DEFAULT_CODE_INPUT
        self.expose_console = bool(expose_console)
        self.console_output = (
            (console_output or EXEC_DEFAULT_CONSOLE_OUTPUT).strip()
            or EXEC_DEFAULT_CONSOLE_OUTPUT
        )
        super().__init__(
            name=name,
            description=description,
            inputs=inputs,
            outputs=outputs,
            json_data=json_data,
        )
        if json_data is None:
            self._ensure_code_input_port()
            self._ensure_console_output_port()

    def _ensure_code_input_port(self):
        """When code comes from an input, keep that port present (str)."""
        if self.code_source != "input":
            return
        name = (self.code_input or EXEC_DEFAULT_CODE_INPUT).strip() or EXEC_DEFAULT_CODE_INPUT
        self.code_input = name
        if name not in self.inputs:
            self.inputs = {name: "str", **dict(self.inputs)}

    def _ensure_console_output_port(self):
        """When console is exposed, keep that output port present (str)."""
        name = (
            (self.console_output or EXEC_DEFAULT_CONSOLE_OUTPUT).strip()
            or EXEC_DEFAULT_CONSOLE_OUTPUT
        )
        self.console_output = name
        if self.expose_console:
            if name not in self.outputs:
                self.outputs = {**dict(self.outputs), name: "str"}
        elif name in self.outputs:
            # Drop the reserved console port when the option is turned off.
            self.outputs = {k: v for k, v in self.outputs.items() if k != name}

    def from_json(self, json_data):
        super().from_json(json_data)
        self.code = json_data.get("code", self.code)
        self.code_source = json_data.get("code_source", self.code_source) or "embedded"
        self.code_input = (
            json_data.get("code_input", self.code_input) or EXEC_DEFAULT_CODE_INPUT
        ).strip() or EXEC_DEFAULT_CODE_INPUT
        self.expose_console = bool(json_data.get("expose_console", self.expose_console))
        self.console_output = (
            json_data.get("console_output", self.console_output)
            or EXEC_DEFAULT_CONSOLE_OUTPUT
        ).strip() or EXEC_DEFAULT_CONSOLE_OUTPUT
        self._ensure_code_input_port()
        self._ensure_console_output_port()

    def to_json(self):
        self._ensure_code_input_port()
        self._ensure_console_output_port()
        data = super().to_json()
        data["code"] = self.code
        data["code_source"] = self.code_source
        data["code_input"] = self.code_input
        data["expose_console"] = bool(self.expose_console)
        data["console_output"] = self.console_output
        return data

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        import io
        from contextlib import redirect_stderr, redirect_stdout

        inputs = dict(inputs or {})
        if self.code_source == "input":
            port = (self.code_input or EXEC_DEFAULT_CODE_INPUT).strip() or EXEC_DEFAULT_CODE_INPUT
            if port not in inputs:
                raise ValueError(
                    f"Exec module '{self.name}' expects code on input '{port}'."
                )
            code = inputs.get(port)
            if code is None:
                raise ValueError(f"Exec module '{self.name}' received empty code on '{port}'.")
            if not isinstance(code, str):
                code = str(code)
        else:
            code = self.code or ""

        exec_dict = dict(inputs)
        # Always available in script scope (not a pluggable port).
        exec_dict["environment"] = environment
        console_buf = io.StringIO()
        self._last_console = ""
        try:
            compiled = compile(code, f"<module:{self.name}>", "exec")
            with redirect_stdout(console_buf), redirect_stderr(console_buf):
                exec(compiled, exec_dict)
        except Exception as exc:
            captured = console_buf.getvalue()
            err_text = f"Error: {exc}\n{traceback.format_exc()}"
            console_text = (
                f"{captured.rstrip()}\n{err_text}".strip() if captured else err_text
            )
            self._last_console = console_text
            if self.expose_console:
                outputs = {name: exec_dict.get(name) for name in self.outputs}
                # Always publish console text (prints + error), not only on failure paths.
                outputs[self.console_output] = console_text
                raise ExecModuleFailedWithConsole(str(exc), outputs) from exc
            raise

        captured = console_buf.getvalue()
        self._last_console = captured
        outputs = {name: exec_dict.get(name) for name in self.outputs}
        if self.expose_console:
            # Pluggable console carries stdout/stderr on success (prints, etc.),
            # not only when an exception occurs.
            if (
                self.console_output in exec_dict
                and exec_dict.get(self.console_output) is not None
            ):
                outputs[self.console_output] = exec_dict.get(self.console_output)
            else:
                outputs[self.console_output] = captured
        return outputs



class DataSourceModule(Module):
    """Fetches market data from an environment-backed source (e.g. working data)."""

    module_type = "data_source"

    def __init__(
        self,
        name="Data Source",
        description="",
        source="working_data",
        dataset_name="",
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.source = source or "working_data"
        self.dataset_name = "" if dataset_name is None else str(dataset_name)
        ports = DATA_SOURCE_PORTS.get(self.source, DATA_SOURCE_PORTS["working_data"])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def optional_input_names(self) -> set:
        if self.source == "saved_data":
            return {"dataset_name"}
        return set()

    def _sync_ports(self):
        ports = DATA_SOURCE_PORTS.get(self.source, DATA_SOURCE_PORTS["working_data"])
        self.inputs = dict(ports["inputs"])
        self.outputs = dict(ports["outputs"])

    def from_json(self, json_data):
        super().from_json(json_data)
        self.source = json_data.get("source", self.source) or "working_data"
        if self.source not in DATA_SOURCE_PORTS:
            self.source = "working_data"
        self.dataset_name = str(json_data.get("dataset_name", self.dataset_name) or "")
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["source"] = self.source
        data["dataset_name"] = self.dataset_name
        return data

    def node_meta(self) -> str:
        if self.source == "list_saved_data":
            return "list saved data"
        if self.source == "saved_data":
            label = (self.dataset_name or "").strip() or "…"
            return f"saved · {label}"
        if self.source == "economic_events":
            return "econ events"
        return "working data"

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Data source requires a host environment.")

        if self.source == "working_data":
            symbol = inputs.get("symbol")
            timeframe = inputs.get("timeframe")
            if not symbol or not timeframe:
                raise ValueError("Data source requires connected 'symbol' and 'timeframe' inputs.")
            working = getattr(environment, "working_data_dict", None) or {}
            symbol_data = working.get(symbol, {})
            if not isinstance(symbol_data, dict):
                raise ValueError(f"No working data found for symbol '{symbol}'.")
            frame = symbol_data.get(timeframe)
            if frame is None:
                raise ValueError(
                    f"No working data for {symbol} @ {timeframe}."
                )
            return {"data": frame}

        if self.source == "economic_events":
            # Host environments typically store this as economic_events.
            events = getattr(environment, "economic_events", None)
            if events is None:
                events = getattr(environment, "econ_events", None)
            if events is None:
                raise ValueError("Environment has no economic events data.")
            if not isinstance(events, dict):
                raise ValueError("Economic events data is not a dictionary.")
            return {"events": events}

        if self.source == "list_saved_data":
            account = getattr(environment, "account", None)
            if account is None:
                raise ValueError("Environment has no account for saved datasets.")
            names, index = build_saved_data_index_output(account)
            return {"names": names, "index": index, "count": len(names)}

        if self.source == "saved_data":
            name = (self.dataset_name or "").strip()
            if "dataset_name" in inputs:
                values = flatten_input_values(inputs.get("dataset_name"))
                if values and values[-1] is not None and str(values[-1]).strip():
                    name = str(values[-1]).strip()
            if not name:
                raise ValueError("Saved data source needs a dataset name.")
            account = getattr(environment, "account", None)
            if account is None or not hasattr(account, "load_data"):
                raise ValueError("Environment account has no load_data().")
            index = get_account_data_index(account)
            if name not in index:
                available = ", ".join(list_saved_dataset_names(account)[:12]) or "(none)"
                raise ValueError(
                    f"Dataset '{name}' not found in account data index. "
                    f"Available: {available}"
                )
            loaded = account.load_data(name)
            if not loaded or not isinstance(loaded, dict):
                raise ValueError(f"Failed to load saved dataset '{name}'.")
            # One package for Simulation (and anything else that expects save_data shape).
            return {
                "data": {
                    "data": (
                        loaded.get("data")
                        if isinstance(loaded.get("data"), dict)
                        else {}
                    ),
                    "economic_events": (
                        loaded.get("economic_events")
                        if isinstance(loaded.get("economic_events"), dict)
                        else {}
                    ),
                    "stream_prices": (
                        loaded.get("stream_prices")
                        if isinstance(loaded.get("stream_prices"), dict)
                        else {}
                    ),
                }
            }

        raise ValueError(f"Unsupported data source: {self.source}")


class AIModule(Module):
    """Sends a prompt to an LLM via the host environment and waits for the reply."""

    module_type = "ai"

    def __init__(
        self,
        name="AI Module",
        description="",
        system_prompt=None,
        llm_client=AI_LLM_CLIENT_AUTO,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.system_prompt = (
            AI_DEFAULT_SYSTEM_PROMPT if system_prompt is None else system_prompt
        )
        self.llm_client = (llm_client or AI_LLM_CLIENT_AUTO).strip() or AI_LLM_CLIENT_AUTO
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs or AI_DEFAULT_INPUTS),
            outputs=dict(outputs or AI_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if not self.inputs:
            self.inputs = dict(AI_DEFAULT_INPUTS)
        if not self.outputs:
            self.outputs = dict(AI_DEFAULT_OUTPUTS)

    def allows_input_fan_in(self) -> bool:
        return True

    @staticmethod
    def _combine_str_parts(raw) -> str:
        """Join fan-in values (or a single value) with str() concatenation."""
        if raw is None:
            return ""
        parts = raw if isinstance(raw, list) else [raw]
        return "".join("" if part is None else str(part) for part in parts)

    def from_json(self, json_data):
        super().from_json(json_data)
        self.system_prompt = json_data.get("system_prompt", self.system_prompt)
        self.llm_client = (
            str(json_data.get("llm_client", self.llm_client) or AI_LLM_CLIENT_AUTO).strip()
            or AI_LLM_CLIENT_AUTO
        )

    def to_json(self):
        data = super().to_json()
        data["system_prompt"] = self.system_prompt
        data["llm_client"] = self.llm_client or AI_LLM_CLIENT_AUTO
        return data

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        prompt = self._combine_str_parts(inputs.get("prompt"))
        if not prompt.strip():
            raise ValueError("AI module requires a connected 'prompt' input.")
        if environment is None:
            raise ValueError("AI module requires a host environment.")
        if not hasattr(environment, "request_modulink_ai"):
            raise ValueError("Environment does not support ModuLink AI requests.")

        response = environment.request_modulink_ai(
            prompt=prompt,
            system_prompt=self.system_prompt or AI_DEFAULT_SYSTEM_PROMPT,
            llm_client=self.llm_client or AI_LLM_CLIENT_AUTO,
        )
        return {"response": response}


class MessageModule(Module):
    """Sends a text message via the host environment or a Discord webhook."""

    module_type = "message"

    def __init__(
        self,
        name="Message",
        description="",
        medium=MESSAGE_MEDIUM_HOST,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.medium = medium or MESSAGE_MEDIUM_HOST
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs or MESSAGE_DEFAULT_INPUTS),
            outputs=dict(outputs or MESSAGE_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if not self.inputs:
            self.inputs = dict(MESSAGE_DEFAULT_INPUTS)
        if not self.outputs:
            self.outputs = dict(MESSAGE_DEFAULT_OUTPUTS)

    def from_json(self, json_data):
        super().from_json(json_data)
        self.medium = json_data.get("medium", self.medium)

    def to_json(self):
        data = super().to_json()
        data["medium"] = self.medium
        return data

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        message = inputs.get("message")
        to = inputs.get("to")
        if message is None or str(message).strip() == "":
            raise ValueError("Message module requires a connected 'message' input.")
        if environment is None:
            raise ValueError("Message module requires a host environment.")

        message_text = str(message)
        to_text = "" if to is None else str(to).strip()

        if self.medium == "discord_webhook":
            if not to_text:
                raise ValueError(
                    "Discord webhook requires a 'to' input set to the webhook URL."
                )
            account = getattr(environment, "account", None)
            if account is None or not hasattr(account, "send_webhook_message"):
                raise ValueError("Environment account does not support webhook messages.")
            ok = account.send_webhook_message(message_text, to_text)
            if not ok:
                raise RuntimeError("Failed to send Discord webhook message.")
            return {"sent": True}

        if self.medium == MESSAGE_MEDIUM_HOST:
            if not hasattr(environment, "send_message"):
                raise ValueError("Environment does not support host messaging.")
            if hasattr(environment, "client_ready") and not environment.client_ready():
                raise RuntimeError("Host client is not connected.")

            if to_text.lower() in MESSAGE_BROADCAST_TARGETS:
                environment.send_message(
                    {
                        "type": "broadcast",
                        "content": message_text,
                    }
                )
            else:
                environment.send_message(
                    {
                        "type": "message",
                        "to": to_text,
                        "content": message_text,
                    }
                )
            return {"sent": True}

        raise ValueError(f"Unsupported message medium: {self.medium}")


class AudioModule(Module):
    """Plays a local audio file (alerts, cues) via the host environment."""

    module_type = "audio"

    def __init__(
        self,
        name="Audio",
        description="",
        volume=AUDIO_DEFAULT_VOLUME,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        try:
            self.volume = float(volume if volume is not None else AUDIO_DEFAULT_VOLUME)
        except (TypeError, ValueError):
            self.volume = AUDIO_DEFAULT_VOLUME
        self.volume = max(0.0, min(1.0, self.volume))
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs or AUDIO_DEFAULT_INPUTS),
            outputs=dict(outputs or AUDIO_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if not self.inputs:
            self.inputs = dict(AUDIO_DEFAULT_INPUTS)
        if not self.outputs:
            self.outputs = dict(AUDIO_DEFAULT_OUTPUTS)

    def from_json(self, json_data):
        super().from_json(json_data)
        try:
            self.volume = float(json_data.get("volume", self.volume))
        except (TypeError, ValueError):
            self.volume = AUDIO_DEFAULT_VOLUME
        self.volume = max(0.0, min(1.0, self.volume))
        if not self.inputs:
            self.inputs = dict(AUDIO_DEFAULT_INPUTS)
        if not self.outputs:
            self.outputs = dict(AUDIO_DEFAULT_OUTPUTS)

    def to_json(self):
        data = super().to_json()
        data["volume"] = float(self.volume)
        data["inputs"] = dict(AUDIO_DEFAULT_INPUTS)
        data["outputs"] = dict(AUDIO_DEFAULT_OUTPUTS)
        return data

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Audio module requires a host environment.")
        if not hasattr(environment, "play_modulink_audio"):
            raise ValueError("Environment does not support ModuLink audio playback.")

        path = inputs.get("path")
        if path is None or str(path).strip() == "":
            raise ValueError("Audio module requires a connected 'path' input.")

        ok = environment.play_modulink_audio(str(path).strip(), volume=self.volume)
        return {"played": bool(ok)}


class FilterModule(Module):
    """Filter a value (string / list / dict / DataFrame) by a practical mode."""

    module_type = "filter"

    def __init__(
        self,
        name="Filter",
        description="",
        mode=None,
        pattern="",
        keywords="",
        field="",
        op="==",
        compare_value="",
        limit=10,
        case_sensitive=False,
        wire_pattern=False,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or FILTER_DEFAULT_MODE
        self.pattern = "" if pattern is None else str(pattern)
        self.keywords = "" if keywords is None else str(keywords)
        self.field = "" if field is None else str(field)
        self.op = op if op in FILTER_COMPARE_OPS else "=="
        self.compare_value = "" if compare_value is None else str(compare_value)
        try:
            self.limit = max(0, int(limit))
        except (TypeError, ValueError):
            self.limit = 10
        self.case_sensitive = bool(case_sensitive)
        self.wire_pattern = bool(wire_pattern)
        self._filter_environment = None
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else FILTER_DEFAULT_INPUTS),
            outputs=dict(outputs if outputs is not None else FILTER_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def optional_input_names(self) -> set:
        if not self.wire_pattern:
            return set()
        names = {FILTER_PATTERN_PORT}
        if (self.mode or FILTER_DEFAULT_MODE) == "between_datetimes":
            names.add(FILTER_END_PORT)
        return names

    def _sync_ports(self):
        inputs = dict(FILTER_DEFAULT_INPUTS)
        if self.wire_pattern:
            inputs[FILTER_PATTERN_PORT] = "any"
            if (self.mode or FILTER_DEFAULT_MODE) == "between_datetimes":
                inputs[FILTER_END_PORT] = "any"
        self.inputs = inputs
        self.outputs = dict(FILTER_DEFAULT_OUTPUTS)

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or FILTER_DEFAULT_MODE
        self.pattern = str(json_data.get("pattern", self.pattern) or "")
        self.keywords = str(json_data.get("keywords", self.keywords) or "")
        self.field = str(json_data.get("field", self.field) or "")
        self.op = json_data.get("op", self.op) or "=="
        if self.op not in FILTER_COMPARE_OPS:
            self.op = "=="
        self.compare_value = str(json_data.get("compare_value", self.compare_value) or "")
        try:
            self.limit = max(0, int(json_data.get("limit", self.limit)))
        except (TypeError, ValueError):
            self.limit = 10
        self.case_sensitive = bool(json_data.get("case_sensitive", self.case_sensitive))
        self.wire_pattern = bool(json_data.get("wire_pattern", self.wire_pattern))
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or FILTER_DEFAULT_MODE
        data["pattern"] = self.pattern
        data["keywords"] = self.keywords
        data["field"] = self.field
        data["op"] = self.op
        data["compare_value"] = self.compare_value
        data["limit"] = int(self.limit)
        data["case_sensitive"] = bool(self.case_sensitive)
        data["wire_pattern"] = bool(self.wire_pattern)
        return data

    def node_meta(self) -> str:
        mode = self.mode or FILTER_DEFAULT_MODE
        wired = " · wired" if self.wire_pattern else ""
        return f"filter · {mode}{wired}"

    def _apply_wired_criteria(self, inputs: dict):
        """Override pattern / keywords / compare_value from optional wired ports."""
        if not self.wire_pattern:
            return
        mode = self.mode or FILTER_DEFAULT_MODE
        if FILTER_PATTERN_PORT in inputs:
            values = flatten_input_values(inputs.get(FILTER_PATTERN_PORT))
            if values and values[-1] is not None:
                text = str(values[-1])
                if mode in FILTER_KEYWORD_MODES:
                    self.keywords = text
                elif mode == "where_compare":
                    self.compare_value = text
                else:
                    self.pattern = text
        if mode == "between_datetimes" and FILTER_END_PORT in inputs:
            values = flatten_input_values(inputs.get(FILTER_END_PORT))
            if values and values[-1] is not None:
                self.compare_value = str(values[-1])

    def _match_text(self, text, mode: str | None = None) -> bool:
        mode = mode or self.mode
        hay = filter_norm_text(text, self.case_sensitive)
        needle = filter_norm_text(self.pattern, self.case_sensitive)

        if mode == "contains":
            return bool(needle) and needle in hay
        if mode == "not_contains":
            return (not needle) or (needle not in hay)
        if mode == "equals":
            return hay == needle
        if mode == "not_equals":
            return hay != needle
        if mode == "regex":
            flags = 0 if self.case_sensitive else re.IGNORECASE
            try:
                return re.search(self.pattern or "", str(text), flags) is not None
            except re.error as exc:
                raise ValueError(f"Invalid regex: {exc}") from exc
        if mode == "include_any":
            keywords = parse_filter_keywords(self.keywords)
            if not keywords:
                return True
            return any(filter_norm_text(k, self.case_sensitive) in hay for k in keywords)
        if mode == "exclude_any":
            keywords = parse_filter_keywords(self.keywords)
            if not keywords:
                return True
            return not any(filter_norm_text(k, self.case_sensitive) in hay for k in keywords)
        raise ValueError(f"Unsupported text filter mode: {mode}")

    def _match_datetime_value(self, candidate) -> bool:
        mode = self.mode or FILTER_DEFAULT_MODE
        env = self._filter_environment
        left = parse_filter_datetime(candidate, env)
        right = parse_filter_datetime(self.pattern, env)
        end = None
        if mode == "between_datetimes":
            end = parse_filter_datetime(self.compare_value, env)
        return filter_datetime_compare(left, mode, right, end)

    def _match_item(self, item) -> bool:
        mode = self.mode
        if mode in FILTER_TEXT_MODES or mode in FILTER_KEYWORD_MODES:
            return self._match_text(item if isinstance(item, str) else str(item), mode)

        if mode in FILTER_DATETIME_MODES:
            field = (self.field or "").strip()
            if field:
                if not isinstance(item, dict):
                    item = {"value": item}
                return self._match_datetime_value(filter_get_field(item, field))
            return self._match_datetime_value(item)

        if mode in FILTER_KEY_MODES:
            field = (self.field or "").strip()
            if not field:
                raise ValueError(f"Filter mode '{mode}' requires a field name.")
            field_value = filter_get_field(item, field)
            if mode == "key_equals":
                left = filter_norm_text(field_value, self.case_sensitive)
                right = filter_norm_text(self.pattern, self.case_sensitive)
                return left == right
            if mode == "key_contains":
                left = filter_norm_text(field_value, self.case_sensitive)
                right = filter_norm_text(self.pattern, self.case_sensitive)
                return bool(right) and right in left
            left = field_value
            right = self.compare_value
            if not self.case_sensitive:
                try:
                    float(left)
                    float(right)
                except (TypeError, ValueError):
                    left = filter_norm_text(left, False)
                    right = filter_norm_text(right, False)
            return filter_compare_values(left, self.op, right)

        raise ValueError(f"Unsupported filter mode: {mode}")

    def _limit_value(self, value):
        n = max(0, int(self.limit))
        if isinstance(value, str):
            return value[:n]
        if isinstance(value, list):
            return value[:n]
        if isinstance(value, tuple):
            return list(value[:n])
        if isinstance(value, set):
            return list(value)[:n]
        if isinstance(value, dict):
            out = {}
            for i, (key, item) in enumerate(value.items()):
                if i >= n:
                    break
                out[key] = item
            return out
        if type(value).__name__ == "DataFrame" and hasattr(value, "head"):
            return value.head(n)
        return value

    def _filter_dataframe(self, frame):
        mode = self.mode
        if mode == "limit":
            return self._limit_value(frame)

        field = (self.field or "").strip()
        if mode in FILTER_DATETIME_MODES:
            if not field:
                raise ValueError(
                    f"Filter mode '{mode}' on a DataFrame requires a field/column name."
                )
            if field not in getattr(frame, "columns", []):
                raise ValueError(f"DataFrame has no column '{field}'.")
            keep_idx = []
            for idx, raw in frame[field].items():
                try:
                    if self._match_datetime_value(raw):
                        keep_idx.append(idx)
                except ValueError:
                    continue
            return frame.loc[keep_idx]

        if mode in FILTER_KEY_MODES:
            if not field:
                raise ValueError(f"Filter mode '{mode}' requires a field/column name.")
            if field not in getattr(frame, "columns", []):
                raise ValueError(f"DataFrame has no column '{field}'.")
            series = frame[field]
            if mode == "key_equals":
                if self.case_sensitive:
                    mask = series.astype(str) == str(self.pattern)
                else:
                    mask = series.astype(str).str.lower() == str(self.pattern).lower()
                return frame.loc[mask]
            if mode == "key_contains":
                needle = str(self.pattern)
                if self.case_sensitive:
                    mask = series.astype(str).str.contains(needle, regex=False, na=False)
                else:
                    mask = series.astype(str).str.lower().str.contains(
                        needle.lower(), regex=False, na=False
                    )
                return frame.loc[mask]
            try:
                numeric = series.astype(float)
                right = float(self.compare_value)
                left_values = numeric
                right_value = right
            except (TypeError, ValueError):
                left_values = series.astype(str)
                right_value = str(self.compare_value)
                if not self.case_sensitive:
                    left_values = left_values.str.lower()
                    right_value = right_value.lower()
            op = self.op
            if op == "==":
                mask = left_values == right_value
            elif op == "!=":
                mask = left_values != right_value
            elif op == "<":
                mask = left_values < right_value
            elif op == "<=":
                mask = left_values <= right_value
            elif op == ">":
                mask = left_values > right_value
            elif op == ">=":
                mask = left_values >= right_value
            else:
                raise ValueError(f"Unsupported compare op: {op}")
            return frame.loc[mask]

        if mode in FILTER_TEXT_MODES or mode in FILTER_KEYWORD_MODES:
            if not field:
                raise ValueError(
                    f"Filter mode '{mode}' on a DataFrame requires a field/column name."
                )
            if field not in getattr(frame, "columns", []):
                raise ValueError(f"DataFrame has no column '{field}'.")
            series = frame[field].astype(str)
            keep_idx = [idx for idx, text in series.items() if self._match_text(text, mode)]
            return frame.loc[keep_idx]

        raise ValueError(f"Unsupported filter mode for DataFrame: {mode}")

    def _filter_dict_by_keys(self, value: dict) -> dict:
        mode = self.mode or FILTER_DEFAULT_MODE
        allow_descend = mode not in ("not_equals", "not_contains", "exclude_any")
        out = {}
        for key, item in value.items():
            if self._match_text(key if isinstance(key, str) else str(key)):
                out[key] = item
                continue
            if allow_descend and isinstance(item, dict):
                nested = self._filter_dict_by_keys(item)
                if nested:
                    out[key] = nested
        return out

    def _filter_dict_by_fields(self, value: dict) -> dict:
        filtered = {}
        for key, item in value.items():
            if isinstance(item, dict):
                if self._match_item(item):
                    filtered[key] = item
            else:
                if self._match_item({str(key): item}):
                    filtered[key] = item
        return filtered

    def _filter_dict_by_datetime(self, value: dict) -> dict:
        """
        Datetime modes on dicts:
        - If Field is set: compare that field inside each record value.
        - Else: treat dict keys as timestamps (econ events style); fall back to values.
        """
        field = (self.field or "").strip()
        if field:
            return self._filter_dict_by_fields(value)

        out = {}
        key_ok = 0
        for key, item in value.items():
            try:
                if self._match_datetime_value(key):
                    out[key] = item
                key_ok += 1
            except ValueError:
                try:
                    if self._match_datetime_value(item):
                        out[key] = item
                except ValueError:
                    continue
        if key_ok == 0 and not out:
            for key, item in value.items():
                try:
                    if self._match_datetime_value(item):
                        out[key] = item
                except ValueError:
                    continue
        return out

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if "value" not in inputs:
            raise ValueError("Filter requires a connected 'value' input.")
        value = inputs.get("value")
        mode = self.mode or FILTER_DEFAULT_MODE

        saved = (self.pattern, self.keywords, self.compare_value)
        self._filter_environment = environment
        try:
            self._apply_wired_criteria(inputs)

            if mode == "limit":
                filtered = self._limit_value(value)
                return {"filtered": filtered, "count": filter_count_value(filtered)}

            if type(value).__name__ == "DataFrame" and hasattr(value, "columns"):
                filtered = self._filter_dataframe(value)
                return {"filtered": filtered, "count": filter_count_value(filtered)}

            if isinstance(value, str) or value is None:
                text = "" if value is None else value
                if mode in FILTER_KEY_MODES or mode in FILTER_DATETIME_MODES:
                    raise ValueError(
                        f"Filter mode '{mode}' needs a list/dict of objects, not a plain string."
                    )
                kept = self._match_text(text, mode)
                filtered = text if kept else ""
                return {"filtered": filtered, "count": filter_count_value(filtered)}

            if isinstance(value, dict):
                if mode in FILTER_KEY_MODES:
                    filtered = self._filter_dict_by_fields(value)
                elif mode in FILTER_DATETIME_MODES:
                    filtered = self._filter_dict_by_datetime(value)
                elif mode in FILTER_TEXT_MODES or mode in FILTER_KEYWORD_MODES:
                    filtered = self._filter_dict_by_keys(value)
                else:
                    raise ValueError(f"Unsupported filter mode for dict: {mode}")
                return {"filtered": filtered, "count": filter_count_value(filtered)}

            if isinstance(value, (list, tuple, set)):
                items = list(value)
                filtered = [item for item in items if self._match_item(item)]
                return {"filtered": filtered, "count": filter_count_value(filtered)}

            if mode in FILTER_KEY_MODES or mode in FILTER_DATETIME_MODES:
                raise ValueError(
                    f"Filter mode '{mode}' needs a list/dict of objects, not {type(value).__name__}."
                )
            kept = self._match_text(value)
            return {
                "filtered": value if kept else None,
                "count": 1 if kept else 0,
            }
        finally:
            self.pattern, self.keywords, self.compare_value = saved
            self._filter_environment = None


class MathModule(Module):
    """Numeric operations with mode-specific ports."""

    module_type = "math"

    def __init__(
        self,
        name="Math",
        description="",
        mode=None,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or MATH_DEFAULT_MODE
        ports = MATH_PORTS.get(self.mode, MATH_PORTS[MATH_DEFAULT_MODE])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return (self.mode or MATH_DEFAULT_MODE) in MATH_FAN_IN_MODES

    def optional_input_names(self) -> set:
        mode = self.mode or MATH_DEFAULT_MODE
        if mode in MATH_FAN_IN_MODES:
            return {"b"}
        return set()

    def _sync_ports(self):
        ports = MATH_PORTS.get(self.mode, MATH_PORTS[MATH_DEFAULT_MODE])
        self.inputs = dict(ports["inputs"])
        self.outputs = dict(ports["outputs"])

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or MATH_DEFAULT_MODE
        if self.mode not in MATH_PORTS:
            self.mode = MATH_DEFAULT_MODE
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or MATH_DEFAULT_MODE
        return data

    def node_meta(self) -> str:
        return f"math · {self.mode or MATH_DEFAULT_MODE}"

    @staticmethod
    def _numbers_from(*raws) -> list[float]:
        numbers = []
        for raw in raws:
            for item in flatten_input_values(raw):
                numbers.append(coerce_number(item))
        return numbers

    @staticmethod
    def _one_number(raw, label: str) -> float:
        values = MathModule._numbers_from(raw)
        if not values:
            raise ValueError(f"Math requires a connected '{label}' input.")
        return values[-1]

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        mode = self.mode or MATH_DEFAULT_MODE

        if mode == "add":
            nums = self._numbers_from(inputs.get("a"), inputs.get("b"))
            if not nums:
                raise ValueError("Math add requires at least one number.")
            return {"result": sum(nums)}

        if mode == "mul":
            nums = self._numbers_from(inputs.get("a"), inputs.get("b"))
            if not nums:
                raise ValueError("Math multiply requires at least one number.")
            result = 1.0
            for n in nums:
                result *= n
            return {"result": result}

        if mode == "min":
            nums = self._numbers_from(inputs.get("a"), inputs.get("b"))
            if not nums:
                raise ValueError("Math min requires at least one number.")
            return {"result": min(nums)}

        if mode == "max":
            nums = self._numbers_from(inputs.get("a"), inputs.get("b"))
            if not nums:
                raise ValueError("Math max requires at least one number.")
            return {"result": max(nums)}

        if mode == "sub":
            return {
                "result": self._one_number(inputs.get("a"), "a")
                - self._one_number(inputs.get("b"), "b")
            }
        if mode == "div":
            b = self._one_number(inputs.get("b"), "b")
            if b == 0:
                raise ValueError("Math divide by zero.")
            return {"result": self._one_number(inputs.get("a"), "a") / b}
        if mode == "mod":
            b = self._one_number(inputs.get("b"), "b")
            if b == 0:
                raise ValueError("Math modulo by zero.")
            return {"result": self._one_number(inputs.get("a"), "a") % b}
        if mode == "pow":
            return {
                "result": self._one_number(inputs.get("a"), "a")
                ** self._one_number(inputs.get("b"), "b")
            }

        if mode in {"abs", "neg", "round", "floor", "ceil", "sqrt", "log", "log10", "exp"}:
            value = self._one_number(inputs.get("value"), "value")
            if mode == "abs":
                return {"result": abs(value)}
            if mode == "neg":
                return {"result": -value}
            if mode == "round":
                return {"result": float(round(value))}
            if mode == "floor":
                return {"result": float(mathlib.floor(value))}
            if mode == "ceil":
                return {"result": float(mathlib.ceil(value))}
            if mode == "sqrt":
                if value < 0:
                    raise ValueError("Math sqrt requires a non-negative value.")
                return {"result": mathlib.sqrt(value)}
            if mode == "log":
                if value <= 0:
                    raise ValueError("Math log requires a positive value.")
                return {"result": mathlib.log(value)}
            if mode == "log10":
                if value <= 0:
                    raise ValueError("Math log10 requires a positive value.")
                return {"result": mathlib.log10(value)}
            return {"result": mathlib.exp(value)}

        if mode == "clamp":
            value = self._one_number(inputs.get("value"), "value")
            low = self._one_number(inputs.get("min"), "min")
            high = self._one_number(inputs.get("max"), "max")
            if low > high:
                low, high = high, low
            return {"result": min(max(value, low), high)}

        if mode == "pct_change":
            old = self._one_number(inputs.get("old"), "old")
            new = self._one_number(inputs.get("new"), "new")
            if old == 0:
                raise ValueError("Math percent change requires a non-zero 'old' value.")
            return {"result": (new - old) / old}

        raise ValueError(f"Unsupported math mode: {mode}")


class CompareModule(Module):
    """Boolean comparisons: binary ops, all/any equal, between, approx equal."""

    module_type = "compare"

    def __init__(
        self,
        name="Compare",
        description="",
        mode=None,
        case_sensitive=False,
        epsilon=None,
        b_value=None,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or COMPARE_DEFAULT_MODE
        self.case_sensitive = bool(case_sensitive)
        try:
            self.epsilon = float(
                COMPARE_DEFAULT_EPSILON if epsilon is None else epsilon
            )
        except (TypeError, ValueError):
            self.epsilon = float(COMPARE_DEFAULT_EPSILON)
        self.epsilon = abs(self.epsilon)
        self.b_value = (
            COMPARE_DEFAULT_B_VALUE if b_value is None else str(b_value)
        )
        ports = COMPARE_PORTS.get(self.mode, COMPARE_PORTS[COMPARE_DEFAULT_MODE])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return (self.mode or COMPARE_DEFAULT_MODE) in COMPARE_FAN_IN_MODES

    def optional_input_names(self) -> set:
        mode = self.mode or COMPARE_DEFAULT_MODE
        if mode in COMPARE_BINARY_MODES:
            return {"b"}
        if mode in COMPARE_FAN_IN_MODES:
            return set()
        return set()

    def _sync_ports(self):
        ports = COMPARE_PORTS.get(self.mode, COMPARE_PORTS[COMPARE_DEFAULT_MODE])
        self.inputs = dict(ports["inputs"])
        self.outputs = dict(ports["outputs"])

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or COMPARE_DEFAULT_MODE
        if self.mode not in COMPARE_PORTS:
            self.mode = COMPARE_DEFAULT_MODE
        self.case_sensitive = bool(json_data.get("case_sensitive", self.case_sensitive))
        try:
            self.epsilon = abs(float(json_data.get("epsilon", self.epsilon)))
        except (TypeError, ValueError):
            self.epsilon = float(COMPARE_DEFAULT_EPSILON)
        self.b_value = str(json_data.get("b_value", self.b_value) or "")
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or COMPARE_DEFAULT_MODE
        data["case_sensitive"] = bool(self.case_sensitive)
        data["epsilon"] = float(self.epsilon)
        data["b_value"] = self.b_value
        return data

    def node_meta(self) -> str:
        mode = self.mode or COMPARE_DEFAULT_MODE
        if mode in COMPARE_MODE_OPS:
            return f"compare · {COMPARE_MODE_OPS[mode]}"
        return f"compare · {mode}"

    def _fold(self, value):
        if self.case_sensitive:
            return value
        # Keep numerics as-is so ordering still uses float path in filter_compare_values.
        try:
            if value is not None and str(value).strip() != "":
                float(value)
                return value
        except (TypeError, ValueError):
            pass
        return filter_norm_text(value, False)

    def _values_equal(self, left, right) -> bool:
        return filter_compare_values(self._fold(left), "==", self._fold(right))

    def _compare_op(self, left, right, op: str) -> bool:
        return filter_compare_values(self._fold(left), op, self._fold(right))

    def _one_value(self, raw, label: str):
        values = flatten_input_values(raw)
        if not values:
            raise ValueError(f"Compare requires a connected '{label}' input.")
        return values[-1]

    def _resolve_b(self, inputs: dict):
        if "b" in inputs:
            values = flatten_input_values(inputs.get("b"))
            if values:
                return values[-1]
        # Fall back to editor constant (may be empty string).
        return self.b_value

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        mode = self.mode or COMPARE_DEFAULT_MODE

        if mode in COMPARE_MODE_OPS:
            a = self._one_value(inputs.get("a"), "a")
            b = self._resolve_b(inputs)
            return {"result": self._compare_op(a, b, COMPARE_MODE_OPS[mode])}

        if mode == "approx_eq":
            a = coerce_number(self._one_value(inputs.get("a"), "a"))
            b = coerce_number(self._resolve_b(inputs))
            return {"result": abs(a - b) <= float(self.epsilon)}

        if mode in COMPARE_FAN_IN_MODES:
            values = flatten_input_values(inputs.get("value"))
            if len(values) < 2:
                raise ValueError(
                    f"Compare '{mode}' needs at least two values "
                    "(wire multiple sources into 'value')."
                )
            if mode == "all_equal":
                first = values[0]
                return {
                    "result": all(self._values_equal(first, item) for item in values[1:])
                }
            # any_equal
            for i, left in enumerate(values):
                for right in values[i + 1 :]:
                    if self._values_equal(left, right):
                        return {"result": True}
            return {"result": False}

        if mode == "between":
            value = self._one_value(inputs.get("value"), "value")
            low = self._one_value(inputs.get("min"), "min")
            high = self._one_value(inputs.get("max"), "max")
            # Prefer numeric inclusive range; fall back to string ordering.
            try:
                v = float(value)
                lo = float(low)
                hi = float(high)
                if lo > hi:
                    lo, hi = hi, lo
                return {"result": lo <= v <= hi}
            except (TypeError, ValueError):
                left = self._fold(low)
                right = self._fold(high)
                mid = self._fold(value)
                if filter_compare_values(left, ">", right):
                    left, right = right, left
                return {
                    "result": filter_compare_values(left, "<=", mid)
                    and filter_compare_values(mid, "<=", right)
                }

        raise ValueError(f"Unsupported compare mode: {mode}")


class StringModule(Module):
    """String transforms with mode-specific ports."""

    module_type = "string"

    def __init__(
        self,
        name="String",
        description="",
        mode=None,
        separator="",
        find="",
        replace_with="",
        case_sensitive=True,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or STRING_DEFAULT_MODE
        self.separator = "" if separator is None else str(separator)
        self.find = "" if find is None else str(find)
        self.replace_with = "" if replace_with is None else str(replace_with)
        self.case_sensitive = bool(case_sensitive)
        ports = STRING_PORTS.get(self.mode, STRING_PORTS[STRING_DEFAULT_MODE])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return (self.mode or STRING_DEFAULT_MODE) in STRING_FAN_IN_MODES

    def optional_input_names(self) -> set:
        mode = self.mode or STRING_DEFAULT_MODE
        optional = set()
        if mode == "concat":
            optional.add("b")
        if mode == "slice":
            optional.add("end")
        return optional

    def _sync_ports(self):
        ports = STRING_PORTS.get(self.mode, STRING_PORTS[STRING_DEFAULT_MODE])
        self.inputs = dict(ports["inputs"])
        self.outputs = dict(ports["outputs"])

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or STRING_DEFAULT_MODE
        if self.mode not in STRING_PORTS:
            self.mode = STRING_DEFAULT_MODE
        self.separator = str(json_data.get("separator", self.separator) or "")
        self.find = str(json_data.get("find", self.find) or "")
        self.replace_with = str(json_data.get("replace_with", self.replace_with) or "")
        self.case_sensitive = bool(json_data.get("case_sensitive", self.case_sensitive))
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or STRING_DEFAULT_MODE
        data["separator"] = self.separator
        data["find"] = self.find
        data["replace_with"] = self.replace_with
        data["case_sensitive"] = bool(self.case_sensitive)
        return data

    def node_meta(self) -> str:
        return f"string · {self.mode or STRING_DEFAULT_MODE}"

    @staticmethod
    def _as_text(raw) -> str:
        if raw is None:
            return ""
        if isinstance(raw, list):
            # Fan-in: last wins for single-value modes.
            return "" if not raw else StringModule._as_text(raw[-1])
        return str(raw)

    @staticmethod
    def _as_text_parts(raw) -> list[str]:
        return [
            "" if part is None else str(part) for part in flatten_input_values(raw)
        ]

    @staticmethod
    def _as_int(raw, label: str, default: int | None = None) -> int:
        values = flatten_input_values(raw)
        if not values:
            if default is not None:
                return default
            raise ValueError(f"String requires a connected '{label}' input.")
        try:
            return int(float(values[-1]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"String '{label}' must be an integer.") from exc

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        mode = self.mode or STRING_DEFAULT_MODE

        if mode == "concat":
            parts = self._as_text_parts(inputs.get("a")) + self._as_text_parts(
                inputs.get("b")
            )
            return {"result": "".join(parts)}

        if mode == "join":
            parts = []
            for item in flatten_input_values(inputs.get("value")):
                if isinstance(item, (list, tuple)):
                    parts.extend("" if p is None else str(p) for p in item)
                else:
                    parts.append("" if item is None else str(item))
            return {"result": self.separator.join(parts)}

        if mode in {"upper", "lower", "title", "strip", "length"}:
            if "value" not in inputs:
                raise ValueError("String requires a connected 'value' input.")
            text = self._as_text(inputs.get("value"))
            if mode == "upper":
                return {"result": text.upper()}
            if mode == "lower":
                return {"result": text.lower()}
            if mode == "title":
                return {"result": text.title()}
            if mode == "strip":
                return {"result": text.strip()}
            return {"result": len(text)}

        if mode == "replace":
            if "value" not in inputs:
                raise ValueError("String requires a connected 'value' input.")
            text = self._as_text(inputs.get("value"))
            find = self.find
            repl = self.replace_with
            if not self.case_sensitive:
                # Case-insensitive replace via regex.
                pattern = re.compile(re.escape(find), re.IGNORECASE)
                return {"result": pattern.sub(repl, text)}
            return {"result": text.replace(find, repl)}

        if mode == "split":
            if "value" not in inputs:
                raise ValueError("String requires a connected 'value' input.")
            text = self._as_text(inputs.get("value"))
            sep = self.separator
            parts = text.split(sep) if sep != "" else text.split()
            return {"parts": parts, "count": len(parts)}

        if mode in {"contains", "starts_with", "ends_with"}:
            if "value" not in inputs:
                raise ValueError("String requires a connected 'value' input.")
            text = self._as_text(inputs.get("value"))
            needle = self.find
            if not self.case_sensitive:
                text_cmp = text.lower()
                needle_cmp = needle.lower()
            else:
                text_cmp = text
                needle_cmp = needle
            if mode == "contains":
                return {"result": needle_cmp in text_cmp}
            if mode == "starts_with":
                return {"result": text_cmp.startswith(needle_cmp)}
            return {"result": text_cmp.endswith(needle_cmp)}

        if mode == "slice":
            if "value" not in inputs:
                raise ValueError("String requires a connected 'value' input.")
            text = self._as_text(inputs.get("value"))
            start = self._as_int(inputs.get("start"), "start", default=0)
            if "end" in inputs:
                end = self._as_int(inputs.get("end"), "end")
                return {"result": text[start:end]}
            return {"result": text[start:]}

        raise ValueError(f"Unsupported string mode: {mode}")


class ThrottleModule(Module):
    """
    Rate-limit passthrough: only emit outputs if this key has not fired
    within interval_sec. When blocked, returns {} so dependents skip.
    Session timestamps live on environment.modulink_throttle.
    """

    module_type = "throttle"

    def __init__(
        self,
        name="Throttle",
        description="",
        interval_sec=None,
        default_key="",
        passthrough=None,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        try:
            self.interval_sec = float(
                THROTTLE_DEFAULT_INTERVAL_SEC
                if interval_sec is None
                else interval_sec
            )
        except (TypeError, ValueError):
            self.interval_sec = float(THROTTLE_DEFAULT_INTERVAL_SEC)
        self.interval_sec = max(0.0, self.interval_sec)
        self.default_key = "" if default_key is None else str(default_key)
        self.passthrough = dict(passthrough or THROTTLE_DEFAULT_PASSTHROUGH)
        ports_in, ports_out = self._ports_from_fields()
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports_in),
            outputs=dict(outputs if outputs is not None else ports_out),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def optional_input_names(self) -> set:
        return {THROTTLE_KEY_PORT}

    def _normalize_passthrough(self) -> dict:
        cleaned = {}
        for raw_name, type_hint in (self.passthrough or {}).items():
            name = str(raw_name or "").strip()
            if not name or name in THROTTLE_RESERVED_PORTS or name in cleaned:
                continue
            cleaned[name] = type_hint or "any"
        return cleaned or dict(THROTTLE_DEFAULT_PASSTHROUGH)

    def _ports_from_fields(self):
        passthrough = self._normalize_passthrough()
        inputs = {THROTTLE_KEY_PORT: "str"}
        inputs.update(passthrough)
        return inputs, dict(passthrough)

    def _sync_ports(self):
        self.passthrough = self._normalize_passthrough()
        self.inputs, self.outputs = self._ports_from_fields()

    def from_json(self, json_data):
        super().from_json(json_data)
        try:
            self.interval_sec = max(
                0.0, float(json_data.get("interval_sec", self.interval_sec))
            )
        except (TypeError, ValueError):
            self.interval_sec = float(THROTTLE_DEFAULT_INTERVAL_SEC)
        self.default_key = str(json_data.get("default_key", self.default_key) or "")
        self.passthrough = dict(
            json_data.get("passthrough", self.passthrough)
            or THROTTLE_DEFAULT_PASSTHROUGH
        )
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["interval_sec"] = float(self.interval_sec)
        data["default_key"] = self.default_key
        data["passthrough"] = dict(self.passthrough)
        return data

    def node_meta(self) -> str:
        sec = float(self.interval_sec or 0.0)
        if sec >= 60 and abs(sec % 60) < 1e-9:
            return f"throttle · {int(sec // 60)}m"
        if sec == int(sec):
            return f"throttle · {int(sec)}s"
        return f"throttle · {sec:g}s"

    def _resolve_key(self, inputs: dict) -> str:
        if THROTTLE_KEY_PORT in inputs:
            raw = inputs.get(THROTTLE_KEY_PORT)
            if isinstance(raw, list):
                raw = raw[-1] if raw else ""
            text = str(raw or "").strip()
            if text:
                return text
        text = (self.default_key or "").strip()
        if text:
            return text
        return str(self.module_id)

    def _remaining_sec(self, environment, key: str, now: float | None = None) -> float:
        root = get_modulink_throttle_root(environment)
        last = root.get(key)
        try:
            last = float(last)
        except (TypeError, ValueError):
            return 0.0
        now = time.time() if now is None else float(now)
        remaining = float(self.interval_sec) - (now - last)
        return remaining if remaining > 0 else 0.0

    def node_summary(self, *, environment=None, run_state=None) -> str:
        if environment is not None:
            try:
                key = (self.default_key or "").strip() or str(self.module_id)
                remaining = self._remaining_sec(environment, key)
                if remaining > 0:
                    if remaining >= 60:
                        return f"wait {remaining / 60:.1f}m"
                    return f"wait {remaining:.0f}s"
                return "ready"
            except Exception:
                pass
        return super().node_summary(environment=environment, run_state=run_state)

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Throttle requires a host environment.")
        self._sync_ports()
        if not self.passthrough:
            raise ValueError("Throttle needs at least one passthrough field.")

        key = self._resolve_key(inputs)
        now = time.time()
        remaining = self._remaining_sec(environment, key, now=now)
        if remaining > 0:
            # Block: withhold outputs so dependents skip.
            return {}

        root = get_modulink_throttle_root(environment)
        root[key] = now
        return {name: inputs.get(name) for name in self.passthrough}


class SimBatchModule(Module):
    """Read / load / summarize saved simulation batches."""

    module_type = "sim_batch"

    def __init__(
        self,
        name="Sim Batch",
        description="",
        mode=None,
        default_names="",
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or SIM_BATCH_DEFAULT_MODE
        self.default_names = "" if default_names is None else str(default_names)
        ports = SIM_BATCH_PORTS.get(self.mode, SIM_BATCH_PORTS[SIM_BATCH_DEFAULT_MODE])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def _sync_ports(self):
        ports = SIM_BATCH_PORTS.get(self.mode, SIM_BATCH_PORTS[SIM_BATCH_DEFAULT_MODE])
        self.inputs = dict(ports["inputs"])
        self.outputs = dict(ports["outputs"])

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or SIM_BATCH_DEFAULT_MODE
        self.default_names = str(json_data.get("default_names", self.default_names) or "")
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or SIM_BATCH_DEFAULT_MODE
        data["default_names"] = self.default_names
        return data

    def _resolve_names(self, inputs: dict, *, required: bool) -> list[str]:
        raw = inputs.get("names", None)
        if raw is None or raw == "":
            raw = self.default_names
        names = normalize_batch_names(raw)
        if required and not names:
            raise ValueError(
                "Sim Batch requires batch name(s) via the 'names' input "
                "(string, list, or dict keys) or Default names."
            )
        return names

    def _cached_metrics_map(self, environment, names: list[str] | None = None) -> dict:
        account = getattr(environment, "account", None)
        cache = getattr(account, "sim_batch_performance_cache", None) or {}
        if names is None:
            # Prefer on-disk names; include cache-only leftovers too.
            disk_names = list_sim_batch_names(environment)
            ordered = list(disk_names)
            for name in cache.keys():
                if name not in ordered:
                    ordered.append(name)
            names = ordered
        out = {}
        for name in names:
            metrics = cache.get(name)
            if isinstance(metrics, dict):
                out[name] = dict(metrics)
            else:
                out[name] = {}
        return out

    def _load_named_batches(self, environment, names: list[str]) -> dict:
        batches = {}
        for name in names:
            batches[name] = load_sim_batch_by_name(environment, name)
        return batches

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Sim Batch requires a host environment.")
        mode = self.mode or SIM_BATCH_DEFAULT_MODE

        if mode == "list":
            names = list_sim_batch_names(environment)
            cache = self._cached_metrics_map(environment, names)
            return {"names": names, "cache": cache, "count": len(names)}

        if mode == "cache":
            # Empty names → all known batches (disk + cache).
            names = self._resolve_names(inputs, required=False)
            if not names:
                names = list(self._cached_metrics_map(environment).keys())
                if not names:
                    names = list_sim_batch_names(environment)
            metrics = self._cached_metrics_map(environment, names)
            return {"names": list(metrics.keys()), "metrics": metrics, "count": len(metrics)}

        if mode == "load":
            names = self._resolve_names(inputs, required=True)
            batches = self._load_named_batches(environment, names)
            return {"names": names, "batches": batches, "count": len(batches)}

        if mode == "sims":
            names = self._resolve_names(inputs, required=True)
            batches = self._load_named_batches(environment, names)
            sims = {}
            for batch_name, batch in batches.items():
                for sim_id, sim_data in batch.items():
                    key = str(sim_id)
                    if key in sims:
                        key = f"{batch_name}::{sim_id}"
                    sims[key] = sim_data
            return {"names": names, "sims": sims, "count": len(sims)}

        if mode == "performance":
            names = self._resolve_names(inputs, required=True)
            batches = self._load_named_batches(environment, names)
            metrics = {}
            combined_sims = {}
            for batch_name, batch in batches.items():
                metrics[batch_name] = compute_sim_batch_metrics(environment, batch)
                for sim_id, sim_data in batch.items():
                    key = str(sim_id)
                    if key in combined_sims:
                        key = f"{batch_name}::{sim_id}"
                    combined_sims[key] = sim_data
            combined = compute_sim_batch_metrics(environment, combined_sims)
            return {
                "names": names,
                "metrics": metrics,
                "combined": combined,
                "count": len(metrics),
            }

        raise ValueError(f"Unsupported sim batch mode: {mode}")


class MemoryModule(Module):
    """
    Session variable owned by this module instance.

    Survives blueprint re-runs on environment.modulink_memory[module_id].
    Not saved to the account file. Inputs are optional; multiple wires may
    fan into the same input (list appends each value; single/dict last-wins).
    """

    module_type = "memory"

    def __init__(
        self,
        name="Memory",
        description="",
        kind=None,
        keys=None,
        allow_duplicates=True,
        output_is_set=False,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.kind = kind or MEMORY_DEFAULT_KIND
        self.keys = list(keys if keys is not None else MEMORY_DEFAULT_DICT_KEYS)
        self.allow_duplicates = bool(allow_duplicates)
        self.output_is_set = bool(output_is_set)
        ports_in, ports_out = self._ports_from_fields()
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports_in),
            outputs=dict(outputs if outputs is not None else ports_out),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return True

    def optional_input_names(self) -> set:
        return set(self.inputs.keys())

    def node_meta(self) -> str:
        kind = self.kind or MEMORY_DEFAULT_KIND
        if self.output_is_set:
            return f"memory · {kind} · is_set"
        return f"memory · {kind}"

    def node_summary(self, *, environment=None, run_state=None) -> str:
        if environment is not None:
            root = getattr(environment, "modulink_memory", None)
            if isinstance(root, dict):
                slot = root.get(str(self.module_id))
                if isinstance(slot, dict) and "value" in slot:
                    return format_memory_summary(
                        slot.get("kind") or self.kind,
                        slot.get("value"),
                    )
        return super().node_summary(environment=environment, run_state=run_state)

    def _normalize_keys(self) -> list[str]:
        cleaned = []
        seen = set()
        for raw in self.keys or []:
            name = str(raw or "").strip()
            if not name or name in MEMORY_RESERVED_PORTS or name in seen:
                continue
            seen.add(name)
            cleaned.append(name)
        if self.kind == "dict" and not cleaned:
            cleaned = list(MEMORY_DEFAULT_DICT_KEYS)
        return cleaned

    def _ports_from_fields(self):
        kind = self.kind or MEMORY_DEFAULT_KIND
        if kind == "list":
            inputs = {"item": "any", MEMORY_CLEAR_PORT: "bool"}
            outputs = {"items": "list", "count": "int"}
        elif kind == "dict":
            keys = self._normalize_keys()
            inputs = {key: "any" for key in keys}
            inputs[MEMORY_CLEAR_PORT] = "bool"
            outputs = {key: "any" for key in keys}
            outputs[MEMORY_DATA_PORT] = "dict"
        else:
            # single
            inputs = {"value": "any", MEMORY_CLEAR_PORT: "bool"}
            outputs = {"value": "any"}
        if self.output_is_set:
            outputs[MEMORY_IS_SET_PORT] = "bool"
        return inputs, outputs

    def _sync_ports(self):
        self.keys = self._normalize_keys()
        self.inputs, self.outputs = self._ports_from_fields()

    def from_json(self, json_data):
        super().from_json(json_data)
        # Prefer new "kind"; fall back to default (ignore legacy mode/store).
        self.kind = json_data.get("kind", self.kind) or MEMORY_DEFAULT_KIND
        if self.kind not in {k for k, _ in MEMORY_KIND_OPTIONS}:
            self.kind = MEMORY_DEFAULT_KIND
        self.keys = list(json_data.get("keys", self.keys) or MEMORY_DEFAULT_DICT_KEYS)
        self.allow_duplicates = bool(json_data.get("allow_duplicates", self.allow_duplicates))
        self.output_is_set = bool(json_data.get("output_is_set", self.output_is_set))
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["kind"] = self.kind or MEMORY_DEFAULT_KIND
        data["keys"] = list(self.keys)
        data["allow_duplicates"] = bool(self.allow_duplicates)
        data["output_is_set"] = bool(self.output_is_set)
        return data

    @staticmethod
    def _as_value_list(raw):
        if raw is None:
            return []
        if isinstance(raw, list):
            return list(raw)
        return [raw]

    def _empty_value(self):
        kind = self.kind or MEMORY_DEFAULT_KIND
        if kind == "list":
            return []
        if kind == "dict":
            return {}
        return None

    def _value_is_set(self, value) -> bool:
        """True when the slot holds a value (not clear / empty for this kind)."""
        kind = self.kind or MEMORY_DEFAULT_KIND
        if kind == "list":
            return isinstance(value, list) and len(value) > 0
        if kind == "dict":
            return isinstance(value, dict) and len(value) > 0
        return value is not None

    def _ensure_slot(self, environment) -> dict:
        slot = get_modulink_memory_slot(environment, self.module_id)
        kind = self.kind or MEMORY_DEFAULT_KIND
        if slot.get("kind") != kind:
            slot["kind"] = kind
            slot["value"] = self._empty_value()
            return slot
        value = slot.get("value")
        if kind == "list" and not isinstance(value, list):
            slot["value"] = []
        elif kind == "dict" and not isinstance(value, dict):
            slot["value"] = {}
        return slot

    def _should_clear(self, inputs: dict) -> bool:
        if MEMORY_CLEAR_PORT not in inputs:
            return False
        return any(bool(v) for v in self._as_value_list(inputs.get(MEMORY_CLEAR_PORT)))

    def _with_is_set(self, outputs: dict, value) -> dict:
        if self.output_is_set:
            outputs[MEMORY_IS_SET_PORT] = self._value_is_set(value)
        return outputs

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Memory requires a host environment.")
        kind = self.kind or MEMORY_DEFAULT_KIND
        slot = self._ensure_slot(environment)

        if self._should_clear(inputs):
            slot["value"] = self._empty_value()

        if kind == "single":
            if "value" in inputs:
                values = [
                    v for v in self._as_value_list(inputs.get("value")) if v is not None
                ]
                if values:
                    slot["value"] = values[-1]
            return self._with_is_set({"value": slot["value"]}, slot["value"])

        if kind == "list":
            items = list(slot["value"] if isinstance(slot["value"], list) else [])
            if "item" in inputs:
                for value in self._as_value_list(inputs.get("item")):
                    if value is None:
                        continue
                    if not self.allow_duplicates and value in items:
                        continue
                    items.append(value)
            if not self.allow_duplicates:
                # Collapse any pre-existing duplicates (e.g. from when dupes were allowed).
                unique = []
                for value in items:
                    if value not in unique:
                        unique.append(value)
                items = unique
            slot["value"] = items
            return self._with_is_set(
                {"items": list(items), "count": len(items)},
                items,
            )

        if kind == "dict":
            data = dict(slot["value"] if isinstance(slot["value"], dict) else {})
            for key in self._normalize_keys():
                if key not in inputs:
                    continue
                values = [
                    v for v in self._as_value_list(inputs.get(key)) if v is not None
                ]
                if values:
                    data[key] = values[-1]
            slot["value"] = data
            outputs = {key: data.get(key) for key in self._normalize_keys()}
            outputs[MEMORY_DATA_PORT] = dict(data)
            return self._with_is_set(outputs, data)

        raise ValueError(f"Unsupported memory kind: {kind}")


class ConstantModule(Module):
    """Fixed named outputs — constants the graph can wire into other modules."""

    module_type = "constant"

    def __init__(
        self,
        name="Constant",
        description="",
        values=None,
        outputs=None,
        json_data=None,
    ):
        self.values = dict(values or CONSTANT_DEFAULT_VALUES)
        super().__init__(
            name=name,
            description=description,
            inputs={},
            outputs=dict(outputs or CONSTANT_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if not self.outputs:
            self.outputs = dict(CONSTANT_DEFAULT_OUTPUTS)
        self._sync_values_to_outputs()

    def _sync_values_to_outputs(self):
        """Keep values keys aligned with declared outputs."""
        synced = {}
        for name in self.outputs:
            if name in self.values:
                synced[name] = self.values[name]
            else:
                synced[name] = ""
        self.values = synced

    def from_json(self, json_data):
        super().from_json(json_data)
        self.inputs = {}
        self.values = dict(json_data.get("values", self.values))
        self._sync_values_to_outputs()

    def to_json(self):
        data = super().to_json()
        data["inputs"] = {}
        data["values"] = dict(self.values)
        return data

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        result = {}
        for name, type_hint in self.outputs.items():
            try:
                result[name] = coerce_constant_value(self.values.get(name), type_hint)
            except Exception as exc:
                raise ValueError(f"Constant '{name}': {exc}") from exc
        return result

    def node_meta(self) -> str:
        return "constant"

    def node_summary(self, *, environment=None, run_state=None) -> str:
        if not self.values:
            return ""
        if len(self.values) == 1:
            key = next(iter(self.values))
            hint = self.outputs.get(key, "any")
            try:
                value = coerce_constant_value(self.values.get(key), hint)
            except Exception:
                value = self.values.get(key)
            return format_value(value, max_len=NODE_SUMMARY_MAX_LEN)
        return f"{len(self.values)} constants"


class ConditionModule(Module):
    """
    Boolean gate / result.

    Default: when the condition passes, passthrough inputs become outputs;
    when False, outputs are withheld (dependents skip).

    output_result=True: no passthrough — always emits bool `result` (True/False).
    """

    module_type = "condition"

    def __init__(
        self,
        name="Condition",
        description="",
        mode=None,
        condition_inputs=None,
        passthrough=None,
        output_result=False,
        json_data=None,
    ):
        self.mode = mode or CONDITION_DEFAULT_MODE
        self.condition_inputs = dict(
            condition_inputs or CONDITION_DEFAULT_CONDITION_INPUTS
        )
        self.passthrough = dict(passthrough or CONDITION_DEFAULT_PASSTHROUGH)
        self.output_result = bool(output_result)
        inputs, outputs = self._ports_from_fields()
        super().__init__(
            name=name,
            description=description,
            inputs=inputs,
            outputs=outputs,
            json_data=json_data,
        )
        if json_data is None:
            self._normalize_mode_ports()

    def _ports_from_fields(self):
        inputs = dict(self.condition_inputs)
        if self.output_result:
            return inputs, {CONDITION_RESULT_PORT: "bool"}
        inputs.update(self.passthrough)
        return inputs, dict(self.passthrough)

    def _rebuild_ports(self):
        self.inputs, self.outputs = self._ports_from_fields()

    def _normalize_mode_ports(self):
        """Keep condition port count consistent with mode (if/not = one port)."""
        if self.mode in CONDITION_SINGLE_MODES:
            if len(self.condition_inputs) != 1:
                name = next(iter(self.condition_inputs), "cond")
                self.condition_inputs = {name: "bool"}
        elif self.mode in CONDITION_MULTI_MODES:
            if not self.condition_inputs:
                self.condition_inputs = {"cond_1": "bool", "cond_2": "bool"}
        # Result port name cannot collide with a condition input.
        if CONDITION_RESULT_PORT in self.condition_inputs:
            raise ValueError(
                f"Condition input cannot be named '{CONDITION_RESULT_PORT}' "
                "(reserved for result output mode)."
            )
        if self.output_result:
            self.passthrough = {}
        else:
            if not self.passthrough:
                self.passthrough = dict(CONDITION_DEFAULT_PASSTHROUGH)
            # Condition and passthrough names must not collide.
            overlap = set(self.condition_inputs) & set(self.passthrough)
            if overlap:
                raise ValueError(
                    f"Condition and passthrough ports cannot share names: {sorted(overlap)}"
                )
        self._rebuild_ports()

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode)
        self.condition_inputs = dict(
            json_data.get("condition_inputs", self.condition_inputs)
        )
        self.passthrough = dict(json_data.get("passthrough", self.passthrough))
        self.output_result = bool(json_data.get("output_result", self.output_result))
        # Older saves may only have inputs/outputs — recover if needed.
        if not self.condition_inputs and not self.passthrough and not self.output_result:
            recovered_pass = dict(json_data.get("outputs") or self.outputs or {})
            recovered_cond = {
                name: "bool"
                for name in (json_data.get("inputs") or self.inputs or {})
                if name not in recovered_pass
            }
            self.passthrough = recovered_pass or dict(CONDITION_DEFAULT_PASSTHROUGH)
            self.condition_inputs = recovered_cond or dict(
                CONDITION_DEFAULT_CONDITION_INPUTS
            )
        self._normalize_mode_ports()

    def to_json(self):
        self._rebuild_ports()
        data = super().to_json()
        data["mode"] = self.mode
        data["condition_inputs"] = dict(self.condition_inputs)
        data["passthrough"] = dict(self.passthrough)
        data["output_result"] = bool(self.output_result)
        return data

    def node_meta(self) -> str:
        mode = self.mode or CONDITION_DEFAULT_MODE
        if self.output_result:
            return f"condition · {mode} · result"
        return f"condition · {mode}"

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if not self.condition_inputs:
            raise ValueError("Condition module needs at least one condition input.")
        if not self.output_result and not self.passthrough:
            raise ValueError("Condition module needs at least one passthrough field.")

        flags = [
            coerce_condition_bool(inputs.get(name))
            for name in self.condition_inputs
        ]
        if self.mode == "if":
            passed = flags[0]
        elif self.mode == "not":
            passed = not flags[0]
        elif self.mode == "and":
            passed = all(flags)
        elif self.mode == "or":
            passed = any(flags)
        else:
            raise ValueError(f"Unsupported condition mode: {self.mode}")

        if self.output_result:
            return {CONDITION_RESULT_PORT: bool(passed)}
        if not passed:
            return {}
        return {name: inputs.get(name) for name in self.passthrough}


class DrawingModule(Module):
    """Draws/updates a named overlay via the host environment (no outputs)."""

    module_type = "drawing"

    def __init__(
        self,
        name="Drawing",
        description="",
        drawing_type=None,
        color=None,
        size=None,
        style=None,
        anchor=None,
        border_color=None,
        filled=None,
        glow=None,
        glow_color=None,
        glow_width=None,
        timeframe=None,
        inputs=None,
        json_data=None,
    ):
        self.drawing_type = drawing_type or DRAWING_DEFAULT_TYPE
        self.color = DRAWING_DEFAULT_STYLE["color"] if color is None else color
        self.size = DRAWING_DEFAULT_STYLE["size"] if size is None else size
        self.style = DRAWING_DEFAULT_STYLE["style"] if style is None else style
        self.anchor = DRAWING_DEFAULT_STYLE["anchor"] if anchor is None else anchor
        self.border_color = (
            DRAWING_DEFAULT_STYLE["border_color"] if border_color is None else border_color
        )
        self.filled = DRAWING_DEFAULT_STYLE["filled"] if filled is None else filled
        self.glow = DRAWING_DEFAULT_STYLE["glow"] if glow is None else glow
        self.glow_color = (
            DRAWING_DEFAULT_STYLE["glow_color"] if glow_color is None else glow_color
        )
        self.glow_width = (
            DRAWING_DEFAULT_STYLE["glow_width"] if glow_width is None else glow_width
        )
        self.timeframe = (
            DRAWING_DEFAULT_STYLE["timeframe"] if timeframe is None else timeframe
        )
        port_inputs = dict(inputs or DRAWING_TYPE_INPUTS.get(self.drawing_type, {}))
        super().__init__(
            name=name,
            description=description,
            inputs=port_inputs,
            outputs={},
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def _sync_ports(self):
        self.inputs = dict(DRAWING_TYPE_INPUTS.get(self.drawing_type, {}))
        self.outputs = {}

    def from_json(self, json_data):
        super().from_json(json_data)
        self.drawing_type = json_data.get("drawing_type", self.drawing_type)
        self.color = json_data.get("color", self.color)
        self.size = json_data.get("size", self.size)
        self.style = json_data.get("style", self.style)
        anchor = json_data.get("anchor", self.anchor)
        if isinstance(anchor, list):
            anchor = tuple(anchor)
        self.anchor = anchor
        self.border_color = json_data.get("border_color", self.border_color)
        self.filled = json_data.get("filled", self.filled)
        self.glow = json_data.get("glow", self.glow)
        glow_color = json_data.get("glow_color", self.glow_color)
        if isinstance(glow_color, list):
            glow_color = tuple(glow_color)
        self.glow_color = glow_color
        self.glow_width = json_data.get("glow_width", self.glow_width)
        self.timeframe = json_data.get("timeframe", self.timeframe)
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["drawing_type"] = self.drawing_type
        data["color"] = self.color
        data["size"] = self.size
        data["style"] = self.style
        data["anchor"] = list(self.anchor) if isinstance(self.anchor, tuple) else self.anchor
        data["border_color"] = self.border_color
        data["filled"] = self.filled
        data["glow"] = self.glow
        data["glow_color"] = (
            list(self.glow_color) if isinstance(self.glow_color, tuple) else self.glow_color
        )
        data["glow_width"] = self.glow_width
        data["timeframe"] = self.timeframe
        data["outputs"] = {}
        return data

    def _coerce_port(self, name: str, type_hint: str, raw):
        if raw is None:
            raise ValueError(f"Drawing input '{name}' is required.")
        if type_hint == "str":
            text = str(raw).strip()
            if not text and name == "name":
                raise ValueError("Drawing 'name' cannot be empty.")
            return text if name != "text" else str(raw)
        if type_hint == "float":
            return float(raw)
        if type_hint == "int":
            return int(raw)
        return raw

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Drawing module requires a host environment.")

        if self.drawing_type == "clear":
            if not hasattr(environment, "clear_modulink_drawings"):
                raise ValueError("Environment does not support clearing ModuLink drawings.")
            if not coerce_condition_bool(inputs.get("clear")):
                return {}
            environment.clear_modulink_drawings()
            return {}

        if not hasattr(environment, "update_modulink_drawing"):
            raise ValueError("Environment does not support ModuLink drawings.")

        ports = DRAWING_TYPE_INPUTS.get(self.drawing_type)
        if ports is None:
            raise ValueError(f"Unsupported drawing type: {self.drawing_type}")

        try:
            size = max(1, int(round(float(self.size))))
        except (TypeError, ValueError):
            size = 10
        drawing_data = {
            "type": self.drawing_type,
            "color": self.color,
            "size": size,
        }
        for port_name, type_hint in ports.items():
            drawing_data[port_name] = self._coerce_port(
                port_name, type_hint, inputs.get(port_name)
            )

        if self.drawing_type == "line":
            drawing_data["style"] = self.style or "solid"
        elif self.drawing_type == "text":
            drawing_data["anchor"] = self.anchor or (0.5, 0.5)
        elif self.drawing_type == "candle":
            drawing_data["border_color"] = self.border_color
            drawing_data["filled"] = bool(self.filled)
            drawing_data["glow"] = bool(self.glow)
            drawing_data["glow_color"] = self.glow_color
            drawing_data["glow_width"] = self.glow_width
            drawing_data["timeframe"] = self.timeframe or "1m"

        environment.update_modulink_drawing(drawing_data)
        return {}


class WaitModule(Module):
    """Interruptible wait: duration (seconds) or until a clock time.

    require_activate (off by default): only wait when wired activate is True
    (any True if fan-in); otherwise withhold outputs and skip the wait.

    Optional value input/output: passthrough unchanged after a successful wait
    (withheld when the wait is skipped / stopped).
    """

    module_type = "wait"

    def __init__(
        self,
        name="Wait",
        description="",
        mode=None,
        seconds=None,
        until=None,
        require_activate=False,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.mode = mode or WAIT_DEFAULT_MODE
        try:
            self.seconds = float(
                WAIT_DEFAULT_SECONDS if seconds is None else seconds
            )
        except (TypeError, ValueError):
            self.seconds = float(WAIT_DEFAULT_SECONDS)
        self.seconds = max(0.0, self.seconds)
        self.until = "" if until is None else str(until)
        self.require_activate = bool(require_activate)
        ports = WAIT_PORTS.get(self.mode, WAIT_PORTS[WAIT_DEFAULT_MODE])
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports["inputs"]),
            outputs=dict(outputs if outputs is not None else ports["outputs"]),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return True

    def optional_input_names(self) -> set:
        return set(self.inputs.keys())

    def _sync_ports(self):
        ports = WAIT_PORTS.get(self.mode, WAIT_PORTS[WAIT_DEFAULT_MODE])
        inputs = dict(ports["inputs"])
        outputs = dict(ports["outputs"])
        if self.require_activate:
            inputs[WAIT_ACTIVATE_PORT] = "bool"
        inputs[WAIT_VALUE_PORT] = "any"
        outputs[WAIT_VALUE_PORT] = "any"
        self.inputs = inputs
        self.outputs = outputs

    def from_json(self, json_data):
        super().from_json(json_data)
        self.mode = json_data.get("mode", self.mode) or WAIT_DEFAULT_MODE
        if self.mode not in WAIT_PORTS:
            self.mode = WAIT_DEFAULT_MODE
        try:
            self.seconds = max(0.0, float(json_data.get("seconds", self.seconds)))
        except (TypeError, ValueError):
            self.seconds = float(WAIT_DEFAULT_SECONDS)
        self.until = str(json_data.get("until", self.until) or "")
        self.require_activate = bool(
            json_data.get("require_activate", self.require_activate)
        )
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["mode"] = self.mode or WAIT_DEFAULT_MODE
        data["seconds"] = float(self.seconds)
        data["until"] = self.until
        data["require_activate"] = bool(self.require_activate)
        return data

    def node_meta(self) -> str:
        mode = self.mode or WAIT_DEFAULT_MODE
        suffix = " · activate" if self.require_activate else ""
        if mode == "until":
            target = (self.until or "").strip() or "…"
            return f"wait · until {target}{suffix}"
        sec = float(self.seconds or 0.0)
        if sec == int(sec):
            return f"wait · {int(sec)}s{suffix}"
        return f"wait · {sec:g}s{suffix}"

    def _is_activated(self, inputs: dict) -> bool:
        if not self.require_activate:
            return True
        if WAIT_ACTIVATE_PORT not in inputs:
            return False
        values = flatten_input_values(inputs.get(WAIT_ACTIVATE_PORT))
        if not values:
            return False
        return any(coerce_condition_bool(v) for v in values)

    def _success_outputs(self, inputs: dict, started: float) -> dict:
        out = {"done": True, "elapsed": time.time() - started}
        if WAIT_VALUE_PORT in inputs:
            values = [
                v
                for v in flatten_input_values(inputs.get(WAIT_VALUE_PORT))
                if v is not None
            ]
            if values:
                out[WAIT_VALUE_PORT] = values[-1]
        return out

    @staticmethod
    def _sleep_interruptible(environment, total_sec: float) -> bool:
        """Sleep up to total_sec. Returns False if stopped early."""
        remaining = max(0.0, float(total_sec))
        end = time.time() + remaining
        while True:
            if modulink_should_stop(environment):
                return False
            now = time.time()
            if now >= end:
                return True
            time.sleep(min(0.1, end - now))

    def _resolve_until(self, raw, environment) -> datetime.datetime:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("Wait until requires a time / datetime string.")
        tz = getattr(environment, "tzinfo", None) if environment is not None else None
        now = datetime.datetime.now(tz) if tz is not None else datetime.datetime.now()

        # Full ISO-ish datetime first.
        for parser in (
            lambda s: datetime.datetime.fromisoformat(s),
            lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S"),
            lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M"),
            lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S"),
            lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M"),
        ):
            try:
                dt = parser(text)
                if tz is not None and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                return dt
            except Exception:
                pass

        # Time-of-day → today, or tomorrow if already past.
        # Truncation to whole seconds can make a near-future target look
        # slightly past; only roll to tomorrow when clearly ≥1s overdue.
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                dt = now.replace(
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=parsed.second if fmt.endswith("%S") else 0,
                    microsecond=0,
                )
                if dt <= now and (now - dt).total_seconds() >= 1.0:
                    dt = dt + datetime.timedelta(days=1)
                return dt
            except Exception:
                pass
        raise ValueError(
            f"Unrecognized wait-until time '{text}'. "
            "Use HH:MM, HH:MM:SS, or YYYY-MM-DD HH:MM[:SS]."
        )

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        mode = self.mode or WAIT_DEFAULT_MODE
        started = time.time()

        if not self._is_activated(inputs):
            # Not activated: skip wait and withhold outputs.
            return {}

        if mode == "duration":
            seconds = self.seconds
            if "seconds" in inputs:
                values = flatten_input_values(inputs.get("seconds"))
                if values:
                    seconds = max(0.0, coerce_number(values[-1]))
            ok = self._sleep_interruptible(environment, seconds)
            if not ok:
                return {}
            return self._success_outputs(inputs, started)

        if mode == "until":
            raw = self.until
            if "until" in inputs:
                values = flatten_input_values(inputs.get("until"))
                if values:
                    raw = values[-1]
            target = self._resolve_until(raw, environment)
            tz = getattr(target, "tzinfo", None)
            while True:
                if modulink_should_stop(environment):
                    return {}
                now = datetime.datetime.now(tz) if tz is not None else datetime.datetime.now()
                if now >= target:
                    return self._success_outputs(inputs, started)
                delta = (target - now).total_seconds()
                time.sleep(min(0.1, max(0.0, delta)))

        raise ValueError(f"Unsupported wait mode: {mode}")


class PromptModule(Module):
    """
    Multi-field human prompt dialog (UI thread).

    Not activated → empty outputs (dependents skip; no None field writes).
    Cancel → accepted=False only (field values withheld).

    trigger_mode:
      - message (default): only open when wired Message values arrive; fan-in joins text
      - activate: use built-in message; open when any wired Activate value is True
    """

    module_type = "prompt"

    def __init__(
        self,
        name="Prompt",
        description="",
        title="ModuLink Prompt",
        message="Please provide the following:",
        fields=None,
        trigger_mode=None,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.title = title or "ModuLink Prompt"
        self.message = message or ""
        self.fields = list(fields if fields is not None else PROMPT_DEFAULT_FIELDS)
        self.trigger_mode = trigger_mode or PROMPT_DEFAULT_TRIGGER_MODE
        ports_in, ports_out = self._ports_from_fields()
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ports_in),
            outputs=dict(outputs if outputs is not None else ports_out),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def allows_input_fan_in(self) -> bool:
        return True

    def trigger_port_name(self) -> str:
        if self.trigger_mode == "activate":
            return PROMPT_ACTIVATE_PORT
        return PROMPT_MESSAGE_PORT

    def optional_input_names(self) -> set:
        return {self.trigger_port_name()}

    def _normalize_fields(self) -> list[dict]:
        cleaned = []
        seen = set()
        for raw in self.fields or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            if not name or name in seen or name in PROMPT_RESERVED_PORTS:
                continue
            ftype = str(raw.get("type", "str") or "str")
            if ftype not in PROMPT_FIELD_TYPES:
                ftype = "str"
            cleaned.append(
                {
                    "name": name,
                    "type": ftype,
                    "password": bool(raw.get("password")) and ftype == "str",
                    "label": str(raw.get("label") or name),
                    "choices": str(raw.get("choices") or ""),
                }
            )
            seen.add(name)
        return cleaned or [
            dict(field) for field in PROMPT_DEFAULT_FIELDS
        ]

    def _ports_from_fields(self):
        fields = self._normalize_fields()
        if self.trigger_mode == "activate":
            inputs = {PROMPT_ACTIVATE_PORT: "bool"}
        else:
            inputs = {PROMPT_MESSAGE_PORT: "str"}
        outputs = {field["name"]: field["type"] for field in fields}
        outputs[PROMPT_ACCEPTED_PORT] = "bool"
        return inputs, outputs

    def _sync_ports(self):
        if self.trigger_mode not in {m for m, _ in PROMPT_TRIGGER_MODE_OPTIONS}:
            self.trigger_mode = PROMPT_DEFAULT_TRIGGER_MODE
        self.fields = self._normalize_fields()
        self.inputs, self.outputs = self._ports_from_fields()

    def from_json(self, json_data):
        super().from_json(json_data)
        self.title = str(json_data.get("title", self.title) or "ModuLink Prompt")
        self.message = str(json_data.get("message", self.message) or "")
        self.fields = list(json_data.get("fields", self.fields) or PROMPT_DEFAULT_FIELDS)
        self.trigger_mode = (
            json_data.get("trigger_mode", self.trigger_mode)
            or PROMPT_DEFAULT_TRIGGER_MODE
        )
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["title"] = self.title
        data["message"] = self.message
        data["fields"] = [dict(field) for field in self.fields]
        data["trigger_mode"] = self.trigger_mode or PROMPT_DEFAULT_TRIGGER_MODE
        return data

    def node_meta(self) -> str:
        mode = self.trigger_mode or PROMPT_DEFAULT_TRIGGER_MODE
        return f"prompt · {mode} · {len(self.fields)} field(s)"

    def _cancelled_outputs(self) -> dict:
        """User closed/refused the dialog — only emit accepted=False (no None fields)."""
        return {PROMPT_ACCEPTED_PORT: False}

    def _resolve_dialog_message(self, inputs: dict) -> str | None:
        """
        Return dialog message text, or None to skip the dialog (no prompt).
        """
        if self.trigger_mode == "activate":
            if PROMPT_ACTIVATE_PORT not in inputs:
                return None
            values = flatten_input_values(inputs.get(PROMPT_ACTIVATE_PORT))
            if not values:
                return None
            if not any(coerce_condition_bool(v) for v in values):
                return None
            return self.message or ""

        # message mode (default): require at least one wired contribution
        if PROMPT_MESSAGE_PORT not in inputs:
            return None
        values = flatten_input_values(inputs.get(PROMPT_MESSAGE_PORT))
        if not values:
            return None
        parts = [
            str(v)
            for v in values
            if v is not None and str(v) != ""
        ]
        # Values were present (even if all empty) → still prompt.
        return "\n".join(parts)

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        self._sync_ports()
        if environment is None:
            raise ValueError("Prompt requires a host environment.")

        message = self._resolve_dialog_message(inputs)
        if message is None:
            # Not activated: withhold all outputs so dependents / Memory writes skip.
            return {}

        spec = {
            "title": self.title,
            "message": message,
            "fields": [dict(field) for field in self.fields],
        }
        prompt_fn = getattr(environment, "prompt_modulink_form", None)
        if not callable(prompt_fn):
            raise ValueError(
                "Prompt requires environment.prompt_modulink_form "
                "(UI host must provide a form callback)."
            )
        result = prompt_fn(spec)

        if not result or not result.get("accepted"):
            return self._cancelled_outputs()
        values = dict(result.get("values") or {})
        out = {}
        for field in self.fields:
            value = values.get(field["name"])
            # Never publish bare Nones — treat missing answers as withheld ports.
            if value is not None:
                out[field["name"]] = value
        out[PROMPT_ACCEPTED_PORT] = True
        return out


class SecretModule(Module):
    """Read a named secret from account.modulink_secrets (never stored in blueprints)."""

    module_type = "secret"

    def __init__(
        self,
        name="Secret",
        description="",
        secret_name="",
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.secret_name = "" if secret_name is None else str(secret_name)
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else {}),
            outputs=dict(outputs if outputs is not None else SECRET_OUTPUTS),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def _sync_ports(self):
        self.inputs = {}
        self.outputs = dict(SECRET_OUTPUTS)

    def from_json(self, json_data):
        super().from_json(json_data)
        self.secret_name = str(json_data.get("secret_name", self.secret_name) or "")
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["secret_name"] = self.secret_name
        # Never embed the secret value in module / blueprint JSON.
        return data

    def node_meta(self) -> str:
        label = (self.secret_name or "").strip() or "…"
        return f"secret · {label}"

    def node_summary(self, *, environment=None, run_state=None) -> str:
        name = (self.secret_name or "").strip()
        if not name:
            return "no name"
        if environment is not None:
            try:
                secrets = get_modulink_secrets(environment)
                return "set" if name in secrets and secrets.get(name) not in (None, "") else "missing"
            except Exception:
                pass
        return name

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        name = (self.secret_name or "").strip()
        if not name:
            raise ValueError("Secret module needs a secret name.")
        secrets = get_modulink_secrets(environment)
        if name not in secrets:
            return {"value": None, "exists": False}
        value = secrets.get(name)
        return {"value": "" if value is None else str(value), "exists": True}


def is_iterator_sequence(raw) -> bool:
    """True when a wire value is a collection to walk (not a scalar item)."""
    if raw is None:
        return False
    # Strings/bytes are single items, never character-iterated.
    if isinstance(raw, (str, bytes, bytearray)):
        return False
    if isinstance(raw, (list, tuple, set, dict)):
        return True
    type_name = type(raw).__name__
    if type_name in ("Series", "DataFrame"):
        return True
    if hasattr(raw, "__iter__"):
        return True
    return False


def normalize_iterator_items(raw) -> list:
    """Normalize common ModuLink shapes into a flat list for IteratorModule."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, tuple):
        return list(raw)
    if isinstance(raw, set):
        return list(raw)
    if isinstance(raw, dict):
        return list(raw.keys())
    type_name = type(raw).__name__
    if type_name == "Series" and hasattr(raw, "tolist"):
        try:
            return list(raw.tolist())
        except Exception:
            return list(raw)
    if type_name == "DataFrame" and hasattr(raw, "to_dict"):
        try:
            return raw.to_dict(orient="records")
        except Exception:
            pass
    if hasattr(raw, "__iter__") and not isinstance(raw, (str, bytes, bytearray)):
        try:
            return list(raw)
        except Exception:
            pass
    return [raw]


class IteratorModule(Module):
    """
    Walk an iterable and re-run every module transitively downstream once per item.

    Ports: items → item / index / count. The Blueprint runner owns the loop;
    iter_items() only builds the pass list.

    Fan-in rules:
      - One wire (list or scalar): iterate that sequence / single item.
      - Multiple scalar wires (str/number/bool): one pass per wire value.
      - Multiple sequence wires (lists, etc.): zip lockstep; each pass item
        is a tuple (truncated to the shortest list).
    """

    module_type = "iterator"

    def __init__(
        self,
        name="Iterator",
        description="",
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else ITERATOR_DEFAULT_INPUTS),
            outputs=dict(outputs if outputs is not None else ITERATOR_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def _sync_ports(self):
        self.inputs = dict(ITERATOR_DEFAULT_INPUTS)
        self.outputs = dict(ITERATOR_DEFAULT_OUTPUTS)

    def from_json(self, json_data):
        super().from_json(json_data)
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        return super().to_json()

    def node_meta(self) -> str:
        return "iterator · zip"

    def allows_input_fan_in(self) -> bool:
        # Multiple wires into items: scalars collect; sequences zip.
        return True

    def optional_input_names(self) -> set:
        # Unwired items → empty iterable (count=0, body skipped).
        return {ITERATOR_ITEMS_PORT}

    def iter_items(self, inputs: dict | None = None) -> list:
        """Return the pass list from resolved inputs."""
        inputs = dict(inputs or {})
        if ITERATOR_ITEMS_PORT not in inputs:
            return []
        raw = inputs.get(ITERATOR_ITEMS_PORT)

        # Fan-in always delivers a list of per-wire contributions (even for one wire).
        if self.allows_input_fan_in() and isinstance(raw, list):
            contributions = [value for value in raw if value is not None]
        elif raw is None:
            contributions = []
        else:
            contributions = [raw]

        if not contributions:
            return []

        sequences = [normalize_iterator_items(value) for value in contributions]
        if len(sequences) == 1:
            # One wire: walk the list (or the single scalar item).
            items = sequences[0]
        elif all(not is_iterator_sequence(value) for value in contributions):
            # Multiple scalars (str/number/bool/…): one pass per wire.
            items = [seq[0] for seq in sequences if seq]
        else:
            # Multiple sequences: lockstep zip; truncate to the shortest.
            items = [tuple(row) for row in zip(*sequences)]

        if len(items) > ITERATOR_MAX_ITEMS:
            raise ValueError(
                f"Iterator refuses more than {ITERATOR_MAX_ITEMS} items "
                f"(got {len(items)})."
            )
        return items

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        """
        Single-shot fallback: emit the first item (or count-only when empty).

        The Blueprint runner prefers iter_items() and drives the loop itself.
        """
        items = self.iter_items(inputs)
        count = len(items)
        if not items:
            return {ITERATOR_COUNT_PORT: 0}
        return {
            ITERATOR_ITEM_PORT: items[0],
            ITERATOR_INDEX_PORT: 0,
            ITERATOR_COUNT_PORT: count,
        }



def _normalize_strategy_param_defs(raw) -> list:
    """Normalize param defs to [{name, type?, default}, ...]."""
    defs = []
    if raw is None:
        return defs
    if isinstance(raw, dict):
        # {name: default} shorthand
        for name, default in raw.items():
            key = str(name).strip()
            if not key:
                continue
            defs.append({"name": key, "type": "any", "default": default})
        return defs
    if not isinstance(raw, (list, tuple)):
        return defs
    for entry in raw:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            item = {
                "name": name,
                "type": str(entry.get("type") or "any"),
                "default": entry.get("default", entry.get("value", entry.get("start", None))),
            }
            defs.append(item)
        elif isinstance(entry, (list, tuple)) and entry:
            name = str(entry[0]).strip()
            if not name:
                continue
            default = entry[1] if len(entry) > 1 else None
            defs.append({"name": name, "type": "any", "default": default})
    return defs


def _param_defs_to_defaults(param_defs: list) -> dict:
    out = {}
    for entry in param_defs or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        out[name] = entry.get("default")
    return out


def _coerce_ops_list(raw) -> list:
    if raw is None:
        return []
    values = flatten_input_values(raw)
    ops = []
    for value in values:
        if isinstance(value, list):
            ops.extend(v for v in value if isinstance(v, dict))
        elif isinstance(value, dict):
            # Single op or {ops: [...]} wrapper
            if "op" in value:
                ops.append(value)
            elif isinstance(value.get("ops"), list):
                ops.extend(v for v in value["ops"] if isinstance(v, dict))
    return ops


class StrategyModule(Module):
    """
    Private strategies + param-defaults bundle for ModuLink.

    Does not auto-write account.strategies; hosts may import/restore explicitly.
    AI edits arrive via structured ops; hosts may provide their own editors.
    The strategies output embeds __primary__ (meta); account I/O strips meta keys.
    Primary is a module setting (editor / JSON / set_primary op), not an output port.
    """

    module_type = "strategy"

    def __init__(
        self,
        name="Strategy Bundle",
        description="",
        strategies=None,
        param_defs=None,
        primary="",
        params_mode=STRATEGY_DEFAULT_PARAMS_MODE,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.strategies = dict(strategies or {})
        self.param_defs = _normalize_strategy_param_defs(param_defs)
        self.primary = str(primary or "")
        self.params_mode = params_mode or STRATEGY_DEFAULT_PARAMS_MODE
        if self.params_mode not in dict(STRATEGY_PARAMS_MODE_OPTIONS):
            self.params_mode = STRATEGY_DEFAULT_PARAMS_MODE
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else STRATEGY_DEFAULT_INPUTS),
            outputs=dict(outputs if outputs is not None else STRATEGY_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()
            self._normalize_primary()

    def _sync_ports(self):
        self.inputs = dict(STRATEGY_DEFAULT_INPUTS)
        self.outputs = dict(STRATEGY_DEFAULT_OUTPUTS)

    def _normalize_primary(self):
        # Never treat meta keys as real scripts.
        self.strategies = strategy_scripts_only(self.strategies)
        primary = str(self.primary or "").strip()
        if primary and primary not in self.strategies:
            primary = ""
        if not primary and self.strategies:
            primary = next(iter(self.strategies.keys()))
        self.primary = primary

    def from_json(self, json_data):
        super().from_json(json_data)
        raw_strats = json_data.get("strategies", self.strategies)
        embedded_primary = ""
        self.strategies = {}
        if isinstance(raw_strats, dict):
            embedded_primary = strategy_primary_from_payload(raw_strats)
            self.strategies = strategy_scripts_only(raw_strats)
        self.param_defs = _normalize_strategy_param_defs(
            json_data.get("param_defs", self.param_defs)
        )
        self.primary = str(
            json_data.get("primary", embedded_primary or self.primary) or ""
        )
        self.params_mode = (
            json_data.get("params_mode", self.params_mode) or STRATEGY_DEFAULT_PARAMS_MODE
        )
        if self.params_mode not in dict(STRATEGY_PARAMS_MODE_OPTIONS):
            self.params_mode = STRATEGY_DEFAULT_PARAMS_MODE
        self._sync_ports()
        self._normalize_primary()

    def to_json(self):
        self._sync_ports()
        self._normalize_primary()
        data = super().to_json()
        # Persist real scripts only — primary is its own field, never __primary__ in JSON.
        data["strategies"] = strategy_scripts_only(self.strategies)
        data["param_defs"] = [dict(p) for p in self.param_defs]
        data["primary"] = self.primary
        data["params_mode"] = self.params_mode
        return data

    def optional_input_names(self) -> set:
        return {STRATEGY_PARAMS_PORT, STRATEGY_OPS_PORT}

    def allows_input_fan_in(self) -> bool:
        return True

    def node_meta(self) -> str:
        return f"strategy · {len(self.strategies)} script(s)"

    def node_summary(self, *, environment=None, run_state=None) -> str:
        if self.primary:
            return str(self.primary)
        if self.strategies:
            return next(iter(self.strategies.keys()))
        return "(empty)"

    @staticmethod
    def ops_reference_text() -> str:
        """Full human-readable ops catalog (for UI / AI prompts)."""
        return format_strategy_ops_reference()

    def _log_op(self, message: str):
        # Collected during run into module console via Blueprint state.log; store temporarily.
        bucket = getattr(self, "_op_log", None)
        if bucket is None:
            self._op_log = []
            bucket = self._op_log
        bucket.append(str(message))

    def apply_ops(self, ops: list) -> None:
        """Apply structured edit ops in order; persist successful mutations."""
        for raw in ops or []:
            if not isinstance(raw, dict):
                continue
            op = str(raw.get("op") or "").strip().lower()
            if not op:
                continue
            try:
                if op == "set":
                    name = str(raw.get("name") or "").strip()
                    if not name:
                        self._log_op("set skipped: missing name")
                        continue
                    if is_strategy_meta_key(name):
                        self._log_op(f"set skipped: reserved meta name '{name}'")
                        continue
                    code = raw.get("code")
                    self.strategies[name] = "" if code is None else str(code)
                    self._log_op(f"set '{name}' ({len(self.strategies[name])} chars)")
                elif op == "delete":
                    name = str(raw.get("name") or "").strip()
                    if is_strategy_meta_key(name):
                        self._log_op(f"delete skipped: reserved meta name '{name}'")
                        continue
                    if name in self.strategies:
                        del self.strategies[name]
                        self._log_op(f"deleted '{name}'")
                    else:
                        self._log_op(f"delete skipped: '{name}' not found")
                elif op == "rename":
                    name = str(raw.get("name") or "").strip()
                    new_name = str(raw.get("new_name") or "").strip()
                    if not name or not new_name:
                        self._log_op("rename skipped: need name and new_name")
                        continue
                    if is_strategy_meta_key(name) or is_strategy_meta_key(new_name):
                        self._log_op("rename skipped: reserved meta name")
                        continue
                    if name not in self.strategies:
                        self._log_op(f"rename skipped: '{name}' not found")
                        continue
                    if new_name != name and new_name in self.strategies:
                        self._log_op(f"rename skipped: '{new_name}' already exists")
                        continue
                    self.strategies[new_name] = self.strategies.pop(name)
                    if self.primary == name:
                        self.primary = new_name
                    self._log_op(f"renamed '{name}' → '{new_name}'")
                elif op == "replace":
                    name = str(raw.get("name") or "").strip()
                    old = raw.get("old")
                    new = raw.get("new")
                    replace_all = bool(raw.get("replace_all", False))
                    if is_strategy_meta_key(name):
                        self._log_op(f"replace skipped: reserved meta name '{name}'")
                        continue
                    if name not in self.strategies:
                        self._log_op(f"replace skipped: '{name}' not found")
                        continue
                    if old is None:
                        self._log_op(f"replace skipped on '{name}': missing old")
                        continue
                    old_s = str(old)
                    new_s = "" if new is None else str(new)
                    code = self.strategies[name]
                    count = code.count(old_s)
                    if count == 0:
                        self._log_op(f"replace skipped on '{name}': old not found")
                        continue
                    if not replace_all and count != 1:
                        self._log_op(
                            f"replace skipped on '{name}': expected 1 match, found {count}"
                        )
                        continue
                    if replace_all:
                        self.strategies[name] = code.replace(old_s, new_s)
                        self._log_op(f"replace_all on '{name}' ({count} matches)")
                    else:
                        self.strategies[name] = code.replace(old_s, new_s, 1)
                        self._log_op(f"replace on '{name}'")
                elif op == "set_params":
                    params = raw.get("params", raw.get("param_defs"))
                    if isinstance(params, dict) and "op" not in params:
                        # merge name→default into defs
                        defaults = dict(params)
                        by_name = {d["name"]: dict(d) for d in self.param_defs}
                        for key, value in defaults.items():
                            name = str(key).strip()
                            if not name:
                                continue
                            if name in by_name:
                                by_name[name]["default"] = value
                            else:
                                by_name[name] = {"name": name, "type": "any", "default": value}
                        self.param_defs = list(by_name.values())
                        self._log_op(f"set_params merged {len(defaults)} value(s)")
                    else:
                        self.param_defs = _normalize_strategy_param_defs(params)
                        self._log_op(f"set_params replaced defs ({len(self.param_defs)})")
                elif op == "set_primary":
                    name = str(raw.get("name") or "").strip()
                    if is_strategy_meta_key(name):
                        self._log_op(f"set_primary skipped: reserved meta name '{name}'")
                        continue
                    if name and name not in self.strategies:
                        self._log_op(f"set_primary skipped: '{name}' not found")
                        continue
                    self.primary = name
                    self._log_op(f"set_primary '{name}'")
                else:
                    self._log_op(f"unknown op '{op}' skipped")
            except Exception as exc:
                self._log_op(f"op '{op}' failed: {exc}")
        self._normalize_primary()

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        self._op_log = []
        inputs = dict(inputs or {})
        ops = _coerce_ops_list(inputs.get(STRATEGY_OPS_PORT))
        if ops:
            self.apply_ops(ops)

        default_params = _param_defs_to_defaults(self.param_defs)

        # Inbound params overrides
        override_raw = inputs.get(STRATEGY_PARAMS_PORT)
        overrides = {}
        if override_raw is not None:
            values = flatten_input_values(override_raw)
            for value in values:
                if isinstance(value, dict):
                    overrides.update(value)
        if self.params_mode == "replace" and overrides:
            effective = dict(overrides)
        else:
            effective = dict(default_params)
            effective.update(overrides)

        self._normalize_primary()
        strategies_out = with_strategy_primary(self.strategies, self.primary)
        scripts_only = strategy_scripts_only(strategies_out)
        outline = python_outline.build_strategies_outline(scripts_only)
        names = sorted(scripts_only.keys())

        # Surface op log for Blueprint console if present
        if self._op_log:
            # Prefer environment console hook; Blueprint logs Inputs/Outputs itself.
            # Stash for ModuleEditor / callers; Blueprint.run will not auto-read this,
            # so also print via a soft attribute consumed nowhere unless we log in run_states.
            pass

        outputs = {
            "strategies": strategies_out,
            "names": names,
            "default_params": default_params,
            "params": effective,
            "outline": outline,
        }
        # Attach op log text for the runner to optionally surface — use description field? 
        # Store on module for console: Blueprint _execute_module logs Outputs only.
        # We'll append op messages by monkeypatching via environment status if needed.
        self._last_op_log = list(self._op_log)
        return outputs


class SimulationModule(Module):
    """Black-box simulation job: start via environment, wait until done/stop.

    Does not step bars through the ModuLink graph. Two completion modes:

    - wait (default): block until Finished/Stopped; hide finished port;
      downstream runs once with final outputs.
    - poll: same block, but every N seconds publish all outputs live
      (UI / state.outputs only — graph still advances once at the end);
      finished port is shown (False while running, final value on return).
    """

    module_type = "simulation"

    def __init__(
        self,
        name="Simulation",
        description="",
        run_target=None,
        completion_mode=None,
        poll_interval_sec=None,
        symbol="",
        timeframe=None,
        step_size=None,
        starting_funds=None,
        use_ny_timezone=False,
        emit_full_result=False,
        default_start_time="",
        default_stop_time="",
        expose_symbol=False,
        expose_timeframe=False,
        expose_step_size=False,
        expose_funds=False,
        inputs=None,
        outputs=None,
        json_data=None,
    ):
        self.run_target = run_target or SIMULATION_DEFAULT_RUN_TARGET
        if self.run_target not in dict(SIMULATION_RUN_TARGET_OPTIONS):
            self.run_target = SIMULATION_DEFAULT_RUN_TARGET
        self.completion_mode = (
            completion_mode or SIMULATION_DEFAULT_COMPLETION_MODE
        )
        if self.completion_mode not in dict(SIMULATION_COMPLETION_MODE_OPTIONS):
            self.completion_mode = SIMULATION_DEFAULT_COMPLETION_MODE
        try:
            self.poll_interval_sec = float(
                SIMULATION_DEFAULT_POLL_INTERVAL_SEC
                if poll_interval_sec is None
                else poll_interval_sec
            )
        except (TypeError, ValueError):
            self.poll_interval_sec = float(SIMULATION_DEFAULT_POLL_INTERVAL_SEC)
        self.poll_interval_sec = max(0.05, self.poll_interval_sec)
        self.symbol = str(symbol or "")
        self.timeframe = str(timeframe or SIMULATION_DEFAULT_TIMEFRAME)
        try:
            self.step_size = float(
                SIMULATION_DEFAULT_STEP_SIZE if step_size is None else step_size
            )
        except (TypeError, ValueError):
            self.step_size = float(SIMULATION_DEFAULT_STEP_SIZE)
        self.step_size = max(0.001, self.step_size)
        try:
            self.starting_funds = float(
                SIMULATION_DEFAULT_FUNDS if starting_funds is None else starting_funds
            )
        except (TypeError, ValueError):
            self.starting_funds = float(SIMULATION_DEFAULT_FUNDS)
        self.use_ny_timezone = bool(use_ny_timezone)
        self.emit_full_result = bool(emit_full_result)
        self.default_start_time = "" if default_start_time is None else str(default_start_time)
        self.default_stop_time = "" if default_stop_time is None else str(default_stop_time)
        self.expose_symbol = bool(expose_symbol)
        self.expose_timeframe = bool(expose_timeframe)
        self.expose_step_size = bool(expose_step_size)
        self.expose_funds = bool(expose_funds)
        super().__init__(
            name=name,
            description=description,
            inputs=dict(inputs if inputs is not None else SIMULATION_CORE_INPUTS),
            outputs=dict(outputs if outputs is not None else SIMULATION_DEFAULT_OUTPUTS),
            json_data=json_data,
        )
        if json_data is None:
            self._sync_ports()

    def _is_poll_mode(self) -> bool:
        return self.completion_mode == "poll"

    def _sync_ports(self):
        inputs = dict(SIMULATION_CORE_INPUTS)
        if self.expose_symbol:
            inputs["symbol"] = SIMULATION_EXPOSABLE_INPUTS["symbol"]
        if self.expose_timeframe:
            inputs["timeframe"] = SIMULATION_EXPOSABLE_INPUTS["timeframe"]
        if self.expose_step_size:
            inputs["step_size"] = SIMULATION_EXPOSABLE_INPUTS["step_size"]
        if self.expose_funds:
            inputs["funds"] = SIMULATION_EXPOSABLE_INPUTS["funds"]
        self.inputs = inputs
        outputs = {
            "status": SIMULATION_DEFAULT_OUTPUTS["status"],
            "sim_id": SIMULATION_DEFAULT_OUTPUTS["sim_id"],
            "performance": SIMULATION_DEFAULT_OUTPUTS["performance"],
        }
        if self.emit_full_result:
            outputs.update(SIMULATION_FULL_RESULT_OUTPUT)
        outputs["params"] = SIMULATION_DEFAULT_OUTPUTS["params"]
        # finished only in poll mode (live False → final value on completion).
        if self._is_poll_mode():
            outputs["finished"] = SIMULATION_DEFAULT_OUTPUTS["finished"]
        self.outputs = outputs

    @staticmethod
    def _legacy_expose_flag(json_data: dict, flag: str, port: str) -> bool:
        """New modules default off; older saves that listed the port stay exposed."""
        if flag in json_data:
            return bool(json_data.get(flag))
        saved_inputs = json_data.get("inputs")
        if isinstance(saved_inputs, dict) and port in saved_inputs:
            return True
        return False

    def optional_input_names(self) -> set:
        return set(self.inputs.keys())

    def allows_input_fan_in(self) -> bool:
        return True

    def from_json(self, json_data):
        super().from_json(json_data)
        self.run_target = (
            json_data.get("run_target", self.run_target) or SIMULATION_DEFAULT_RUN_TARGET
        )
        if self.run_target not in dict(SIMULATION_RUN_TARGET_OPTIONS):
            self.run_target = SIMULATION_DEFAULT_RUN_TARGET
        self.completion_mode = (
            json_data.get("completion_mode", self.completion_mode)
            or SIMULATION_DEFAULT_COMPLETION_MODE
        )
        if self.completion_mode not in dict(SIMULATION_COMPLETION_MODE_OPTIONS):
            self.completion_mode = SIMULATION_DEFAULT_COMPLETION_MODE
        try:
            self.poll_interval_sec = max(
                0.05,
                float(
                    json_data.get("poll_interval_sec", self.poll_interval_sec)
                ),
            )
        except (TypeError, ValueError):
            self.poll_interval_sec = float(SIMULATION_DEFAULT_POLL_INTERVAL_SEC)
        self.symbol = str(json_data.get("symbol", self.symbol) or "")
        self.timeframe = str(
            json_data.get("timeframe", self.timeframe) or SIMULATION_DEFAULT_TIMEFRAME
        )
        try:
            self.step_size = max(
                0.001, float(json_data.get("step_size", self.step_size))
            )
        except (TypeError, ValueError):
            self.step_size = float(SIMULATION_DEFAULT_STEP_SIZE)
        try:
            self.starting_funds = float(
                json_data.get("starting_funds", self.starting_funds)
            )
        except (TypeError, ValueError):
            self.starting_funds = float(SIMULATION_DEFAULT_FUNDS)
        self.use_ny_timezone = bool(
            json_data.get("use_ny_timezone", self.use_ny_timezone)
        )
        self.emit_full_result = bool(
            json_data.get("emit_full_result", self.emit_full_result)
        )
        self.default_start_time = str(
            json_data.get("default_start_time", self.default_start_time) or ""
        )
        self.default_stop_time = str(
            json_data.get("default_stop_time", self.default_stop_time) or ""
        )
        self.expose_symbol = self._legacy_expose_flag(
            json_data, "expose_symbol", "symbol"
        )
        self.expose_timeframe = self._legacy_expose_flag(
            json_data, "expose_timeframe", "timeframe"
        )
        self.expose_step_size = self._legacy_expose_flag(
            json_data, "expose_step_size", "step_size"
        )
        self.expose_funds = self._legacy_expose_flag(
            json_data, "expose_funds", "funds"
        )
        self._sync_ports()

    def to_json(self):
        self._sync_ports()
        data = super().to_json()
        data["run_target"] = self.run_target or SIMULATION_DEFAULT_RUN_TARGET
        data["completion_mode"] = (
            self.completion_mode or SIMULATION_DEFAULT_COMPLETION_MODE
        )
        data["poll_interval_sec"] = float(self.poll_interval_sec)
        data["symbol"] = self.symbol
        data["timeframe"] = self.timeframe
        data["step_size"] = float(self.step_size)
        data["starting_funds"] = float(self.starting_funds)
        data["use_ny_timezone"] = bool(self.use_ny_timezone)
        data["emit_full_result"] = bool(self.emit_full_result)
        data["default_start_time"] = self.default_start_time
        data["default_stop_time"] = self.default_stop_time
        data["expose_symbol"] = bool(self.expose_symbol)
        data["expose_timeframe"] = bool(self.expose_timeframe)
        data["expose_step_size"] = bool(self.expose_step_size)
        data["expose_funds"] = bool(self.expose_funds)
        return data

    def node_meta(self) -> str:
        target = self.run_target or SIMULATION_DEFAULT_RUN_TARGET
        tf = self.timeframe or SIMULATION_DEFAULT_TIMEFRAME
        mode = "poll" if self._is_poll_mode() else "wait"
        return f"sim · {target} · {mode} · {tf} · step {self.step_size:g}s"

    def node_summary(self, *, environment=None, run_state=None) -> str:
        if run_state is not None and getattr(run_state, "outputs", None):
            status = run_state.outputs.get("status")
            perf = run_state.outputs.get("performance")
            if isinstance(perf, dict):
                pct = perf.get("percent_complete")
                pnl = perf.get("pnl")
                try:
                    if status:
                        return f"{status} {float(pct):.0f}% · pnl {float(pnl):g}"
                except (TypeError, ValueError):
                    pass
            if status:
                return str(status)
        return self.symbol or self.timeframe or "simulation"

    @staticmethod
    def _performance_from_snapshot(snap: dict) -> dict:
        """Compact performance / run summary for the single performance output."""
        def _num(key, default=0.0, cast=float):
            try:
                return cast(snap.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        perf = {
            "sim_id": str(snap.get("sim_id") or ""),
            "sim_name": snap.get("sim_name") or "",
            "status": snap.get("status") or "",
            "percent_complete": _num("percent_complete", 0.0, float),
            "stopped": bool(snap.get("stopped", False)),
            "paused": bool(snap.get("paused", False)),
            "pnl": _num("pnl", 0.0, float),
            "funds": _num("funds", 0.0, float),
            "start_funds": _num("start_funds", 0.0, float),
            "fees_paid": _num("fees_paid", 0.0, float),
            "num_trades": _num("num_trades", 0, int),
            "num_wins": _num("num_wins", 0, int),
            "num_losses": _num("num_losses", 0, int),
            "selected_strategy": snap.get("selected_strategy") or "",
            "current_symbol": snap.get("current_symbol") or "",
            "starting_timeframe": snap.get("starting_timeframe") or "",
        }
        for key in (
            "start_time",
            "end_time",
            "current_time",
            "winlose_ratio",
            "profitloss_ratio",
            "simulation_runtime",
        ):
            if snap.get(key) is not None:
                perf[key] = snap.get(key)
        return perf

    @staticmethod
    def _outputs_from_snapshot(
        snap: dict, *, emit_full: bool, params=None, include_finished: bool = True
    ) -> dict:
        status = str(snap.get("status") or "")
        out = {
            "status": status,
            "sim_id": str(snap.get("sim_id") or ""),
            "performance": SimulationModule._performance_from_snapshot(snap),
        }
        if emit_full:
            out["full_result"] = dict(snap)
        out["params"] = dict(params) if isinstance(params, dict) else {}
        if include_finished:
            out["finished"] = status == "Finished"
        return out

    @staticmethod
    def _last_value(inputs: dict, *names):
        for name in names:
            if name not in inputs:
                continue
            values = [
                v
                for v in flatten_input_values(inputs.get(name))
                if v is not None and v != ""
            ]
            if values:
                return values[-1]
        return None

    @staticmethod
    def _resolve_strategy(raw_strategy, strategy_name=None, primary=None):
        # Explicit ports still win if present (legacy blueprints); else __primary__.
        name = str(strategy_name or primary or "").strip()
        code = None
        strategies = None
        if isinstance(raw_strategy, dict):
            if not name:
                name = strategy_primary_from_payload(raw_strategy)
            strategies = strategy_scripts_only(raw_strategy)
            if name and name in strategies:
                code = strategies[name]
            elif strategies:
                name = next(iter(strategies.keys()))
                code = strategies[name]
            else:
                name = name or ""
                code = None
        elif raw_strategy is not None:
            code = str(raw_strategy)
            if not name:
                name = "ModuLinkStrategy"
        return name, code, strategies

    @staticmethod
    def _resolve_data_package(raw):
        """Normalize DataSource/package input into strategy_process market_data shape.

        Expected (from saved_data):
            {"data": {symbol: {tf: frame}}, "economic_events": {...}, "stream_prices": {...}}
        Also accepts a bare bars tree {symbol: {tf: frame}} for convenience.
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None
        if "data" in raw and isinstance(raw.get("data"), dict):
            inner = raw["data"]
            # Already a package (inner values are timeframe→frame dicts, not OHLC columns).
            # Bare bars tree also uses "data" only if someone named a symbol "data" — rare.
            # Package if it also has econ/stream keys OR inner looks like symbol→tf map.
            if "economic_events" in raw or "stream_prices" in raw:
                return {
                    "data": inner,
                    "economic_events": (
                        raw.get("economic_events")
                        if isinstance(raw.get("economic_events"), dict)
                        else {}
                    ),
                    "stream_prices": (
                        raw.get("stream_prices")
                        if isinstance(raw.get("stream_prices"), dict)
                        else {}
                    ),
                }
            # {"data": {symbol: {tf: df}}} without econ/stream
            sample = next(iter(inner.values()), None) if inner else None
            if isinstance(sample, dict):
                return {
                    "data": inner,
                    "economic_events": {},
                    "stream_prices": {},
                }
        # Bare {symbol: {tf: frame}}
        sample = next(iter(raw.values()), None) if raw else None
        if isinstance(sample, dict):
            return {"data": raw, "economic_events": {}, "stream_prices": {}}
        return None

    def _build_job(self, inputs: dict) -> dict:
        # Prefer `data` (DataSource package). Legacy `market` still accepted if wired.
        package = self._resolve_data_package(
            self._last_value(inputs, "data", "market")
        )
        strategy_name, strategy_code, strategies = self._resolve_strategy(
            self._last_value(inputs, "strategy", "strategies"),
            # Legacy optional ports (not in default inputs anymore).
            self._last_value(inputs, "strategy_name"),
            self._last_value(inputs, "primary"),
        )
        params = self._last_value(inputs, "params")
        if params is not None and not isinstance(params, dict):
            params = {}
        symbol = self._last_value(inputs, "symbol")
        if symbol is None:
            symbol = self.symbol
        timeframe = self._last_value(inputs, "timeframe")
        if timeframe is None:
            timeframe = self.timeframe
        step_size = self._last_value(inputs, "step_size")
        if step_size is None:
            step_size = self.step_size
        funds = self._last_value(inputs, "funds")
        if funds is None:
            funds = self.starting_funds
        start_time = self._last_value(inputs, "start_time")
        if start_time is None or start_time == "":
            start_time = self.default_start_time or None
        stop_time = self._last_value(inputs, "stop_time")
        if stop_time is None or stop_time == "":
            stop_time = self.default_stop_time or None

        if package is None:
            raise ValueError(
                "Simulation requires a data package on 'data' "
                "(DataSource saved_data → {data, economic_events, stream_prices})."
            )
        if not strategy_code and not strategy_name:
            raise ValueError(
                "Simulation requires strategy code "
                "(wire StrategyModule.strategies; primary rides as __primary__)."
            )

        return {
            "run_target": self.run_target or SIMULATION_DEFAULT_RUN_TARGET,
            "data": package,
            "strategy_name": str(strategy_name or "ModuLinkStrategy"),
            "strategy_code": strategy_code,
            "strategies": strategies,
            "params": dict(params or {}),
            "symbol": str(symbol or "").strip(),
            "timeframe": str(timeframe or SIMULATION_DEFAULT_TIMEFRAME),
            "step_size": float(step_size),
            "starting_funds": float(funds),
            "start_time": start_time,
            "stop_time": stop_time,
            "use_ny_timezone": bool(self.use_ny_timezone),
        }

    def run(self, inputs: dict | None = None, environment=None) -> dict:
        inputs = dict(inputs or {})
        if environment is None:
            raise ValueError("Simulation requires a host environment.")
        start_fn = getattr(environment, "start_modulink_simulation", None)
        get_fn = getattr(environment, "get_modulink_simulation", None)
        stop_fn = getattr(environment, "stop_modulink_simulation", None)
        if not callable(start_fn) or not callable(get_fn):
            raise ValueError(
                "Environment must provide start_modulink_simulation / "
                "get_modulink_simulation."
            )

        job = self._build_job(inputs)
        used_params = dict(job.get("params") or {})
        sim_id = start_fn(job)
        if not sim_id:
            raise ValueError("start_modulink_simulation returned no sim_id.")

        poll_mode = self._is_poll_mode()
        publish_interval = max(0.05, float(self.poll_interval_sec))
        last_publish = 0.0
        last_pct_logged = -1.0
        while True:
            snap = get_fn(sim_id) or {}
            status = str(snap.get("status") or "")
            stopped = bool(snap.get("stopped", False))
            try:
                pct = float(snap.get("percent_complete") or 0.0)
            except (TypeError, ValueError):
                pct = 0.0

            want_stop = modulink_should_stop(environment)
            stop_input = self._last_value(inputs, "stop")
            if stop_input is not None and coerce_condition_bool(stop_input):
                want_stop = True
            if want_stop and callable(stop_fn) and not stopped:
                stop_fn(sim_id)
                snap = get_fn(sim_id) or snap
                status = str(snap.get("status") or status)
                stopped = bool(snap.get("stopped", False))

            if hasattr(environment, "status_message") and abs(pct - last_pct_logged) >= 5.0:
                environment.status_message(
                    f"Simulation {sim_id[:8]}… {status} {pct:.0f}%"
                )
                last_pct_logged = pct

            terminal = stopped or status in SIMULATION_TERMINAL_STATUSES
            if poll_mode and not terminal:
                now = time.monotonic()
                if (now - last_publish) >= publish_interval:
                    live = self._outputs_from_snapshot(
                        snap,
                        emit_full=bool(self.emit_full_result),
                        params=used_params,
                        include_finished=True,
                    )
                    live["finished"] = False
                    modulink_publish_progress(environment, live)
                    last_publish = now

            if terminal:
                if status == "Error":
                    errors = snap.get("errors") or {}
                    detail = ""
                    if isinstance(errors, dict) and errors:
                        detail = str(next(iter(errors.values())))
                    raise ValueError(detail or "Simulation ended with Error status.")
                return self._outputs_from_snapshot(
                    snap,
                    emit_full=bool(self.emit_full_result),
                    params=used_params,
                    include_finished=poll_mode,
                )

            time.sleep(SIMULATION_POLL_INTERVAL_SEC)


MODULE_TYPE_MAP = {
    "exec": ExecModule,
    "data_source": DataSourceModule,
    "ai": AIModule,
    "message": MessageModule,
    "constant": ConstantModule,
    "condition": ConditionModule,
    "filter": FilterModule,
    "math": MathModule,
    "string": StringModule,
    "compare": CompareModule,
    "wait": WaitModule,
    "prompt": PromptModule,
    "secret": SecretModule,
    "throttle": ThrottleModule,
    "sim_batch": SimBatchModule,
    "simulation": SimulationModule,
    "memory": MemoryModule,
    "drawing": DrawingModule,
    "audio": AudioModule,
    "iterator": IteratorModule,
    "strategy": StrategyModule,
}


def module_from_json(json_data: dict) -> Module:
    module_type = json_data.get("module_type", "exec")
    cls = MODULE_TYPE_MAP.get(module_type)
    if cls is None:
        raise ValueError(f"Unknown module type: {module_type}")
    return cls(json_data=json_data)



def run_exec_module(module: ExecModule, inputs: dict | None = None, environment=None) -> dict:
    """Run an exec module and return declared outputs."""
    if not isinstance(module, ExecModule):
        raise ValueError(f"Unsupported module type: {getattr(module, 'module_type', type(module))}")
    return module.run(inputs, environment=environment)


def parse_prompt_choices(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).replace(",", "\n")
    return [part.strip() for part in text.splitlines() if part.strip()]


def coerce_prompt_field_value(raw, field: dict):
    ftype = (field or {}).get("type") or "str"
    if ftype == "bool":
        return coerce_condition_bool(raw)
    if ftype == "int":
        if raw is None or str(raw).strip() == "":
            raise ValueError(f"Field '{field.get('name')}' requires an integer.")
        return int(float(raw))
    if ftype == "float":
        if raw is None or str(raw).strip() == "":
            raise ValueError(f"Field '{field.get('name')}' requires a number.")
        return float(raw)
    if ftype == "choice":
        text = "" if raw is None else str(raw)
        choices = parse_prompt_choices(field.get("choices"))
        if choices and text not in choices:
            raise ValueError(
                f"Field '{field.get('name')}' must be one of: {', '.join(choices)}"
            )
        return text
    return "" if raw is None else str(raw)

