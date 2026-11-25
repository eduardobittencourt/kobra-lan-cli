import argparse
import os
import re
import sys
from pathlib import Path

from . import __version__
from .camera import (
    DEFAULT_SNAPSHOT_TIMEOUT,
    MAX_PIPE_BYTES,
    MAX_PIPE_TIMEOUT,
    MAX_SNAPSHOT_TIMEOUT,
    CameraArgumentError,
    camera_pipe,
    camera_snapshot,
    camera_status,
    validate_snapshot_request,
)
from .cli_output import emit, safe_text
from .config import ProtocolError
from .control import control_print, validate_filename
from .delete_file import delete_file
from .filaments import inspect_gcode_filaments, list_slots
from .jobs import DEFAULT_LIMIT, KINDS, MAX_LIMIT, job_info, list_jobs, valid_record_id
from .mqtt import MQTT, validate_delete_filename
from .printer import snapshot, file_details, safe_file_details, list_files
from .upload import describe, execute
from .start import start, valid_attempt_id
from .pairing import PairingLocalError
from .profiles import Registry, ProfileLocalError, validate_name
from .qualification import (
    KOBRA_X,
    QUALIFICATION_SUMMARY,
    QUALIFIED_FIRMWARE,
    is_camera_hardware_validated,
    is_control_hardware_validated,
    is_delete_hardware_validated,
    is_valid_onboard_slot,
    onboard_topology,
)
from .watch import DEFAULT_TIMEOUT, MAX_TIMEOUT, WatchProgress, observe


class ArgumentFailure(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_abbrev=False, **kwargs)

    def parse_args(self, args=None, namespace=None):
        parsed, extras = self.parse_known_args(args, namespace)
        if extras:
            prog = self.prog
            if getattr(parsed, "command", None) == "print" and parsed.print_command in ("plan", "start"):
                prog = f"{prog} print {parsed.print_command}"
            elif getattr(parsed, "command", None) == "camera" and parsed.camera_command in ("status", "snapshot", "pipe"):
                prog = f"{prog} camera {parsed.camera_command}"
            self.error("Unrecognized arguments", prog=prog)
        return parsed

    def error(self, message, *, prog=None):
        # argparse interpolates arbitrary supplied values; never publish its message.
        prog = prog or self.prog
        guidance = {
            "kobra-lan printer pair": "; supply --name NAME and --host IPv4",
            "kobra-lan camera": "; choose status, snapshot, or pipe",
            "kobra-lan camera snapshot": f"; supply --output PATH (.jpg, .jpeg, or .png) and optional --timeout (1 to {MAX_SNAPSHOT_TIMEOUT})",
            "kobra-lan camera pipe": f"; --timeout accepts 1 to {MAX_PIPE_TIMEOUT} and --max-bytes accepts 1 to {MAX_PIPE_BYTES}",
            "kobra-lan files upload": "; review first with kobra-lan gcode inspect",
            "kobra-lan files delete": "; find a root filename with kobra-lan files list and supply --execute",
            "kobra-lan print plan": ". Supply --slot-map PAINT_INDEX=SLOT for each G-code paint index.",
            "kobra-lan print start": ". Supply --slot-map PAINT_INDEX=SLOT and review first with kobra-lan print plan.",
            "kobra-lan print watch": f"; --timeout accepts whole seconds from 1 to {MAX_TIMEOUT}",
            "kobra-lan print pause": "; inspect kobra-lan status first and supply --execute (optional --filename NAME)",
            "kobra-lan print resume": "; inspect kobra-lan status first and supply --execute (optional --filename NAME)",
            "kobra-lan print cancel": "; inspect kobra-lan status first and supply --execute (optional --filename NAME)",
            "kobra-lan jobs list": f"; --kind accepts all, start, or observation and --limit accepts 1 to {MAX_LIMIT}",
            "kobra-lan jobs info": "; supply a local attempt_id, obs-<32hex>, or unreadable-<64hex> record ID",
        }.get(prog, "")
        raise ArgumentFailure("Invalid arguments; use " + prog + " --help for supported commands and required options" + guidance)


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


def argv_is_camera_pipe(argv):
    """Detect whether the positional command tokens invoke `camera pipe`."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--json":
            index += 1
        elif token in ("--config", "--printer", "--state-dir"):
            index += 2
        elif any(token.startswith(flag + "=") for flag in ("--config", "--printer", "--state-dir")):
            index += 1
        else:
            break
    return argv[index:index + 2] == ["camera", "pipe"]


def _bounded_positive_int(value, maximum, label):
    if value.isascii() and value.isdecimal():
        parsed = int(value)
        if 1 <= parsed <= maximum:
            return parsed
    raise argparse.ArgumentTypeError(f"Invalid {label}")


def watch_timeout(value):
    return _bounded_positive_int(value, MAX_TIMEOUT, "observation timeout")


def camera_snapshot_timeout(value):
    return _bounded_positive_int(value, MAX_SNAPSHOT_TIMEOUT, "snapshot timeout")


def camera_pipe_timeout(value):
    return _bounded_positive_int(value, MAX_PIPE_TIMEOUT, "pipe timeout")


def camera_pipe_max_bytes(value):
    return _bounded_positive_int(value, MAX_PIPE_BYTES, "max-bytes limit")


def jobs_limit(value):
    return _bounded_positive_int(value, MAX_LIMIT, "history limit")


def slot_map_entry(value):
    topology = onboard_topology()
    match = re.fullmatch(r"(\d+)=([1-9]\d*)", value, flags=re.ASCII)
    if match:
        try:
            paint_index = int(match[1].lstrip("0") or "0")
            slot = int(match[2])
        except ValueError:
            pass
        else:
            if is_valid_onboard_slot(KOBRA_X.model_id, slot):
                return paint_index, slot
    raise argparse.ArgumentTypeError(
        f"Invalid slot mapping. Use PAINT_INDEX=SLOT with an onboard slot from 1 to {topology.slot_count}."
    )


def build_parser():
    """Build the canonical command metadata without opening access or state."""
    slot_count = onboard_topology().slot_count
    camera_validated = "true" if is_camera_hardware_validated(KOBRA_X.model_id, QUALIFIED_FIRMWARE) else "false"
    control_validated = "true" if is_control_hardware_validated(KOBRA_X.model_id, QUALIFIED_FIRMWARE) else "false"
    delete_validated = "true" if is_delete_hardware_validated(KOBRA_X.model_id, QUALIFIED_FIRMWARE) else "false"
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
    p = sub.add_parser("slots", help="Inspect onboard four-slot filament inventory; read-only",
                       description="Read-only inspection of the qualified Kobra X onboard four-slot filament box. "
                                   "Does not modify slots, credentials, or local state; external ACE units remain unqualified.")
    slots = p.add_subparsers(dest="slots_command", required=True)
    slots.add_parser("list", help=f"List onboard filament slots (1..{slot_count}); read-only",
                     description=f"Read-only onboard four-slot inventory on {QUALIFICATION_SUMMARY} "
                                 "(idle or printing). Reports slot numbering, status, material, color, and start availability.")
    p = sub.add_parser("camera", help="Inspect camera status, capture a snapshot, or pipe raw FLV",
                       description="status is read-only over pinned MQTT without touching port 18088. "
                                   "snapshot and pipe attempt a direct read-only HTTP-FLV fetch first, falling back to "
                                   "one video/startCapture + video/stopCapture pair unless --no-start-capture is supplied. "
                                   "Stream URLs and tokens are never exposed.")
    camera = p.add_subparsers(dest="camera_command", required=True)
    camera.add_parser("status", help="Read-only camera presence, timelapse flag, and stream announcement",
                      description=f"Read-only camera inspection on {QUALIFICATION_SUMMARY} "
                                  f"(hardware_camera_validated: {camera_validated}). Queries pinned MQTT info and "
                                  "peripherie without mutating printer state, opening port 18088, or exposing stream tokens.")
    p = camera.add_parser("snapshot", help="Capture one JPEG or PNG frame via optional external ffmpeg",
                          description=f"Experimental single-frame snapshot on {QUALIFICATION_SUMMARY} "
                                      f"(hardware_camera_validated: {camera_validated}). Requires optional external ffmpeg "
                                      "on PATH; pipes validated FLV bytes via stdin without passing stream URLs in argv. "
                                      "Attempts direct read-only fetch first, falling back to startCapture/stopCapture "
                                      "unless --no-start-capture is set.")
    p.add_argument("--output", type=Path, required=True, metavar="PATH",
                   help="Destination .jpg, .jpeg, or .png path (refuses existing files without --overwrite)")
    p.add_argument("--timeout", type=camera_snapshot_timeout, default=DEFAULT_SNAPSHOT_TIMEOUT, metavar="SECONDS",
                   help=f"Snapshot deadline in seconds (1 to {MAX_SNAPSHOT_TIMEOUT}, default {DEFAULT_SNAPSHOT_TIMEOUT})")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing destination file atomically")
    p.add_argument("--no-start-capture", action="store_true",
                   help="Fail instead of falling back to MQTT video/startCapture when direct stream read fails")
    p = camera.add_parser("pipe", help="Stream raw HTTP-FLV bytes to stdout without external binaries",
                          description=f"Experimental raw HTTP-FLV stdout stream on {QUALIFICATION_SUMMARY} "
                                      f"(hardware_camera_validated: {camera_validated}). Requires no external video binaries "
                                      "and rejects global --json. Attempts direct read-only fetch first, falling back to "
                                      "startCapture/stopCapture unless --no-start-capture is set. Diagnostics use stderr only.")
    p.add_argument("--timeout", type=camera_pipe_timeout, default=None, metavar="SECONDS",
                   help=f"Optional streaming deadline in seconds (1 to {MAX_PIPE_TIMEOUT})")
    p.add_argument("--max-bytes", type=camera_pipe_max_bytes, default=None, metavar="BYTES",
                   help=f"Optional raw byte cap (1 to {MAX_PIPE_BYTES})")
    p.add_argument("--no-start-capture", action="store_true",
                   help="Fail instead of falling back to MQTT video/startCapture when direct stream read fails")
    p = sub.add_parser("files", help="Inspect storage, upload, or delete a stored file",
                       description="list/info are read-only. upload requires a reviewed hash and --execute. "
                                   "Experimental delete requires an idle printer and --execute.")
    files = p.add_subparsers(dest="files_command", required=True)
    files.add_parser("list", help="List printer storage; read-only")
    p = files.add_parser("info", help="Read remote metadata; no upload")
    p.add_argument("name")
    p = files.add_parser("upload", help="Upload reviewed bytes once; never starts a print")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p.add_argument("--execute", action="store_true", required=True)
    p.add_argument("--sha256", required=True, help="Reviewed file SHA-256 from gcode inspect")
    p = files.add_parser("delete", help="Experimental removal of one root file; requires --execute",
                         description=f"Experimental single-shot deletion on {QUALIFICATION_SUMMARY} "
                                     f"(hardware_delete_validated: {delete_validated}). Requires an idle printer with no active job. "
                                     "Preserves local receipts and markers. If the outcome is uncertain, inspect "
                                     "files list before taking further action. Do not resend blindly.")
    p.add_argument("name", help="Root filename from files list")
    p.add_argument("--execute", action="store_true", required=True, help="Explicitly execute one delete command")
    p = sub.add_parser("gcode", help="Local inspection; no target or network")
    gcode = p.add_subparsers(dest="gcode_command", required=True)
    p = gcode.add_parser("inspect", help="Inspect immutable local G-code; no state writes")
    p.add_argument("file", type=Path)
    p.add_argument("--name")
    p = sub.add_parser("print", help="Watch, plan, start or control a print",
                       description="watch and plan are read-only. start requires a reviewed plan hash and --execute. "
                                   "pause, resume and cancel are experimental controls requiring --execute")
    printing = p.add_subparsers(dest="print_command", required=True)
    for command in ("plan", "start"):
        p = printing.add_parser(command, help="Read-only plan" if command == "plan" else "Experimental guarded execution")
        p.add_argument("file", type=Path, help="Local copy of the previously uploaded G-code")
        p.add_argument("--name", required=True, help="Existing remote filename")
        p.add_argument("--slot-map", action="append", required=True, type=slot_map_entry, metavar="PAINT_INDEX=SLOT",
                       help=f"Map a G-code paint index to an onboard slot (1..{slot_count}). Repeat for each declared index.")
        p.add_argument("--reprint-from", metavar="PREVIOUS_ATTEMPT_ID",
                       help="Reprint after observed activity; find the latest local attempt ID with print plan or jobs list")
        for flag in ["auto-leveling", "vibration-compensation", "flow-calibration"]:
            p.add_argument("--" + flag, choices=["on", "off"], required=True)
        if command == "start":
            p.add_argument("--execute", action="store_true", required=True)
            p.add_argument("--plan-sha256", required=True, help="Reviewed hash from print plan")
    p = printing.add_parser("watch", help="Observe the active print without controlling it",
                            description=f"Read-only observation on {QUALIFICATION_SUMMARY}. "
                                        "Reports an unknown outcome when telemetry cannot establish it.")
    p.add_argument("--timeout", type=watch_timeout, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                   help=f"Observation deadline in seconds (1 to {MAX_TIMEOUT}, default {DEFAULT_TIMEOUT})")
    control_docs = {
        "pause": (
            "Experimental guarded pause of an active print; requires --execute",
            f"Experimental single-shot pause on {QUALIFICATION_SUMMARY} "
            f"(hardware_control_validated: {control_validated}). Requires active printing state and --execute; "
            "never retries uncertain commands automatically.",
        ),
        "resume": (
            "Experimental guarded resume of a paused print; requires --execute",
            f"Experimental single-shot resume on {QUALIFICATION_SUMMARY} "
            f"(hardware_control_validated: {control_validated}). Requires paused state and --execute; "
            "never retries uncertain commands automatically.",
        ),
        "cancel": (
            "Experimental guarded cancel of an active or paused print; requires --execute",
            f"Experimental single-shot cancel on {QUALIFICATION_SUMMARY} "
            f"(hardware_control_validated: {control_validated}). Requires printing, recognized preparation phase, "
            "or paused state and --execute; never retries uncertain commands automatically.",
        ),
    }
    for command, (help_text, desc_text) in control_docs.items():
        p = printing.add_parser(command, help=help_text, description=desc_text)
        p.add_argument("--execute", action="store_true", required=True,
                       help="Explicitly execute one control command; no implicit dry run")
        p.add_argument("--filename", metavar="NAME",
                       help="Optional active remote filename guard; refuses before publish on mismatch")
    p = sub.add_parser("jobs", help="Inspect local job history; no network or state writes",
                       description="Offline read-only inspection of local start receipts/markers and saved watch "
                                   "observations. Does not query the printer; unwatched other-client prints are absent.")
    jobs = p.add_subparsers(dest="jobs_command", required=True)
    p = jobs.add_parser("list", help="List local start attempts and saved watch observations",
                        description="Offline device-scoped local job history ordered newest first. "
                                    "Locate eligible attempt_id values for print plan --reprint-from.")
    p.add_argument("--kind", choices=list(KINDS), default="all",
                   help="Record kind filter (default: all)")
    p.add_argument("--limit", type=jobs_limit, default=DEFAULT_LIMIT, metavar="N",
                   help=f"Maximum records to return (1 to {MAX_LIMIT}, default {DEFAULT_LIMIT})")
    p = jobs.add_parser("info", help="Inspect one local start attempt, watch observation, or unreadable record",
                        description="Offline device-scoped detail view for a local attempt_id, obs-<32hex> "
                                    "observation_id, or unreadable-<64hex> record reference.")
    p.add_argument("record_id", metavar="RECORD_ID",
                   help="Local 64-hex attempt_id, obs-<32hex> observation_id, or unreadable-<64hex> reference")
    p = sub.add_parser("completion", help="Generate offline shell completion; no access or state")
    p.add_argument("shell", choices=["bash", "zsh", "fish"])
    return parser


def _silence_broken_stdout():
    """Redirect stdout fd to /dev/null after BrokenPipeError to prevent shutdown exit 120."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        pass
    finally:
        os.close(devnull)


def _emit_error(json_mode, pipe_mode, *, code, message, partial=None):
    if pipe_mode and not json_mode:
        print(f"Error ({code}): {safe_text(message)}", file=sys.stderr)
        return
    emit(json_mode, partial, code=code, message=message)


def main(argv=None):
    """Dispatch CLI operations using the established exit classes."""
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = root_json(argv)
    pipe_mode = (not json_mode) and argv_is_camera_pipe(argv)
    watch = None
    state_dir = None
    try:
        args = parser.parse_args(argv)
        json_mode = args.json
        state_dir = args.state_dir
        if args.command == "camera" and args.camera_command == "pipe":
            if json_mode:
                raise ArgumentFailure("camera pipe writes raw binary FLV to stdout and rejects --json")
            pipe_mode = True
        if args.command == "camera" and args.camera_command == "snapshot":
            try:
                validate_snapshot_request(args.output, timeout=args.timeout, overwrite=args.overwrite)
            except CameraArgumentError as error:
                raise ArgumentFailure(str(error)) from None
        if args.command == "files" and args.files_command == "upload":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
                raise ArgumentFailure("Upload requires a full --sha256 from gcode inspect and --execute")
            args.sha256 = args.sha256.lower()
            _, manifest = describe(args.file, args.name)
            if manifest["sha256"] != args.sha256:
                raise ProtocolError("File SHA-256 differs from reviewed manifest; use gcode inspect")
        if args.command == "files" and args.files_command == "delete":
            try:
                validate_delete_filename(args.name)
            except ProtocolError:
                raise ArgumentFailure("Invalid filename. Supply one safe root filename from kobra-lan files list.") from None
        if getattr(args, "reprint_from", None) is not None and not valid_attempt_id(args.reprint_from):
            raise ArgumentFailure("--reprint-from requires a full lowercase local attempt ID from print plan")
        if args.command == "print" and args.print_command in ("plan", "start"):
            slot_map = dict(args.slot_map)
            if len(slot_map) != len(args.slot_map):
                raise ArgumentFailure("Duplicate paint index. Supply --slot-map PAINT_INDEX=SLOT once for each index.")
            args.slot_map = slot_map
        if args.command == "print" and args.print_command == "start":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", args.plan_sha256):
                raise ArgumentFailure("Start requires a full --plan-sha256 from print plan and --execute")
            args.plan_sha256 = args.plan_sha256.lower()
        if args.command == "print" and args.print_command == "watch":
            watch = WatchProgress()
        if args.command == "print" and args.print_command in ("pause", "resume", "cancel"):
            if args.filename is not None:
                try:
                    validate_filename(args.filename)
                except ProtocolError:
                    raise ArgumentFailure(
                        "Invalid --filename guard; supply a safe printable filename without path separators or URL characters"
                    ) from None
        if args.command == "jobs" and args.jobs_command == "info":
            if not valid_record_id(args.record_id):
                raise ArgumentFailure(
                    "jobs info requires a valid local attempt_id, obs-<32hex>, or unreadable-<64hex> record ID"
                )
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
            data, result = describe(args.file, args.name)
            result = {**result, **inspect_gcode_filaments(data), "dry_run": True}
        elif watch is not None:
            result = observe(registry, args.config, args.selected_printer, args.timeout,
                             watch.update, on_target=watch.bind_device)
            if result is None:
                result = watch.result("unknown", "deadline_expired")
            result = watch.record(result, args.state_dir)
        elif pipe_mode:
            with registry.access(args.config, args.selected_printer) as (config, _):
                pipe_result = camera_pipe(
                    config,
                    sys.stdout.buffer,
                    timeout=args.timeout,
                    max_bytes=args.max_bytes,
                    allow_start_capture=not args.no_start_capture,
                )
            if isinstance(pipe_result, dict) and pipe_result.get("broken_pipe"):
                _silence_broken_stdout()
            return 0
        else:
            with registry.access(args.config, args.selected_printer) as (config, source):
                result = operate(args, config)
        emit(json_mode, result)
        return 0
    except ArgumentFailure as error:
        _emit_error(json_mode, pipe_mode, code="invalid_arguments", message=str(error))
        return 2
    except ProtocolError as error:
        status = getattr(error, "exit_code", 2)
        if status not in (2, 3, 130):
            status = 2
        code = "interrupted" if status == 130 else ("operation_failed" if status == 3 else "validation_failed")
        partial = watch.record(watch.partial(code), state_dir) if watch else getattr(error, "result", None)
        _emit_error(json_mode, pipe_mode, code=code, message=str(error), partial=partial)
        return status
    except (PairingLocalError, ProfileLocalError) as error:
        _emit_error(json_mode, pipe_mode, code="operation_failed", message=str(error),
                    partial=getattr(error, "result", None))
        return 3
    except (ImportError, OSError, ValueError, TypeError, KeyError):
        partial = watch.record(watch.partial("operation_failed"), state_dir) if watch else None
        _emit_error(json_mode, pipe_mode, code="operation_failed",
                    message="Local configuration or network operation failed; no automatic retry",
                    partial=partial)
        return 3
    except KeyboardInterrupt:
        if pipe_mode:
            print("Error (interrupted): Camera pipe interrupted", file=sys.stderr)
            return 130
        if watch is None:
            raise
        emit(json_mode, watch.record(watch.partial("interrupted"), state_dir),
             code="interrupted", message="Print observation interrupted")
        return 130


def _operate_camera(args, config):
    if args.camera_command == "status":
        return camera_status(config)
    return camera_snapshot(
        config,
        args.output,
        timeout=args.timeout,
        overwrite=args.overwrite,
        allow_start_capture=not args.no_start_capture,
    )


def _operate_files(args, config):
    if args.files_command == "list":
        with MQTT(config) as client:
            return {"records": list_files(client)}
    if args.files_command == "info":
        with MQTT(config) as client:
            return safe_file_details(file_details(client, args.name))
    if args.files_command == "delete":
        return delete_file(config, args.name, args.state_dir)
    if not args.sha256:
        raise ProtocolError("--sha256 is required for an actual upload")
    return execute(config, args.file, args.sha256, args.state_dir, args.name)


def _operate_print(args, config):
    if args.print_command in ("pause", "resume", "cancel"):
        return control_print(config, args.print_command, args.state_dir, expected_filename=args.filename)
    return start(config, args.file, args.name, args.slot_map,
        args.auto_leveling == "on", args.vibration_compensation == "on", args.flow_calibration == "on",
        args.state_dir, args.print_command == "start", getattr(args, "plan_sha256", None), args.reprint_from)


def operate(args, config):
    """Run one operation while its selected managed configuration is leased."""
    if args.command == "status":
        return snapshot(config)
    if args.command == "slots":
        return list_slots(config)
    if args.command == "camera":
        return _operate_camera(args, config)
    if args.command == "files":
        return _operate_files(args, config)
    if args.command == "print":
        return _operate_print(args, config)
    if args.jobs_command == "list":
        return list_jobs(config, args.state_dir, kind=args.kind, limit=args.limit)
    return job_info(config, args.state_dir, args.record_id)


if __name__ == "__main__":
    raise SystemExit(main())
