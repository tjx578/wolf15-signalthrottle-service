#!/usr/bin/env python3
"""Audit the canonical production-forbidden artifact inventory."""

from __future__ import annotations

import argparse
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


MANIFEST_START = "# BEGIN production_forbidden_artifacts"
MANIFEST_END = "# END production_forbidden_artifacts"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactPattern:
    raw: str
    pattern: str
    negated: bool
    regex: re.Pattern[str]

    def matches(self, relative_path: str) -> bool:
        return bool(self.regex.fullmatch(relative_path))


@dataclass(frozen=True)
class ArtifactAudit:
    manifest_entries: int
    checked_entries: int
    unchecked_entries: int
    forbidden_paths: tuple[str, ...]


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    normalized = pattern.strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ManifestError("Empty forbidden-artifact pattern")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise ManifestError(f"Parent traversal is forbidden in manifest: {pattern}")

    output = ["^"]
    index = 0
    while index < len(normalized):
        if normalized.startswith("**/", index):
            output.append("(?:.*/)?")
            index += 3
            continue
        if normalized.startswith("**", index):
            output.append(".*")
            index += 2
            continue
        character = normalized[index]
        if character == "*":
            output.append("[^/]*")
        elif character == "?":
            output.append("[^/]")
        else:
            output.append(re.escape(character))
        index += 1

    if not any(character in normalized for character in "*?"):
        output.append("(?:/.*)?")
    output.append("$")
    return re.compile("".join(output))


def parse_manifest_lines(lines: Iterable[str]) -> tuple[ArtifactPattern, ...]:
    patterns: list[ArtifactPattern] = []
    seen: set[str] = set()
    inside = False
    found_start = False
    found_end = False

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if stripped == MANIFEST_START:
            if found_start or inside:
                raise ManifestError(f"Duplicate manifest start marker at line {line_number}")
            found_start = True
            inside = True
            continue
        if stripped == MANIFEST_END:
            if not inside:
                raise ManifestError(f"Manifest end marker without start at line {line_number}")
            inside = False
            found_end = True
            continue
        if not inside or not stripped or stripped.startswith("#"):
            continue

        negated = stripped.startswith("!")
        pattern = stripped[1:].strip() if negated else stripped
        identity = f"!{pattern}" if negated else pattern
        if identity in seen:
            raise ManifestError(f"Duplicate manifest entry at line {line_number}: {identity}")
        seen.add(identity)
        patterns.append(
            ArtifactPattern(
                raw=identity,
                pattern=pattern,
                negated=negated,
                regex=_compile_pattern(pattern),
            )
        )

    if not found_start or not found_end or inside:
        raise ManifestError("Canonical forbidden-artifact manifest markers are incomplete")
    if not patterns:
        raise ManifestError("Canonical forbidden-artifact manifest is empty")
    return tuple(patterns)


def load_manifest(path: Path) -> tuple[ArtifactPattern, ...]:
    return parse_manifest_lines(path.read_text(encoding="utf-8").splitlines())


def audit_image_root(
    root: Path,
    *,
    workdir: str,
    patterns: Sequence[ArtifactPattern],
) -> ArtifactAudit:
    image_workdir = root / workdir
    if not image_workdir.is_dir():
        raise ManifestError(f"Image workdir does not exist: {image_workdir}")

    forbidden: list[str] = []
    candidates = sorted(
        path.relative_to(image_workdir).as_posix()
        for path in image_workdir.rglob("*")
    )
    for candidate in candidates:
        is_forbidden = False
        for pattern in patterns:
            if pattern.matches(candidate):
                is_forbidden = not pattern.negated
        if is_forbidden:
            forbidden.append(candidate)

    return ArtifactAudit(
        manifest_entries=len(patterns),
        checked_entries=len(patterns),
        unchecked_entries=0,
        forbidden_paths=tuple(forbidden),
    )


def run_negative_control(patterns: Sequence[ArtifactPattern], workdir: str) -> None:
    with tempfile.TemporaryDirectory(prefix="observer-artifact-negative-control-") as tmp:
        root = Path(tmp)
        target = root / workdir / "app" / "api" / "routes_replay.py"
        target.parent.mkdir(parents=True)
        target.write_text("# forbidden negative control\n", encoding="utf-8")

        dirty = audit_image_root(root, workdir=workdir, patterns=patterns)
        if "app/api/routes_replay.py" not in dirty.forbidden_paths:
            raise ManifestError("Negative control was not rejected by the checker")

        target.unlink()
        clean = audit_image_root(root, workdir=workdir, patterns=patterns)
        if clean.forbidden_paths:
            raise ManifestError("Checker did not pass after removing negative control")


def _print_audit(audit: ArtifactAudit) -> None:
    print(f"forbidden_manifest_entries={audit.manifest_entries}")
    print(f"checked_entries={audit.checked_entries}")
    print(f"unchecked_entries={audit.unchecked_entries}")
    print(f"forbidden_artifacts={len(audit.forbidden_paths)}")
    for path in audit.forbidden_paths:
        print(f"FORBIDDEN: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(".dockerignore"))
    parser.add_argument("--workdir", default="app")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--root", type=Path)
    args = parser.parse_args(argv)

    try:
        patterns = load_manifest(args.manifest)
        if args.validate_only:
            print(f"forbidden_manifest_entries={len(patterns)}")
            print(f"checked_entries={len(patterns)}")
            print("unchecked_entries=0")
            return 0
        if args.self_test:
            run_negative_control(patterns, args.workdir)
            print("negative_control=PASS")
            return 0

        audit = audit_image_root(args.root, workdir=args.workdir, patterns=patterns)
        _print_audit(audit)
        return 1 if audit.forbidden_paths or audit.unchecked_entries else 0
    except (ManifestError, OSError) as exc:
        print(f"artifact inventory error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
