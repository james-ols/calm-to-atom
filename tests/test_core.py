import pytest
from core import compute_parent_id, clean_level, ATOM_VERSIONS, extract_leaf_identifier, resolve_version

def test_clean_level():
    # Should normalize known terms
    assert clean_level("Piece") == "item"
    assert clean_level("sub-series") == "subseries"
    assert clean_level("Fonds") == "fonds"
    
    # Should fallback to otherlevel or item
    assert clean_level("") == "item"
    assert clean_level("BespokeLevel") == "otherlevel"

def test_compute_parent_id():
    legacy_ids = {"GB 123 ABC", "GB 123 ABC/1", "GB 123 ABC/1/2"}
    
    # Standard slash delimiting
    assert compute_parent_id("GB 123 ABC/1/2/3", legacy_ids) == "GB 123 ABC/1/2"
    assert compute_parent_id("GB 123 ABC/1/2", legacy_ids) == "GB 123 ABC/1"
    
    # Unknown parent returns None
    assert compute_parent_id("GB 123 XYZ/1/2", legacy_ids) is None

def test_atom_versions_exist():
    assert "2.10" in ATOM_VERSIONS
    assert "2.9" in ATOM_VERSIONS
    assert "2.8" in ATOM_VERSIONS
    assert "heratio" in ATOM_VERSIONS
    assert "2.1" in ATOM_VERSIONS
    
    # 2.8, 2.9, 2.10 should have exactly 56 headers for ISAD(G)
    assert len(ATOM_VERSIONS["2.10"]) == 56
    assert len(ATOM_VERSIONS["2.9"]) == 56
    assert len(ATOM_VERSIONS["2.8"]) == 56
    # 2.1 should have 53 headers
    assert len(ATOM_VERSIONS["2.1"]) == 53

def test_identifier_leaf_mode():
    # Top-level fonds (no delimiter) must stay whole
    assert extract_leaf_identifier("GB 123 ABC") == "GB 123 ABC"
    # Hyphenated segment must not be shredded
    assert extract_leaf_identifier("GB 123 ABC/PP-1") == "PP-1"
    # Deeper level extracts just the final segment
    assert extract_leaf_identifier("GB 123 ABC/PP-1/2") == "2"

def test_version_resolution():
    # heratio aliases to the 2.8 template family
    assert resolve_version("heratio") == (2, 8)
    # 2.10 must sort ABOVE 2.3 (regression guard for the float("2.10")==2.1 trap)
    assert resolve_version("2.10") == (2, 10)
    assert resolve_version("2.10") >= (2, 3)
    assert resolve_version("2.3") == (2, 3)

def test_2_10_event_mapping(tmp_path):
    from core import convert_csv
    import csv
    
    # Create dummy calm CSV
    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Date", "CreatorName"])
        writer.writeheader()
        writer.writerow({"RefNo": "ABC/1", "Date": "1990", "CreatorName": "John Doe"})
        
    output_csv = tmp_path / "atom.csv"
    
    # Convert using 2.10
    convert_csv(str(input_csv), str(output_csv), atom_version="2.10")
    
    # Assert
    with open(output_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        
        assert row["eventDates"] == "1990"
        assert row["eventActors"] == "John Doe"
        assert row["eventTypes"] == "Creation"
