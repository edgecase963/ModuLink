"""Portable ModuLink blueprint runner: Connection, Group, Blueprint.

Qt-free — depends only on modulink.core (+ stdlib).
"""

from __future__ import annotations

import traceback
from uuid import uuid4

from .core import (
    ConditionModule,
    EXEC_DEFAULT_CONSOLE_OUTPUT,
    ExecModule,
    ExecModuleFailedWithConsole,
    ITERATOR_COUNT_PORT,
    ITERATOR_INDEX_PORT,
    ITERATOR_ITEM_PORT,
    IteratorModule,
    MemoryModule,
    Module,
    ModuleRunState,
    STATUS_FAILED,
    STATUS_IDLE,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    STATUS_WAITING,
    StrategyModule,
    flatten_input_values,
    format_memory_summary,
    format_port_section,
    format_value,
    get_modulink_memory_root,
    module_from_json,
    normalize_iterator_items,
    modulink_should_stop,
)


class Connection:
    """Wire from one module output port to another module input port."""

    def __init__(
        self,
        source_module=None,
        source_port=None,
        target_module=None,
        target_port=None,
        json_data=None,
    ):
        self.source_module = source_module
        self.source_port = source_port
        self.target_module = target_module
        self.target_port = target_port
        self.connection_id = uuid4()

        if json_data is not None:
            self.from_json(json_data)

    def from_json(self, json_data):
        self.source_module = json_data.get("source_module", self.source_module)
        self.source_port = json_data.get("source_port", self.source_port)
        self.target_module = json_data.get("target_module", self.target_module)
        self.target_port = json_data.get("target_port", self.target_port)
        self.connection_id = json_data.get("connection_id", self.connection_id)

    def to_json(self):
        return {
            "source_module": str(self.source_module),
            "source_port": self.source_port,
            "target_module": str(self.target_module),
            "target_port": self.target_port,
            "connection_id": str(self.connection_id),
        }

    def randomize_id(self):
        self.connection_id = uuid4()


# Soft accents for display-only group frames (cycle on create).
GROUP_COLOR_PALETTE = (
    "#5C6BC0",
    "#26A69A",
    "#EF5350",
    "#AB47BC",
    "#42A5F5",
    "#FFA726",
    "#66BB6A",
    "#78909C",
)


class Group:
    """Display-only titled frame grouping module instances (layout annotation)."""

    def __init__(
        self,
        group_id=None,
        title="Group",
        color=None,
        member_ids=None,
        json_data=None,
    ):
        self.group_id = str(group_id) if group_id is not None else str(uuid4())
        self.title = title or "Group"
        self.color = color or GROUP_COLOR_PALETTE[0]
        self.member_ids = [str(mid) for mid in (member_ids or [])]
        if json_data is not None:
            self.from_json(json_data)

    def from_json(self, json_data):
        self.group_id = str(json_data.get("group_id", self.group_id))
        self.title = json_data.get("title", self.title) or "Group"
        self.color = json_data.get("color", self.color) or GROUP_COLOR_PALETTE[0]
        members = json_data.get("member_ids", []) or []
        self.member_ids = [str(mid) for mid in members]

    def to_json(self):
        return {
            "group_id": str(self.group_id),
            "title": self.title,
            "color": self.color,
            "member_ids": [str(mid) for mid in self.member_ids],
        }


class Blueprint:
    """Placed module instances + connections that define an executable graph."""

    def __init__(self, name="Blueprint", description=""):
        self.name = name
        self.description = description
        self.modules = {}  # {module_id: Module}
        self.positions = {}  # {module_id: (x, y)}
        self.connections = {}  # {connection_id: Connection}
        self.groups = {}  # {group_id: Group} — layout-only, ignored by runner
        self.run_states = {}  # {module_id: ModuleRunState}
        self._stop_requested = False

    def request_stop(self):
        """Ask a running blueprint to halt before the next pending module."""
        self._stop_requested = True

    def _abandon_pending(self, on_update=None):
        """Mark waiting/running modules idle after a user stop (outputs ignored)."""
        for module_id in self.modules:
            state = self.get_run_state(module_id)
            if state.status in (STATUS_WAITING, STATUS_RUNNING):
                state.status = STATUS_IDLE
                state.log("Stopped by user.")
                if on_update:
                    on_update(module_id)

    def add_module(self, module: Module, x=0.0, y=0.0) -> Module:
        module_id = str(module.module_id)
        self.modules[module_id] = module
        self.positions[module_id] = (float(x), float(y))
        self.run_states[module_id] = ModuleRunState()
        return module

    def remove_module(self, module_id):
        module_id = str(module_id)
        self.modules.pop(module_id, None)
        self.positions.pop(module_id, None)
        self.run_states.pop(module_id, None)
        stale = [
            conn_id
            for conn_id, conn in self.connections.items()
            if str(conn.source_module) == module_id or str(conn.target_module) == module_id
        ]
        for conn_id in stale:
            self.connections.pop(conn_id, None)
        self.remove_module_from_groups(module_id)

    def add_group(self, group: Group) -> Group:
        group_id = str(group.group_id)
        # Keep only members that still exist on the blueprint.
        group.member_ids = [
            mid for mid in group.member_ids if mid in self.modules
        ]
        self.groups[group_id] = group
        return group

    def remove_group(self, group_id):
        self.groups.pop(str(group_id), None)

    def remove_module_from_groups(self, module_id):
        """Drop a module id from all groups; remove groups that become empty."""
        module_id = str(module_id)
        empty = []
        for group_id, group in self.groups.items():
            if module_id in group.member_ids:
                group.member_ids = [mid for mid in group.member_ids if mid != module_id]
            if not group.member_ids:
                empty.append(group_id)
        for group_id in empty:
            self.groups.pop(group_id, None)

    def serialize_group_snippet(self, group_id) -> dict | None:
        """
        Snapshot a group for account storage: instance modules (with edits),
        relative positions, and internal connections only.
        """
        group = self.groups.get(str(group_id))
        if group is None:
            return None
        member_ids = [mid for mid in group.member_ids if mid in self.modules]
        if not member_ids:
            return None

        positions = {}
        for mid in member_ids:
            pos = self.positions.get(mid, (0.0, 0.0))
            positions[mid] = (float(pos[0]), float(pos[1]))
        origin_x = min(p[0] for p in positions.values())
        origin_y = min(p[1] for p in positions.values())

        modules = {
            mid: self.modules[mid].to_json()
            for mid in member_ids
        }
        relative_positions = {
            mid: [positions[mid][0] - origin_x, positions[mid][1] - origin_y]
            for mid in member_ids
        }
        member_set = set(member_ids)
        connections = {}
        for conn_id, conn in self.connections.items():
            src = str(conn.source_module)
            tgt = str(conn.target_module)
            if src in member_set and tgt in member_set:
                connections[str(conn_id)] = conn.to_json()

        return {
            "title": group.title or "Group",
            "color": group.color or GROUP_COLOR_PALETTE[0],
            "modules": modules,
            "positions": relative_positions,
            "connections": connections,
        }

    def add_connection(self, connection: Connection) -> Connection:
        target = self.modules.get(str(connection.target_module))
        allow_fan_in = bool(target is not None and target.allows_input_fan_in())
        for conn_id, existing in list(self.connections.items()):
            if str(existing.target_module) != str(connection.target_module):
                continue
            if existing.target_port != connection.target_port:
                continue
            # Always replace an identical source→target wire.
            same_source = (
                str(existing.source_module) == str(connection.source_module)
                and existing.source_port == connection.source_port
            )
            if same_source or not allow_fan_in:
                self.connections.pop(conn_id, None)
        self.connections[str(connection.connection_id)] = connection
        return connection

    def remove_connection(self, connection_id):
        self.connections.pop(str(connection_id), None)

    def prune_invalid_connections(self, module_id=None):
        """Drop wires that reference missing modules or removed ports."""
        stale = []
        for conn_id, conn in self.connections.items():
            source = self.modules.get(str(conn.source_module))
            target = self.modules.get(str(conn.target_module))
            if source is None or target is None:
                stale.append(conn_id)
                continue
            if module_id is not None and str(module_id) not in (
                str(conn.source_module),
                str(conn.target_module),
            ):
                continue
            if conn.source_port not in source.outputs or conn.target_port not in target.inputs:
                stale.append(conn_id)
        for conn_id in stale:
            self.connections.pop(conn_id, None)
        return stale

    def remap_module_ports(self, module_id, input_map=None, output_map=None):
        """Rewrite connection port names after a module port rename."""
        module_id = str(module_id)
        input_map = dict(input_map or {})
        output_map = dict(output_map or {})
        if not input_map and not output_map:
            return
        for conn in self.connections.values():
            if str(conn.target_module) == module_id and conn.target_port in input_map:
                conn.target_port = input_map[conn.target_port]
            if str(conn.source_module) == module_id and conn.source_port in output_map:
                conn.source_port = output_map[conn.source_port]

    def get_run_state(self, module_id) -> ModuleRunState:
        module_id = str(module_id)
        state = self.run_states.get(module_id)
        if state is None:
            state = ModuleRunState()
            self.run_states[module_id] = state
        return state

    def reset_run_states(self, status: str = STATUS_IDLE):
        """Total wipe of temporary per-module run data (console, I/O, errors, status)."""
        self.run_states = {
            str(module_id): ModuleRunState()
            for module_id in self.modules
        }
        for state in self.run_states.values():
            state.status = status

    def _modules_reachable_from(self, start_id) -> set:
        """Module ids reachable from start_id via outgoing wires (not including start)."""
        start_id = str(start_id)
        adjacency = {module_id: set() for module_id in self.modules}
        for conn in self.connections.values():
            src = str(conn.source_module)
            dst = str(conn.target_module)
            if src in adjacency and dst in adjacency and src != dst:
                adjacency[src].add(dst)

        reached = set()
        stack = list(adjacency.get(start_id, ()))
        while stack:
            node = stack.pop()
            if node in reached:
                continue
            reached.add(node)
            stack.extend(adjacency.get(node, ()))
        return reached

    def _is_memory_feedback_edge(self, source_id, target_id) -> bool:
        """True when source is downstream of a Memory target (write-back / soft edge)."""
        target = self.modules.get(str(target_id))
        if not isinstance(target, MemoryModule):
            return False
        return str(source_id) in self._modules_reachable_from(target_id)

    def execution_order(self) -> list[str]:
        """Topological order of module ids. Raises ValueError on cycles.

        Write-back wires into Memory from modules reachable via that Memory's
        outputs are soft (feedback) and do not create schedule dependencies.
        """
        dependents = {module_id: set() for module_id in self.modules}
        indegree = {module_id: 0 for module_id in self.modules}

        # Cache reachability per Memory so soft-edge checks stay cheap.
        memory_downstream = {
            module_id: self._modules_reachable_from(module_id)
            for module_id, module in self.modules.items()
            if isinstance(module, MemoryModule)
        }

        for conn in self.connections.values():
            src = str(conn.source_module)
            dst = str(conn.target_module)
            if src not in self.modules or dst not in self.modules or src == dst:
                continue
            # Soft: Prompt/etc. writing back into an upstream Memory.
            if dst in memory_downstream and src in memory_downstream[dst]:
                continue
            if dst not in dependents[src]:
                dependents[src].add(dst)
                indegree[dst] += 1

        queue = [module_id for module_id, degree in indegree.items() if degree == 0]
        ordered = []
        while queue:
            module_id = queue.pop(0)
            ordered.append(module_id)
            for dependent in sorted(dependents[module_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(self.modules):
            raise ValueError("Blueprint has a cycle and cannot be executed.")
        return ordered

    def _collect_module_inputs(self, module_id, results: dict):
        """Resolve inbound wires for one module.

        Returns (inputs, missing_wires, gated_inputs).
        """
        module = self.modules[module_id]
        inbound = {}
        for conn in self.connections.values():
            if str(conn.target_module) != module_id:
                continue
            inbound.setdefault(conn.target_port, []).append(conn)

        allow_fan_in = module.allows_input_fan_in()
        optional_inputs = set(module.optional_input_names() or ())
        inputs = {}
        missing_wires = []
        gated_inputs = []
        for name in module.inputs:
            conns = inbound.get(name) or []
            if not conns:
                if name not in optional_inputs:
                    missing_wires.append(name)
                continue

            values = []
            any_gated = False
            for conn in conns:
                source_id = str(conn.source_module)
                if source_id not in results:
                    any_gated = True
                    continue
                source_outputs = results[source_id]
                if conn.source_port not in source_outputs:
                    any_gated = True
                    continue
                value = source_outputs[conn.source_port]
                # None means "no value" — same as a withheld/gated port.
                if value is None:
                    any_gated = True
                    continue
                values.append(value)

            if not values:
                if name in optional_inputs:
                    continue
                gated_inputs.append(name)
                continue

            if allow_fan_in:
                inputs[name] = values
            else:
                # Non-fan-in: last surviving wire wins.
                inputs[name] = values[-1]
                if any_gated and name not in optional_inputs:
                    pass

        return inputs, missing_wires, gated_inputs

    def _mark_modules_idle(self, module_ids, on_update=None, message=None):
        for mid in module_ids:
            mid = str(mid)
            if mid not in self.modules:
                continue
            state = self.get_run_state(mid)
            if state.status in (STATUS_WAITING, STATUS_RUNNING):
                state.status = STATUS_IDLE
                if message:
                    state.log(message)
                if on_update:
                    on_update(mid)

    def _reset_body_for_pass(self, body, results: dict, on_update=None):
        """Clear prior results / run-state for iterator body modules only."""
        for bid in body:
            bid = str(bid)
            results.pop(bid, None)
            state = ModuleRunState()
            state.status = STATUS_WAITING
            self.run_states[bid] = state
            if on_update:
                on_update(bid)

    def _execute_module(self, module_id, results: dict, on_update=None, environment=None) -> str:
        """
        Run one non-iterator module.

        Returns 'ok', 'skipped', or 'stopped'. Hard failures re-raise after
        updating run states (same as the former Blueprint.run loop body).
        """
        module_id = str(module_id)
        if self._stop_requested:
            self._abandon_pending(on_update)
            return "stopped"

        module = self.modules[module_id]
        state = self.get_run_state(module_id)
        state.status = STATUS_RUNNING
        if on_update:
            on_update(module_id)

        if self._stop_requested:
            self._abandon_pending(on_update)
            return "stopped"

        inputs, missing_wires, gated_inputs = self._collect_module_inputs(
            module_id, results
        )

        if missing_wires:
            message = f"Skipped: missing connected inputs: {missing_wires}"
            state.status = STATUS_IDLE
            state.inputs = inputs
            state.outputs = {}
            state.log(message)
            if on_update:
                on_update(module_id)
            return "skipped"

        if gated_inputs:
            message = f"Skipped: gated/unsatisfied inputs: {gated_inputs}"
            state.status = STATUS_IDLE
            state.inputs = inputs
            state.outputs = {}
            state.log(message)
            if on_update:
                on_update(module_id)
            return "skipped"

        state.inputs = dict(inputs)
        state.log(format_port_section("Inputs", inputs, compact=True))
        if on_update:
            on_update(module_id)

        if self._stop_requested:
            self._abandon_pending(on_update)
            return "stopped"

        stop_attr_set = False
        prev_stop_checker = None
        progress_attr_set = False
        prev_progress = None
        if environment is not None:
            prev_stop_checker = getattr(environment, "_modulink_should_stop", None)
            environment._modulink_should_stop = lambda: self._stop_requested
            stop_attr_set = True

            def _progress(partial_outputs):
                # Live UI only — do not write results[] until run() returns.
                state.outputs = dict(partial_outputs or {})
                if on_update:
                    on_update(module_id)

            prev_progress = getattr(environment, "_modulink_progress", None)
            environment._modulink_progress = _progress
            progress_attr_set = True
        try:
            try:
                outputs = module.run(inputs, environment=environment)
            except ExecModuleFailedWithConsole as exc:
                outputs = dict(exc.outputs or {})
                state.status = STATUS_FAILED
                state.error = str(exc)
                state.outputs = outputs
                state.log(f"Error: {exc}")
                console_text = outputs.get(
                    getattr(module, "console_output", EXEC_DEFAULT_CONSOLE_OUTPUT), ""
                )
                if not console_text:
                    console_text = getattr(module, "_last_console", "") or ""
                if console_text:
                    state.log("--- Console ---")
                    state.log(str(console_text))
                state.log(format_port_section("Outputs", outputs, compact=True))
                results[module_id] = outputs
                if on_update:
                    on_update(module_id)
                return "ok"
            except Exception as exc:
                state.status = STATUS_FAILED
                state.error = str(exc)
                state.log(f"Error: {exc}")
                captured = getattr(module, "_last_console", "") or ""
                if captured:
                    state.log("--- Console ---")
                    state.log(str(captured))
                else:
                    state.log(traceback.format_exc())
                if on_update:
                    on_update(module_id)
                for pending_id in self.modules:
                    pending = self.get_run_state(pending_id)
                    if pending.status == STATUS_WAITING:
                        pending.status = STATUS_IDLE
                        if on_update:
                            on_update(pending_id)
                raise

            if self._stop_requested:
                state.status = STATUS_IDLE
                state.outputs = {}
                state.log("Stopped by user (module output discarded).")
                if on_update:
                    on_update(module_id)
                self._abandon_pending(on_update)
                return "stopped"

            outputs = dict(outputs or {})
            state.outputs = outputs
            state.status = STATUS_SUCCESS
            if (
                isinstance(module, ConditionModule)
                and not outputs
                and module.passthrough
                and not module.output_result
            ):
                state.log("Gate blocked: condition was False (passthrough withheld).")
            if isinstance(module, ExecModule):
                captured = getattr(module, "_last_console", "") or ""
                if captured.strip():
                    state.log("--- Console ---")
                    state.log(captured)
            if isinstance(module, StrategyModule):
                op_log = getattr(module, "_last_op_log", None) or []
                if op_log:
                    state.log("--- Strategy ops ---")
                    for line in op_log:
                        state.log(str(line))
            state.log(format_port_section("Outputs", outputs, compact=True))
            results[module_id] = outputs
            if on_update:
                on_update(module_id)
            return "ok"
        finally:
            if stop_attr_set and environment is not None:
                if prev_stop_checker is None:
                    try:
                        delattr(environment, "_modulink_should_stop")
                    except Exception:
                        environment._modulink_should_stop = None
                else:
                    environment._modulink_should_stop = prev_stop_checker
            if progress_attr_set and environment is not None:
                if prev_progress is None:
                    try:
                        delattr(environment, "_modulink_progress")
                    except Exception:
                        environment._modulink_progress = None
                else:
                    environment._modulink_progress = prev_progress

    def _run_modules_in_order(
        self,
        order,
        allowed,
        results: dict,
        on_update=None,
        environment=None,
        consumed=None,
    ) -> str:
        """
        Execute modules from topo order that are in allowed and not consumed.

        Iterator modules expand into a full body loop. Returns 'ok' or 'stopped'.
        """
        if consumed is None:
            consumed = set()
        allowed = set(allowed)

        for module_id in order:
            module_id = str(module_id)
            if module_id not in allowed or module_id in consumed:
                continue
            if self._stop_requested:
                self._abandon_pending(on_update)
                return "stopped"

            module = self.modules[module_id]
            if isinstance(module, IteratorModule):
                outcome = self._run_iterator(
                    module_id,
                    order,
                    results,
                    on_update=on_update,
                    environment=environment,
                    consumed=consumed,
                )
                if outcome == "stopped":
                    return "stopped"
                continue

            outcome = self._execute_module(
                module_id, results, on_update=on_update, environment=environment
            )
            consumed.add(module_id)
            if outcome == "stopped":
                return "stopped"
        return "ok"

    def _run_iterator(
        self,
        module_id,
        order,
        results: dict,
        on_update=None,
        environment=None,
        consumed=None,
    ) -> str:
        """Resolve items, then re-run reachable body modules once per item."""
        module_id = str(module_id)
        if consumed is None:
            consumed = set()

        module = self.modules[module_id]
        body = self._modules_reachable_from(module_id)
        consumed.add(module_id)
        consumed.update(body)

        state = self.get_run_state(module_id)
        state.status = STATUS_RUNNING
        if on_update:
            on_update(module_id)

        if self._stop_requested:
            self._abandon_pending(on_update)
            return "stopped"

        inputs, missing_wires, gated_inputs = self._collect_module_inputs(
            module_id, results
        )

        if missing_wires:
            message = f"Skipped: missing connected inputs: {missing_wires}"
            state.status = STATUS_IDLE
            state.inputs = inputs
            state.outputs = {}
            state.log(message)
            if on_update:
                on_update(module_id)
            self._mark_modules_idle(body, on_update=on_update)
            return "ok"

        if gated_inputs:
            message = f"Skipped: gated/unsatisfied inputs: {gated_inputs}"
            state.status = STATUS_IDLE
            state.inputs = inputs
            state.outputs = {}
            state.log(message)
            if on_update:
                on_update(module_id)
            self._mark_modules_idle(body, on_update=on_update)
            return "ok"

        state.inputs = dict(inputs)
        state.log(format_port_section("Inputs", inputs, compact=True))
        if on_update:
            on_update(module_id)

        try:
            items = module.iter_items(inputs)
        except Exception as exc:
            state.status = STATUS_FAILED
            state.error = str(exc)
            state.log(f"Error: {exc}")
            state.log(traceback.format_exc())
            if on_update:
                on_update(module_id)
            for pending_id in self.modules:
                pending = self.get_run_state(pending_id)
                if pending.status == STATUS_WAITING:
                    pending.status = STATUS_IDLE
                    if on_update:
                        on_update(pending_id)
            raise

        count = len(items)
        if count == 0:
            outputs = {ITERATOR_COUNT_PORT: 0}
            state.outputs = outputs
            state.status = STATUS_SUCCESS
            state.log("Empty iterable — body not run.")
            state.log(format_port_section("Outputs", outputs, compact=True))
            results[module_id] = outputs
            if on_update:
                on_update(module_id)
            self._mark_modules_idle(body, on_update=on_update)
            return "ok"

        state.log(f"Iterating {count} item(s).")
        if on_update:
            on_update(module_id)

        for index, item in enumerate(items):
            if self._stop_requested:
                self._abandon_pending(on_update)
                return "stopped"

            outputs = {
                ITERATOR_ITEM_PORT: item,
                ITERATOR_INDEX_PORT: index,
                ITERATOR_COUNT_PORT: count,
            }
            results[module_id] = outputs
            state.outputs = outputs
            state.status = STATUS_SUCCESS
            state.log(
                f"--- Pass {index + 1}/{count} ---"
            )
            state.log(format_port_section("Outputs", outputs, compact=True))
            if on_update:
                on_update(module_id)

            self._reset_body_for_pass(body, results, on_update=on_update)

            pass_consumed = set()
            outcome = self._run_modules_in_order(
                order,
                body,
                results,
                on_update=on_update,
                environment=environment,
                consumed=pass_consumed,
            )
            if outcome == "stopped":
                return "stopped"

        return "ok"

    def run(self, on_update=None, environment=None) -> dict:
        """
        Execute modules in connection order.
        Inputs come only from upstream output connections.
        Per-module console/outputs/status are stored in run_states.

        Iterator modules re-run every reachable downstream module once per item.
        """
        # Always start from a clean slate on every blueprint run.
        self._stop_requested = False
        self.reset_run_states(STATUS_WAITING)
        if on_update:
            for module_id in self.modules:
                on_update(module_id)

        results = {}
        try:
            order = self.execution_order()
        except Exception as exc:
            for module_id in self.modules:
                state = self.get_run_state(module_id)
                state.status = STATUS_FAILED
                state.error = str(exc)
                state.log(f"Error: {exc}")
                if on_update:
                    on_update(module_id)
            raise

        outcome = self._run_modules_in_order(
            order,
            set(order),
            results,
            on_update=on_update,
            environment=environment,
            consumed=set(),
        )
        if outcome == "stopped":
            pass

        # Any modules never reached stay idle rather than waiting.
        for pending_id in self.modules:
            pending = self.get_run_state(pending_id)
            if pending.status == STATUS_WAITING:
                pending.status = STATUS_IDLE
                if on_update:
                    on_update(pending_id)

        if not self._stop_requested:
            self._commit_memory_writes(results, on_update=on_update, environment=environment)

        return results

    def _collect_memory_feedback_inputs(self, module_id, results: dict) -> dict:
        """Gather write/clear inputs on a Memory from downstream feedback sources only."""
        module = self.modules.get(str(module_id))
        if not isinstance(module, MemoryModule):
            return {}

        inbound = {}
        for conn in self.connections.values():
            if str(conn.target_module) != str(module_id):
                continue
            if not self._is_memory_feedback_edge(conn.source_module, module_id):
                continue
            inbound.setdefault(conn.target_port, []).append(conn)

        inputs = {}
        for name in module.inputs:
            conns = inbound.get(name) or []
            if not conns:
                continue
            values = []
            for conn in conns:
                source_id = str(conn.source_module)
                if source_id not in results:
                    continue
                source_outputs = results[source_id]
                if conn.source_port not in source_outputs:
                    continue
                value = source_outputs[conn.source_port]
                if value is None:
                    continue
                values.append(value)
            if not values:
                continue
            # Memory always allows fan-in; run() normalizes list vs last-wins.
            inputs[name] = values
        return inputs

    def _commit_memory_writes(self, results: dict, on_update=None, environment=None):
        """
        Apply Memory write-back inputs after the main pass.

        Soft feedback edges (Prompt→Memory, etc.) are ignored for scheduling so
        Memory can publish its stored slot first. Once writers have finished,
        re-run those Memory modules with the feedback values only — hard
        upstream writes (Constant→Memory) already applied in the main pass.
        """
        for module_id, module in self.modules.items():
            if self._stop_requested:
                break
            if not isinstance(module, MemoryModule):
                continue
            if module_id not in results:
                # Skipped / failed in main pass — do not invent a commit write.
                continue

            inputs = self._collect_memory_feedback_inputs(module_id, results)
            if not inputs:
                continue

            state = self.get_run_state(module_id)
            state.status = STATUS_RUNNING
            if on_update:
                on_update(module_id)

            if self._stop_requested:
                self._abandon_pending(on_update)
                break

            state.inputs = dict(inputs)
            state.log("--- Memory write-back ---")
            state.log(format_port_section("Inputs", inputs, compact=True))
            if on_update:
                on_update(module_id)

            stop_attr_set = False
            prev_stop_checker = None
            if environment is not None:
                prev_stop_checker = getattr(environment, "_modulink_should_stop", None)
                environment._modulink_should_stop = lambda: self._stop_requested
                stop_attr_set = True
            try:
                try:
                    outputs = module.run(inputs, environment=environment)
                except Exception as exc:
                    state.status = STATUS_FAILED
                    state.error = str(exc)
                    state.log(f"Error: {exc}")
                    if on_update:
                        on_update(module_id)
                    continue

                if self._stop_requested:
                    state.status = STATUS_IDLE
                    state.log("Stopped by user (memory write-back discarded).")
                    if on_update:
                        on_update(module_id)
                    self._abandon_pending(on_update)
                    break

                outputs = dict(outputs or {})
                state.outputs = outputs
                state.status = STATUS_SUCCESS
                state.log(format_port_section("Outputs", outputs, compact=True))
                results[module_id] = outputs
                if on_update:
                    on_update(module_id)
            finally:
                if stop_attr_set and environment is not None:
                    if prev_stop_checker is None:
                        try:
                            delattr(environment, "_modulink_should_stop")
                        except Exception:
                            environment._modulink_should_stop = None
                    else:
                        environment._modulink_should_stop = prev_stop_checker

    def from_json(self, json_data):
        self.name = json_data.get("name", self.name)
        self.description = json_data.get("description", self.description)
        self.modules = {
            str(module_id): module_from_json(data)
            for module_id, data in json_data.get("modules", {}).items()
        }
        self.positions = {
            str(module_id): tuple(pos)
            for module_id, pos in json_data.get("positions", {}).items()
        }
        self.connections = {
            str(conn_id): Connection(json_data=data)
            for conn_id, data in json_data.get("connections", {}).items()
        }
        self.groups = {}
        for group_id, data in (json_data.get("groups") or {}).items():
            group = Group(json_data=data)
            group.group_id = str(group_id)
            group.member_ids = [
                mid for mid in group.member_ids if mid in self.modules
            ]
            if group.member_ids:
                self.groups[str(group.group_id)] = group
        self.run_states = {module_id: ModuleRunState() for module_id in self.modules}

    def to_json(self):
        return {
            "name": self.name,
            "description": self.description,
            "modules": {
                str(module_id): module.to_json()
                for module_id, module in self.modules.items()
            },
            "positions": {
                str(module_id): list(pos)
                for module_id, pos in self.positions.items()
            },
            "connections": {
                str(conn_id): connection.to_json()
                for conn_id, connection in self.connections.items()
            },
            "groups": {
                str(group_id): group.to_json()
                for group_id, group in self.groups.items()
            },
        }


