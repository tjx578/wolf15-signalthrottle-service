from __future__ import annotations

from pathlib import Path

from scripts.check_production_artifacts import (
    audit_image_root,
    load_manifest,
    main,
    parse_manifest_lines,
    run_negative_control,
)


MANIFEST_PATH = Path(".dockerignore")


def test_canonical_manifest_covers_required_containment_categories() -> None:
    raw_entries = {pattern.raw for pattern in load_manifest(MANIFEST_PATH)}

    assert {
        ".env",
        ".env.*",
        "scripts",
        "app/market",
        "app/outcomes",
        "app/planner",
        "app/api/routes_debug.py",
        "app/api/routes_market.py",
        "app/api/routes_outcomes.py",
        "app/api/routes_replay.py",
        "app/models/trade_plan.py",
        "app/scoring/execution_grader.py",
        "app/scoring/final_score.py",
        "app/**/risk_reservation*",
        "app/**/final_signal*",
        "app/**/execution_command*",
        "app/**/broker_export*",
        "app/**/ea_export*",
    } <= raw_entries


def test_checker_negative_control_fails_then_passes(tmp_path: Path) -> None:
    patterns = load_manifest(MANIFEST_PATH)
    target = tmp_path / "app" / "app" / "api" / "routes_replay.py"
    target.parent.mkdir(parents=True)
    target.write_text("# injected forbidden artifact\n", encoding="utf-8")

    dirty = audit_image_root(tmp_path, workdir="app", patterns=patterns)
    assert dirty.forbidden_paths == ("app/api/routes_replay.py",)
    assert main(["--root", str(tmp_path), "--workdir", "app"]) == 1

    target.unlink()
    clean = audit_image_root(tmp_path, workdir="app", patterns=patterns)
    assert clean.forbidden_paths == ()
    assert main(["--root", str(tmp_path), "--workdir", "app"]) == 0


def test_checker_glob_and_negation_semantics(tmp_path: Path) -> None:
    patterns = parse_manifest_lines(
        [
            "# BEGIN production_forbidden_artifacts",
            "app/**/final_signal*",
            "!app/fixtures/final_signal_example.py",
            "# END production_forbidden_artifacts",
        ]
    )
    forbidden = tmp_path / "app" / "app" / "runtime" / "final_signal_exporter.py"
    allowed = tmp_path / "app" / "app" / "fixtures" / "final_signal_example.py"
    forbidden.parent.mkdir(parents=True)
    allowed.parent.mkdir(parents=True)
    forbidden.touch()
    allowed.touch()

    audit = audit_image_root(tmp_path, workdir="app", patterns=patterns)

    assert audit.forbidden_paths == ("app/runtime/final_signal_exporter.py",)
    assert audit.manifest_entries == audit.checked_entries
    assert audit.unchecked_entries == 0


def test_checker_builtin_self_test_passes() -> None:
    patterns = load_manifest(MANIFEST_PATH)

    run_negative_control(patterns, "app")
    assert main(["--self-test"]) == 0
