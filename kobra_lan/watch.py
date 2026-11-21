"""Read-only observation over one pinned printer session."""
from contextlib import ExitStack
import re
import time

from .config import ProtocolError
from .diagnostics import compatibility_issue
from .mqtt import MQTT, MQTTClosed, MQTTFailure, MQTTIOFailure
from .printer import payload_data

DEFAULT_TIMEOUT = 86400
MAX_TIMEOUT = 259200
POLL_INTERVAL = 5
PREPARATION_STATES = frozenset({
    "extfilbox_filament_feeding", "frequency_sweeping", "hotbed_cooling_off", "hotbed_heating",
    "nozzle_cooling", "nozzle_heating", "nozzle_purging", "nozzle_wiping", "z_offset_calibrating",
})


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

    def __init__(self):
        self.last = None
        self.initial_filename = None
        self.initial_last_project = None

    def result(self, outcome, reason):
        return {"outcome": outcome, "reason": reason, **(self.last or {})}

    def partial(self, reason):
        if self.last is not None:
            return self.result("unknown", reason)
        return None

    def update(self, info):
        project = info.get("project")
        if self.last is None:
            idle = info["state"] == "free"
            if idle and (project is None or project == {}):
                return self.result("no_active_job", "idle")
            phase = project.get("state") if isinstance(project, dict) else None
            if idle or not isinstance(phase, str):
                return self.result("unknown", "active_job_unverified")
            if phase in PREPARATION_STATES:
                self.last = {"phase": "preparing"}
            elif phase == "printing":
                self.last = {"phase": "printing", **progress_fields(project)}
            else:
                return self.result("unknown", "active_job_unverified")
            self.initial_filename = project_filename(project)
            self.initial_last_project = last_project_baseline(info.get("last_project"))
            return None

        latest_last_project = last_project_baseline(info.get("last_project"))
        if latest_last_project is not None and latest_last_project != self.initial_last_project:
            return self.result("unknown", "last_project_unattributed")
        if project is None or project == {}:
            return self.result("unknown", "job_disappeared")
        filename = project_filename(project) if isinstance(project, dict) else None
        if self.initial_filename and filename and filename != self.initial_filename:
            return self.result("unknown", "job_replaced")
        # Filenames can be reused, and the observed task_id is a start placeholder.
        return self.result("unknown", "identity_unverified")


def observe(registry, config, name, timeout, on_report):
    """Deliver fresh qualified info to on_report until it returns a result or time expires."""
    deadline = time.monotonic() + timeout
    try:
        with ExitStack() as session:
            with registry.access(config, name) as (cfg, _):
                client = session.enter_context(MQTT(cfg, deadline=deadline))

            while time.monotonic() < deadline:
                info = payload_data(client.query("info", require_fresh=True))
                if time.monotonic() >= deadline:
                    break
                if compatibility_issue(cfg, info):
                    raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
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
