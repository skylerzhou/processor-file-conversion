"""The registry: every converter has the same shape, and detect() is unambiguous."""
from pathlib import Path

from processor.converters import CONVERTERS, find_converter, known_names
from processor.converters import mef2_to_nwb
from processor.schema import build


def test_every_converter_has_the_contract():
    for c in CONVERTERS:
        assert isinstance(c.NAME, str) and c.NAME
        assert c.OUTPUT_EXTENSION.startswith(".")
        assert callable(c.detect)
        assert callable(c.convert)


def test_names_are_unique():
    names = known_names()
    assert len(names) == len(set(names))
    assert "mef2_to_nwb" in names


def test_detect_ignores_non_mef_input(tmp_path):
    (tmp_path / "rec.edf").write_bytes(b"0       ")
    (tmp_path / "table.csv").write_text("a\n")
    assert mef2_to_nwb.detect(tmp_path) is None
    assert find_converter(tmp_path) == (None, None)


def test_detect_finds_mef_files_in_input_dir_or_one_level_down(tmp_path):
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "ch.MEF").write_bytes(b"\x00")          # extension match is case-insensitive
    assert mef2_to_nwb.detect(flat) == flat

    nested = tmp_path / "nested"
    (nested / "sub01").mkdir(parents=True)
    (nested / "sub01" / "ch.mef").write_bytes(b"\x00")
    assert mef2_to_nwb.detect(nested) == nested / "sub01"

    converter, source = find_converter(nested)
    assert converter is mef2_to_nwb and source == nested / "sub01"


def test_at_most_one_converter_claims_a_fixture(tmp_path):
    (tmp_path / "ch.mef").write_bytes(b"\x00")
    claims = [c.NAME for c in CONVERTERS if c.detect(tmp_path) is not None]
    assert claims == ["mef2_to_nwb"]


def test_schema_lists_the_registry():
    schema = build()
    assert [c["name"] for c in schema["converters"]] == known_names()
    assert schema["converters"][0]["input_extensions"] == [".mef"]
    assert schema["converters"][0]["execution_target"] == "standard"
    assert schema["pass_through_execution_target"] == "lambda"


def test_checked_in_schema_is_current():
    checked_in = Path(__file__).resolve().parents[1] / "schema" / "converters.json"
    import json
    assert json.loads(checked_in.read_text()) == build(), "run `make schemas`"
