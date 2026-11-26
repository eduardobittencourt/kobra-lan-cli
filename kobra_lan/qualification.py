"""Authoritative hardware qualification definitions and pure validation predicates.

Leaf module with stdlib-only imports so every layer of kobra_lan derives
qualified printer identity, firmware, slicer markers, onboard box topology,
and per-operation hardware-evidence flags from one place.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

QUALIFIED_FIRMWARE = "2.0.2.2"


@dataclass(frozen=True)
class OnboardBoxTopology:
    box_id: int
    box_kind: str
    slot_count: int


@dataclass(frozen=True)
class StartHardwareEvidence:
    slot_maps: frozenset[tuple[tuple[int, int], ...]]
    materials: frozenset[str]
    auto_leveling: bool
    vibration_compensation: bool
    flow_calibration: bool
    allow_any_distinct_onboard_slot_map: bool = False
    allow_shared_onboard_slots: bool = False


@dataclass(frozen=True)
class PrinterQualification:
    model_id: int
    model_name: str
    short_name: str
    firmware_versions: frozenset[str]
    slicer_name: str
    gcode_model_marker: bytes
    onboard_box: OnboardBoxTopology
    start_evidence: tuple[StartHardwareEvidence, ...]
    control_hardware_validated: bool
    delete_hardware_validated: bool
    camera_hardware_validated: bool = False
    discovery_hardware_validated: bool = False


KOBRA_X = PrinterQualification(
    model_id=20030,
    model_name="Anycubic Kobra X",
    short_name="Kobra X",
    firmware_versions=frozenset({QUALIFIED_FIRMWARE}),
    slicer_name="AnycubicSlicerNext",
    gcode_model_marker=b"; printer_model = Anycubic Kobra X",
    onboard_box=OnboardBoxTopology(box_id=-1, box_kind="onboard", slot_count=4),
    start_evidence=(
        StartHardwareEvidence(
            slot_maps=frozenset(),
            materials=frozenset({"PLA High Speed"}),
            auto_leveling=True,
            vibration_compensation=False,
            flow_calibration=False,
            allow_any_distinct_onboard_slot_map=True,
            allow_shared_onboard_slots=True,
        ),
        StartHardwareEvidence(
            slot_maps=frozenset(),
            materials=frozenset({"PLA High Speed"}),
            auto_leveling=False,
            vibration_compensation=False,
            flow_calibration=False,
            allow_any_distinct_onboard_slot_map=True,
            allow_shared_onboard_slots=True,
        ),
        StartHardwareEvidence(
            slot_maps=frozenset(),
            materials=frozenset({"PLA High Speed"}),
            auto_leveling=False,
            vibration_compensation=True,
            flow_calibration=False,
            allow_any_distinct_onboard_slot_map=True,
            allow_shared_onboard_slots=True,
        ),
        StartHardwareEvidence(
            slot_maps=frozenset(),
            materials=frozenset({"PLA High Speed"}),
            auto_leveling=False,
            vibration_compensation=False,
            flow_calibration=True,
            allow_any_distinct_onboard_slot_map=True,
            allow_shared_onboard_slots=True,
        ),
        StartHardwareEvidence(
            slot_maps=frozenset({((0, 4),)}),
            materials=frozenset({"PETG"}),
            auto_leveling=True,
            vibration_compensation=False,
            flow_calibration=False,
        ),
    ),
    control_hardware_validated=True,
    delete_hardware_validated=True,
    camera_hardware_validated=True,
    discovery_hardware_validated=True,
)

QUALIFIED_PRINTERS = MappingProxyType({KOBRA_X.model_id: KOBRA_X})
QUALIFICATION_SUMMARY = (
    f"{KOBRA_X.short_name} model {KOBRA_X.model_id} / "
    f"firmware {', '.join(sorted(KOBRA_X.firmware_versions))}"
)


def qualification_for_model_id(model_id):
    """Return the immutable PrinterQualification for an exact integer model ID, or None."""
    if type(model_id) is not int:
        return None
    return QUALIFIED_PRINTERS.get(model_id)


def _parse_qualified_model_id(value):
    if type(value) is int:
        return value if value in QUALIFIED_PRINTERS else None
    if type(value) is str:
        for model_id in QUALIFIED_PRINTERS:
            if value == str(model_id):
                return model_id
    return None


def normalize_qualified_model_id(values):
    """Normalize one or more candidate modelId/modeId values to a single qualified int ID."""
    items = list(values)
    if not items:
        return None
    parsed = [_parse_qualified_model_id(value) for value in items]
    if any(item is None for item in parsed) or len(set(parsed)) != 1:
        return None
    return parsed[0]


def is_qualified_profile_firmware(version):
    """Accept None or any firmware version declared by a qualified printer profile."""
    if version is None:
        return True
    return type(version) is str and any(
        version in profile.firmware_versions for profile in QUALIFIED_PRINTERS.values()
    )


def _valid_printer_state(state):
    return (
        isinstance(state, str)
        and 0 < len(state) <= 80
        and state.isascii()
        and state.isprintable()
    )


def info_compatibility_issue(model_id, printer_id, info):
    """Evaluate fresh MQTT info report against a qualified printer profile.

    Returns None when qualified, 'outside_qualification' on any conflict or
    unqualified target, or 'qualification_incomplete' when required fields are
    omitted without conflicting values.
    """
    profile = qualification_for_model_id(model_id)
    if profile is None or not isinstance(info, Mapping):
        return "outside_qualification"
    model = info.get("model")
    version = info.get("version")
    state = info.get("state")
    if (
        (model is not None and model != profile.model_name)
        or (version is not None and (type(version) is not str or version not in profile.firmware_versions))
        or any(
            type(info[key]) not in (int, str) or str(info[key]) != str(profile.model_id)
            for key in ("modelId", "modeId")
            if key in info
        )
        or ("deviceId" in info and info["deviceId"] != printer_id)
        or (state is not None and not _valid_printer_state(state))
    ):
        return "outside_qualification"
    if any(info.get(key) is None for key in ("model", "version", "state")):
        return "qualification_incomplete"
    return None


def is_qualified_remote_model(model_id, remote_model):
    """Return True when remote file metadata printer_model matches the qualified profile."""
    profile = qualification_for_model_id(model_id)
    return profile is not None and type(remote_model) is str and remote_model == profile.model_name


def matches_slicer_model_marker(data, model_id=None):
    """Return True when G-code bytes declare a qualified printer_model marker."""
    if not isinstance(data, (bytes, bytearray)):
        return False
    if model_id is not None:
        profile = qualification_for_model_id(model_id)
        return profile is not None and profile.gcode_model_marker in data
    return any(profile.gcode_model_marker in data for profile in QUALIFIED_PRINTERS.values())


def onboard_topology(model_id=KOBRA_X.model_id):
    """Return the qualified onboard filament-box topology for model_id, or None."""
    profile = qualification_for_model_id(model_id)
    return profile.onboard_box if profile is not None else None


def is_valid_onboard_slot(model_id, slot):
    """Return True when slot is an exact integer within the model's 1..N onboard range."""
    topology = onboard_topology(model_id)
    return topology is not None and type(slot) is int and 1 <= slot <= topology.slot_count


def _evidence_matches_slot_map(evidence, normalized_map):
    if normalized_map in evidence.slot_maps:
        return True
    slots = [slot for _, slot in normalized_map]
    has_shared_slot = len(set(slots)) < len(slots)
    if has_shared_slot:
        return evidence.allow_shared_onboard_slots
    return evidence.allow_any_distinct_onboard_slot_map


def is_start_hardware_validated(
    model_id,
    firmware,
    *,
    slot_map,
    materials,
    auto_leveling,
    vibration_compensation,
    flow_calibration,
):
    """Return True only for start combinations matching recorded live hardware evidence."""
    profile = qualification_for_model_id(model_id)
    if (
        profile is None
        or type(firmware) is not str
        or firmware not in profile.firmware_versions
        or any(type(flag) is not bool for flag in (auto_leveling, vibration_compensation, flow_calibration))
        or not isinstance(slot_map, Mapping)
        or not slot_map
        or not isinstance(materials, Mapping)
        or set(materials.keys()) != set(slot_map.keys())
    ):
        return False
    for paint_index, slot in slot_map.items():
        if (
            type(paint_index) is not int
            or paint_index < 0
            or not is_valid_onboard_slot(model_id, slot)
            or type(materials[paint_index]) is not str
        ):
            return False
    normalized_map = tuple(sorted(slot_map.items()))
    return any(
        _evidence_matches_slot_map(evidence, normalized_map)
        and all(materials[paint_index] in evidence.materials for paint_index in slot_map)
        and auto_leveling is evidence.auto_leveling
        and vibration_compensation is evidence.vibration_compensation
        and flow_calibration is evidence.flow_calibration
        for evidence in profile.start_evidence
    )


def is_control_hardware_validated(model_id, firmware):
    """Return True when lifecycle controls are hardware-validated for model_id and firmware."""
    profile = qualification_for_model_id(model_id)
    return (
        profile is not None
        and type(firmware) is str
        and firmware in profile.firmware_versions
        and profile.control_hardware_validated
    )


def is_delete_hardware_validated(model_id, firmware):
    """Return True when stored-file deletion is hardware-validated for model_id and firmware."""
    profile = qualification_for_model_id(model_id)
    return (
        profile is not None
        and type(firmware) is str
        and firmware in profile.firmware_versions
        and profile.delete_hardware_validated
    )


def is_camera_hardware_validated(model_id, firmware):
    """Return True when camera operations are hardware-validated for model_id and firmware."""
    profile = qualification_for_model_id(model_id)
    return (
        profile is not None
        and type(firmware) is str
        and firmware in profile.firmware_versions
        and profile.camera_hardware_validated
    )


def is_discovery_hardware_validated(model_id, firmware):
    """Return True when LAN discovery is hardware-validated for model_id and firmware."""
    profile = qualification_for_model_id(model_id)
    return (
        profile is not None
        and type(firmware) is str
        and firmware in profile.firmware_versions
        and profile.discovery_hardware_validated
    )
