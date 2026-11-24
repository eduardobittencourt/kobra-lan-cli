"""Experimental local-file print/start using the onboard four-slot box.

Hardware start observed on FW 2.0.2.2, PLA High Speed in slots 1, 2, and 4,
leveling on, vibration/flow calibration off. Other combinations remain unqualified.
"""
import hashlib
import json
import os
import re
import time
from contextlib import ExitStack
from pathlib import Path

from .config import ProtocolError
from .filaments import inspect_gcode_filaments, parse_onboard_box, validate_color_channels
from .mqtt import MQTT
from .printer import payload_data, file_details, safe_file_details, sanitized
from .profiles import open_directory, read_json
from .qualification import (
    info_compatibility_issue,
    is_qualified_remote_model,
    is_start_hardware_validated,
    is_valid_onboard_slot,
    onboard_topology,
)
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


def build_plan(config, client, path, name, slot_map, auto_leveling, vibration, flow):
    topology = onboard_topology(config.type_id)
    max_slot = topology.slot_count if topology is not None else 0
    if not isinstance(slot_map, dict) or not slot_map or any(
        type(index) is not int or index < 0 or not is_valid_onboard_slot(config.type_id, slot)
        for index, slot in slot_map.items()
    ):
        raise ProtocolError(f"Slot mapping requires non-negative paint indices and onboard slots 1..{max_slot}")
    data, manifest = describe(path, name)
    filament_info, raw_paint_colors = inspect_gcode_filaments(data, return_raw_colors=True)
    if not filament_info["paint_info_present"]:
        raise ProtocolError("G-code has no paint mapping")
    filaments = filament_info["filaments"]
    declared_indices = {filament["paint_index"] for filament in filaments}
    if not set(filament_info["tool_indices"]) <= declared_indices:
        raise ProtocolError("G-code uses a tool index absent from paint_info")
    if slot_map.keys() != declared_indices:
        raise ProtocolError("Slot mapping must cover exactly the paint indices declared in paint_info")
    info = payload_data(client.query("info"))
    if info_compatibility_issue(config.type_id, config.printer_id, info) is not None:
        raise ProtocolError("Unqualified model/firmware for experimental start")
    if info.get("state") != "free" or info.get("project"):
        raise ProtocolError("Printer is not idle")
    remote = safe_file_details(file_details(client, manifest["remote_filename"]))
    if (remote.get("file_size") != manifest["size_bytes"] or remote.get("layer_count") != manifest["layer_count"]
            or not is_qualified_remote_model(config.type_id, remote.get("printer_model"))):
        raise ProtocolError("Remote file metadata does not match the local G-code")
    boxes = payload_data(client.query("multiColorBox", "getInfo")).get("multi_color_box")
    box = parse_onboard_box(boxes, model_id=config.type_id)
    ams_box_mapping, slot_mapping = build_slot_mappings(
        slot_map, filaments, raw_paint_colors, box["slots"], boxes[0]["slots"],
    )
    if any(type(v) is not bool for v in [auto_leveling, vibration, flow]):
        raise ProtocolError("Preparation settings must be explicit booleans")
    payload = {
        "taskid": "-1", "url": "", "filename": manifest["remote_filename"],
        "md5": manifest["md5"], "filepath": None, "filetype": 1, "project_type": 1,
        "filesize": manifest["size_bytes"],
        "ams_settings": {"use_ams": True, "ams_box_mapping": ams_box_mapping},
        "task_settings": {"auto_leveling": int(auto_leveling), "vibration_compensation": int(vibration),
            "flow_calibration": int(flow), "dry_mode": 0,
            "ai_settings": {"status": 0, "count": 0, "type": 0},
            "timelapse": {"status": 0, "count": 0, "type": 0},
            "drying_settings": {"status": 0, "target_temp": 0, "duration": 0, "remain_time": 0},
            "model_objects_skip_parts": []}}
    # Empty URL starts the stored file; observed on hardware for the cases below.
    multicolor = len(ams_box_mapping) > 1
    hardware_validated = is_start_hardware_validated(
        config.type_id,
        info["version"],
        slot_map=slot_map,
        materials={entry["paint_index"]: entry["material_type"] for entry in ams_box_mapping},
        auto_leveling=auto_leveling,
        vibration_compensation=vibration,
        flow_calibration=flow,
    )
    plan = {"file_sha256": manifest["sha256"], "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
            "model": info["model"], "firmware": info["version"], "payload": payload}
    return {**plan, "plan_sha256": review_digest(plan), "dry_run": True,
            "experimental": True, "hardware_start_validated": hardware_validated,
            "slot_mapping": slot_mapping, "multicolor": multicolor, "upload_performed": False}


def build_slot_mappings(slot_map, filaments, raw_paint_colors, slots, raw_slots):
    raw_by_index = {raw["index"]: raw for raw in raw_slots}
    ams_box_mapping = []
    slot_mapping = []
    # The G-code parser supplies filaments in ascending paint_index order.
    for filament in filaments:
        paint_index = filament["paint_index"]
        slot = slot_map[paint_index]
        ams_index = slot - 1
        selected = slots[ams_index]
        if selected["status"] != 5 or not selected["available_for_start"]:
            raise ProtocolError(f"Mapped slot {slot} is not loaded/available")
        gcode_material = filament["material_type"]
        slot_material = selected["material_type"]
        if slot_material.split()[0].upper() != gcode_material.upper():
            raise ProtocolError(f"Mapped slot {slot} material differs from the G-code")
        ams_color = validate_color_channels(raw_by_index[ams_index].get("color"))
        if len(ams_color) == 3:
            ams_color.append(255)
        ams_box_mapping.append({
            "paint_index": paint_index, "ams_index": ams_index,
            "paint_color": raw_paint_colors[paint_index], "ams_color": ams_color,
            "material_type": slot_material,
        })
        slot_mapping.append({
            "paint_index": paint_index, "slot": slot, "ams_index": ams_index,
            "gcode_material_type": gcode_material, "gcode_color_hex": filament["color_hex"],
            "slot_material_type": slot_material, "slot_color_hex": selected["color_hex"],
        })
    return ams_box_mapping, slot_mapping


def start(config, path, name, slot_map, auto_leveling, vibration, flow, state_dir,
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
        plan = build_plan(config, client, path, name, slot_map, auto_leveling, vibration, flow)
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
