#!/usr/bin/env python3
"""Fail-closed destination checks for read-only audit/report programs.

The callers in this directory inspect valuable ROOT files and campaign
metadata, but also emit JSON.  Destination validation must therefore happen
before any success *or failure* report is written.  In particular, resolving
an output's final component and then replacing that result can turn an output
symlink into an input-file overwrite.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import Iterable, Sequence, Tuple


class ReportDestinationError(ValueError):
    """The requested report destination is not safe for atomic replacement."""


RootPolicy = Tuple[Path, Sequence[Path]]
ParentIdentity = Tuple[int, int, int]


def lexical_absolute(path: Path) -> Path:
    """Return an absolute path without following its final component."""

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def canonical_nonfinal(path: Path) -> Path:
    """Resolve the parent location while preserving the final directory entry."""

    absolute = lexical_absolute(path)
    try:
        parent = absolute.parent.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise ReportDestinationError(
            f"cannot resolve report parent {absolute.parent}: {error}"
        ) from error
    return parent / absolute.name


def _existing_regular(path: Path) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ReportDestinationError(
            f"cannot inspect report destination {path}: {error}"
        ) from error
    if stat.S_ISLNK(info.st_mode):
        raise ReportDestinationError(
            f"refusing symlink report destination: {path}"
        )
    if not stat.S_ISREG(info.st_mode):
        raise ReportDestinationError(
            f"refusing non-regular report destination: {path}"
        )
    return info


def report_parent_identity(path: Path) -> ParentIdentity:
    """Return the identity of an existing canonical report directory."""

    try:
        info = path.parent.lstat()
    except OSError as error:
        raise ReportDestinationError(
            f"report parent is unavailable {path.parent}: {error}"
        ) from error
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReportDestinationError(
            f"report parent is not a real directory: {path.parent}"
        )
    return info.st_dev, info.st_ino, info.st_mode


def require_safe_atomic_target(path: Path) -> ParentIdentity:
    """Recheck the parent and final entry immediately before atomic writing."""

    identity = report_parent_identity(path)
    _existing_regular(path)
    return identity


def atomic_write_report_text(path: Path, text: str) -> None:
    """Publish text through a stable parent descriptor and sibling temporary."""

    parent_identity = require_safe_atomic_target(path)
    flags = os.O_RDONLY
    for option in ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW"):
        if hasattr(os, option):
            flags |= getattr(os, option)
    parent_fd = os.open(path.parent, flags)
    temporary_name: str | None = None
    try:
        opened_parent = os.fstat(parent_fd)
        if (
            opened_parent.st_dev,
            opened_parent.st_ino,
            opened_parent.st_mode,
        ) != parent_identity:
            raise ReportDestinationError(
                f"report parent changed before temporary creation: {path.parent}"
            )

        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            create_flags |= os.O_CLOEXEC
        for _ in range(100):
            candidate = f".{path.name}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(candidate, create_flags, 0o600, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise ReportDestinationError(
                f"could not allocate a unique sibling temporary for {path}"
            )

        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())

        if report_parent_identity(path) != parent_identity:
            raise ReportDestinationError(
                f"report parent changed before publication: {path.parent}"
            )
        # Both names are interpreted relative to the already-opened parent;
        # neither a swapped ancestor nor a final symlink is followed.
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
        if report_parent_identity(path) != parent_identity:
            raise ReportDestinationError(
                f"report parent changed during publication: {path.parent}"
            )
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as error:
        raise ReportDestinationError(
            f"cannot compare report/input identities {left} and {right}: {error}"
        ) from error


def _reject_existing_tree_alias(
    output: Path, output_info: os.stat_result | None, root: Path
) -> None:
    """Reject an external hardlink to any regular file below a protected root."""

    if output_info is None:
        return
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ReportDestinationError(
            f"cannot inspect protected input root {root}: {error}"
        ) from error
    if not stat.S_ISDIR(root_info.st_mode):
        return

    output_identity = (output_info.st_dev, output_info.st_ino)

    def on_walk_error(error: OSError) -> None:
        raise error

    try:
        for directory, _, filenames in os.walk(
            root, topdown=True, followlinks=False, onerror=on_walk_error
        ):
            directory_path = Path(directory)
            for name in filenames:
                candidate = directory_path / name
                if candidate == output:
                    continue
                try:
                    candidate_info = candidate.lstat()
                except FileNotFoundError:
                    continue
                if (
                    stat.S_ISREG(candidate_info.st_mode)
                    and (candidate_info.st_dev, candidate_info.st_ino)
                    == output_identity
                ):
                    raise ReportDestinationError(
                        "report destination is a hardlink alias of protected "
                        f"input {candidate}: {output}"
                    )
    except ReportDestinationError:
        raise
    except OSError as error:
        raise ReportDestinationError(
            f"cannot scan protected input root {root}: {error}"
        ) from error


def validate_report_destination(
    output: Path,
    *,
    protected_files: Iterable[Path] = (),
    root_policies: Iterable[RootPolicy] = (),
) -> Path:
    """Validate and canonicalize one report destination.

    ``root_policies`` contains ``(protected_root, allowed_report_locations)``
    pairs.  A destination below a protected root is rejected unless it is one
    of that root's explicit reserved locations.  The returned path has a
    canonical parent but an unresolved final component, which is essential for
    safe ``os.replace`` semantics.
    """

    raw_output = lexical_absolute(output)
    output_info = _existing_regular(raw_output)
    canonical_output = canonical_nonfinal(raw_output)
    report_parent_identity(canonical_output)

    for protected in protected_files:
        raw_protected = lexical_absolute(protected)
        try:
            canonical_protected = raw_protected.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise ReportDestinationError(
                f"cannot resolve protected input {raw_protected}: {error}"
            ) from error
        if (
            raw_output == raw_protected
            or canonical_output == canonical_protected
            or _same_existing_file(raw_output, raw_protected)
        ):
            raise ReportDestinationError(
                f"report destination aliases protected input {raw_protected}: "
                f"{raw_output}"
            )

    canonical_policies: list[tuple[Path, set[Path]]] = []
    for root, allowed_locations in root_policies:
        try:
            canonical_root = lexical_absolute(root).resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise ReportDestinationError(
                f"cannot resolve protected input root {root}: {error}"
            ) from error
        allowed = {canonical_nonfinal(location) for location in allowed_locations}
        canonical_policies.append((canonical_root, allowed))
        if _is_within(canonical_output, canonical_root) and canonical_output not in allowed:
            allowed_text = ", ".join(str(item) for item in sorted(allowed)) or "none"
            raise ReportDestinationError(
                f"report destination is inside protected input root {canonical_root}; "
                f"reserved locations: {allowed_text}; requested: {canonical_output}"
            )

    # If an existing destination is an external hardlink to a file below a
    # protected tree, lexical/canonical comparisons above cannot reveal it.
    for canonical_root, _ in canonical_policies:
        _reject_existing_tree_alias(canonical_output, output_info, canonical_root)

    return canonical_output
