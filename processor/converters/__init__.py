"""
processor.converters — the registry of file-format converters.

A converter is one module that turns a format quick-plot cannot read into one
it can. Every module has the same four things:

  NAME              identifier, e.g. "mef2_to_nwb"
  OUTPUT_EXTENSION  what it writes, e.g. ".nwb"
  detect(input_dir) -> Path | None
                    the folder (or file) this converter would convert, or
                    None when the input isn't its format. Looks at the files,
                    not only at the extension where it can.
  convert(source, output_dir, config) -> Path
                    writes exactly one file into output_dir and returns it;
                    raises on failure.

CONVERTERS below is the whole registry — an explicit list, in the order they
are asked, the same way quick-plot lists its templates. Adding a format is one
new module and one line here. Nothing else in the repo, the workflow or MCP
changes.
"""

from __future__ import annotations

from pathlib import Path

from processor.converters import mef2_to_nwb

CONVERTERS = [
    mef2_to_nwb,
]


def known_names() -> list[str]:
    return [c.NAME for c in CONVERTERS]


def find_converter(input_dir: Path):
    """Ask each converter in turn; return (converter, source) for the first
    one that recognises the input, or (None, None)."""
    for converter in CONVERTERS:
        source = converter.detect(input_dir)
        if source is not None:
            return converter, source
    return None, None


__all__ = ["CONVERTERS", "find_converter", "known_names"]
