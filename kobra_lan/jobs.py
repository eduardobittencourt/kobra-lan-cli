"""Offline read-only local job history reconstructed from receipts and observations."""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re

from .cli_output import safe_text
from .config import ProtocolError
from .filaments import normalize_color
from .profiles import ProfileLocalError, open_directory
from .start import (
    ACTIVE,
    ATTEMPT_SUFFIX,
    MISSING,
    RECEIPT_SUFFIX,
    STATUSES,
    active_project,
    attempt_id,
    matching_receipt,
    state_record,
    valid_attempt_id,
)
from .watch import project_filename

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_MATCHING_OBSERVATIONS = 50
KINDS = ("all", "start", "observation")
COVERAGE = {
    "scope": "local_state_only",
    "direct_printer_history_available": False,
    "other_client_actions": "only_when_watched_unattributed",
    "terminal_outcomes_verified": False,
}

START_FILE_RE = re.compile(r"^([a-f0-9]{64})\.(attempt|json)$")
OBS_FILE_RE = re.compile(r"^(obs-[a-f0-9]{32})\.json$")
RECORD_ID_RE = re.compile(r"^(?:[a-f0-9]{64}|obs-[a-f0-9]{32}|unreadable-[a-f0-9]{64})$")
OBSERVATION_ID_RE = re.compile(r"^obs-[a-f0-9]{32}$")
UNREADABLE_ID_RE = re.compile(r"^unreadable-([a-f0-9]{64})$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
UPLOAD_STATUSES = frozenset({
    "attempt_reserved",
    "http_response_received_unverified",
    "uploaded_verified_by_listing_and_metadata",
    "uncertain_no_retry",
})
OBSERVATION_OUTCOMES = frozenset({"unknown"})
OBSERVATION_REASONS = frozenset({
    "deadline_expired",
    "job_disappeared",
    "job_replaced",
    "last_project_unattributed",
    "identity_unverified",
    "interrupted",
    "validation_failed",
    "operation_failed",
})
OBSERVATION_PHASES = frozenset({"preparing", "printing"})


def valid_record_id(value):
    return isinstance(value, str) and RECORD_ID_RE.fullmatch(value) is not None


def device_digest_for(config):
    return hashlib.sha256(config.printer_id.encode()).hexdigest()


def _open_optional_dir(resources, path):
    try:
        fd = open_directory(path, create=False, require_private=True)
    except FileNotFoundError:
        return None
    except ProfileLocalError:
        raise
    except OSError:
        raise ProfileLocalError(
            "Local state directory must be a user-owned private directory (0700) without symlinks"
        ) from None
    resources.callback(os.close, fd)
    return fd


def _add_issue(issues, code):
    if code not in issues:
        issues.append(code)


def _safe_filename(value):
    if not isinstance(value, str):
        return None
    return project_filename({"filename": value})


def _safe_short_text(value, limit=80):
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    cleaned = safe_text(value).strip()
    if not cleaned or "[redacted" in cleaned:
        return None
    return cleaned


def _safe_timestamp(value):
    if type(value) is int and value >= 0:
        return value
    return None


def _extract_preparation(payload):
    if not isinstance(payload, dict):
        return None
    settings = payload.get("task_settings")
    if not isinstance(settings, dict):
        return None
    fields = ("auto_leveling", "vibration_compensation", "flow_calibration")
    result = {}
    for field in fields:
        raw = settings.get(field)
        if type(raw) is int and raw in (0, 1):
            result[field] = bool(raw)
        elif type(raw) is bool:
            result[field] = raw
        else:
            return None
    return result


def _safe_color_hex(color):
    try:
        return normalize_color(color)[1]
    except ProtocolError:
        return None


def _extract_slot_mapping(receipt):
    payload = receipt.get("payload")
    ams = payload.get("ams_settings") if isinstance(payload, dict) else None
    mapping = ams.get("ams_box_mapping") if isinstance(ams, dict) else None
    if not isinstance(mapping, list) or not mapping:
        return None
    entries = {}
    for entry in mapping:
        if not isinstance(entry, dict):
            return None
        paint_index, ams_index = entry.get("paint_index"), entry.get("ams_index")
        if (type(paint_index) is not int or paint_index < 0 or paint_index in entries
                or type(ams_index) is not int or not 0 <= ams_index <= 3):
            return None
        entries[paint_index] = {
            "paint_index": paint_index,
            "slot": ams_index + 1,
            "ams_index": ams_index,
            "material_type": _safe_short_text(entry.get("material_type")),
            "gcode_color_hex": _safe_color_hex(entry.get("paint_color")),
            "slot_color_hex": _safe_color_hex(entry.get("ams_color")),
        }
    return [entries[index] for index in sorted(entries)]


def _parse_start_candidate(record, storage_key, device_digest, *, is_marker):
    """Return (file_sha256, previous_attempt_id, identity, record_format, error_issue)."""
    sha_field = record.get("sha256") if is_marker else record.get("file_sha256")
    prev = record.get("previous_attempt_id")
    att = record.get("attempt_id")

    if is_marker:
        if set(record) == {"sha256", "plan_sha256"} and sha_field == storage_key:
            return storage_key, None, attempt_id(device_digest, storage_key, None), "legacy", None
        if prev is None and sha_field == storage_key and "attempt_id" in record:
            expected = attempt_id(device_digest, storage_key, None)
            if att == expected and record.get("device_digest") == device_digest:
                return storage_key, None, expected, "current", None
            return None, None, None, None, "invalid_successor_identity"
        if valid_attempt_id(prev) and valid_attempt_id(sha_field):
            expected = attempt_id(device_digest, sha_field, prev)
            if att == storage_key and expected == storage_key and record.get("device_digest") == device_digest:
                return sha_field, prev, storage_key, "current", None
            return None, None, None, None, "invalid_successor_identity"
        if prev is not None or att is not None:
            return None, None, None, None, "invalid_successor_identity"
        return None, None, None, None, None

    # Receipt parsing
    if "attempt_id" not in record and "previous_attempt_id" not in record:
        if sha_field == storage_key and record.get("device_digest") == device_digest:
            return storage_key, None, attempt_id(device_digest, storage_key, None), "legacy", None
        return None, None, None, None, None
    if prev is None and sha_field == storage_key:
        expected = attempt_id(device_digest, storage_key, None)
        if att == expected and record.get("device_digest") == device_digest:
            return storage_key, None, expected, "current", None
        return None, None, None, None, "invalid_successor_identity"
    if valid_attempt_id(prev) and valid_attempt_id(sha_field):
        expected = attempt_id(device_digest, sha_field, prev)
        if att == storage_key and expected == storage_key and record.get("device_digest") == device_digest:
            return sha_field, prev, storage_key, "current", None
        return None, None, None, None, "invalid_successor_identity"
    return None, None, None, None, "invalid_successor_identity"


def _empty_upload_provenance():
    return {
        "present": False,
        "verified": False,
        "status": None,
        "remote_filename": None,
        "timestamp": None,
        "remote_byte_hash_verified": False,
    }


def _read_upload_provenance(uploads_fd, cache, file_sha256, filename):
    if not valid_attempt_id(file_sha256) or uploads_fd is None:
        return _empty_upload_provenance()
    if file_sha256 not in cache:
        cache[file_sha256] = state_record(uploads_fd, file_sha256 + RECEIPT_SUFFIX)
    rec = cache[file_sha256]
    if rec is MISSING:
        return _empty_upload_provenance()
    if rec is None:
        return {
            "present": True,
            "verified": False,
            "status": "unreadable",
            "remote_filename": None,
            "timestamp": None,
            "remote_byte_hash_verified": False,
        }
    raw_status = rec.get("status")
    status = raw_status if isinstance(raw_status, str) and raw_status in UPLOAD_STATUSES else "unknown"
    remote_filename = _safe_filename(rec.get("remote_filename"))
    verified = (
        rec.get("status") == "uploaded_verified_by_listing_and_metadata"
        and rec.get("sha256") == file_sha256
        and filename is not None
        and rec.get("remote_filename") == filename
    )
    provenance = {
        "present": True,
        "verified": verified,
        "status": status,
        "remote_filename": remote_filename,
        "timestamp": _safe_timestamp(rec.get("timestamp")),
        "remote_byte_hash_verified": False,
    }
    slicer = rec.get("slicer_version")
    if isinstance(slicer, str) and VERSION_RE.fullmatch(slicer):
        provenance["slicer_version"] = slicer
    size_bytes = rec.get("size_bytes")
    if type(size_bytes) is int and size_bytes >= 0:
        provenance["size_bytes"] = size_bytes
    layer_count = rec.get("layer_count")
    if type(layer_count) is int and layer_count >= 0:
        provenance["layer_count"] = layer_count
    return provenance


def _build_unreadable_start(storage_key, device_digest, issues):
    return {
        "record_id": f"unreadable-{storage_key}",
        "record_kind": "start",
        "record_format": None,
        "completeness": "incomplete",
        "client_attribution": "cli",
        "device_digest": device_digest,
        "attempt_id": None,
        "previous_attempt_id": None,
        "next_attempt_id": None,
        "storage_key": storage_key,
        "file_sha256": None,
        "plan_sha256": None,
        "filename": None,
        "timestamp": None,
        "model": None,
        "firmware": None,
        "slot_mapping": None,
        "preparation": None,
        "hardware_start_validated": None,
        "start_status": None,
        "terminal_outcome": "unknown",
        "reprint_eligibility": "blocked_incomplete",
        "upload_provenance": _empty_upload_provenance(),
        "issues": issues,
    }


def _reconstruct_start_entry(storage_key, marker, receipt, device_digest):
    issues = []
    marker_dict = marker if isinstance(marker, dict) else None
    receipt_dict = receipt if isinstance(receipt, dict) else None

    if marker is MISSING:
        _add_issue(issues, "missing_marker")
    elif marker is None:
        _add_issue(issues, "unreadable_marker")
    if receipt is MISSING:
        _add_issue(issues, "missing_receipt")
    elif receipt is None:
        _add_issue(issues, "unreadable_receipt")

    device_mismatch = False
    if marker_dict is not None and "device_digest" in marker_dict and marker_dict.get("device_digest") != device_digest:
        device_mismatch = True
    if receipt_dict is not None and "device_digest" in receipt_dict and receipt_dict.get("device_digest") != device_digest:
        device_mismatch = True
    if device_mismatch:
        _add_issue(issues, "device_mismatch")
        return _build_unreadable_start(storage_key, device_digest, issues)

    m_cand = _parse_start_candidate(marker_dict, storage_key, device_digest, is_marker=True) if marker_dict is not None else None
    r_cand = _parse_start_candidate(receipt_dict, storage_key, device_digest, is_marker=False) if receipt_dict is not None else None

    if m_cand is not None and m_cand[4] is not None:
        _add_issue(issues, m_cand[4])
    if r_cand is not None and r_cand[4] is not None:
        _add_issue(issues, r_cand[4])

    m_id = m_cand[2] if m_cand is not None else None
    r_id = r_cand[2] if r_cand is not None else None

    if m_id is None and r_id is None:
        if marker_dict is not None and receipt_dict is not None and not issues:
            _add_issue(issues, "receipt_mismatch")
        elif not issues:
            _add_issue(issues, "invalid_successor_identity")
        return _build_unreadable_start(storage_key, device_digest, issues)

    if m_id is not None and r_id is not None:
        if (m_cand[0], m_cand[1], m_cand[2]) != (r_cand[0], r_cand[1], r_cand[2]):
            _add_issue(issues, "receipt_mismatch")
            if m_id != r_id:
                return _build_unreadable_start(storage_key, device_digest, issues)
        file_sha256, previous, identity = m_cand[0], m_cand[1], m_cand[2]
        record_format = m_cand[3] if m_cand[3] == r_cand[3] else None
    elif m_id is not None:
        file_sha256, previous, identity, record_format = m_cand[0], m_cand[1], m_cand[2], m_cand[3]
        if receipt_dict is not None:
            _add_issue(issues, "receipt_mismatch")
    else:
        file_sha256, previous, identity, record_format = r_cand[0], r_cand[1], r_cand[2], r_cand[3]
        if marker_dict is not None:
            _add_issue(issues, "receipt_mismatch")

    plan_sha256 = None
    if marker_dict is not None and valid_attempt_id(marker_dict.get("plan_sha256")):
        plan_sha256 = marker_dict["plan_sha256"]
    elif receipt_dict is not None and valid_attempt_id(receipt_dict.get("plan_sha256")):
        plan_sha256 = receipt_dict["plan_sha256"]

    filename = None
    timestamp = None
    model = None
    firmware = None
    slot_mapping = None
    preparation = None
    hardware_validated = None
    start_status = None

    if receipt_dict is not None:
        payload = receipt_dict.get("payload")
        if isinstance(payload, dict):
            filename = _safe_filename(payload.get("filename"))
            preparation = _extract_preparation(payload)
        timestamp = _safe_timestamp(receipt_dict.get("timestamp"))
        model = _safe_short_text(receipt_dict.get("model"), limit=64)
        raw_fw = receipt_dict.get("firmware")
        firmware = raw_fw if isinstance(raw_fw, str) and VERSION_RE.fullmatch(raw_fw) else None
        slot_mapping = _extract_slot_mapping(receipt_dict)
        if type(receipt_dict.get("hardware_start_validated")) is bool:
            hardware_validated = receipt_dict["hardware_start_validated"]
        raw_status = receipt_dict.get("status")
        if isinstance(raw_status, str) and raw_status in STATUSES:
            start_status = raw_status

    if marker_dict is not None and receipt_dict is not None:
        if not matching_receipt(marker_dict, receipt_dict, identity, previous, device_digest, file_sha256):
            _add_issue(issues, "receipt_mismatch")
        else:
            raw_status = receipt_dict.get("status")
            if not isinstance(raw_status, str) or raw_status not in STATUSES:
                _add_issue(issues, "invalid_status")
            elif raw_status == ACTIVE:
                after, project = receipt_dict.get("after"), receipt_dict.get("project")
                raw_filename = receipt_dict["payload"].get("filename")
                if not isinstance(after, dict) or not active_project(after, project, raw_filename):
                    _add_issue(issues, "unverified_active_evidence")

    completeness = "complete" if not issues else "incomplete"
    return {
        "record_id": identity,
        "record_kind": "start",
        "record_format": record_format,
        "completeness": completeness,
        "client_attribution": "cli",
        "device_digest": device_digest,
        "attempt_id": identity,
        "previous_attempt_id": previous,
        "next_attempt_id": None,
        "storage_key": storage_key,
        "file_sha256": file_sha256,
        "plan_sha256": plan_sha256,
        "filename": filename,
        "timestamp": timestamp,
        "model": model,
        "firmware": firmware,
        "slot_mapping": slot_mapping,
        "preparation": preparation,
        "hardware_start_validated": hardware_validated,
        "start_status": start_status,
        "terminal_outcome": "unknown",
        "reprint_eligibility": "blocked_incomplete",
        "upload_provenance": _empty_upload_provenance(),
        "issues": issues,
    }


def _scan_starts(starts_fd, uploads_fd, device_digest):
    if starts_fd is None:
        return []
    keys = set()
    for name in os.listdir(starts_fd):
        match = START_FILE_RE.fullmatch(name)
        if match is not None:
            keys.add(match.group(1))
    records = []
    for storage_key in sorted(keys):
        marker = state_record(starts_fd, storage_key + ATTEMPT_SUFFIX)
        receipt = state_record(starts_fd, storage_key + RECEIPT_SUFFIX)
        if marker is MISSING and receipt is MISSING:
            continue
        records.append(_reconstruct_start_entry(storage_key, marker, receipt, device_digest))

    attempts_by_id = {rec["attempt_id"]: rec for rec in records if rec["attempt_id"] is not None}
    occupied_keys = {rec["storage_key"] for rec in records}

    # Link predecessor -> successor edges for matching file_sha256.
    for rec in attempts_by_id.values():
        prev_id = rec["previous_attempt_id"]
        if prev_id is None:
            continue
        parent = attempts_by_id.get(prev_id)
        if parent is not None and parent["file_sha256"] == rec["file_sha256"]:
            parent["next_attempt_id"] = rec["attempt_id"]

    # Walk chains from every root forward to verify ancestor activity invariant.
    ancestors_active = {}
    visited = set()
    for rec in attempts_by_id.values():
        if rec["previous_attempt_id"] is not None:
            continue
        current = rec
        chain_ok = True
        while current is not None and current["attempt_id"] not in visited:
            visited.add(current["attempt_id"])
            ancestors_active[current["attempt_id"]] = chain_ok
            if not chain_ok:
                _add_issue(current["issues"], "invalid_predecessor")
                current["completeness"] = "incomplete"
            current_active = (current["completeness"] == "complete" and current["start_status"] == ACTIVE)
            chain_ok = chain_ok and current_active
            nxt_id = current["next_attempt_id"]
            current = attempts_by_id.get(nxt_id) if nxt_id is not None else None

    # Any attempt not reached from a root is an orphan successor (or cycle).
    for rec in attempts_by_id.values():
        if rec["attempt_id"] not in visited:
            ancestors_active[rec["attempt_id"]] = False
            _add_issue(rec["issues"], "missing_predecessor")
            rec["completeness"] = "incomplete"

    upload_cache = {}
    for rec in records:
        provenance = _read_upload_provenance(uploads_fd, upload_cache, rec["file_sha256"], rec["filename"])
        rec["upload_provenance"] = provenance
        successor_occupied = (
            rec["attempt_id"] is not None
            and rec["file_sha256"] is not None
            and attempt_id(device_digest, rec["file_sha256"], rec["attempt_id"]) in occupied_keys
        )
        if rec["attempt_id"] is None:
            rec["reprint_eligibility"] = "blocked_incomplete"
        elif rec["completeness"] == "complete" and (rec["next_attempt_id"] is not None or successor_occupied):
            rec["reprint_eligibility"] = "superseded"
        elif rec["completeness"] != "complete" or not ancestors_active.get(rec["attempt_id"], False):
            rec["reprint_eligibility"] = "blocked_incomplete"
        elif rec["start_status"] != ACTIVE:
            rec["reprint_eligibility"] = "blocked_not_observed_active"
        elif not provenance["verified"]:
            rec["reprint_eligibility"] = "blocked_missing_upload_provenance"
        else:
            rec["reprint_eligibility"] = "eligible_for_plan"

    return records


def _incomplete_observation(obs_id, device_digest, issue):
    return {
        "record_id": obs_id,
        "record_kind": "observation",
        "completeness": "incomplete",
        "client_attribution": "unattributed",
        "device_digest": device_digest,
        "observation_id": obs_id,
        "observed_at": None,
        "ended_at": None,
        "timestamp": None,
        "observed_filename": None,
        "filename": None,
        "outcome": None,
        "reason": None,
        "phase": None,
        "terminal_outcome": "unknown",
        "issues": [issue],
    }


def _validate_observation(obs_id, data, device_digest):
    if not isinstance(data, dict):
        return _incomplete_observation(obs_id, device_digest, "unreadable_observation")
    raw_device = data.get("device_digest")
    if valid_attempt_id(raw_device) and raw_device != device_digest:
        return _incomplete_observation(obs_id, device_digest, "device_mismatch")
    if raw_device != device_digest:
        return _incomplete_observation(obs_id, device_digest, "invalid_observation")
    observed_at = _safe_timestamp(data.get("observed_at"))
    ended_at = _safe_timestamp(data.get("ended_at"))
    raw_filename = data.get("observed_filename")
    if raw_filename is None:
        observed_filename = None
    else:
        observed_filename = _safe_filename(raw_filename)
        if observed_filename != raw_filename:
            return _incomplete_observation(obs_id, device_digest, "invalid_observation")
    outcome = data.get("outcome")
    reason = data.get("reason")
    phase = data.get("phase")
    if (type(data.get("version")) is not int or data["version"] != 1
            or data.get("observation_id") != obs_id
            or observed_at is None or ended_at is None
            or data.get("client_attribution") != "unattributed"
            or not isinstance(outcome, str) or outcome not in OBSERVATION_OUTCOMES
            or not isinstance(reason, str) or reason not in OBSERVATION_REASONS
            or not isinstance(phase, str) or phase not in OBSERVATION_PHASES):
        return _incomplete_observation(obs_id, device_digest, "invalid_observation")
    scalars = {}
    if "progress" in data:
        progress = data["progress"]
        if type(progress) is not int or not 0 <= progress <= 100:
            return _incomplete_observation(obs_id, device_digest, "invalid_observation")
        scalars["progress"] = progress
    if "total_layers" in data:
        total = data["total_layers"]
        if type(total) is not int or not 1 <= total <= 1_000_000:
            return _incomplete_observation(obs_id, device_digest, "invalid_observation")
        scalars["total_layers"] = total
    if "current_layer" in data:
        current = data["current_layer"]
        limit = scalars.get("total_layers", 1_000_000)
        if type(current) is not int or not 0 <= current <= limit:
            return _incomplete_observation(obs_id, device_digest, "invalid_observation")
        scalars["current_layer"] = current
    return {
        "record_id": obs_id,
        "record_kind": "observation",
        "completeness": "complete",
        "client_attribution": "unattributed",
        "device_digest": device_digest,
        "observation_id": obs_id,
        "observed_at": observed_at,
        "ended_at": ended_at,
        "timestamp": observed_at,
        "observed_filename": observed_filename,
        "filename": observed_filename,
        "outcome": data["outcome"],
        "reason": data["reason"],
        "phase": data["phase"],
        **scalars,
        "terminal_outcome": "unknown",
        "issues": [],
    }


def _scan_observations(obs_fd, device_digest):
    if obs_fd is None:
        return []
    entries = []
    for name in os.listdir(obs_fd):
        match = OBS_FILE_RE.fullmatch(name)
        if match is not None:
            entries.append((name, match.group(1)))
    records = []
    for name, obs_id in sorted(entries):
        data = state_record(obs_fd, name)
        if data is MISSING:
            continue
        if data is None:
            records.append(_incomplete_observation(obs_id, device_digest, "unreadable_observation"))
        else:
            records.append(_validate_observation(obs_id, data, device_digest))
    return records


def _sort_key(record):
    ts = record["timestamp"]
    return (ts is not None, ts if ts is not None else -1, record["record_id"])


def _summarize(record):
    if record["record_kind"] == "start":
        return {
            "record_id": record["record_id"],
            "record_kind": "start",
            "completeness": record["completeness"],
            "client_attribution": record["client_attribution"],
            "timestamp": record["timestamp"],
            "filename": record["filename"],
            "start_status": record["start_status"],
            "terminal_outcome": record["terminal_outcome"],
            "reprint_eligibility": record["reprint_eligibility"],
            "issues": record["issues"],
        }
    return {
        "record_id": record["record_id"],
        "record_kind": "observation",
        "completeness": record["completeness"],
        "client_attribution": record["client_attribution"],
        "timestamp": record["timestamp"],
        "filename": record["filename"],
        "outcome": record["outcome"],
        "reason": record["reason"],
        "terminal_outcome": record["terminal_outcome"],
        "issues": record["issues"],
    }


def _matching_observations(start_record, observations):
    filename = start_record["filename"]
    if filename is None:
        return []
    start_ts = start_record["timestamp"]
    matches = []
    for obs in observations:
        if obs["completeness"] != "complete":
            continue
        if obs["observed_filename"] != filename:
            continue
        if start_ts is not None and (obs["observed_at"] is None or obs["observed_at"] < start_ts):
            continue
        matches.append(obs)
    matches.sort(key=_sort_key, reverse=True)
    result = []
    for obs in matches[:MAX_MATCHING_OBSERVATIONS]:
        item = {
            "observation_id": obs["observation_id"],
            "observed_at": obs["observed_at"],
            "ended_at": obs["ended_at"],
            "outcome": obs["outcome"],
            "reason": obs["reason"],
            "phase": obs["phase"],
            "attribution": "unattributed_filename_match",
        }
        for field in ("progress", "current_layer", "total_layers"):
            if field in obs:
                item[field] = obs[field]
        result.append(item)
    return result


def list_jobs(config, state_dir, *, kind="all", limit=DEFAULT_LIMIT):
    """Return bounded newest-first local job history for the selected device."""
    if kind not in KINDS:
        raise ProtocolError("Invalid job history kind filter")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ProtocolError(f"Job history limit must be an integer from 1 to {MAX_LIMIT}")
    device_digest = device_digest_for(config)
    device16 = device_digest[:16]
    base = Path(state_dir)
    with ExitStack() as resources:
        uploads_fd = _open_optional_dir(resources, base / device16)
        starts_fd = _open_optional_dir(resources, base / "starts" / device16)
        obs_fd = _open_optional_dir(resources, base / "observations" / device16)
        records = []
        if kind in ("all", "start"):
            records.extend(_scan_starts(starts_fd, uploads_fd, device_digest))
        if kind in ("all", "observation"):
            records.extend(_scan_observations(obs_fd, device_digest))
    records.sort(key=_sort_key, reverse=True)
    total_count = len(records)
    incomplete_count = sum(1 for rec in records if rec["completeness"] != "complete")
    selected = records[:limit]
    return {
        "device_digest": device_digest,
        "kind": kind,
        "limit": limit,
        "total_count": total_count,
        "returned_count": len(selected),
        "incomplete_count": incomplete_count,
        "truncated": total_count > len(selected),
        "jobs": [_summarize(rec) for rec in selected],
        "coverage": dict(COVERAGE),
    }


def job_info(config, state_dir, record_id):
    """Inspect one start attempt, watch observation, or unreadable start record."""
    if not valid_record_id(record_id):
        raise ProtocolError("Invalid local job record ID")
    device_digest = device_digest_for(config)
    device16 = device_digest[:16]
    base = Path(state_dir)
    with ExitStack() as resources:
        uploads_fd = _open_optional_dir(resources, base / device16)
        starts_fd = _open_optional_dir(resources, base / "starts" / device16)
        obs_fd = _open_optional_dir(resources, base / "observations" / device16)
        if OBSERVATION_ID_RE.fullmatch(record_id):
            observations = _scan_observations(obs_fd, device_digest)
            for obs in observations:
                if obs["record_id"] == record_id:
                    if "device_mismatch" in obs["issues"]:
                        raise ProtocolError("Unknown local job record for the selected printer")
                    return {**obs, "coverage": dict(COVERAGE)}
            raise ProtocolError("Unknown local job record for the selected printer")
        starts = _scan_starts(starts_fd, uploads_fd, device_digest)
        for rec in starts:
            if rec["record_id"] == record_id:
                observations = _scan_observations(obs_fd, device_digest)
                return {
                    **rec,
                    "unattributed_matching_observations": _matching_observations(rec, observations),
                    "coverage": dict(COVERAGE),
                }
        raise ProtocolError("Unknown local job record for the selected printer")
