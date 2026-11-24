"""Experimental single-shot print lifecycle controls (pause, resume, cancel).

Protocol reference: KX-Bridge f0ce700fbcc9b3aed54f1a142b4e0318bc11638e and
stribor/anycubic_kobrax 9e22712454b5c65fec6e33c92fd894a61f7f4d6f.
Hardware transitions on Kobra X model 20030 / FW 2.0.2.2 were observed live on
2026-11-23 (pause -> paused, resume -> resuming -> nozzle_purging, stop ->
stopping -> free with empty last_project); resuming/stopping can exceed the
bounded 5 s post-ACK poll window. Results remain experimental=True with
hardware_control_validated=True on the qualified target.
"""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import time

from .config import ProtocolError, validate_filename
from .diagnostics import compatibility_issue
from .mqtt import MQTT, TASKID_RE, mqtt_failure_exit_code
from .printer import payload_data, sanitized
from .upload import device_lock, ensure_directory_bound
from .watch import PREPARATION_STATES, project_filename

WIRE_ACTIONS = {
    "pause": "pause",
    "resume": "resume",
    "cancel": "stop",
}
PAUSE_ALLOWED = frozenset({"printing"})
RESUME_ALLOWED = frozenset({"paused"})
CANCEL_ALLOWED = frozenset({"printing", "paused"}) | PREPARATION_STATES
ALLOWED_STATES = {
    "pause": PAUSE_ALLOWED,
    "resume": RESUME_ALLOWED,
    "cancel": CANCEL_ALLOWED,
}
OBSERVED_STATUS = {
    "pause": "control_observed_paused",
    "resume": "control_observed_resumed",
    "cancel": "control_observed_stopped",
}
CANCEL_CONFIRMED_STATES = frozenset({"stoped", "canceled"})
POLL_COUNT = 5
POLL_INTERVAL = 1


class ControlUncertain(ProtocolError):
    """Post-publish communication, protocol, or interrupt failure retaining safe partial evidence."""

    def __init__(self, result, *, exit_code=3, message=None):
        super().__init__(
            message or "Print control outcome is uncertain; inspect status before taking further action and never resend blindly"
        )
        self.result = result
        self.exit_code = exit_code if exit_code in (2, 3, 130) else 2


def extract_taskid(project):
    if isinstance(project, dict):
        for key in ("task_id", "taskid"):
            value = project.get(key)
            if isinstance(value, str) and TASKID_RE.fullmatch(value) is not None:
                return value
    return "-1"


def transition_confirmed(action, info):
    if not isinstance(info, dict):
        return False
    state = info.get("state")
    project = info.get("project")
    project_state = project.get("state") if isinstance(project, dict) else None
    active_state = isinstance(state, str) and bool(state) and state != "free"
    if action == "pause":
        return active_state and project_state == "paused"
    if action == "resume":
        return active_state and isinstance(project_state, str) and (
            project_state == "printing" or project_state in PREPARATION_STATES
        )
    if action == "cancel":
        return (state == "free" and not project) or (
            isinstance(project_state, str) and project_state in CANCEL_CONFIRMED_STATES
        )
    return False


def control_print(config, action, state_dir, *, expected_filename=None):
    """Execute one guarded print lifecycle control command without retries."""
    if action not in WIRE_ACTIONS:
        raise ProtocolError("Unsupported print control action")
    if expected_filename is not None:
        expected_filename = validate_filename(expected_filename)
    device_digest = hashlib.sha256(config.printer_id.encode()).hexdigest()
    device_dir = Path(state_dir) / device_digest[:16]
    with ExitStack() as resources:
        device_fd = resources.enter_context(device_lock(device_dir, "control"))
        ensure_directory_bound(device_dir, device_fd, action)
        client = resources.enter_context(MQTT(config))
        info = payload_data(client.query("info", require_fresh=True))
        if compatibility_issue(config, info) is not None:
            raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
        info_state = info.get("state")
        project = info.get("project")
        project_state = project.get("state") if isinstance(project, dict) else None
        if (not isinstance(info_state, str) or not info_state or info_state == "free"
                or not isinstance(project, dict) or not isinstance(project_state, str)
                or project_state not in ALLOWED_STATES[action]):
            raise ProtocolError(f"Printer state does not allow print {action}; no control command was sent")
        if expected_filename is not None:
            active_filename = project_filename(project)
            if active_filename != expected_filename:
                raise ProtocolError("Active project filename does not match --filename; no control command was sent")
        taskid = extract_taskid(project)
        ensure_directory_bound(device_dir, device_fd, action)
        wire_action = WIRE_ACTIONS[action]
        result = {
            "action": action,
            "wire_action": wire_action,
            "device_digest": device_digest,
            "model": info["model"],
            "firmware": info["version"],
            "status": "control_uncertain_no_retry",
            "dry_run": False,
            "experimental": True,
            "hardware_control_validated": True,
            "taskid": taskid,
            "before": sanitized(info),
            "before_project": sanitized(project),
        }
        if expected_filename is not None:
            result["expected_filename"] = expected_filename
        try:
            result["ack"] = client.control_once(wire_action, taskid=taskid)
            confirmed = False
            for poll in range(POLL_COUNT):
                after_info = payload_data(client.query("info", require_fresh=True))
                if compatibility_issue(config, after_info) is not None:
                    raise ProtocolError("Post-control status failed qualification check")
                after_project = after_info.get("project") if isinstance(after_info.get("project"), dict) else {}
                result["after"] = sanitized(after_info)
                result["project"] = sanitized(after_project)
                after_filename = project_filename(after_project)
                filename_ok = (expected_filename is None or action == "cancel"
                               or after_filename is None or after_filename == expected_filename)
                if filename_ok and transition_confirmed(action, after_info):
                    result["status"] = OBSERVED_STATUS[action]
                    confirmed = True
                    break
                if poll + 1 < POLL_COUNT:
                    time.sleep(POLL_INTERVAL)
            if not confirmed:
                result["status"] = "control_acknowledged_not_confirmed"
        except KeyboardInterrupt:
            result["status"] = "control_uncertain_no_retry"
            raise ControlUncertain(
                result,
                exit_code=130,
                message="Print control interrupted after publish; inspect status before taking further action and never resend blindly",
            ) from None
        except Exception as error:
            result["status"] = "control_uncertain_no_retry"
            raise ControlUncertain(result, exit_code=mqtt_failure_exit_code(error)) from None
        return result
