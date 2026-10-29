"""
processor-file-conversion — the stage in front of pennsieve-quick-plot.

Looks at what the data-source staged into INPUT_DIR and makes sure OUTPUT_DIR
holds something quick-plot can read:

  a format a converter recognises  ->  converted (MEF2 -> NWB)
  anything else                    ->  copied through unchanged

The one rule: this stage is never a no-op. Every run ends with data in
OUTPUT_DIR or with exit code 1 and a one-line reason. OUTPUT_DIR becomes the
next stage's INPUT_DIR, and an earlier two-stage plot workflow died on exactly
this — a stage that did nothing left the next one with an empty folder.

This file is the gate; the format-specific work lives in processor/converters/.
Runs the same way on Fargate (`python -m processor.main`) and on Lambda
(handler.py bridges the event payload to env vars, then calls main()).
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

from processor.config import Config
from processor.converters import find_converter, known_names

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("file-conversion")


class PrepError(RuntimeError):
    """A failure with a message meant for the person who asked for the plot."""


def _log_listing(folder: Path, limit: int = 50) -> None:
    """What the data-source staged, with sizes: the first thing to look at
    when a run fails, and the one thing the platform doesn't show."""
    entries = sorted(folder.iterdir())
    for entry in entries[:limit]:
        if entry.is_dir():
            n = sum(1 for _ in entry.iterdir())
            log.info("  %s/  (%d entries)", entry.name, n)
        else:
            log.info("  %s  %d bytes", entry.name, entry.stat().st_size)
    if len(entries) > limit:
        log.info("  ... %d more", len(entries) - limit)


def pass_through(input_dir: Path, output_dir: Path) -> list[Path]:
    """Copy everything in input_dir to output_dir, unchanged. Returns the copies."""
    copied: list[Path] = []
    for entry in sorted(input_dir.iterdir()):
        target = output_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)
        copied.append(target)
    return copied


def run(config: Config) -> list[Path]:
    """Fill OUTPUT_DIR from INPUT_DIR. Returns the files written; raises PrepError."""
    input_dir = Path(config.input_dir)
    output_dir = Path(config.output_dir)

    if not input_dir.is_dir():
        raise PrepError(f"INPUT_DIR does not exist: {input_dir}")
    if not any(input_dir.iterdir()):
        raise PrepError("No input file was staged for this run.")
    _log_listing(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    converter, source = find_converter(input_dir)
    if converter is None:
        written = pass_through(input_dir, output_dir)
        log.info("No converter for this input (known: %s); passed %d entr%s through unchanged",
                 ", ".join(known_names()), len(written), "y" if len(written) == 1 else "ies")
        return written

    log.info("Converter %s recognised %s", converter.NAME, source)
    output_path = converter.convert(source, output_dir, config)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise PrepError(f"{converter.NAME} finished without writing {output_path.name}.")
    log.info("Converted %s -> %s", source.name, output_path.name)
    return [output_path]


def main() -> int:
    """Process exit code: 0 when OUTPUT_DIR holds data, 1 otherwise."""
    started = time.time()
    config = Config.from_env()
    log.info("file-conversion  input=%s  output=%s  channels=%s",
             config.input_dir, config.output_dir, ",".join(config.channels) or "(all)")
    try:
        written = run(config)
    except PrepError as err:
        log.error("file-conversion failed: %s", err)
        return 1
    except Exception as err:  # noqa: BLE001 — anything the converter raised
        log.exception("file-conversion failed: %s", err)
        return 1
    log.info("Done in %.1fs: %s", time.time() - started, ", ".join(p.name for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
