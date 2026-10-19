"""
mef2_to_nwb — a folder of MEF 2.0 files (one .mef per channel) -> one NWB file.

The work is done by the three modules under mef2/, moved here unchanged from
processor-mef-timeseries:

  mef_streamer.stage_from_stream   runs mefstreamer.jar (built from
                                   Pennsieve/mef2streamer) and writes one
                                   .bin + .json per channel into a staging dir
  MultiChannelReader               reads the staged channels, memory-mapped
  NWBWriter                        writes the NWB in chunks

The jar is the format check: it reads the MEF header and exits 1 on anything
that is not MEF2 (MEF3 is a different, folder-based format and is not
handled here). detect() therefore only has to find the .mef files.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
from pathlib import Path

# The mef2 modules (pynwb, hdmf, numpy) are imported inside convert(), not
# here: this module is imported on every run, including pass-through runs on
# Lambda, and pynwb alone costs ~15 s of cold start. detect() needs none of it.

log = logging.getLogger(__name__)

NAME = "mef2_to_nwb"
INPUT_EXTENSIONS = (".mef",)
OUTPUT_EXTENSION = ".nwb"
# A MEF 2.x file opens with a 1024-byte header; the jar reads it with
# readFully() and dies with a bare EOFException on anything shorter.
MEF2_HEADER_BYTES = 1024


def _has_mef_files(folder: Path) -> bool:
    return any(
        p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS
        for p in folder.iterdir()
    )


def detect(input_dir: Path) -> Path | None:
    """The folder holding the .mef files: input_dir itself, or the single
    subfolder that has them (a staged package may arrive one level down).
    None when there are no .mef files either place."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        return None
    if _has_mef_files(input_dir):
        return input_dir
    candidates = [d for d in sorted(input_dir.iterdir()) if d.is_dir() and _has_mef_files(d)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        log.warning("%d subfolders of %s hold .mef files; converting the first: %s",
                    len(candidates), input_dir, candidates[0].name)
        return candidates[0]
    return None


def _check_mef_files(source: Path) -> None:
    """Fail with a reason naming the file when a .mef can't be MEF2.

    An empty or truncated file (a staging problem, or a placeholder upload)
    would otherwise surface as a Java EOFException ten lines deep in the log.
    """
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS)
    for p in files:
        size = p.stat().st_size
        log.info("  %s  %d bytes", p.name, size)
        if size < MEF2_HEADER_BYTES:
            raise RuntimeError(
                f"{p.name} is {size} bytes, shorter than the {MEF2_HEADER_BYTES}-byte MEF2 "
                f"header: the staged file is empty or truncated, so there is nothing to convert. "
                f"Check the file's size in Pennsieve and whether the data-source staged it completely."
            )
    log.info("%d .mef file(s) in %s", len(files), source)


def convert(source: Path, output_dir: Path, config) -> Path:
    """Convert the .mef files in `source` to one NWB file in `output_dir`.

    Staging files live under output_dir/.staging while the job runs and are
    removed whether it succeeds or fails: output_dir is the next stage's
    INPUT_DIR, and anything left there would be read as data.
    """
    from processor.converters.mef2.mef_streamer import stage_from_stream
    from processor.converters.mef2.multi_channel_reader import MultiChannelReader
    from processor.converters.mef2.nwb_writer import NWBWriter

    source = Path(source)
    output_dir = Path(output_dir)
    _check_mef_files(source)
    staging_dir = output_dir / ".staging"
    output_name = config.output_filename or f"{source.name}{OUTPUT_EXTENSION}"
    output_path = output_dir / output_name

    java_cmd = shlex.split(config.java_cmd) + [str(source)]
    if config.channels:
        # The jar reads MEF_CHANNELS itself and exits 1 if a name matches no file.
        os.environ["MEF_CHANNELS"] = ",".join(config.channels)
        log.info("Converting only channels: %s", ", ".join(config.channels))

    try:
        stage_from_stream(java_cmd, staging_dir)
        reader = MultiChannelReader.from_staged_dir(staging_dir)
        log.info("Loaded %d channels, %d samples @ %.2f Hz",
                 reader.num_channels, reader.num_samples, reader.sampling_rate)
        NWBWriter(reader, output_path).write()
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return output_path
