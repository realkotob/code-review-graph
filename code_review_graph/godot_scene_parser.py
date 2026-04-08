"""Minimal parser for Godot ``.tscn`` (scene) and ``.tres`` (resource) files.

Godot's text scene/resource format is a stable line-oriented header
syntax — there is no bundled tree-sitter grammar in
``tree_sitter_language_pack``. Since we only need to follow external
script/resource references (to emit ``IMPORTS_FROM`` edges into the
graph), a regex-based extractor is more than enough and sidesteps a new
grammar dependency.

Example input::

    [gd_scene load_steps=3 format=3 uid="uid://abc"]

    [ext_resource type="Script" path="res://player/player.gd" id="1"]
    [ext_resource type="PackedScene" path="res://ui/hud.tscn" id="2"]

    [node name="Player" type="CharacterBody2D"]
    script = ExtResource("1")

The parser extracts every ``ext_resource`` block's ``path=`` attribute
along with its ``type=`` attribute, then returns ``SceneReference``
records that the graph pipeline turns into edges.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ``[ext_resource type="Script" path="res://a/b.gd" id="1"]``
# Attributes may appear in any order; match a whole bracketed header
# whose first token is ``ext_resource``, then pull ``path`` and ``type``
# from inside it.
_EXT_RESOURCE_HEADER_RE = re.compile(
    r"\[ext_resource\b([^\]]*)\]",
)
_PATH_ATTR_RE = re.compile(r'path\s*=\s*"([^"]*)"')
_TYPE_ATTR_RE = re.compile(r'type\s*=\s*"([^"]*)"')


@dataclass
class SceneReference:
    """One ``ext_resource`` entry parsed from a ``.tscn`` / ``.tres`` file."""

    resource_type: str  # "Script", "PackedScene", "Texture2D", ...
    path: str           # project-relative path (res:// stripped)
    line: int           # 1-indexed line number of the header


def extract_scene_references(
    source: bytes, file_path: str,
) -> list[SceneReference]:
    """Return every ``ext_resource`` reference found in ``source``.

    The returned paths have the ``res://`` prefix stripped (if present)
    so they can be fed directly to ``GodotProjectResolver.resolve_res_path``
    or used as bare edge targets when no project is available.
    """
    try:
        text = source.decode("utf-8", errors="replace")
    except Exception:
        logger.debug(
            "godot_scene_parser: decode failed for %s", file_path,
        )
        return []

    refs: list[SceneReference] = []
    for match in _EXT_RESOURCE_HEADER_RE.finditer(text):
        inner = match.group(1)
        path_match = _PATH_ATTR_RE.search(inner)
        if path_match is None:
            continue
        raw_path = path_match.group(1)
        if raw_path.startswith("res://"):
            raw_path = raw_path[len("res://"):]
        type_match = _TYPE_ATTR_RE.search(inner)
        resource_type = type_match.group(1) if type_match else ""

        # Compute 1-indexed line of the header for edge reporting.
        line_no = text.count("\n", 0, match.start()) + 1

        refs.append(SceneReference(
            resource_type=resource_type,
            path=raw_path,
            line=line_no,
        ))
    return refs


def detect_scene_language(path: Path) -> Optional[str]:
    """Return ``"godot_scene"`` for ``.tscn`` / ``.tres``, else None."""
    suffix = path.suffix.lower()
    if suffix in (".tscn", ".tres"):
        return "godot_scene"
    return None
