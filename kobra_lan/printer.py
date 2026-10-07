import http.client
import json

from .config import ProtocolError
from .mqtt import MQTT


def public_info(config):
    conn = http.client.HTTPConnection(config.host, config.http_port, timeout=10)
    try:
        conn.request("GET", "/info")
        response = conn.getresponse()
        raw = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(raw) > 1024 * 1024:
            raise ProtocolError("HTTP identity request failed")
        info = json.loads(raw)
        return {k: info[k] for k in ["deviceName", "modelName", "modelId", "modeId"] if k in info}
    finally:
        conn.close()


def payload_data(report):
    data = report.get("data")
    if not isinstance(data, dict):
        raise ProtocolError("Printer returned no structured data")
    # Don't assume a network ACK means the device accepted the command.
    if report.get("code", 200) not in (0, 200):
        raise ProtocolError("Printer rejected query")
    return data


def sanitized(data):
    # URLs, credentials, certificates and raw unknown fields never reach stdout.
    keys = ["printerName", "version", "modelId", "modeId", "state", "temp", "filename",
            "print_state", "progress", "curr_layer", "total_layers", "taskid", "task_id", "print_status", "model"]
    return {k: data[k] for k in keys if k in data}


def snapshot(config):
    with MQTT(config) as client:
        info = payload_data(client.query("info"))
        # Idle firmware ACKs print/query without a report; info is authoritative.
        project = info.get("project")
        return {"identity": public_info(config), "info": sanitized(info),
                "print": sanitized(project) if isinstance(project, dict) else None,
                "last_print": sanitized(info.get("last_project") or {})}


def file_details(client, filename):
    data = payload_data(client.query("file", "fileDetails", {"root": "local", "filename": filename}))
    if data.get("filename") != filename:
        raise ProtocolError("File metadata belongs to a different file")
    return data


def safe_file_details(data):
    details = data.get("file_details") or {}
    if not isinstance(details, dict):
        raise ProtocolError("Unknown file metadata schema")
    return {"filename": data.get("filename"), **{k: details[k] for k in
            ["file_size", "file_format", "layer_count", "printer_model", "estimated_time_s",
             "model_dimensions", "total_filament_used", "nozzle_diameter", "bed_type"] if k in details}}


def list_files(client):
    records = []
    for page in range(1, 21):
        data = payload_data(client.query("file", "listLocal", {"page_num": page, "page_size": 200, "path": "/"}))
        batch = data.get("records")
        if not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch):
            raise ProtocolError("Unknown file listing schema")
        records.extend({k: r[k] for k in ["filename", "size", "is_dir"] if k in r} for r in batch)
        if len(batch) < 200:
            return records
    raise ProtocolError("Storage listing exceeds qualified pagination limit")
