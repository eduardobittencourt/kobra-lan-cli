"""Read-only observation over one pinned printer session."""
from contextlib import ExitStack
import hashlib
import math
import os
from pathlib import Path
import re
import time
import uuid

from .cli_output import safe_text
from .config import ProtocolError
from .mqtt import MQTT, MQTTClosed, MQTTFailure, MQTTIOFailure, TASKID_RE
from .printer import payload_data
from .profiles import open_directory
from .qualification import info_compatibility_issue
from .upload import atomic_json_at

DEFAULT_TIMEOUT = 86400
MAX_TIMEOUT = 259200
POLL_INTERVAL = 5
WATCH_BACKWARD_SKEW_MS = 5000
PREPARATION_STATES = frozenset({
    "auto_leveling",
    "extfilbox_filament_feeding",
    "extfilbox_filament_unfeeding",
    "filament_cutting",
    "flow_calibrating",
    "frequency_sweeping",
    "hotbed_cooling_off",
    "hotbed_heating",
    "nozzle_cooling",
    "nozzle_heating",
    "nozzle_purging",
    "nozzle_wiping",
    "vibrating",
    "z_offset_calibrating",
})
START_ONLY_PREPARATION_STATES = frozenset({
    "auto_leveling",
    "flow_calibrating",
    "frequency_sweeping",
    "vibrating",
    "z_offset_calibrating",
})
PAUSED_STATES = frozenset({"paused", "pausing"})
STOPPING_STATES = frozenset({"stopping"})


def progress_fields(project):
    fields = {}
    progress = project.get("progress")
    current = project.get("curr_layer")
    total = project.get("total_layers")
    if type(progress) is int and 0 <= progress <= 100:
        fields["progress"] = progress
    if type(total) is int and 1 <= total <= 1_000_000:
        fields["total_layers"] = total
    if type(current) is int and 0 <= current <= fields.get("total_layers", 1_000_000):
        fields["current_layer"] = current
    return fields


def project_filename(project):
    name = project.get("filename")
    if (isinstance(name, str) and 0 < len(name) <= 255 and name.isprintable()
            and all(c not in name for c in "/\\:?#")):
        return name
    return None


def project_task_id(project):
    if not isinstance(project, dict):
        return None
    for key in ("task_id", "taskid"):
        value = project.get(key)
        if isinstance(value, str) and TASKID_RE.fullmatch(value) is not None:
            return None if value == "-1" else value
    return None


def _safe_remain_time(project):
    if not isinstance(project, dict):
        return None
    remain = project.get("remain_time")
    if type(remain) is int and 1 <= remain <= 1_000_000:
        return remain
    return None


def _safe_temp(value):
    if type(value) is int and -50 <= value <= 500:
        return str(value)
    if type(value) is float and math.isfinite(value) and -50.0 <= value <= 500.0:
        return f"{value:g}"
    return None


def _format_progress_line(last, state, remain_time, temp):
    parts = [last["phase"]]
    if (isinstance(state, str) and state != last["phase"]
            and len(state) <= 80 and state.isascii() and state.isidentifier()):
        parts.append(f"({state})")
    if "progress" in last:
        parts.append(f"{last['progress']}%")
    if "current_layer" in last and "total_layers" in last:
        parts.append(f"layer {last['current_layer']}/{last['total_layers']}")
    elif "current_layer" in last:
        parts.append(f"layer {last['current_layer']}")
    if remain_time is not None:
        parts.append(f"remaining {remain_time}m")
    if isinstance(temp, dict):
        curr_nozzle = _safe_temp(temp.get("curr_nozzle_temp"))
        target_nozzle = _safe_temp(temp.get("target_nozzle_temp"))
        if curr_nozzle is not None and target_nozzle is not None:
            parts.append(f"nozzle {curr_nozzle}/{target_nozzle}C")
        curr_bed = _safe_temp(temp.get("curr_hotbed_temp"))
        target_bed = _safe_temp(temp.get("target_hotbed_temp"))
        if curr_bed is not None and target_bed is not None:
            parts.append(f"bed {curr_bed}/{target_bed}C")
    return safe_text(" ".join(parts))


def last_project_baseline(last):
    if not isinstance(last, dict) or not last:
        return None
    state = last.get("state")
    if not isinstance(state, str) or len(state) > 80 or not state.isascii() or not state.isidentifier():
        state = None
    task_id = last.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
        task_id = None
    snapshot = state, task_id, project_filename(last), progress_fields(last)
    return snapshot if any(snapshot) else None


class WatchProgress:
    """Keep only scalar progress established for the job selected at startup."""

    def __init__(self, *, on_progress=None):
        self.last = None
        self.observed_at = None
        self.device_digest = None
        self.observation_id = None
        self.initial_filename = None
        self.initial_task_id = None
        self.initial_last_project = None
        self.saw_printing_progress = False
        self.max_progress = None
        self.max_layer = None
        self.observed_total_layers = None
        self._on_progress = on_progress
        self._last_progress_key = None

    def bind_device(self, config):
        self.device_digest = hashlib.sha256(config.printer_id.encode()).hexdigest()

    def result(self, outcome, reason):
        return {"outcome": outcome, "reason": reason, **(self.last or {})}

    def partial(self, reason):
        if self.last is not None:
            return self.result("unknown", reason)
        return None

    def record(self, result, state_dir):
        if result is None or self.last is None:
            return result
        if self.observation_id is None:
            self.observation_id = "obs-" + uuid.uuid4().hex
        observation_id = persist_observation(
            state_dir,
            self.device_digest,
            self.observed_at,
            self.initial_filename,
            result,
            observation_id=self.observation_id,
        )
        if observation_id is None:
            return {**result, "observation_recorded": False}
        return {**result, "observation_id": observation_id, "observation_recorded": True}

    def _preserved_scalars(self):
        if not self.last:
            return {}
        return {k: self.last[k] for k in ("progress", "current_layer", "total_layers") if k in self.last}

    def _record_high_water(self, fields):
        progress = fields.get("progress")
        current = fields.get("current_layer")
        total = fields.get("total_layers")
        if progress is not None:
            if self.max_progress is None or progress > self.max_progress:
                self.max_progress = progress
            if progress > 0:
                self.saw_printing_progress = True
        if current is not None:
            if self.max_layer is None or current > self.max_layer:
                self.max_layer = current
            if current > 0:
                self.saw_printing_progress = True
        if total is not None and self.observed_total_layers is None:
            self.observed_total_layers = total

    def _emit_progress(self, info, project, state):
        if self._on_progress is None or self.last is None:
            return
        remain_time = _safe_remain_time(project)
        key = (
            self.last["phase"],
            state,
            self.last.get("progress"),
            self.last.get("current_layer"),
            self.last.get("total_layers"),
            remain_time,
        )
        if key == self._last_progress_key:
            return
        self._last_progress_key = key
        self._on_progress(_format_progress_line(self.last, state, remain_time, info.get("temp")))

    def _printing_regression(self, progress, current, total):
        if total is not None and self.observed_total_layers is not None and total != self.observed_total_layers:
            return True
        if not self.saw_printing_progress:
            return False
        if progress is not None and self.max_progress is not None and progress < self.max_progress:
            return True
        return current is not None and current > 0 and self.max_layer is not None and current < self.max_layer

    def _merge_printing(self, project):
        fields = progress_fields(project)
        progress = fields.get("progress")
        current = fields.get("current_layer")
        total = fields.get("total_layers")
        if self._printing_regression(progress, current, total):
            return self.result("unknown", "identity_unverified")
        merged = self._preserved_scalars()
        if progress is not None:
            merged["progress"] = progress
        if total is not None:
            merged["total_layers"] = total
        if current is not None and (current > 0 or "current_layer" not in merged):
            merged["current_layer"] = current
        if merged.get("current_layer", 0) > merged.get("total_layers", 1_000_000):
            return self.result("unknown", "identity_unverified")
        self._record_high_water(merged)
        self.last = {"phase": "printing", **merged}
        return None

    def _merge_transitional_counters(self, project, phase):
        fields = progress_fields(project)
        progress = fields.get("progress")
        current = fields.get("current_layer")
        total = fields.get("total_layers")
        preserved = self._preserved_scalars()
        candidate = dict(preserved)
        if progress is not None and progress > 0 and (self.max_progress is None or progress >= self.max_progress):
            candidate["progress"] = progress
        if total is not None and (self.observed_total_layers is None or total == self.observed_total_layers):
            candidate["total_layers"] = total
        if current is not None and current > 0 and (self.max_layer is None or current >= self.max_layer):
            candidate["current_layer"] = current
        if candidate.get("current_layer", 0) > candidate.get("total_layers", 1_000_000):
            candidate = preserved
        else:
            self._record_high_water(candidate)
        self.last = {"phase": phase, **candidate}

    def update(self, info):
        project = info.get("project")
        if self.last is None:
            idle = info["state"] == "free"
            if idle and (project is None or project == {}):
                return self.result("no_active_job", "idle")
            state = project.get("state") if isinstance(project, dict) else None
            if idle or not isinstance(state, str):
                return self.result("unknown", "active_job_unverified")
            if state in PREPARATION_STATES or state == "resuming":
                self.last = {"phase": "preparing"}
            elif state == "printing":
                fields = progress_fields(project)
                self.last = {"phase": "printing", **fields}
                self._record_high_water(fields)
            elif state in PAUSED_STATES:
                fields = progress_fields(project)
                if fields.get("progress", 0) > 0 or fields.get("current_layer", 0) > 0 or "total_layers" in fields:
                    self.last = {"phase": "paused", **fields}
                    self._record_high_water(fields)
                else:
                    self.last = {"phase": "paused"}
            elif state in STOPPING_STATES:
                fields = progress_fields(project)
                if fields.get("progress", 0) > 0 or fields.get("current_layer", 0) > 0 or "total_layers" in fields:
                    self.last = {"phase": "stopping", **fields}
                    self._record_high_water(fields)
                else:
                    self.last = {"phase": "stopping"}
            else:
                return self.result("unknown", "active_job_unverified")
            self.observed_at = int(time.time())
            self.initial_filename = project_filename(project)
            self.initial_task_id = project_task_id(project)
            self.initial_last_project = last_project_baseline(info.get("last_project"))
            self._emit_progress(info, project, state)
            return None

        latest_last_project = last_project_baseline(info.get("last_project"))
        if latest_last_project is not None and latest_last_project != self.initial_last_project:
            return self.result("unknown", "last_project_unattributed")
        if info.get("state") == "free" or project is None or project == {}:
            return self.result("unknown", "job_disappeared")
        if not isinstance(project, dict):
            return self.result("unknown", "active_job_unverified")
        filename = project_filename(project)
        if self.initial_filename is None or filename is None:
            return self.result("unknown", "identity_unverified")
        if filename != self.initial_filename:
            return self.result("unknown", "job_replaced")
        current_task_id = project_task_id(project)
        if self.initial_task_id is not None and current_task_id is not None and current_task_id != self.initial_task_id:
            return self.result("unknown", "job_replaced")
        if self.initial_task_id is None and current_task_id is not None:
            self.initial_task_id = current_task_id

        state = project.get("state")
        if not isinstance(state, str):
            return self.result("unknown", "active_job_unverified")
        if state == "printing":
            stop = self._merge_printing(project)
            if stop is not None:
                return stop
        elif state in START_ONLY_PREPARATION_STATES:
            if self.saw_printing_progress:
                return self.result("unknown", "identity_unverified")
            self.last = {"phase": "preparing", **self._preserved_scalars()}
        elif state in PREPARATION_STATES or state == "resuming":
            self.last = {"phase": "preparing", **self._preserved_scalars()}
        elif state in PAUSED_STATES:
            self._merge_transitional_counters(project, "paused")
        elif state in STOPPING_STATES:
            self._merge_transitional_counters(project, "stopping")
        else:
            return self.result("unknown", "active_job_unverified")
        self._emit_progress(info, project, state)
        return None


def persist_observation(state_dir, device_digest, observed_at, observed_filename, result, *, observation_id=None):
    """Atomically store one sanitized private watch observation under state_dir."""
    if (not state_dir or not isinstance(device_digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", device_digest) is None
            or type(observed_at) is not int or not isinstance(result, dict)):
        return None
    if observation_id is None:
        observation_id = "obs-" + uuid.uuid4().hex
    elif not isinstance(observation_id, str) or re.fullmatch(r"obs-[a-f0-9]{32}", observation_id) is None:
        return None
    record = {
        "version": 1,
        "observation_id": observation_id,
        "device_digest": device_digest,
        "observed_at": observed_at,
        "ended_at": int(time.time()),
        "observed_filename": observed_filename,
        "client_attribution": "unattributed",
        "outcome": result["outcome"],
        "reason": result["reason"],
        "phase": result["phase"],
    }
    for field in ("progress", "current_layer", "total_layers"):
        if field in result:
            record[field] = result[field]
    directory = Path(state_dir) / "observations" / device_digest[:16]
    try:
        directory_fd = open_directory(directory, create=True, require_private=True)
    except (OSError, ValueError):
        return None
    try:
        atomic_json_at(directory_fd, observation_id + ".json", record)
    except (OSError, ValueError, ProtocolError):
        return None
    finally:
        os.close(directory_fd)
    return observation_id


def observe(registry, config, name, timeout, on_report, *, on_target=None):
    """Deliver fresh qualified info to on_report until it returns a result or time expires."""
    deadline = time.monotonic() + timeout
    last_timestamp = None
    try:
        with ExitStack() as session:
            with registry.access(config, name) as (cfg, _):
                if on_target is not None:
                    on_target(cfg)
                client = session.enter_context(MQTT(cfg, deadline=deadline))

            while time.monotonic() < deadline:
                report = client.query(
                    "info",
                    require_fresh=True,
                    max_backward_skew_ms=WATCH_BACKWARD_SKEW_MS,
                    min_timestamp=last_timestamp,
                )
                info = payload_data(report)
                if time.monotonic() >= deadline:
                    break
                if info_compatibility_issue(cfg.type_id, cfg.printer_id, info):
                    raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
                stamp = report.get("timestamp") if isinstance(report, dict) else None
                if type(stamp) in (int, float):
                    last_timestamp = stamp
                result = on_report(info)
                if result is not None:
                    return result
                left = deadline - time.monotonic()
                if left > 0:
                    time.sleep(min(POLL_INTERVAL, left))
    except MQTTClosed as error:
        raise ConnectionError("MQTT connection closed") from error
    except UnicodeDecodeError:
        raise ProtocolError("Malformed MQTT status response") from None
    except (MQTTFailure, MQTTIOFailure, TimeoutError) as error:
        timed_out = (isinstance(error, TimeoutError)
                     or isinstance(error, MQTTFailure) and error.code == "timeout"
                     or isinstance(error, MQTTIOFailure) and error.timed_out)
        if not timed_out or time.monotonic() < deadline:
            raise
    return None
