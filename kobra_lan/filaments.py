"""Shared G-code filament/color parsing and read-only onboard slot inventory."""
import hashlib
import json
import math
import re

from .config import ProtocolError
from .diagnostics import compatibility_issue
from .mqtt import MQTT, MQTTClosed
from .printer import payload_data

PAINT_INFO_RE = re.compile(rb"^; paint_info = (.*)$", re.M)
TOOL_RE = re.compile(rb"^T(\d+)(?:[\s;]|$)", re.M)
FILAMENT_USED_G_RE = re.compile(rb"^; filament used \[g\] = (.*)$", re.M)
TOTAL_FILAMENT_USED_G_RE = re.compile(rb"^; total filament used \[g\] = (.*)$", re.M)


def normalize_color(color):
    """Validate 3- or 4-channel integer RGB/RGBA values in 0..255 and return ([R, G, B], '#RRGGBB')."""
    if (not isinstance(color, list) or len(color) not in (3, 4)
            or not all(type(channel) is int and 0 <= channel <= 255 for channel in color)):
        raise ProtocolError("Invalid filament color schema")
    rgb = [color[0], color[1], color[2]]
    return rgb, f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _parse_paint_info_line(raw_line):
    try:
        parsed = json.loads(raw_line.strip().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ProtocolError("Malformed G-code paint_info metadata") from None
    if not isinstance(parsed, list) or not parsed:
        raise ProtocolError("Malformed G-code paint_info metadata")
    entries = []
    seen_indices = set()
    for item in parsed:
        if not isinstance(item, dict):
            raise ProtocolError("Malformed G-code paint_info entry")
        paint_index = item.get("paint_index")
        if type(paint_index) is not int or paint_index < 0 or paint_index in seen_indices:
            raise ProtocolError("Invalid or duplicate paint_index in G-code paint_info")
        seen_indices.add(paint_index)
        material = item.get("material_type")
        if (not isinstance(material, str) or not material.strip() or len(material) > 80
                or not material.isascii() or not material.isprintable()):
            raise ProtocolError("Invalid material_type in G-code paint_info")
        color_rgb, color_hex = normalize_color(item.get("paint_color"))
        entries.append({
            "paint_index": paint_index,
            "material_type": material.strip(),
            "color_rgb": color_rgb,
            "color_hex": color_hex,
        })
    entries.sort(key=lambda entry: entry["paint_index"])
    return entries


def _parse_weight(raw_value):
    try:
        value = float(raw_value.strip())
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _parse_filament_weights(data):
    per_index = None
    used_matches = FILAMENT_USED_G_RE.findall(data)
    if used_matches:
        try:
            parts = used_matches[-1].decode("ascii").split(",")
        except UnicodeDecodeError:
            parts = []
        parsed = [_parse_weight(part) for part in parts]
        if parsed and all(value is not None for value in parsed):
            per_index = parsed
    total_used = None
    total_matches = TOTAL_FILAMENT_USED_G_RE.findall(data)
    if total_matches:
        try:
            total_used = _parse_weight(total_matches[-1].decode("ascii"))
        except UnicodeDecodeError:
            total_used = None
    return per_index, total_used


def inspect_gcode_filaments(data):
    """Parse all paint_info lines, T<n> tools, and optional weights from G-code bytes."""
    paint_matches = list(PAINT_INFO_RE.finditer(data))
    declarations = [_parse_paint_info_line(match.group(1)) for match in paint_matches]
    if len(declarations) > 1:
        canonical = declarations[0]
        if any(other != canonical for other in declarations[1:]):
            raise ProtocolError("Conflicting paint_info declarations in G-code")
    paint_info_present = bool(declarations)
    per_index_weights, total_filament_used_g = _parse_filament_weights(data)
    filaments = []
    if paint_info_present:
        for entry in declarations[0]:
            weight = None
            if per_index_weights is not None and entry["paint_index"] < len(per_index_weights):
                weight = per_index_weights[entry["paint_index"]]
            filaments.append({**entry, "filament_used_g": weight})
    tool_indices = sorted({int(match.group(1)) for match in TOOL_RE.finditer(data)})
    multicolor = len(filaments) > 1 or len(tool_indices) > 1
    single_filament_start_compatible = (
        paint_info_present
        and len(filaments) == 1
        and filaments[0]["paint_index"] == 0
        and set(tool_indices) <= {0}
    )
    return {
        "paint_info_present": paint_info_present,
        "filaments": filaments,
        "filament_count": len(filaments),
        "multicolor": multicolor,
        "tool_indices": tool_indices,
        "total_filament_used_g": total_filament_used_g,
        "single_filament_start_compatible": single_filament_start_compatible,
    }


def _sanitize_slot_material(raw_type):
    if raw_type is None:
        return None
    if not isinstance(raw_type, str):
        raise ProtocolError("Unsupported filament box schema")
    candidate = raw_type.strip()
    if (not candidate or len(candidate) > 80 or not candidate.isprintable()
            or "://" in candidate or "-----BEGIN" in candidate):
        return None
    return candidate


def _parse_slot_color(raw_color):
    if raw_color is None or raw_color == [] or raw_color == "":
        return None, None
    if not isinstance(raw_color, list):
        raise ProtocolError("Invalid filament color schema")
    try:
        return normalize_color(raw_color)
    except ProtocolError:
        return None, None


def parse_onboard_box(boxes):
    """Validate and sanitize the qualified Kobra X onboard four-slot box payload."""
    if not isinstance(boxes, list) or len(boxes) != 1 or not isinstance(boxes[0], dict):
        raise ProtocolError("Only the onboard four-slot configuration is supported")
    box_id = boxes[0].get("id")
    if type(box_id) is not int or box_id != -1:
        raise ProtocolError("Only the onboard four-slot configuration is supported")
    raw_slots = boxes[0].get("slots")
    if not isinstance(raw_slots, list) or len(raw_slots) != 4 or not all(isinstance(s, dict) for s in raw_slots):
        raise ProtocolError("Unsupported filament box schema")
    by_index = {}
    for raw in raw_slots:
        ams_index = raw.get("index")
        if type(ams_index) is not int or ams_index not in (0, 1, 2, 3) or ams_index in by_index:
            raise ProtocolError("Unsupported filament box schema")
        by_index[ams_index] = raw
    slots = []
    for ams_index in range(4):
        raw = by_index[ams_index]
        status = raw.get("status")
        if type(status) is not int:
            raise ProtocolError("Unsupported filament box schema")
        if status == 5:
            status_label = "loaded"
        elif status == 0:
            status_label = "empty"
        else:
            status_label = "other"
        material_type = _sanitize_slot_material(raw.get("type"))
        color_rgb, color_hex = _parse_slot_color(raw.get("color"))
        available_for_start = status == 5 and material_type is not None and color_rgb is not None
        slots.append({
            "slot": ams_index + 1,
            "ams_index": ams_index,
            "status": status,
            "status_label": status_label,
            "available_for_start": available_for_start,
            "material_type": material_type,
            "color_rgb": color_rgb,
            "color_hex": color_hex,
        })
    return {
        "box_id": -1,
        "box_kind": "onboard",
        "slot_count": 4,
        "loaded_count": sum(1 for item in slots if item["status_label"] == "loaded"),
        "slots": slots,
    }


def list_slots(config):
    """Query onboard four-slot filament inventory over one pinned read-only MQTT session."""
    try:
        with MQTT(config) as client:
            info = payload_data(client.query("info", require_fresh=True))
            if compatibility_issue(config, info) is not None:
                raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
            box_data = payload_data(client.query("multiColorBox", "getInfo"))
            box = parse_onboard_box(box_data.get("multi_color_box"))
    except MQTTClosed as error:
        raise ConnectionError("MQTT connection closed") from error
    return {
        "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
        "model": info["model"],
        "firmware": info["version"],
        "printer_state": info["state"],
        **box,
    }
