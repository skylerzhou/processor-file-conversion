"""The gate: OUTPUT_DIR always ends up with data, or the run fails loudly.

These tests drive processor.main.run() / main() with a fake jar
(tests/fake_streamer.py) so no Java is needed.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from processor.config import Config
from processor.main import PrepError, main, run

FAKE = Path(__file__).with_name("fake_streamer.py")


def _config(tmp_path: Path, **overrides) -> Config:
    cfg = Config(
        input_dir=str(tmp_path / "input"),
        output_dir=str(tmp_path / "output"),
        java_cmd=f"{sys.executable} {FAKE}",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    Path(cfg.input_dir).mkdir(parents=True, exist_ok=True)
    return cfg


def _entries(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


############# PASS THROUGH ##################

def test_unknown_formats_pass_through_byte_identical(tmp_path):
    cfg = _config(tmp_path)
    (Path(cfg.input_dir) / "rec.edf").write_bytes(b"0       edf header and data" * 10)
    (Path(cfg.input_dir) / "notes.csv").write_text("a,b\n1,2\n")

    written = run(cfg)

    out = Path(cfg.output_dir)
    assert _entries(out) == ["notes.csv", "rec.edf"]
    assert sorted(p.name for p in written) == ["notes.csv", "rec.edf"]
    assert (out / "rec.edf").read_bytes() == (Path(cfg.input_dir) / "rec.edf").read_bytes()
    assert (out / "notes.csv").read_text() == "a,b\n1,2\n"


def test_pass_through_keeps_subfolders(tmp_path):
    cfg = _config(tmp_path)
    nested = Path(cfg.input_dir) / "bundle"
    nested.mkdir()
    (nested / "x.tsv").write_text("t\tv\n0\t1\n")

    run(cfg)

    assert (Path(cfg.output_dir) / "bundle" / "x.tsv").read_text() == "t\tv\n0\t1\n"


############# CONVERT ##################

def _mef_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("A1", "B2"):
        (folder / f"{name}.mef").write_bytes(b"\x00" * 2048)   # >= the 1024-byte MEF2 header


def test_mef_folder_becomes_exactly_one_nwb_named_after_it(tmp_path):
    cfg = _config(tmp_path)
    _mef_folder(Path(cfg.input_dir) / "sub01")

    written = run(cfg)

    out = Path(cfg.output_dir)
    assert _entries(out) == ["sub01.nwb"], "nothing but the NWB may be left for the next stage"
    assert [p.name for p in written] == ["sub01.nwb"]

    from pynwb import NWBHDF5IO
    with NWBHDF5IO(str(out / "sub01.nwb"), "r") as io:
        nwb = io.read()
        series = nwb.acquisition["ElectricalSeries"]
        assert series.data.shape == (50, 2)
        assert list(nwb.electrodes["channel_name"][:]) == ["A1", "B2"]


def test_mef_files_directly_in_input_dir_also_convert(tmp_path):
    cfg = _config(tmp_path)
    _mef_folder(Path(cfg.input_dir))

    run(cfg)

    assert _entries(Path(cfg.output_dir)) == ["input.nwb"]


def test_output_filename_override(tmp_path):
    cfg = _config(tmp_path, output_filename="recording.nwb")
    _mef_folder(Path(cfg.input_dir) / "sub01")

    run(cfg)

    assert _entries(Path(cfg.output_dir)) == ["recording.nwb"]


def test_channels_are_handed_to_the_jar(tmp_path, monkeypatch):
    note = tmp_path / "note.json"
    monkeypatch.setenv("FAKE_STREAMER_NOTE", str(note))
    monkeypatch.delenv("MEF_CHANNELS", raising=False)
    cfg = _config(tmp_path, channels=["A1", "EEG PT 01-Ref"])
    _mef_folder(Path(cfg.input_dir) / "sub01")

    run(cfg)

    seen = json.loads(note.read_text())
    assert seen["MEF_CHANNELS"] == "A1,EEG PT 01-Ref"
    assert seen["input_dir"].endswith("sub01")


############# FAILURES ##################

def test_empty_input_is_a_failure_not_a_no_op(tmp_path):
    cfg = _config(tmp_path)

    with pytest.raises(PrepError, match="No input file"):
        run(cfg)


def test_missing_input_dir_is_a_failure(tmp_path):
    cfg = _config(tmp_path)
    Path(cfg.input_dir).rmdir()

    with pytest.raises(PrepError, match="does not exist"):
        run(cfg)


def test_jar_failure_fails_the_run_and_cleans_staging(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_STREAMER_FRAMES", "0")
    monkeypatch.setenv("FAKE_STREAMER_EXIT", "1")
    cfg = _config(tmp_path)
    _mef_folder(Path(cfg.input_dir) / "sub01")

    with pytest.raises(RuntimeError, match="exit code 1"):
        run(cfg)

    assert _entries(Path(cfg.output_dir)) == [], "a failed conversion leaves nothing behind"


############# main() EXIT CODES ##################

def _env_for(monkeypatch, cfg: Config) -> None:
    monkeypatch.setenv("INPUT_DIR", cfg.input_dir)
    monkeypatch.setenv("OUTPUT_DIR", cfg.output_dir)
    monkeypatch.setenv("JAVA_CMD", cfg.java_cmd)
    monkeypatch.delenv("CHANNELS", raising=False)
    monkeypatch.delenv("OUTPUT_FILENAME", raising=False)


def test_main_returns_0_on_pass_through(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    (Path(cfg.input_dir) / "data.csv").write_text("x\n1\n")
    _env_for(monkeypatch, cfg)

    assert main() == 0
    assert _entries(Path(cfg.output_dir)) == ["data.csv"]


def test_main_returns_1_when_nothing_was_staged(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    _env_for(monkeypatch, cfg)

    assert main() == 1


def test_main_returns_1_when_the_jar_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_STREAMER_FRAMES", "0")
    monkeypatch.setenv("FAKE_STREAMER_EXIT", "1")
    cfg = _config(tmp_path)
    _mef_folder(Path(cfg.input_dir) / "sub01")
    _env_for(monkeypatch, cfg)

    assert main() == 1
    assert _entries(Path(cfg.output_dir)) == []


############# TRUNCATED MEF ##################

def test_truncated_mef_fails_with_a_reason_naming_the_file(tmp_path):
    """An empty or short .mef must not reach the jar (it dies with a bare EOFException)."""
    cfg = _config(tmp_path)
    folder = Path(cfg.input_dir) / "sub01"
    folder.mkdir()
    (folder / "LA01.mef").write_bytes(b"\x00" * 12)

    with pytest.raises(RuntimeError, match=r"LA01\.mef is 12 bytes"):
        run(cfg)

    assert _entries(Path(cfg.output_dir)) == []
