import argparse
import json
from pathlib import Path

from . import __version__
from .config import ProtocolError
from .mqtt import MQTT
from .printer import snapshot, file_details, safe_file_details, list_files
from .upload import describe, execute
from .start import start
from .pairing import pair, PairingLocalError
from .profiles import Registry, ProfileLocalError, validate_name


def main(argv=None):
    """Dispatch CLI operations and emit one JSON result using the established exit codes."""
    parser = argparse.ArgumentParser(description="Direct Kobra X LAN client; upload never requests print/start")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="Explicit config; conflicts with --printer")
    parser.add_argument("--printer", dest="selected_printer", help="Named local profile")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/kobra-lan/uploads")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("printer", help="Set up direct LAN access")
    printer = p.add_subparsers(dest="printer_command", required=True)
    p = printer.add_parser("pair", help="Pair an already LAN-enabled printer; never controls or uploads")
    p.add_argument("--host", required=True, help="Bare printer IPv4 address")
    p.add_argument("--trust-sha256", help="Expected server certificate SHA-256; required without a terminal")
    p.add_argument("--name", help="New managed profile name")
    p.add_argument("--default", action="store_true", help="Select the new named profile explicitly")
    printer.add_parser("list", help="List saved local profiles; no network")
    p = printer.add_parser("info", help="Inspect saved metadata; no network")
    p.add_argument("profile_name", nargs="?")
    p = printer.add_parser("use", help="Select a locally loadable profile as default; no network")
    p.add_argument("profile_name")
    p = printer.add_parser("remove", help="Remove local managed access; never revokes device credentials")
    p.add_argument("profile_name")
    p.add_argument("--yes", action="store_true", help="Confirm local deletion without a terminal")
    sub.add_parser("doctor", help="Bounded read-only connection diagnosis; never repairs or provisions")
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
        registry = Registry()
        explicit = args.config is not None or args.selected_printer is not None
        if args.config is not None and args.selected_printer is not None:
            raise ProtocolError("--config and --printer are mutually exclusive")
        if args.selected_printer is not None:
            validate_name(args.selected_printer)
        if args.command == "doctor":
            from .diagnostics import diagnose
            envelope, code = diagnose(registry, args.config, args.selected_printer)
            print(json.dumps(envelope, ensure_ascii=True))
            return code
        if args.command == "printer":
            command = args.printer_command
            if command in ("list", "use", "remove") and explicit:
                raise ProtocolError("Local management commands reject global target selectors")
            if command == "info" and args.profile_name is not None and explicit:
                raise ProtocolError("Positional profile and global target selectors conflict")
            if command == "list":
                result = registry.inventory()
            elif command == "info":
                result = registry.info(args.config, args.profile_name or args.selected_printer)
            elif command == "remove":
                result = registry.remove(args.profile_name, args.yes)
                if result["cleanup_failed"]:
                    print(json.dumps({"ok": False, "result": result, "error": "Profile detached; some local files retained after cleanup failure"}))
                    return 3
            elif command == "use":
                result = registry.select(args.profile_name)
            else:
                if args.selected_printer is not None:
                    raise ProtocolError("Pairing rejects --printer")
                if args.name is not None and args.config is not None:
                    raise ProtocolError("Named pairing rejects explicit --config")
                if args.default and args.name is None:
                    raise ProtocolError("--default requires --name")
                if args.name is not None:
                    result = registry.pair(args.name, args.host, args.trust_sha256, args.default)
                else:
                    result = pair(args.config or registry.legacy, args.host, args.trust_sha256)
        elif args.command == "inspect" or (args.command == "upload" and not args.execute):
            _, result = describe(args.file, args.name)
            result["dry_run"] = True
        else:
            with registry.access(args.config, args.selected_printer) as (config, source):
                result = operate(args, config)
        print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False))
        return 0
    except ProtocolError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    except (PairingLocalError, ProfileLocalError) as error:
        envelope = {"ok": False, "error": str(error)}
        if getattr(error, 'result', None) is not None:
            envelope['result'] = error.result
        print(json.dumps(envelope, ensure_ascii=True))
        return 3
    except (ImportError, OSError, ValueError, TypeError, KeyError):
        # Never print URLs with tokens, arbitrary JSON bodies or config contents.
        print(json.dumps({"ok": False, "error": "Local configuration or network operation failed; no automatic retry"}))
        return 3


def operate(args, config):
    """Run one operation while its selected managed configuration is leased."""
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
    return result


if __name__ == "__main__":
    raise SystemExit(main())
