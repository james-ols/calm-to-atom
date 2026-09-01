import pytest
from core import (
    compute_parent_id,
    clean_level,
    ATOM_VERSIONS,
    extract_leaf_identifier,
    resolve_version,
    archon_to_slug,
    ARCHON_FALLBACK,
)

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


# ---------------------------------------------------------------------------
# Archon code handling (Step 3)
# ---------------------------------------------------------------------------

def test_archon_to_slug_variants():
    """archon_to_slug must produce a stable AtoM-friendly slug regardless of
    how the caller punctuates the source code."""
    assert archon_to_slug("GB 166") == "gb-166"
    assert archon_to_slug("GB  166") == "gb-166"       # tolerate double space
    assert archon_to_slug("GB-166") == "gb-166"        # Discovery URL form
    assert archon_to_slug("GB 000") == "gb-000"        # fallback code
    assert archon_to_slug("") == ""


def test_archon_fallback_constant():
    """The fallback must be 'GB 000' — a deliberately-invalid placeholder
    that stands out in AtoM if it ever reaches production."""
    assert ARCHON_FALLBACK == "GB 000"
    assert archon_to_slug(ARCHON_FALLBACK) == "gb-000"


def test_prefix_archon_prepends_and_preserves_hierarchy(tmp_path):
    """The critical Step 3 invariant: --prefix-archon must prepend the code
    to identifiers AND keep parentage linked correctly. Parentage is
    resolved against the raw RefNos, then prefixed at write time — so a
    child's parentId must point at its (also-prefixed) parent's legacyId.
    """
    from core import convert_csv
    import csv

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title", "Level"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB",     "Title": "Fonds",   "Level": "Collection"})
        writer.writerow({"RefNo": "XBCB/A",   "Title": "Series",  "Level": "Section"})
        writer.writerow({"RefNo": "XBCB/A/1", "Title": "Item",    "Level": "Item"})

    output_csv = tmp_path / "atom.csv"
    convert_csv(
        str(input_csv),
        str(output_csv),
        atom_version="2.10",
        prefix_archon=True,
        archon_code="GB 166",
    )

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Identifiers prefixed.
    assert rows[0]["legacyId"] == "GB 166 XBCB"
    assert rows[1]["legacyId"] == "GB 166 XBCB/A"
    assert rows[2]["legacyId"] == "GB 166 XBCB/A/1"

    # And crucially — parentage links between the prefixed legacyIds.
    assert rows[0]["parentId"] == ""
    assert rows[1]["parentId"] == "GB 166 XBCB"
    assert rows[2]["parentId"] == "GB 166 XBCB/A"

    # Repository slug derived from the Archon code.
    assert rows[0]["repository"] == "gb-166"


def test_prefix_archon_without_code_uses_fallback(tmp_path, caplog):
    """When --prefix-archon is on but no code can be resolved, the
    fallback 'GB 000' must be applied and a warning logged."""
    from core import convert_csv
    import csv
    import logging

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB", "Title": "Fonds"})

    output_csv = tmp_path / "atom.csv"

    with caplog.at_level(logging.WARNING):
        convert_csv(
            str(input_csv),
            str(output_csv),
            atom_version="2.10",
            prefix_archon=True,
            # deliberately no archon_code
        )

    with open(output_csv, "r", encoding="utf-8") as f:
        row = next(csv.DictReader(f))

    assert row["legacyId"] == "GB 000 XBCB"
    assert row["repository"] == "gb-000"
    assert any("GB 000" in rec.message for rec in caplog.records), (
        "Expected a warning mentioning the fallback code 'GB 000'"
    )


def test_repository_slug_override_wins(tmp_path):
    """--repository-slug must override any slug derived from the Archon code."""
    from core import convert_csv
    import csv

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB", "Title": "Fonds"})

    output_csv = tmp_path / "atom.csv"
    convert_csv(
        str(input_csv),
        str(output_csv),
        atom_version="2.10",
        archon_code="GB 123",
        repository_slug="some-archive",  # explicit override
    )

    with open(output_csv, "r", encoding="utf-8") as f:
        row = next(csv.DictReader(f))

    # Slug must be the explicit override, NOT the derived 'gb-166'.
    assert row["repository"] == "some-archive"


def test_no_repository_features_no_behaviour_change(tmp_path):
    """The Step 3 code paths must not touch behaviour when none of the
    three flags are used. This is the safety net for existing CSV callers."""
    from core import convert_csv
    import csv

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB",   "Title": "Fonds"})
        writer.writerow({"RefNo": "XBCB/A", "Title": "Series"})

    output_csv = tmp_path / "atom.csv"
    convert_csv(str(input_csv), str(output_csv), atom_version="2.10")

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # No prefixing.
    assert rows[0]["legacyId"] == "XBCB"
    assert rows[1]["legacyId"] == "XBCB/A"
    assert rows[1]["parentId"] == "XBCB"
    # Repository stays empty (no mapping, no CLI override).
    assert rows[0]["repository"] == ""


def test_xml_archon_from_metadata_is_used(tmp_path):
    """End-to-end: converting XML with --prefix-archon (but no --archon-code)
    should pick up the code embedded in <CountryCode>+<RepositoryCode>."""
    from core import convert_xml
    import csv
    import textwrap

    input_xml = tmp_path / "cca.xml"
    input_xml.write_text(textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <Title>Fonds</Title>
                <Level>Collection</Level>
                <CountryCode>GB</CountryCode>
                <RepositoryCode>166</RepositoryCode>
            </DScribeRecord>
            <DScribeRecord>
                <RefNo>XBCB/A</RefNo>
                <Title>Series</Title>
                <Level>Section</Level>
            </DScribeRecord>
        </DScribeDatabase>
    """), encoding="utf-8")

    output_csv = tmp_path / "atom.csv"
    convert_xml(
        str(input_xml),
        str(output_csv),
        atom_version="2.10",
        prefix_archon=True,
        # No --archon-code: reader must supply it from metadata.
    )

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["legacyId"] == "GB 166 XBCB"
    assert rows[1]["legacyId"] == "GB 166 XBCB/A"
    assert rows[1]["parentId"] == "GB 166 XBCB"
    assert rows[0]["repository"] == "gb-166"

    # ---------------------------------------------------------------------------
# Culture handling (AtoM information_object_i18n NOT NULL requirement)
# ---------------------------------------------------------------------------

def test_culture_defaults_to_en_on_every_row(tmp_path):
    """Every output row must have a 'culture' value set. AtoM's
    information_object_i18n table requires it (NOT NULL), and leaving
    it blank both fails the SQL insert and confuses AtoM's
    translation-row detection heuristic."""
    from core import convert_csv
    import csv

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB",   "Title": "Fonds"})
        writer.writerow({"RefNo": "XBCB/A", "Title": "Series"})

    output_csv = tmp_path / "atom.csv"
    convert_csv(str(input_csv), str(output_csv), atom_version="2.10")

    with open(output_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        assert row["culture"] == "en", (
            f"row {row['legacyId']!r} has empty/wrong culture: "
            f"{row['culture']!r}"
        )


def test_culture_override_via_argument(tmp_path):
    """The --culture flag must set the value on every output row."""
    from core import convert_csv
    import csv

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB", "Title": "Fonds"})

    output_csv = tmp_path / "atom.csv"
    convert_csv(str(input_csv), str(output_csv),
                atom_version="2.10", culture="cy")

    with open(output_csv, "r", encoding="utf-8") as f:
        row = next(csv.DictReader(f))

    assert row["culture"] == "cy"


# ---------------------------------------------------------------------------
# Duplicate-legacyId detection (real-world data quality issues)
# ---------------------------------------------------------------------------

def test_audit_reports_duplicate_legacy_ids(tmp_path, caplog):
    """When the input CALM data contains repeated RefNos, audit_data must
    log an ERROR that names each offending legacyId with its occurrence
    count. Without this, AtoM's csv:import silently misclassifies the
    second occurrence as a translation row and crashes on a duplicate-
    PK collision in information_object_i18n — an obtuse failure mode we
    hit on with a customer import."""
    from core import convert_csv
    import csv
    import logging

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB",      "Title": "Fonds"})
        writer.writerow({"RefNo": "XBCB/A",    "Title": "Series"})
        writer.writerow({"RefNo": "XBCB/A/1",  "Title": "First"})
        writer.writerow({"RefNo": "XBCB/A/1",  "Title": "Duplicate of first"})
        writer.writerow({"RefNo": "XBCB/A/2",  "Title": "Second"})
        writer.writerow({"RefNo": "XBCB/A/2",  "Title": "Duplicate of second"})

    output_csv = tmp_path / "atom.csv"

    with caplog.at_level(logging.ERROR):
        convert_csv(
            str(input_csv), str(output_csv),
            atom_version="2.10", audit=True,
        )

    error_messages = [rec.message for rec in caplog.records
                      if rec.levelno == logging.ERROR]

    # Summary line names the count of distinct duplicates:
    assert any("2 distinct value(s) appear more than once" in m
               for m in error_messages), (
        f"Expected summary of duplicate-legacyId count in errors, got: "
        f"{error_messages}"
    )
    # And both offending legacyIds are individually named:
    joined = "\n".join(error_messages)
    assert "XBCB/A/1" in joined
    assert "XBCB/A/2" in joined


def test_audit_ignores_non_duplicate_legacy_ids(tmp_path, caplog):
    """The duplicate check must not fire on a well-formed CSV — no
    'DUPLICATE legacyId' error should appear when every legacyId is
    unique. Regression guard for false positives."""
    from core import convert_csv
    import csv
    import logging

    input_csv = tmp_path / "calm.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["RefNo", "Title"])
        writer.writeheader()
        writer.writerow({"RefNo": "XBCB",     "Title": "Fonds"})
        writer.writerow({"RefNo": "XBCB/A",   "Title": "Series"})
        writer.writerow({"RefNo": "XBCB/A/1", "Title": "Item"})

    output_csv = tmp_path / "atom.csv"

    with caplog.at_level(logging.ERROR):
        convert_csv(
            str(input_csv), str(output_csv),
            atom_version="2.10", audit=True,
        )

    for rec in caplog.records:
        assert "DUPLICATE legacyId" not in rec.message, (
            f"False positive: audit flagged duplicates in clean CSV: "
            f"{rec.message}"
        )