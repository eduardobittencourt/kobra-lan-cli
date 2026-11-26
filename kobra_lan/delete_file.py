"""Experimental single-shot deletion of a root-level stored file."""
import hashlib
import os
from pathlib import Path
import time

from .config import ProtocolError
from .mqtt import MQTT, mqtt_failure_exit_code, validate_delete_filename
from .printer import list_files, payload_data, sanitized
from .profiles import open_directory, read_json
from .qualification import info_compatibility_issue, is_delete_hardware_validated
from .start import RECEIPT_SUFFIX, STATUSES, attempt_id, review_digest, valid_attempt_id
from .upload import device_lock, ensure_directory_bound
from .watch import project_filename

POLL_COUNT = 3
POLL_INTERVAL = 1


class DeleteUncertain(ProtocolError):
    """Failure after the delete publish began, with safe evidence collected so far."""

    def __init__(self, result, *, exit_code):
        super().__init__(
            "File deletion outcome is uncertain. Inspect files list before taking further action. Do not resend blindly."
        )
        self.result = result
        self.exit_code = exit_code


def _receipts(directory_fd):
    try:
        names = os.listdir(directory_fd)
    except OSError:
        return
    for name in names:
        key, suffix = os.path.splitext(name)
        if suffix != RECEIPT_SUFFIX or not valid_attempt_id(key):
            continue
        try:
            record = read_json(directory_fd, name)
        except (OSError, ValueError, RecursionError):
            continue
        if isinstance(record, dict):
            yield key, record


def _matching_start_receipt(key, record, device_prefix, filename):
    device = record.get("device_digest")
    file_sha = record.get("file_sha256")
    payload = record.get("payload")
    status = record.get("status")
    if (not valid_attempt_id(device) or device[:16] != device_prefix or not valid_attempt_id(file_sha)
            or record.get("dry_run") is not False or not isinstance(status, str) or status not in STATUSES
            or not isinstance(payload, dict) or payload.get("filename") != filename):
        return False
    previous = record.get("previous_attempt_id")
    if previous is not None and not valid_attempt_id(previous):
        return False
    identity = attempt_id(device, file_sha, previous)
    if key != identity or record.get("attempt_id") != identity:
        return False
    try:
        return record.get("plan_sha256") == review_digest(record, previous)
    except (KeyError, ValueError, RecursionError):
        return False


def summarize_local_state(device_fd, state_dir, device_prefix, filename):
    """Count matching private receipts through read-only descriptors."""
    uploads = sum(
        record.get("sha256") == key and record.get("remote_filename") == filename
        for key, record in _receipts(device_fd)
    )
    starts = 0
    try:
        starts_fd = open_directory(Path(state_dir) / "starts" / device_prefix)
    except OSError:
        pass
    else:
        try:
            starts = sum(
                _matching_start_receipt(key, record, device_prefix, filename)
                for key, record in _receipts(starts_fd)
            )
        finally:
            os.close(starts_fd)
    return {"preserved": True, "matching_upload_receipts": uploads, "matching_start_receipts": starts}


def _qualified_info(config, client):
    info = payload_data(client.query("info", require_fresh=True))
    if info_compatibility_issue(config.type_id, config.printer_id, info) is not None:
        raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
    return info


def _matching_files(client, filename):
    return [record for record in list_files(client) if record.get("filename") == filename]


def delete_file(config, filename, state_dir):
    """Delete one stored root file and check removal on the same pinned session."""
    filename = validate_delete_filename(filename)
    device_digest = hashlib.sha256(config.printer_id.encode()).hexdigest()
    device_prefix = device_digest[:16]
    device_dir = Path(state_dir) / device_prefix
    result = None
    try:
        with device_lock(device_dir) as device_fd:
            ensure_directory_bound(device_dir, device_fd, "delete")
            local_state = summarize_local_state(device_fd, state_dir, device_prefix, filename)
            with MQTT(config) as client:
                info = _qualified_info(config, client)
                project = info.get("project")
                if isinstance(project, dict) and project_filename(project) == filename:
                    raise ProtocolError("Target file is active on the printer")
                if info.get("state") != "free" or project:
                    raise ProtocolError("Stored file deletion requires an idle printer")
                matches = _matching_files(client, filename)
                if not matches:
                    raise ProtocolError("Target file was not found in printer storage")
                if len(matches) != 1:
                    raise ProtocolError("Target file is ambiguous in the printer listing")
                directory_flag = matches[0].get("is_dir")
                if type(directory_flag) not in (bool, int) or directory_flag not in (0, 1):
                    raise ProtocolError("Printer listing did not establish whether the target is a directory")
                if directory_flag:
                    raise ProtocolError("Stored file deletion does not accept directories")
                ensure_directory_bound(device_dir, device_fd, "delete")
                result = {
                    "filename": filename,
                    "device_digest": device_digest,
                    "model": info["model"],
                    "firmware": info["version"],
                    "status": "delete_uncertain_no_retry",
                    "dry_run": False,
                    "experimental": True,
                    "hardware_delete_validated": is_delete_hardware_validated(config.type_id, info["version"]),
                    "before": sanitized(info),
                    "before_listing": matches[0],
                    "local_state": local_state,
                }

                def record_ack(ack):
                    result["ack"] = ack

                def record_report(report):
                    result["report"] = report

                result.update(client.delete_file_once(filename, on_ack=record_ack, on_report=record_report))
                for poll in range(POLL_COUNT):
                    matches = _matching_files(client, filename)
                    result["after_listing"] = matches
                    if not matches:
                        break
                    if poll + 1 < POLL_COUNT:
                        time.sleep(POLL_INTERVAL)
                result["after"] = sanitized(_qualified_info(config, client))
    except (Exception, KeyboardInterrupt) as error:
        if result is None:
            raise
        exit_code = 130 if isinstance(error, KeyboardInterrupt) else mqtt_failure_exit_code(error)
        raise DeleteUncertain(result, exit_code=exit_code) from None
    result["status"] = "delete_acknowledged_not_confirmed" if matches else "delete_observed_removed"
    return result
