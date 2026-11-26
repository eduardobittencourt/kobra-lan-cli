"""Shared G-code filament/color parsing and read-only onboard slot inventory."""
import hashlib
import json
import math
import re

from .config import ProtocolError
from .mqtt import MQTT, MQTTClosed
from .printer import payload_data
from .qualification import KOBRA_X, info_compatibility_issue, onboard_topology

PAINT_INFO_RE = re.compile(rb"^; paint_info = (.*)$", re.M)
TOOL_RE = re.compile(rb"^T(\d+)(?:[\s;]|$)", re.M)
FILAMENT_USED_G_RE = re.compile(rb"^; filament used \[g\] = (.*)$", re.M)
TOTAL_FILAMENT_USED_G_RE = re.compile(rb"^; total filament used \[g\] = (.*)$", re.M)
UNSUPPORTED_BOX_SCHEMA = "Unsupported filament box schema"
STATUS_LABELS = {5: "loaded", 0: "empty"}


def validate_color_channels(color):
    """Validate 3- or 4-channel integer RGB/RGBA values in 0..255 and return a channel copy."""
    if (not isinstance(color, list) or len(color) not in (3, 4)
            or not all(type(channel) is int and 0 <= channel <= 255 for channel in color)):
        raise ProtocolError("Invalid filament color schema")
    return list(color)


def normalize_color(color):
    """Validate 3- or 4-channel integer RGB/RGBA values in 0..255 and return ([R, G, B], '#RRGGBB')."""
    channels = validate_color_channels(color)
    rgb = channels[:3]
    return rgb, f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _parse_paint_info_line(raw_line):
    try:
        parsed = json.loads(raw_line.strip().decode("utf-8"))
    except (ValueError, RecursionError):
        raise ProtocolError("Malformed G-code paint_info metadata") from None
    if not isinstance(parsed, list) or not parsed:
        raise ProtocolError("Malformed G-code paint_info metadata")
    entries = []
    raw_colors = {}
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
        channels = validate_color_channels(item.get("paint_color"))
        color_rgb, color_hex = normalize_color(channels)
        raw_colors[paint_index] = channels
        entries.append({
            "paint_index": paint_index,
            "material_type": material.strip(),
            "color_rgb": color_rgb,
            "color_hex": color_hex,
        })
    entries.sort(key=lambda entry: entry["paint_index"])
    return entries, raw_colors


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


def inspect_gcode_filaments(data, *, return_raw_colors=False):
    """Parse all paint_info lines, T<n> tools, and optional weights from G-code bytes."""
    paint_matches = list(PAINT_INFO_RE.finditer(data))
    parsed_lines = [_parse_paint_info_line(match.group(1)) for match in paint_matches]
    declarations = [entries for entries, _ in parsed_lines]
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
    result = {
        "paint_info_present": paint_info_present,
        "filaments": filaments,
        "filament_count": len(filaments),
        "multicolor": multicolor,
        "tool_indices": tool_indices,
        "total_filament_used_g": total_filament_used_g,
    }
    if return_raw_colors:
        return result, (parsed_lines[0][1] if parsed_lines else {})
    return result


def _sanitize_slot_material(raw_type):
    if raw_type is None:
        return None
    if not isinstance(raw_type, str):
        raise ProtocolError(UNSUPPORTED_BOX_SCHEMA)
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


def _parse_onboard_slot(ams_index, raw):
    status = raw.get("status")
    if type(status) is not int:
        raise ProtocolError(UNSUPPORTED_BOX_SCHEMA)
    status_label = STATUS_LABELS.get(status, "other")
    material_type = _sanitize_slot_material(raw.get("type"))
    color_rgb, color_hex = _parse_slot_color(raw.get("color"))
    return {
        "slot": ams_index + 1,
        "ams_index": ams_index,
        "status": status,
        "status_label": status_label,
        "available_for_start": status == 5 and material_type is not None and color_rgb is not None,
        "material_type": material_type,
        "color_rgb": color_rgb,
        "color_hex": color_hex,
    }


def _index_onboard_slots(raw_slots, slot_count):
    if not isinstance(raw_slots, list) or len(raw_slots) != slot_count or not all(isinstance(s, dict) for s in raw_slots):
        raise ProtocolError(UNSUPPORTED_BOX_SCHEMA)
    by_index = {}
    for raw in raw_slots:
        ams_index = raw.get("index")
        if type(ams_index) is not int or ams_index not in range(slot_count) or ams_index in by_index:
            raise ProtocolError(UNSUPPORTED_BOX_SCHEMA)
        by_index[ams_index] = raw
    return by_index


def parse_onboard_box(boxes, *, model_id=KOBRA_X.model_id):
    """Validate and sanitize the qualified Kobra X onboard four-slot box payload."""
    topology = onboard_topology(model_id)
    if topology is None or not isinstance(boxes, list) or len(boxes) != 1 or not isinstance(boxes[0], dict):
        raise ProtocolError("Only the onboard four-slot configuration is supported")
    box_id = boxes[0].get("id")
    if type(box_id) is not int or box_id != topology.box_id:
        raise ProtocolError("Only the onboard four-slot configuration is supported")
    by_index = _index_onboard_slots(boxes[0].get("slots"), topology.slot_count)
    slots = [_parse_onboard_slot(ams_index, by_index[ams_index]) for ams_index in range(topology.slot_count)]
    return {
        "box_id": topology.box_id,
        "box_kind": topology.box_kind,
        "slot_count": topology.slot_count,
        "loaded_count": sum(1 for item in slots if item["status_label"] == "loaded"),
        "slots": slots,
    }


def list_slots(config):
    """Query onboard four-slot filament inventory over one pinned read-only MQTT session."""
    try:
        with MQTT(config) as client:
            info = payload_data(client.query("info", require_fresh=True))
            if info_compatibility_issue(config.type_id, config.printer_id, info) is not None:
                raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
            box_data = payload_data(client.query("multiColorBox", "getInfo"))
            box = parse_onboard_box(box_data.get("multi_color_box"), model_id=config.type_id)
    except MQTTClosed as error:
        raise ConnectionError("MQTT connection closed") from error
    return {
        "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
        "model": info["model"],
        "firmware": info["version"],
        "printer_state": info["state"],
        **box,
    }
