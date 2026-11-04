"""Private local profile registry; no device access or operational state writes."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .config import Config, ProtocolError

CONFIG_FILE = 'config.json'
REGISTRY_FILE = 'profiles.json'
UNKNOWN_PROFILE = 'Unknown profile; run printer list'

DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class ProfileSelectionError(ProtocolError):
    """A missing or conflicting explicit selection, rather than broken local access."""


class ProfileLocalError(OSError):
    """Safe local diagnostics, independent of arbitrary filesystem contents."""
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


def validate_name(name):
    if not isinstance(name, str) or re.fullmatch(r'[a-z][a-z0-9-]{0,47}', name) is None:
        raise ProtocolError('Profile name must match [a-z][a-z0-9-]{0,47}')
    return name


def private(fd, directory=False):
    current = os.fstat(fd)
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if current.st_uid != os.geteuid() or not kind(current.st_mode) or stat.S_IMODE(current.st_mode) != mode:
        raise ProfileLocalError('Managed storage must be user-owned with directories 0700 and files 0600')


def open_directory(path, create=False, require_private=True):
    """Walk every component via directory descriptors, never following symlinks."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
                child = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        if require_private:
            private(fd, directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_json(fd, name):
    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        private(file_fd)
        with os.fdopen(file_fd, 'r') as stream:
            file_fd = None
            # Avoid unbounded reads of corrupt local files.
            raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError
            return json.loads(raw)
    finally:
        if file_fd is not None:
            os.close(file_fd)


class Registry:
    def __init__(self, root=None):
        self.root = Path(os.path.abspath(root or Path.home() / '.config/kobra-lan'))

    def path(self, name):
        return self.root / 'profiles' / validate_name(name) / CONFIG_FILE

    def empty(self):
        return {'version': 1, 'default': None, 'profiles': {}}

    def _validate_entry(self, name, entry):
        validate_name(name)
        if (not isinstance(entry, dict) or set(entry) != {'config_path', 'owned_files', 'firmware'}
                or entry.get('config_path') != str(self.path(name))
                or not isinstance(entry.get('owned_files'), list)):
            raise ValueError
        for relative in entry['owned_files']:
            if not isinstance(relative, str) or not self._owned_name(relative):
                raise ValueError
        if entry.get('firmware') not in (None, '2.0.2.2'):
            raise ValueError

    def _validate_index(self, data):
        if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1
                or not isinstance(data.get('profiles'), dict)):
            raise ValueError
        for name, entry in data['profiles'].items():
            self._validate_entry(name, entry)
        selected = data.get('default')
        if selected is not None:
            if not isinstance(selected, dict) or set(selected) != {'name'} or selected['name'] not in data['profiles']:
                raise ValueError
        return data

    def read(self):
        try:
            fd = open_directory(self.root, require_private=False)
        except FileNotFoundError:
            return self.empty()
        try:
            try:
                data = read_json(fd, REGISTRY_FILE)
            except FileNotFoundError:
                return self.empty()
            private(fd, directory=True)
            return self._validate_index(data)
        except (ValueError, TypeError, KeyError, ProtocolError):
            raise ProfileLocalError('Profile registry is invalid or has an unknown version; preserve it for local review') from None
        finally:
            os.close(fd)

    @staticmethod
    def _owned_name(relative):
        return relative == CONFIG_FILE or re.fullmatch(r'\.pair-[0-9a-f]{32}/(client\.crt|client\.key|candidate\.json)', relative) is not None

    @contextmanager
    def lock(self, exclusive=True, create=True, timeout=1.0):
        """Readers do not create metadata; a missing lock means a pristine registry."""
        try:
            fd = open_directory(self.root, create=create, require_private=create)
        except FileNotFoundError:
            yield False
            return
        lock_fd = None
        try:
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
            if create:
                flags |= os.O_CREAT
            try:
                lock_fd = os.open('.profiles.lock', flags, 0o600, dir_fd=fd)
            except FileNotFoundError:
                # Every managed writer creates this file before publishing its index.
                if (self.root / REGISTRY_FILE).exists():
                    raise ProfileLocalError('Managed registry lock is missing; preserve storage for local review') from None
                yield False
                return
            private(fd, directory=True)
            private(lock_fd)
            end = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(lock_fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= end:
                        raise ProfileLocalError('Profile storage is busy; wait for the active operation to finish') from None
                    time.sleep(min(0.02, max(0, end - time.monotonic())))
            yield True
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(fd)

    def write(self, data):
        """Caller holds exclusive lock; after replace, errors retain the committed index."""
        fd = open_directory(self.root)
        temporary = '.profiles-' + uuid.uuid4().hex
        try:
            stream_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(stream_fd, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(data, stream, ensure_ascii=True)
                stream.flush()
                os.fsync(stream.fileno())
            # Validate the existing index/destination again; never overwrite unknown formats.
            self.read()
            os.replace(temporary, REGISTRY_FILE, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)

    def reserve(self, name):
        name = validate_name(name)
        if name in self.read()['profiles']:
            raise ProtocolError('Profile already registered; choose a new name')
        fd = open_directory(self.root / 'profiles', create=True)
        try:
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                raise ProtocolError('Profile destination exists; inspect locally instead of repeating provisioning') from None
            os.fsync(fd)
        finally:
            os.close(fd)
        return self.path(name)

    def load(self, name, data=None):
        name = validate_name(name)
        data = self.read() if data is None else data
        if name not in data['profiles']:
            raise ProfileSelectionError(UNKNOWN_PROFILE)
        path = self.path(name)
        parent_fd = open_directory(self.root / "profiles")
        os.close(parent_fd)
        fd = open_directory(path.parent)
        try:
            raw = read_json(fd, path.name)
            cfg = Config(**raw)
            # Validate known files via no-follow descriptors, including PEM paths.
            for filename in (cfg.client_cert, cfg.client_key):
                parent = open_directory(Path(filename).parent)
                try:
                    secret = os.open(Path(filename).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    try:
                        private(secret)
                    finally:
                        os.close(secret)
                finally:
                    os.close(parent)
            # Existing config schema and validation remain authoritative.
            cfg.validate()
            return cfg
        finally:
            os.close(fd)

    def register(self, name, firmware):
        cfg = self.load_unregistered(name)
        parent = self.path(name).parent
        owned = [CONFIG_FILE]
        for filename in (cfg.client_cert, cfg.client_key):
            relative = str(Path(filename).relative_to(parent))
            if not self._owned_name(relative):
                raise ProfileLocalError('Unrecognized managed pairing material; inspect the complete config locally')
            owned.append(relative)
        # Interrupted pairing finalization can retain this extra hardlink.
        candidate = str(Path(cfg.client_key).parent.relative_to(parent) / 'candidate.json')
        if (parent / candidate).exists():
            owned.append(candidate)
        data = self.read()
        if name in data['profiles']:
            raise ProtocolError('Profile already registered')
        data['profiles'][name] = {'config_path': str(self.path(name)), 'firmware': firmware, 'owned_files': owned}
        self.write(data)

    def load_unregistered(self, name):
        return self.load(name, {'profiles': {name: {}}})

    def select(self, name):
        with self.lock():
            self.load(name)
            data = self.read()
            data['default'] = {'name': name}
            self.write(data)
        return {'name': name, 'default': True}

    def _explicit(self, config):
        path = Path(os.path.abspath(config))
        for candidate in (self.root / 'profiles', (self.root / 'profiles').resolve()):
            if not path.is_relative_to(candidate):
                continue
            relative = path.relative_to(candidate).parts
            if len(relative) != 2 or relative[1] != CONFIG_FILE:
                raise ProtocolError('Explicit managed configuration must name a complete profile config')
            name = validate_name(relative[0])
            if name in self.read()['profiles']:
                self.load(name)
                return self.path(name), {'source': 'profile', 'name': name}
            # A published orphan is recoverable via explicit config, never via --printer.
            break
        return path, {'source': 'explicit-config', 'name': None}

    def resolve(self, config=None, name=None):
        if config is not None and name is not None:
            raise ProtocolError('--config and --printer are mutually exclusive')
        if name is not None:
            validate_name(name)
        if config is not None:
            return self._explicit(config)
        data = self.read()
        if name is None:
            selected = data['default']
            if selected is None:
                raise ProfileSelectionError('No default selected; run printer use NAME or supply --printer/--config')
            name = selected['name']
        if name not in data['profiles']:
            raise ProfileSelectionError(UNKNOWN_PROFILE)
        return self.path(name), {'source': 'profile', 'name': name}

    @contextmanager
    def access(self, config=None, name=None):
        # Lock before resolution so selection/removal cannot race config loading.
        with self.lock(exclusive=False, create=False) as leased:
            path, source = self.resolve(config, name)
            if source['source'] == 'profile' and not leased:
                # A writer published profiles after the missing-lock check; acquire its lock.
                with self.lock(exclusive=False, create=False):
                    yield self.load(source['name']), {**source, 'config_path': str(path)}
            else:
                cfg = self.load(source['name']) if source['source'] == 'profile' else Config.load(path)
                yield cfg, {**source, 'config_path': str(path)}

    def metadata(self, cfg, path, source, data):
        name = source.get('name')
        return {**source, 'config_path': str(path), 'available': True, 'host': cfg.host,
                'model_id': cfg.type_id, 'printer_id': cfg.printer_id, 'tls_sha256': cfg.tls_sha256,
                'default': name is not None and data['default'] == {'name': name},
                'last_observed_firmware': data['profiles'].get(name, {}).get('firmware')}

    def info(self, config=None, name=None):
        with self.access(config, name) as (cfg, source):
            return self.metadata(cfg, source['config_path'], source, self.read())

    def inventory(self):
        with self.lock(exclusive=False, create=False):
            data = self.read()
            entries = []
            for name in data['profiles']:
                source = {'source': 'profile', 'name': name}
                try:
                    entry = self.metadata(self.load(name, data), self.path(name), source, data)
                except (OSError, ValueError, TypeError, KeyError, ProtocolError):
                    entry = {**source, 'available': False, 'default': data['default'] == {'name': name},
                             'code': 'local_config_unavailable'}
                entries.append(entry)
            return {'profiles': entries, 'default': data['default']}

    def _observed_registration(self, name):
        try:
            return name in self.read()['profiles']
        except (OSError, ValueError, TypeError, KeyError, ProtocolError):
            return None

    def _observed_default(self, name):
        try:
            return self.read()['default'] == {'name': name}
        except (OSError, ValueError, TypeError, KeyError, ProtocolError):
            return None

    @staticmethod
    def _outcome(value, yes, no, unknown='uncertain'):
        if value is None:
            return unknown
        return yes if value else no

    def _register_published(self, name, destination, firmware):
        try:
            self.register(name, firmware)
        except (OSError, ValueError, TypeError, KeyError, ProtocolError):
            registered = self._observed_registration(name)
            outcome = self._outcome(registered, 'registered', 'unregistered', 'registration uncertain')
            result = {'name': name, 'config_path': str(destination), 'registered': registered,
                      'default': self._observed_default(name)}
            raise ProfileLocalError(f'Named config committed; profile {name} {outcome}. Retain PEMs; inspect printer list and complete config locally, do not repeat provisioning', result) from None

    def _select_published(self, name, destination):
        data = self.read()
        data['default'] = {'name': name}
        try:
            self.write(data)
        except (OSError, ValueError, TypeError, KeyError, ProtocolError):
            selected = self._observed_default(name)
            outcome = self._outcome(selected, 'selected', 'unchanged')
            result = {'name': name, 'config_path': str(destination), 'registered': True, 'default': selected}
            raise ProfileLocalError(f'Profile {name} committed; default {outcome}. Retain PEMs, inspect printer list and run printer use {name} locally; do not repeat provisioning', result) from None

    def pair(self, name, host, expected=None, make_default=False):
        """Reserve before provisioning; reconcile ambiguous commits without replay."""
        from .pairing import pair, validate_host, validate_pin
        validate_name(name)
        validate_host(host)
        validate_pin(expected)
        with self.lock():
            destination = self.reserve(name)
            try:
                result = pair(destination, host, expected)
            except OSError:
                if destination.exists():
                    raise ProfileLocalError('Named pairing finalization failed; complete config may exist. Retain PEMs and inspect locally; do not repeat provisioning') from None
                raise
            self._register_published(name, destination, result['firmware'])
            if make_default:
                self._select_published(name, destination)
            return {**result, 'name': name, 'default': self.read()['default'] == {'name': name}}

    def removal_preview(self, name):
        validate_name(name)
        data = self.read()
        if name not in data['profiles']:
            raise ProtocolError(UNKNOWN_PROFILE)
        entry = data['profiles'][name]
        return {'name': name, 'config_path': str(self.path(name)), 'entry': entry,
                'default': data['default'] == {'name': name},
                'files': [str(self.path(name).parent / f) for f in entry['owned_files']]}

    @staticmethod
    def _confirm_removal(preview, stdin, stderr):
        if not stdin.isatty():
            raise ProtocolError('Local removal requires terminal consent or --yes; no files changed')
        print(json.dumps({'local_removal_preview': preview}, ensure_ascii=True), file=stderr)
        print('Remove this local profile? Device credentials are not revoked. [y/N] ', end='', file=stderr, flush=True)
        try:
            answer = stdin.readline(32)
        except (EOFError, OSError):
            answer = ''
        if len(answer) == 32 or answer.strip().lower() not in ('y', 'yes'):
            raise ProtocolError('Local removal was not confirmed; no files changed')

    def _detach(self, name, data, preview):
        entry = data['profiles'].pop(name)
        if data['default'] == {'name': name}:
            data['default'] = None
        try:
            self.write(data)
        except OSError:
            registered = self._observed_registration(name)
            detached = None if registered is None else not registered
            outcome = self._outcome(detached, 'detached', 'still registered')
            result = {'name': name, 'registration_removed': detached, 'deleted_files': [],
                      'preserved_files': preview['files'], 'device_credentials_revoked': False, 'cleanup_failed': True}
            raise ProfileLocalError(f'Profile removal commit {outcome}; files retained. Inspect printer list and the managed directory locally; do not repeat provisioning', result) from None
        return entry

    def remove(self, name, yes=False, stdin=None, stderr=None):
        import sys
        stdin = sys.stdin if stdin is None else stdin
        stderr = sys.stderr if stderr is None else stderr
        with self.lock(exclusive=False, create=False):
            preview = self.removal_preview(name)
        if not yes:
            self._confirm_removal(preview, stdin, stderr)
        with self.lock():
            if self.removal_preview(name) != preview:
                raise ProtocolError('Profile metadata changed after preview; inspect again before removal')
            data = self.read()
            references, uncertain = self._references(data, name)
            entry = self._detach(name, data, preview)
            return self._cleanup(name, entry, references, uncertain)

    def _references(self, data, removed):
        """Known retained configs only; any ambiguity conservatively retains PEMs."""
        references = set()
        uncertain = False
        for name in data['profiles']:
            if name == removed:
                continue
            try:
                references.add(str(self.path(name).resolve(strict=True)))
                cfg = self.load(name, data)
                for filename in (cfg.client_cert, cfg.client_key):
                    references.update((os.path.abspath(filename), str(Path(filename).resolve(strict=True))))
            except (OSError, ValueError, TypeError, KeyError, ProtocolError):
                uncertain = True
        return references, uncertain

    @staticmethod
    def _exclusive_file(current, path, relative, references, uncertain):
        return (stat.S_ISREG(current.st_mode) and current.st_uid == os.geteuid()
                and stat.S_IMODE(current.st_mode) == 0o600 and current.st_nlink == 1
                and path not in references and (not uncertain or relative == CONFIG_FILE))

    def _cleanup_file(self, fd, root, relative, references, uncertain, deleted, preserved):
        parts = Path(relative).parts
        parent = fd
        path = str(root / relative)
        try:
            if len(parts) == 2:
                parent = os.open(parts[0], DIRECTORY_FLAGS, dir_fd=fd)
                private(parent, directory=True)
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if not self._exclusive_file(current, path, relative, references, uncertain):
                preserved.append(path)
                return False
            os.unlink(parts[-1], dir_fd=parent)
            deleted.append(path)
            os.fsync(parent)
        except FileNotFoundError:
            return False
        except OSError:
            if path not in deleted:
                preserved.append(path)
            return True
        finally:
            if parent != fd:
                os.close(parent)
        return False

    @staticmethod
    def _cleanup_directories(fd, root, directories, preserved):
        for directory in directories:
            try:
                os.rmdir(directory, dir_fd=fd)
            except FileNotFoundError:
                continue
            except OSError:
                preserved.append(str(root / directory))
        preserved.extend(str(root / f) for f in os.listdir(fd) if str(root / f) not in preserved)
        os.fsync(fd)

    @staticmethod
    def _cleanup_root(root, preserved):
        try:
            parent = open_directory(root.parent)
            try:
                os.rmdir(root.name, dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(parent)
        except OSError:
            if root.exists() and str(root) not in preserved:
                preserved.append(str(root))
            return not preserved
        return False

    @staticmethod
    def _cleanup_receipt(name, deleted, preserved, errors=False):
        return {'name': name, 'registration_removed': True, 'deleted_files': sorted(deleted),
                'preserved_files': sorted(set(preserved)), 'device_credentials_revoked': False,
                'cleanup_failed': errors}

    def _cleanup(self, name, entry, references, uncertain):
        # Enforce the ownership boundary here too, even for a direct internal caller.
        name = validate_name(name)
        owned_files = entry['owned_files']
        if not isinstance(owned_files, list) or any(
                not isinstance(relative, str) or not self._owned_name(relative) for relative in owned_files):
            raise ProtocolError('Unsafe managed cleanup manifest; preserve files for local review')
        root = self.path(name).parent
        deleted, preserved = [], []
        errors = False
        try:
            fd = open_directory(root)
        except FileNotFoundError:
            return self._cleanup_receipt(name, [], [])
        except OSError:
            return self._cleanup_receipt(name, [], [str(root)], True)
        try:
            for relative in owned_files:
                failed = self._cleanup_file(fd, root, relative, references, uncertain, deleted, preserved)
                errors |= failed
            directories = {Path(f).parts[0] for f in owned_files if len(Path(f).parts) == 2}
            self._cleanup_directories(fd, root, directories, preserved)
        except OSError:
            preserved.append(str(root))
            errors = True
        finally:
            os.close(fd)
        errors |= self._cleanup_root(root, preserved)
        return self._cleanup_receipt(name, deleted, preserved, errors)
