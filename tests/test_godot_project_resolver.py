"""Tests for GodotProjectResolver and the autoload IMPORTS_FROM wiring."""

from __future__ import annotations

from pathlib import Path

from code_review_graph.godot_project_resolver import GodotProjectResolver
from code_review_graph.parser import CodeParser


def _write_project(tmp: Path) -> None:
    """Write a minimal project.godot with one autoload and a res script."""
    (tmp / "project.godot").write_text(
        '; Godot config ;\n'
        '[application]\n'
        'config/name="Test"\n'
        '\n'
        '[autoload]\n'
        'GameState="*res://autoload/game_state.gd"\n'
        'Utils="res://utils.gd"\n',
        encoding="utf-8",
    )
    (tmp / "autoload").mkdir(parents=True, exist_ok=True)
    (tmp / "autoload" / "game_state.gd").write_text(
        'extends Node\n'
        'class_name GameState\n'
        'var level: int = 1\n',
        encoding="utf-8",
    )
    (tmp / "utils.gd").write_text(
        'class_name Utils\n'
        'static func add(a, b):\n'
        '    return a + b\n',
        encoding="utf-8",
    )


class TestGodotProjectResolver:
    def test_finds_project_walking_up(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        nested = tmp_path / "scripts" / "player"
        nested.mkdir(parents=True)
        player_gd = nested / "player.gd"
        player_gd.write_text("extends Node\n", encoding="utf-8")

        resolver = GodotProjectResolver()
        project_dir = resolver.get_project_dir(str(player_gd))
        assert project_dir == str(tmp_path.resolve())

    def test_autoloads_parsed_with_names(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        resolver = GodotProjectResolver()
        autoloads = resolver.get_autoloads(str(tmp_path / "dummy.gd"))
        assert autoloads == {
            "GameState": "autoload/game_state.gd",
            "Utils": "utils.gd",
        }

    def test_resolve_res_path_returns_absolute(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        resolver = GodotProjectResolver()
        fake_caller = tmp_path / "somewhere.gd"
        resolved = resolver.resolve_res_path(
            "res://utils.gd", str(fake_caller),
        )
        assert resolved == str((tmp_path / "utils.gd").resolve())

    def test_resolve_res_path_probes_extensions(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        resolver = GodotProjectResolver()
        fake_caller = tmp_path / "somewhere.gd"
        resolved = resolver.resolve_res_path(
            "utils", str(fake_caller),
        )
        assert resolved == str((tmp_path / "utils.gd").resolve())

    def test_no_project_returns_none(self, tmp_path: Path) -> None:
        resolver = GodotProjectResolver()
        fake_caller = tmp_path / "orphan.gd"
        fake_caller.write_text("extends Node\n", encoding="utf-8")
        assert resolver.get_project_dir(str(fake_caller)) is None
        assert resolver.resolve_res_path(
            "res://x.gd", str(fake_caller),
        ) is None
        assert resolver.get_autoloads(str(fake_caller)) == {}

    def test_cache_hit_second_lookup(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        resolver = GodotProjectResolver()
        fake_caller = tmp_path / "scripts" / "a.gd"
        (tmp_path / "scripts").mkdir()
        fake_caller.write_text("extends Node\n", encoding="utf-8")
        first = resolver.get_project_dir(str(fake_caller))
        second = resolver.get_project_dir(str(fake_caller))
        assert first == second


class TestAutoloadEdgeWiring:
    def test_preload_res_path_resolves_to_absolute(
        self, tmp_path: Path,
    ) -> None:
        _write_project(tmp_path)
        player_path = tmp_path / "player.gd"
        player_path.write_text(
            'extends Node\n'
            'const GS = preload("res://autoload/game_state.gd")\n',
            encoding="utf-8",
        )

        parser = CodeParser()
        _, edges = parser.parse_file(player_path)
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) >= 1
        resolved_targets = {e.target for e in imports}
        expected = str((tmp_path / "autoload" / "game_state.gd").resolve())
        assert expected in resolved_targets

    def test_autoload_reference_emits_import(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        player_path = tmp_path / "player.gd"
        player_path.write_text(
            'extends Node\n'
            'func _ready():\n'
            '    var lvl = GameState.level\n',
            encoding="utf-8",
        )

        parser = CodeParser()
        _, edges = parser.parse_file(player_path)
        autoload_edges = [
            e for e in edges
            if e.kind == "IMPORTS_FROM"
            and e.extra.get("gdscript_autoload") == "GameState"
        ]
        assert len(autoload_edges) == 1
        expected = str((tmp_path / "autoload" / "game_state.gd").resolve())
        assert autoload_edges[0].target == expected

    def test_unused_autoload_does_not_emit_edge(
        self, tmp_path: Path,
    ) -> None:
        _write_project(tmp_path)
        player_path = tmp_path / "player.gd"
        player_path.write_text(
            'extends Node\n'
            'func _ready():\n'
            '    print("hi")\n',
            encoding="utf-8",
        )

        parser = CodeParser()
        _, edges = parser.parse_file(player_path)
        autoload_edges = [
            e for e in edges
            if e.kind == "IMPORTS_FROM"
            and e.extra.get("gdscript_autoload")
        ]
        assert autoload_edges == []
