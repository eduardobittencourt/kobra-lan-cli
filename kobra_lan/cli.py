import argparse
import re
import sys
from pathlib import Path

from . import __version__
from .cli_output import emit
from .config import ProtocolError
from .mqtt import MQTT
from .printer import snapshot, file_details, safe_file_details, list_files
from .upload import describe, execute
from .start import start
from .pairing import PairingLocalError
from .profiles import Registry, ProfileLocalError, validate_name


class ArgumentFailure(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_abbrev=False, **kwargs)

    def error(self, message):
        # argparse interpolates arbitrary supplied values; never publish its message.
        guidance = {
            "kobra-lan printer pair": "; supply --name NAME and --host IPv4",
            "kobra-lan files upload": "; review first with kobra-lan gcode inspect",
            "kobra-lan print start": "; review first with kobra-lan print plan",
        }.get(self.prog, "")
        raise ArgumentFailure("Invalid arguments; use " + self.prog + " --help for supported commands and required options" + guidance)


def root_json(argv):
    """Recognize root --json without interpreting positional operands as options."""
    index = 0
    selected = False
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            selected = True
        elif token in ("--config", "--printer", "--state-dir"):
            index += 1
        elif any(token.startswith(flag + "=") for flag in ("--config", "--printer", "--state-dir")):
            index += 1
            continue
        else:
            break
        index += 1
    return selected


def build_parser():
    """Build the canonical command metadata without opening access or state."""
    parser = Parser(prog="kobra-lan", description="Direct Kobra X LAN client; global options precede commands")
    parser.add_argument("--json", action="store_true", help="Version-1 machine result; place before command")
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
    p.add_argument("--name", required=True, help="New managed profile name")
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
    p = sub.add_parser("files", help="Observe storage or explicitly upload; never starts prints",
                       description="list/info are read-only; upload requires reviewed hash and --execute")
    files = p.add_subparsers(dest="files_command", required=True)
    files.add_parser("list", help="List printer storage; read-only")
    p = files.add_parser("info", help="Read remote metadata; no upload")
    p.add_argument("name")
    p = files.add_parser("upload", help="Upload reviewed bytes once; never starts a print")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p.add_argument("--execute", action="store_true", required=True)
    p.add_argument("--sha256", required=True, help="Reviewed file SHA-256 from gcode inspect")
    p = sub.add_parser("gcode", help="Local inspection; no target or network")
    gcode = p.add_subparsers(dest="gcode_command", required=True)
    p = gcode.add_parser("inspect", help="Inspect immutable local G-code; no state writes")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p = sub.add_parser("print", help="Review a plan or explicitly start an experimental print",
                       description="plan is read-only; start requires reviewed plan hash and --execute")
    printing = p.add_subparsers(dest="print_command", required=True)
    for command in ("plan", "start"):
        p = printing.add_parser(command, help="Read-only plan" if command == "plan" else "Experimental guarded execution")
        p.add_argument("file", type=Path, help="Local copy of the previously uploaded G-code")
        p.add_argument("--name", required=True, help="Existing remote filename")
        p.add_argument("--slot", type=int, choices=range(1, 5), required=True)
        for flag in ["auto-leveling", "vibration-compensation", "flow-calibration"]:
            p.add_argument("--" + flag, choices=["on", "off"], required=True)
        if command == "start":
            p.add_argument("--execute", action="store_true", required=True)
            p.add_argument("--plan-sha256", required=True, help="Reviewed hash from print plan")
    p = sub.add_parser("completion", help="Generate offline shell completion; no access or state")
    p.add_argument("shell", choices=["bash", "zsh", "fish"])
    return parser


def main(argv=None):
    """Dispatch CLI operations using the established exit classes."""
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = root_json(argv)
    try:
        args = parser.parse_args(argv)
        json_mode = args.json
        if args.command == "files" and args.files_command == "upload":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
                raise ArgumentFailure("Upload requires a full --sha256 from gcode inspect and --execute")
            args.sha256 = args.sha256.lower()
            _, manifest = describe(args.file, args.name)
            if manifest["sha256"] != args.sha256:
                raise ProtocolError("File SHA-256 differs from reviewed manifest; use gcode inspect")
        if args.command == "print" and args.print_command == "start":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", args.plan_sha256):
                raise ArgumentFailure("Start requires a full --plan-sha256 from print plan and --execute")
            args.plan_sha256 = args.plan_sha256.lower()
        if args.command == "completion":
            from .completions import generate
            print(generate(parser, args.shell), end="")
            return 0
        registry = Registry()
        explicit = args.config is not None or args.selected_printer is not None
        if args.config is not None and args.selected_printer is not None:
            raise ProtocolError("--config and --printer are mutually exclusive")
        if args.selected_printer is not None:
            validate_name(args.selected_printer)
        if args.command == "doctor":
            from .diagnostics import diagnose
            envelope, code = diagnose(registry, args.config, args.selected_printer)
            emit(json_mode, envelope["result"], code="diagnostic_failed" if code else None,
                 message="Connection diagnosis failed; inspect ordered checks and next steps")
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
                    emit(json_mode, result, code="operation_failed", message="Profile detached; some local files retained after cleanup failure")
                    return 3
            elif command == "use":
                result = registry.select(args.profile_name)
            else:
                if explicit:
                    raise ProtocolError("Pairing rejects --printer and --config; supply --name for a new profile")
                result = registry.pair(args.name, args.host, args.trust_sha256, args.default)
        elif args.command == "gcode":
            _, result = describe(args.file, args.name)
            result["dry_run"] = True
        else:
            with registry.access(args.config, args.selected_printer) as (config, source):
                result = operate(args, config)
        emit(json_mode, result)
        return 0
    except ArgumentFailure as error:
        emit(json_mode, code="invalid_arguments", message=str(error))
        return 2
    except ProtocolError as error:
        status = 3 if getattr(error, "exit_code", 2) == 3 else 2
        emit(json_mode, code="operation_failed" if status == 3 else "validation_failed", message=str(error))
        return status
    except (PairingLocalError, ProfileLocalError) as error:
        emit(json_mode, getattr(error, "result", None), code="operation_failed", message=str(error))
        return 3
    except (ImportError, OSError, ValueError, TypeError, KeyError):
        emit(json_mode, code="operation_failed", message="Local configuration or network operation failed; no automatic retry")
        return 3


def operate(args, config):
    """Run one operation while its selected managed configuration is leased."""
    if args.command == "status":
        result = snapshot(config)
    elif args.command == "files" and args.files_command == "list":
        with MQTT(config) as client:
            result = {"records": list_files(client)}
    elif args.command == "files" and args.files_command == "info":
        with MQTT(config) as client:
            result = safe_file_details(file_details(client, args.name))
    elif args.command == "print":
        result = start(config, args.file, args.name, args.slot,
            args.auto_leveling == "on", args.vibration_compensation == "on", args.flow_calibration == "on",
            args.state_dir, args.print_command == "start", getattr(args, "plan_sha256", None))
    else:
        if not args.sha256:
            raise ProtocolError("--sha256 is required for an actual upload")
        result = execute(config, args.file, args.sha256, args.state_dir, args.name)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
