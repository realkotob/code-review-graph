"""Tests for the Godot .tscn / .tres scene parser."""

from __future__ import annotations

from pathlib import Path

from code_review_graph.godot_scene_parser import (
    SceneReference,
    detect_scene_language,
    extract_scene_references,
)
from code_review_graph.parser import CodeParser


class TestSceneExtraction:
    def test_detects_tscn_and_tres(self) -> None:
        assert detect_scene_language(Path("x.tscn")) == "godot_scene"
        assert detect_scene_language(Path("x.tres")) == "godot_scene"
        assert detect_scene_language(Path("x.gd")) is None

    def test_extracts_script_reference(self) -> None:
        src = (
            b'[gd_scene load_steps=2 format=3]\n'
            b'\n'
            b'[ext_resource type="Script" path="res://player.gd" id="1"]\n'
            b'\n'
            b'[node name="Player" type="CharacterBody2D"]\n'
            b'script = ExtResource("1")\n'
        )
        refs = extract_scene_references(src, "scene.tscn")
        assert len(refs) == 1
        ref = refs[0]
        assert isinstance(ref, SceneReference)
        assert ref.resource_type == "Script"
        assert ref.path == "player.gd"
        assert ref.line == 3

    def test_extracts_multiple_mixed_types(self) -> None:
        src = (
            b'[gd_scene load_steps=3 format=3]\n'
            b'[ext_resource type="Script" path="res://p.gd" id="1"]\n'
            b'[ext_resource type="PackedScene" path="res://hud.tscn" id="2"]\n'
            b'[ext_resource type="Texture2D" path="res://icon.png" id="3"]\n'
        )
        refs = extract_scene_references(src, "scene.tscn")
        types = [r.resource_type for r in refs]
        paths = [r.path for r in refs]
        assert types == ["Script", "PackedScene", "Texture2D"]
        assert paths == ["p.gd", "hud.tscn", "icon.png"]

    def test_ignores_non_ext_resource_headers(self) -> None:
        src = (
            b'[gd_scene load_steps=1 format=3]\n'
            b'[node name="Root" type="Node"]\n'
            b'[sub_resource type="Theme" id="abc"]\n'
        )
        assert extract_scene_references(src, "scene.tscn") == []


class TestSceneParserIntegration:
    def _write_project(self, tmp: Path) -> None:
        (tmp / "project.godot").write_text(
            '[application]\n'
            'config/name="Test"\n',
            encoding="utf-8",
        )
        (tmp / "player.gd").write_text(
            "extends CharacterBody2D\n",
            encoding="utf-8",
        )

    def test_parse_file_emits_imports_from(self, tmp_path: Path) -> None:
        self._write_project(tmp_path)
        scene_path = tmp_path / "player.tscn"
        scene_path.write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '\n'
            '[ext_resource type="Script" path="res://player.gd" id="1"]\n'
            '\n'
            '[node name="Player" type="CharacterBody2D"]\n'
            'script = ExtResource("1")\n',
            encoding="utf-8",
        )

        parser = CodeParser()
        nodes, edges = parser.parse_file(scene_path)

        assert parser.detect_language(scene_path) == "godot_scene"
        file_nodes = [n for n in nodes if n.kind == "File"]
        assert len(file_nodes) == 1
        assert file_nodes[0].language == "godot_scene"

        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) == 1
        assert imports[0].source == str(scene_path)
        assert imports[0].target == str((tmp_path / "player.gd").resolve())
        assert imports[0].extra.get("godot_resource_type") == "Script"

    def test_parse_file_without_project_falls_back_to_raw_path(
        self, tmp_path: Path,
    ) -> None:
        scene_path = tmp_path / "orphan.tscn"
        scene_path.write_text(
            '[gd_scene format=3]\n'
            '[ext_resource type="Script" path="res://foo.gd" id="1"]\n',
            encoding="utf-8",
        )

        parser = CodeParser()
        _, edges = parser.parse_file(scene_path)
        imports = [e for e in edges if e.kind == "IMPORTS_FROM"]
        assert len(imports) == 1
        assert imports[0].target == "foo.gd"
