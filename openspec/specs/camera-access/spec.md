# camera-access Specification

## Purpose

Provide direct, bounded, token-redacted access to a qualified Anycubic Kobra X printer's local LAN camera—supporting read-only status inspection, single-frame snapshot capture via an optional external `ffmpeg` binary, and raw HTTP-FLV piping to stdout—without a background daemon, bridge, or credential leakage.

## Requirements

### Requirement: Read-only camera status inspection
`camera status` SHALL connect over one pinned authenticated MQTT session, verify fresh qualification, query `info` and `peripherie` without mutating printer state, opening port `18088`, or writing local state, and report `camera_present`, `timelapse_supported`, `stream_url_announced`, `stream_protocol`, `stream_port`, `printer_state`, `experimental: true`, and centralized `hardware_camera_validated` without exposing any URL or token.

#### Scenario: Qualified printer with camera present and local FLV URL announced
- **WHEN** `camera status` runs against a qualified printer whose fresh `peripherie` report declares `camera: 1` and whose fresh `info` report announces a valid `http://<host>:18088/live/<token>` URL in `urls.rtspUrl` and `features.camera_timelapse_support: true`
- **THEN** the CLI exits 0 and reports `camera_present: true`, `timelapse_supported: true`, `stream_url_announced: true`, `stream_protocol: "http-flv"`, `stream_port: 18088`, `experimental: true`, and centralized `hardware_camera_validated` without exposing the URL or token in stdout or stderr

#### Scenario: Camera absent or stream URL not announced
- **WHEN** `camera status` runs against a qualified printer reporting `camera: 0` or omitting `urls.rtspUrl`
- **THEN** the CLI exits 0 and reports `camera_present: false` and/or `stream_url_announced: false` (`stream_protocol: null`, `stream_port: null`) without sending `startCapture` or contacting port `18088`

#### Scenario: Unqualified printer rejected before camera inspection
- **WHEN** `camera status` receives an unqualified model, firmware version, or mismatched identity in the fresh `info` report
- **THEN** the CLI exits 2 (`validation_failed`) without opening port `18088` or writing local state

### Requirement: Strict local stream URL validation and token redaction
Before opening any HTTP stream connection, the CLI SHALL accept only plain `http` URLs targeting the paired IPv4 host on port `18088` with a bounded `/live/<token>` path and no userinfo, query, fragment, path traversal, or control characters. HTTP connections SHALL disable proxies and redirects. Stream URLs and tokens SHALL NEVER appear in stdout, stderr, JSON envelopes, exceptions, or subprocess arguments.

#### Scenario: Hostile or off-host stream URL rejected before HTTP connection
- **WHEN** a printer's `info` report announces a stream URL targeting a different host, a different port, `https`, a query string, userinfo, or a non-`/live/` path
- **THEN** `camera status` reports `stream_url_announced: false` and `camera snapshot` / `camera pipe` exit 2 (`validation_failed`) without opening any HTTP socket and without echoing the URL or token

#### Scenario: Token never exposed in errors or subprocess arguments
- **WHEN** `camera snapshot` or `camera pipe` fails during stream fetch or `ffmpeg` decoding on a URL containing a synthetic token
- **THEN** neither stdout, stderr, JSON error fields, nor the `ffmpeg` argv contain the stream URL or token

### Requirement: Read-only-first stream acquisition with optional capture fallback
`camera snapshot` and `camera pipe` SHALL verify qualification and `camera == 1`, then attempt a direct read-only HTTP `GET` to the validated stream URL (accepting HTTP `200`/`206` with valid `FLV` magic) without sending `startCapture`. Only if direct read fails and `--no-start-capture` is omitted SHALL the CLI send one `video`/`startCapture`, refresh `info`, retry the `GET` once, and send best-effort `video`/`stopCapture` in cleanup.

#### Scenario: Direct read succeeds without mutating printer state
- **WHEN** `camera snapshot` or `camera pipe` connects to a qualified printer whose `:18088/live/<token>` endpoint directly serves `HTTP 206 Partial Content` with valid FLV bytes
- **THEN** no MQTT `video/startCapture` or `video/stopCapture` message is published and capture completes with `capture_mode: "direct"`, `start_capture_used: false`, `stop_capture_sent: false`

#### Scenario: Direct read fails and fallback activates and cleans up capture
- **WHEN** direct `GET :18088/live/<token>` returns `404`, closes empty, or refuses connection and `--no-start-capture` is omitted
- **THEN** the CLI sends one `video/startCapture`, refreshes `info`, retries the validated stream `GET` once, and sends best-effort `video/stopCapture` in cleanup regardless of whether decoding succeeds, fails, or is interrupted

#### Scenario: Fallback disabled with --no-start-capture
- **WHEN** direct `GET :18088/live/<token>` fails to deliver a valid FLV stream and `--no-start-capture` is supplied
- **THEN** the CLI sends no `video/startCapture` or `video/stopCapture` message and exits 3 (`operation_failed`) with a safe diagnostic message

### Requirement: Single-frame camera snapshot via optional external ffmpeg
`camera snapshot` SHALL validate `--output` (`.jpg`/`.jpeg`/`.png`, existing parent, absent destination unless `--overwrite`), `--timeout` (`1..60`, default `15`), and `ffmpeg` on `PATH` before network access. It SHALL pipe bounded FLV bytes into `ffmpeg` via `stdin`, publish the decoded image atomically, and emit safe metadata (`output_path`, `format`, `bytes`, `sha256`, `width`, `height`, `capture_mode`, `start_capture_used`, `stop_capture_sent`, `experimental`, `hardware_camera_validated`).

#### Scenario: Snapshot succeeds and writes image atomically
- **WHEN** `camera snapshot --output /tmp/bed.jpg` runs against a qualified printer serving a valid HTTP-FLV stream with `ffmpeg` available
- **THEN** the CLI pipes FLV bytes to `ffmpeg` via stdin, writes `/tmp/bed.jpg` atomically, exits 0, and reports safe metadata including SHA-256, byte count, dimensions, and `capture_mode` without any token or URL

#### Scenario: Missing ffmpeg fails before network access
- **WHEN** `camera snapshot --output /tmp/bed.jpg` runs without `ffmpeg` on `PATH`
- **THEN** the CLI exits 3 (`operation_failed`) with clear guidance to install `ffmpeg`, performs zero network requests, and writes no file

#### Scenario: Existing output path rejected without --overwrite
- **WHEN** `camera snapshot --output /tmp/existing.jpg` runs without `--overwrite` and the destination already exists (including symlinks)
- **THEN** the CLI exits 2 (`validation_failed`) before contacting the printer and leaves the existing file untouched

#### Scenario: Invalid output extension or timeout rejected before network access
- **WHEN** `camera snapshot` receives an unsupported extension (e.g. `.bmp`), a directory path, or an out-of-range `--timeout`
- **THEN** the CLI exits 2 (`invalid_arguments`) before target selection or network access without echoing arbitrary unsafe values

### Requirement: Raw HTTP-FLV piping to stdout without external dependencies
`camera pipe` SHALL validate optional `--timeout` (`1..86400`) and `--max-bytes` (`1..10737418240`), require no external video binaries, verify `FLV` magic before forwarding any bytes, and write raw FLV bytes directly to `stdout` until EOF, deadline, byte cap, broken pipe, or interrupt. Diagnostics and errors SHALL go only to stderr and SHALL NEVER expose stream tokens.

#### Scenario: Raw FLV stream piped cleanly without ffmpeg
- **WHEN** `camera pipe --max-bytes 65536` runs without `ffmpeg` installed against a qualified printer serving valid HTTP-FLV bytes
- **THEN** stdout contains exact raw FLV bytes starting with `FLV` up to the byte limit, stderr contains no tokens, and the CLI exits 0

#### Scenario: Downstream consumer closes pipe early
- **WHEN** the reader attached to `camera pipe`'s stdout closes the pipe (causing `BrokenPipeError`)
- **THEN** the CLI stops reading, runs cleanup (sending `stopCapture` if fallback was used), and exits 0 without a traceback

#### Scenario: Foreground interruption during camera pipe
- **WHEN** the user interrupts `camera pipe` with `SIGINT`
- **THEN** the CLI stops streaming, runs cleanup (sending `stopCapture` if fallback was used), emits a safe stderr notice, and exits 130
