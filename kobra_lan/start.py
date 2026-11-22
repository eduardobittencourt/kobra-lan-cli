"""Experimental local-file print/start, single filament, onboard four-slot box.

Hardware start observed on FW 2.0.2.2, PLA High Speed in slot 1, leveling on,
vibration/flow calibration off. Other combinations remain unqualified.
"""
import hashlib
import json
import os
import re
import time
from contextlib import ExitStack
from pathlib import Path

from .config import ProtocolError
from .mqtt import MQTT
from .printer import payload_data, file_details, safe_file_details, sanitized
from .profiles import open_directory, read_json
from .upload import ATTEMPT_SUFFIX, describe, atomic_json, device_lock, ensure_directory_bound, reserve_at

PLAN_FIELDS = ("file_sha256", "device_digest", "model", "firmware", "payload")
ACTIVE = "start_observed_active"
STATUSES = {"start_reserved", "start_acknowledged_not_confirmed", ACTIVE, "start_uncertain_no_retry"}
RECEIPT_SUFFIX = ".json"
MISSING = object()


class StartUncertain(ProtocolError):
    def __init__(self, result):
        super().__init__("Start is uncertain; attempt recorded, inspect status and never resend blindly")
        self.result = result


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def review_digest(plan, previous=None):
    canonical = {field: plan[field] for field in PLAN_FIELDS}
    if previous is None:
        return json_digest(canonical)
    return json_digest({"scope": "reprint", "plan": canonical, "previous_attempt_id": previous})


def valid_attempt_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def attempt_id(device, file_sha256, previous):
    if previous is None:
        return json_digest(["start-root", device, file_sha256])
    return json_digest(["start-successor", previous])


def state_record(directory_fd, name):
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return MISSING
    try:
        record = read_json(directory_fd, name)
        return record if isinstance(record, dict) else None
    except (OSError, ValueError, RecursionError):
        return None


def matching_receipt(marker, receipt, identity, previous, device, file_sha256):
    if not isinstance(marker, dict) or not isinstance(receipt, dict):
        return False
    digest = marker.get("plan_sha256")
    if (not valid_attempt_id(digest) or marker.get("sha256") != file_sha256
            or receipt.get("plan_sha256") != digest or receipt.get("device_digest") != device
            or receipt.get("file_sha256") != file_sha256 or receipt.get("dry_run") is not False
            or not isinstance(receipt.get("payload"), dict)):
        return False
    if previous is None and set(marker) == {"sha256", "plan_sha256"}:
        if "attempt_id" in receipt or "previous_attempt_id" in receipt:
            return False
    elif (marker.get("attempt_id") != identity or marker.get("device_digest") != device
          or marker.get("previous_attempt_id") != previous or receipt.get("attempt_id") != identity
          or receipt.get("previous_attempt_id") != previous):
        return False
    try:
        return review_digest(receipt, previous) == digest
    except (KeyError, ValueError, RecursionError):
        return False


def attempt_outcome(marker, receipt, identity, previous, device, file_sha256):
    if not matching_receipt(marker, receipt, identity, previous, device, file_sha256):
        return None, None
    status = receipt.get("status")
    filename = receipt["payload"].get("filename")
    if not isinstance(status, str) or status not in STATUSES:
        return None, filename
    if status == ACTIVE:
        after, project = receipt.get("after"), receipt.get("project")
        if not isinstance(after, dict) or not active_project(after, project, filename):
            return None, filename
    return status, filename


def latest_attempt(directory_fd, plan):
    if directory_fd is None:
        return None, None, None
    device, file_sha256 = plan["device_digest"], plan["file_sha256"]
    latest = (None, None, None)
    previous = None
    while True:
        identity = attempt_id(device, file_sha256, previous)
        key = file_sha256 if previous is None else identity
        marker = state_record(directory_fd, key + ATTEMPT_SUFFIX)
        receipt = state_record(directory_fd, key + RECEIPT_SUFFIX)
        if marker is MISSING and receipt is MISSING:
            return latest
        if previous is None or latest[1] == ACTIVE:
            status, filename = attempt_outcome(marker, receipt, identity, previous, device, file_sha256)
        else:
            status, filename = None, None
        latest = identity, status, filename
        previous = identity


def active_project(info, project, filename):
    state = info.get("state")
    return (isinstance(state, str) and bool(state) and state != "free"
            and isinstance(filename, str) and isinstance(project, dict) and project.get("filename") == filename)


def reviewed_attempt(plan, directory_fd, previous, execute):
    identity, status, filename = latest_attempt(directory_fd, plan)
    if previous is None:
        if execute and identity is not None:
            raise ProtocolError("Start already attempted; inspect print plan for the latest local attempt")
    elif previous != identity or status != ACTIVE or filename != plan["payload"]["filename"]:
        raise ProtocolError("Reprint requires the latest matching attempt with observed activity; no start was sent")
    if identity is not None:
        plan["attempt_id"] = identity
        if status is not None:
            plan["start_status"] = status
    if previous is not None:
        plan["previous_attempt_id"] = previous
        plan["plan_sha256"] = review_digest(plan, previous)


def build_plan(config, client, path, name, slot, auto_leveling, vibration, flow):
    if slot not in range(1, 5):
        raise ProtocolError("Slot must be 1..4 (human numbering)")
    data, manifest = describe(path, name)
    paints = re.search(rb'^; paint_info = (.*)$', data, re.M)
    if not paints:
        raise ProtocolError("G-code has no paint mapping")
    paints = json.loads(paints.group(1))
    tools = set(re.findall(rb'^T(\d+)(?:\s|$)', data, re.M))
    if (not isinstance(paints, list) or len(paints) != 1 or not isinstance(paints[0], dict)
            or paints[0].get("paint_index") != 0 or tools - {b"0"}):
        raise ProtocolError("Start currently supports only one filament, paint/tool index 0")
    info = payload_data(client.query("info"))
    if info.get("model") != "Anycubic Kobra X" or info.get("version") != "2.0.2.2":
        raise ProtocolError("Unqualified model/firmware for experimental start")
    if info.get("state") != "free" or info.get("project"):
        raise ProtocolError("Printer is not idle")
    remote = safe_file_details(file_details(client, manifest["remote_filename"]))
    if (remote.get("file_size") != manifest["size_bytes"] or remote.get("layer_count") != manifest["layer_count"]
            or remote.get("printer_model") != "Anycubic Kobra X"):
        raise ProtocolError("Remote file metadata does not match the local G-code")
    boxes = payload_data(client.query("multiColorBox", "getInfo")).get("multi_color_box")
    if not isinstance(boxes, list) or len(boxes) != 1 or boxes[0].get("id") != -1:
        raise ProtocolError("Only the onboard four-slot configuration is supported")
    slots = boxes[0].get("slots")
    if not isinstance(slots, list) or len(slots) != 4:
        raise ProtocolError("Unsupported filament box schema")
    selected = [s for s in slots if s.get("index") == slot - 1]
    if len(selected) != 1 or selected[0].get("status") != 5:
        raise ProtocolError("Selected slot is not loaded/available")
    selected = selected[0]
    material = paints[0].get("material_type")
    # PLA High Speed is a PLA variant; PETG must never pass a PLA comparison.
    slot_material = str(selected.get("type", "")).split()
    if not isinstance(material, str) or not slot_material or slot_material[0].upper() != material.upper():
        raise ProtocolError("Selected slot material differs from the G-code")
    color = paints[0].get("paint_color")
    ams_color = selected.get("color")
    for c in [color, ams_color]:
        if not isinstance(c, list) or len(c) not in (3, 4) or not all(type(x) is int and 0 <= x <= 255 for x in c):
            raise ProtocolError("Invalid filament color schema")
    if any(type(v) is not bool for v in [auto_leveling, vibration, flow]):
        raise ProtocolError("Preparation settings must be explicit booleans")
    payload = {
        "taskid": "-1", "url": "", "filename": manifest["remote_filename"],
        "md5": manifest["md5"], "filepath": None, "filetype": 1, "project_type": 1,
        "filesize": manifest["size_bytes"],
        "ams_settings": {"use_ams": True, "ams_box_mapping": [{
            "paint_index": 0, "ams_index": slot - 1,
            "paint_color": color, "ams_color": ams_color + [255] if len(ams_color) == 3 else ams_color,
            "material_type": selected["type"]}]},
        "task_settings": {"auto_leveling": int(auto_leveling), "vibration_compensation": int(vibration),
            "flow_calibration": int(flow), "dry_mode": 0,
            "ai_settings": {"status": 0, "count": 0, "type": 0},
            "timelapse": {"status": 0, "count": 0, "type": 0},
            "drying_settings": {"status": 0, "target_temp": 0, "duration": 0, "remain_time": 0},
            "model_objects_skip_parts": []}}
    # Empty URL starts the stored file; observed on hardware for the case below.
    hardware_validated = (slot == 1 and selected["type"] == "PLA High Speed"
                          and auto_leveling and not vibration and not flow)
    plan = {"file_sha256": manifest["sha256"], "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
            "model": info["model"], "firmware": info["version"], "payload": payload}
    return {**plan, "plan_sha256": review_digest(plan), "dry_run": True,
            "experimental": True, "hardware_start_validated": hardware_validated,
            "selected_slot": slot, "upload_performed": False}


def start(config, path, name, slot, auto_leveling, vibration, flow, state_dir,
          execute=False, expected_plan=None, reprint_from=None):
    if reprint_from is not None and not valid_attempt_id(reprint_from):
        raise ProtocolError("Reprint requires a full local attempt ID from print plan")
    device = hashlib.sha256(config.printer_id.encode()).hexdigest()[:16]
    device_dir = Path(state_dir) / device
    starts_dir = Path(state_dir) / "starts" / device
    with ExitStack() as resources:
        if execute:
            device_fd = resources.enter_context(device_lock(device_dir, "start"))
        starts_fd = open_starts(resources, starts_dir)
        if execute:
            ensure_directory_bound(device_dir, device_fd, "start")
        client = resources.enter_context(MQTT(config))
        plan = build_plan(config, client, path, name, slot, auto_leveling, vibration, flow)
        reviewed_attempt(plan, starts_fd, reprint_from, execute)
        if not execute:
            return plan
        if plan["plan_sha256"] != expected_plan:
            raise ProtocolError("Start plan changed or was not reviewed; no start was sent")
        uploaded = state_record(device_fd, plan["file_sha256"] + RECEIPT_SUFFIX)
        if (not isinstance(uploaded, dict) or uploaded.get("status") != "uploaded_verified_by_listing_and_metadata"
                or uploaded.get("remote_filename") != plan["payload"]["filename"]
                or uploaded.get("sha256") != plan["file_sha256"]):
            raise ProtocolError("Start requires a verified upload receipt matching the reviewed plan")
        info = payload_data(client.query("info", require_fresh=True))
        if info.get("state") != "free" or info.get("project"):
            raise ProtocolError("Printer became busy; no start was sent")
        ensure_directory_bound(device_dir, device_fd, "start")
        if starts_fd is None:
            starts_fd = open_starts(resources, starts_dir, create=True)
            reviewed_attempt(plan, starts_fd, reprint_from, execute)
        return publish_start(client, plan, starts_dir, starts_fd, device_dir, device_fd, reprint_from)


def open_starts(resources, directory, create=False):
    try:
        directory_fd = open_directory(directory, create=create)
    except FileNotFoundError:
        if create:
            raise
        return None
    resources.callback(os.close, directory_fd)
    return directory_fd


def publish_start(client, plan, starts_dir, starts_fd, device_dir, device_fd, previous):
    def check_state():
        ensure_directory_bound(device_dir, device_fd, "start")
        ensure_directory_bound(starts_dir, starts_fd, "start")

    file_sha256 = plan["file_sha256"]
    identity = attempt_id(plan["device_digest"], file_sha256, previous)
    key = file_sha256 if previous is None else identity
    attempt = starts_dir / (key + RECEIPT_SUFFIX)
    receipt = {field: value for field, value in plan.items() if field != "start_status"}
    receipt.update(attempt_id=identity, dry_run=False, status="start_reserved", timestamp=int(time.time()))
    marker = {field: receipt[field] for field in ("attempt_id", "device_digest", "plan_sha256")}
    marker.update(sha256=file_sha256, previous_attempt_id=previous)
    check_state()
    reserve_at(starts_fd, marker, key=key, operation="start")
    try:
        atomic_json(attempt, receipt, directory_fd=starts_fd)
        check_state()
        receipt["ack"] = client.start_once(plan["payload"])
        receipt["status"] = "start_acknowledged_not_confirmed"
        atomic_json(attempt, receipt, directory_fd=starts_fd)
        for _ in range(5):
            info = payload_data(client.query("info", require_fresh=True))
            project = info.get("project") or {}
            receipt["after"] = sanitized(info)
            receipt["project"] = sanitized(project)
            if active_project(info, project, plan["payload"]["filename"]):
                receipt["status"] = ACTIVE
                break
            time.sleep(1)
        check_state()
        atomic_json(attempt, receipt, directory_fd=starts_fd)
        check_state()
    except Exception:
        receipt["status"] = "start_uncertain_no_retry"
        try:
            atomic_json(attempt, receipt, directory_fd=starts_fd)
        except (OSError, ValueError):
            pass
        partial = {field: receipt[field] for field in ("attempt_id", "previous_attempt_id", "status", "ack", "after", "project")
                   if field in receipt}
        raise StartUncertain(partial) from None
    return {**receipt, "receipt_path": str(attempt)}
