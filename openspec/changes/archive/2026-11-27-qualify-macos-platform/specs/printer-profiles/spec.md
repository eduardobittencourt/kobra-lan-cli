# Spec Delta

## MODIFIED Requirements

### Requirement: Private crash-safe profile management
Profile storage SHALL use user-owned private directories and files, reject unsafe names and symlink destinations, prevent replacement, serialize local mutations, and preserve shared or active files on removal. On macOS (`darwin`), strict non-symlink traversal SHALL permit only verified root-owned OS aliases (`/var` → `/private/var`, `/tmp` → `/private/tmp`) while rejecting all user or managed symlinks.

#### Scenario: Unsafe destination or concurrent writers
- **WHEN** a profile name escapes its storage root, a destination is a symlink or two writers contend for the same name
- **THEN** invalid operations fail before provisioning and only one complete profile can become registered without replacing existing data

#### Scenario: Interrupted removal or shared files
- **WHEN** deletion encounters shared PEMs, uncertain ownership, an active profile user or a filesystem failure
- **THEN** shared/uncertain material and active access are preserved, the command reports the outcome, and no partial state silently selects another target

#### Scenario: macOS root system alias under temporary or system paths
- **WHEN** profile or state operations on macOS target a path prefixed by the OS-owned `/var` or `/tmp` root alias (such as `$TMPDIR` under `/var/folders/...`) with no user-controlled symlinks below it
- **THEN** directory traversal resolves only that verified root-owned system alias to `/private/var` or `/private/tmp`, enforces strict non-symlink (`O_NOFOLLOW`) traversal on every remaining component, and enforces user ownership and `0700`/`0600` permissions on the managed target directories and files

#### Scenario: User-controlled symlink below macOS system alias
- **WHEN** a managed profile root, device state directory, or target file under `/var` or `/tmp` on macOS contains a user-controlled symlink
- **THEN** traversal rejects the path without following the symlink and without mutating files
