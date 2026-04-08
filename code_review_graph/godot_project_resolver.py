"""Godot ``project.godot`` resolver.

Resolves Godot ``res://`` paths to absolute filesystem paths by locating
the nearest ``project.godot`` file walking up from the GDScript source
file. Also exposes the autoload list declared in the ``[autoload]``
section, which Godot treats as globally accessible singletons — the
graph uses this list to emit ``IMPORTS_FROM`` edges from scripts that
reference an autoload by name.

Parallels ``tsconfig_resolver.py`` in structure: a cached walk-upward
lookup plus an INI-style config parse. ``project.godot`` is INI-
compatible, so Python's stdlib ``configparser`` handles it directly.
"""

from __future__ import annotations

import configparser
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# File extensions probed when resolving a bare ``res://path`` with no
# explicit extension. GDScript projects typically use ``.gd`` for scripts
# and ``.tscn`` / ``.tres`` for scenes and resources.
_PROBE_EXTENSIONS = [".gd", ".tscn", ".tres"]


class GodotProjectResolver:
    """Resolves ``res://`` paths using the nearest ``project.godot``.

    Caches the resolved project directory, autoload table, and parsed
    config per-directory so repeated lookups during a large graph build
    avoid redundant filesystem walks.
    """

    def __init__(self) -> None:
        # Directory (string) -> project dict or None (no project.godot).
        # Project dict shape:
        #   {
        #     "project_dir": <str absolute path>,
        #     "autoloads": {<name>: <stripped res:// path>},
        #   }
        self._cache: dict[str, Optional[dict]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_res_path(
        self, res_path: str, file_path: str,
    ) -> Optional[str]:
        """Resolve a ``res://foo/bar.gd`` (or ``foo/bar.gd``) to a file.

        Strips any leading ``res://``, joins to the project root, probes
        ``_PROBE_EXTENSIONS`` when no extension is given, and returns an
        absolute path string. Returns ``None`` when no project.godot is
        found or the target doesn't exist.
        """
        project = self._load_project_for_file(file_path)
        if project is None:
            return None
        stripped = (
            res_path[len("res://"):]
            if res_path.startswith("res://") else res_path
        )
        if not stripped:
            return None
        base = Path(project["project_dir"]) / stripped
        probed = _probe_path(base)
        if probed is not None:
            return str(probed.resolve())
        return None

    def get_autoloads(self, file_path: str) -> dict[str, str]:
        """Return ``{autoload_name: stripped_res_path}`` for the project.

        Values are the raw (res://-stripped) paths declared in the
        ``[autoload]`` section of ``project.godot``. Empty dict if no
        project file is found.
        """
        project = self._load_project_for_file(file_path)
        if project is None:
            return {}
        return dict(project.get("autoloads", {}))

    def get_project_dir(self, file_path: str) -> Optional[str]:
        """Return the directory containing the nearest ``project.godot``.

        Useful for relativizing absolute paths when emitting edges.
        """
        project = self._load_project_for_file(file_path)
        if project is None:
            return None
        return project["project_dir"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_project_for_file(self, file_path: str) -> Optional[dict]:
        """Walk up from ``file_path``'s directory to find project.godot."""
        start_dir = Path(file_path).parent.resolve()
        current = start_dir
        visited: list[str] = []

        while True:
            dir_str = str(current)
            if dir_str in self._cache:
                cached = self._cache[dir_str]
                for v in visited:
                    self._cache[v] = cached
                return cached

            visited.append(dir_str)
            candidate = current / "project.godot"
            if candidate.is_file():
                parsed = self._parse_project_godot(candidate)
                parsed["project_dir"] = dir_str
                for v in visited:
                    self._cache[v] = parsed
                return parsed

            parent = current.parent
            if parent == current:
                for v in visited:
                    self._cache[v] = None
                return None
            current = parent

    @staticmethod
    def _parse_project_godot(path: Path) -> dict:
        """Parse ``project.godot`` and extract the ``[autoload]`` section.

        Godot's config files are INI-compatible with a few edge cases:
        values may contain unquoted commas or be raw string literals
        wrapped in double quotes. We only care about the autoload names
        and their target paths, so a forgiving configparser does the job.
        """
        parser = configparser.ConfigParser(
            strict=False,
            interpolation=None,
            comment_prefixes=(";",),  # Godot uses ';' for comments
            inline_comment_prefixes=(";",),
        )
        # Preserve original case of autoload keys — configparser lowercases
        # option names by default, but GameState != gamestate when matching
        # identifiers in GDScript source text.
        parser.optionxform = str  # type: ignore[assignment,method-assign]
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            logger.debug(
                "GodotProjectResolver: cannot read %s", path,
            )
            return {"autoloads": {}}

        try:
            parser.read_string(raw)
        except configparser.Error as exc:
            logger.debug(
                "GodotProjectResolver: parse failed for %s: %s", path, exc,
            )
            return {"autoloads": {}}

        autoloads: dict[str, str] = {}
        if parser.has_section("autoload"):
            for key, value in parser.items("autoload"):
                cleaned = _clean_autoload_value(value)
                if cleaned:
                    autoloads[key] = cleaned
        return {"autoloads": autoloads}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


_AUTOLOAD_LEADING = re.compile(r"^\*")


def _clean_autoload_value(value: str) -> str:
    """Strip the leading ``*`` marker, quotes, and ``res://`` prefix.

    Godot autoload declarations look like::

        [autoload]
        GameState="*res://autoload/game_state.gd"
        Utils="res://utils.gd"

    The leading ``*`` marks the autoload as a singleton (always included
    in the scene tree). We strip it alongside surrounding quotes and the
    ``res://`` scheme so the result is the raw project-relative path.
    """
    raw = value.strip().strip('"').strip("'")
    raw = _AUTOLOAD_LEADING.sub("", raw).strip()
    if raw.startswith("res://"):
        raw = raw[len("res://"):]
    return raw


def _probe_path(base: Path) -> Optional[Path]:
    """Probe ``base`` and ``base + extension`` for an existing file."""
    if base.is_file():
        return base
    if base.suffix:
        return None
    for ext in _PROBE_EXTENSIONS:
        candidate = base.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None
