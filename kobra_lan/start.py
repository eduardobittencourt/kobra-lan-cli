"""Experimental local-file print/start, single filament, onboard four-slot box.

Code and dry runs tested; a real print/start has NOT yet been qualified.
"""
import hashlib
import json
import re
import time
from pathlib import Path

from .config import ProtocolError
from .mqtt import MQTT
from .printer import payload_data, file_details, safe_file_details, sanitized
from .upload import describe, atomic_json, reserve


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
    # Empty URL requests the already uploaded local filename; this remains untested on hardware.
    plan = {"file_sha256": manifest["sha256"], "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
            "model": info["model"], "firmware": info["version"], "payload": payload}
    return {**plan, "plan_sha256": json_digest(plan), "dry_run": True,
            "experimental": True, "hardware_start_validated": False,
            "selected_slot": slot, "upload_performed": False}


def start(config, path, name, slot, auto_leveling, vibration, flow, state_dir,
          execute=False, expected_plan=None):
    with MQTT(config) as client:
        plan = build_plan(config, client, path, name, slot, auto_leveling, vibration, flow)
        if not execute:
            return plan
        if plan["plan_sha256"] != expected_plan:
            raise ProtocolError("Start plan changed or was not reviewed; no start was sent")
        # Require our verified upload receipt as provenance; never uploads again.
        device = hashlib.sha256(config.printer_id.encode()).hexdigest()[:16]
        upload_receipt = Path(state_dir) / device / (plan["file_sha256"] + ".json")
        if not upload_receipt.exists():
            raise ProtocolError("Start requires a verified upload receipt from this client")
        uploaded = json.loads(upload_receipt.read_text())
        if (uploaded.get("status") != "uploaded_verified_by_listing_and_metadata"
                or uploaded.get("remote_filename") != plan["payload"]["filename"]
                or uploaded.get("sha256") != plan["file_sha256"]):
            raise ProtocolError("Upload receipt does not match the reviewed start plan")
        # Recheck idle state immediately before durable reservation and publish.
        info = payload_data(client.query("info"))
        if info.get("state") != "free" or info.get("project"):
            raise ProtocolError("Printer became busy; no start was sent")
        receipt = {**plan, "dry_run": False, "status": "start_reserved", "timestamp": int(time.time())}
        attempt = reserve(Path(state_dir) / "starts" / device,
                          {"sha256": plan["file_sha256"], "plan_sha256": plan["plan_sha256"]})
        atomic_json(attempt, receipt)
        try:
            receipt["ack"] = client.start_once(plan["payload"])
            receipt["status"] = "start_acknowledged_not_confirmed"
            atomic_json(attempt, receipt)
            # Bounded read-only observation, no start retry even if the ACK is ambiguous.
            for _ in range(5):
                info = payload_data(client.query("info"))
                project = info.get("project") or {}
                receipt["after"] = sanitized(info)
                receipt["project"] = sanitized(project)
                if info.get("state") != "free" and project.get("filename") == plan["payload"]["filename"]:
                    receipt["status"] = "start_observed_active"
                    break
                time.sleep(1)
            atomic_json(attempt, receipt)
        except Exception:
            receipt["status"] = "start_uncertain_no_retry"
            atomic_json(attempt, receipt)
            raise ProtocolError("Start is uncertain; attempt recorded, inspect status and never resend blindly") from None
        return {**receipt, "receipt_path": str(attempt)}
