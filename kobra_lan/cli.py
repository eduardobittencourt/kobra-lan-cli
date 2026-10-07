import argparse
import json
from pathlib import Path

from . import __version__
from .config import Config, ProtocolError
from .mqtt import MQTT
from .printer import snapshot, file_details, safe_file_details, list_files
from .upload import describe, execute
from .start import start


def main(argv=None):
    parser = argparse.ArgumentParser(description="Direct Kobra X LAN client; upload never requests print/start")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/kobra-lan/config.json")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/kobra-lan/uploads")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Read identity, firmware, temperature and current print")
    sub.add_parser("files", help="List printer storage; read-only")
    p = sub.add_parser("inspect", help="Inspect local G-code; no network")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p = sub.add_parser("file", help="Read remote file metadata; no upload")
    p.add_argument("name")
    p = sub.add_parser("upload", help="Default dry run; --execute sends exactly once, without print/start")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--sha256", help="Reviewed file SHA-256, required for execution")
    p = sub.add_parser("start", help="Experimental: read-only plan by default; never uploads a file")
    p.add_argument("file", type=Path, help="Local copy of the previously uploaded G-code")
    p.add_argument("--name", required=True, help="Existing remote filename")
    p.add_argument("--slot", type=int, choices=range(1, 5), required=True)
    for flag in ["auto-leveling", "vibration-compensation", "flow-calibration"]:
        p.add_argument("--" + flag, choices=["on", "off"], required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--plan-sha256", help="Reviewed dry-run plan hash required to execute")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect" or (args.command == "upload" and not args.execute):
            _, result = describe(args.file, args.name)
            result["dry_run"] = True
        else:
            config = Config.load(args.config)
            if args.command == "status":
                result = snapshot(config)
            elif args.command == "files":
                with MQTT(config) as client:
                    result = {"records": list_files(client)}
            elif args.command == "file":
                with MQTT(config) as client:
                    result = safe_file_details(file_details(client, args.name))
            elif args.command == "start":
                result = start(config, args.file, args.name, args.slot,
                    args.auto_leveling == "on", args.vibration_compensation == "on", args.flow_calibration == "on",
                    args.state_dir, args.execute, args.plan_sha256)
            else:
                if not args.sha256:
                    raise ProtocolError("--sha256 is required for an actual upload")
                result = execute(config, args.file, args.sha256, args.state_dir, args.name)
        print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False))
        return 0
    except ProtocolError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        # Never print URLs with tokens, arbitrary JSON bodies or config contents.
        print(json.dumps({"ok": False, "error": "Local configuration or network operation failed; no automatic retry"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
