"""Unit tests for readers.xml_reader.

The fixtures embed small, deliberately-crafted DSCribe XML snippets in the
tests themselves (via tmp_path). That keeps this file self-contained and
avoids depending on the private customer data under customers/shropshire/.

Each test targets one specific behaviour of the reader so a failure gives
a clear signal about what regressed.
"""

import textwrap
from pathlib import Path

import pytest

from readers.xml_reader import (
    DSCRIBE_ENTITIES,
    _extract_archon_code,
    read_calm_xml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, contents: str) -> str:
    """Write an XML fixture to tmp_path and return its str path."""
    path = tmp_path / name
    path.write_text(textwrap.dedent(contents), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Structural parsing
# ---------------------------------------------------------------------------

def test_basic_shropshire_shape(tmp_path):
    """A minimal Shropshire-flavoured XML parses into the expected rows and
    picks up the Archon code and database name."""
    path = _write(tmp_path, "cca.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE DScribeDatabase SYSTEM "cca.dtd">
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <AltRefNo>BCB</AltRefNo>
                <Title>Bishop's Castle Borough Collection</Title>
                <Level>Collection</Level>
                <Repository>Shropshire Archives</Repository>
                <CountryCode>GB</CountryCode>
                <RepositoryCode>166</RepositoryCode>
            </DScribeRecord>
            <DScribeRecord>
                <RefNo>XBCB/A</RefNo>
                <Title>Charters</Title>
                <Level>Section</Level>
                <Repository>Shropshire Archives</Repository>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, metadata = read_calm_xml(path)

    assert metadata == {
        "archon_code": "GB 166",
        "database_name": "Catalog",
        "record_count": 2,
    }
    assert rows[0]["RefNo"] == "XBCB"
    assert rows[0]["Title"] == "Bishop's Castle Borough Collection"
    assert rows[1]["RefNo"] == "XBCB/A"
    assert rows[1]["Level"] == "Section"


def test_empty_elements_are_dropped(tmp_path):
    """DSCribe exports include hundreds of empty <Field></Field> elements
    per record. These must not appear in the parsed dict, or downstream
    'if not value' checks would misbehave."""
    path = _write(tmp_path, "empties.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB/A/1</RefNo>
                <Title>Charter (Queen Elizabeth)</Title>
                <Description></Description>
                <AdminHistory></AdminHistory>
                <CustodialHistory>   </CustodialHistory>
                <ArchNote>
                </ArchNote>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, _ = read_calm_xml(path)

    assert rows[0]["RefNo"] == "XBCB/A/1"
    assert rows[0]["Title"] == "Charter (Queen Elizabeth)"
    # Empty, whitespace-only and newline-only elements must all be absent.
    assert "Description" not in rows[0]
    assert "AdminHistory" not in rows[0]
    assert "CustodialHistory" not in rows[0]
    assert "ArchNote" not in rows[0]


def test_whitespace_and_newlines_stripped(tmp_path):
    """CALM's <RCN> field often carries trailing whitespace and newlines
    (real-world quirk from the Shropshire exports). Values must be
    stripped."""
    path = _write(tmp_path, "rcn.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB/A/1</RefNo>
                <RCN>X\x20\x20\n\n</RCN>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, _ = read_calm_xml(path)

    assert rows[0]["RCN"] == "X"


def test_repeated_elements_concatenated(tmp_path):
    """DSCribe permits multiple occurrences of the same element within a
    single record (e.g. multiple <CreatorName>). The reader concatenates
    them with the same '\\n\\n' separator core.convert_rows uses for
    multi-mapped fields."""
    path = _write(tmp_path, "repeats.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <CreatorName>Bishop's Castle Corporation</CreatorName>
                <CreatorName>Bishop's Castle Town Council</CreatorName>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, _ = read_calm_xml(path)

    assert rows[0]["CreatorName"] == (
        "Bishop's Castle Corporation\n\nBishop's Castle Town Council"
    )


# ---------------------------------------------------------------------------
# Entity handling
# ---------------------------------------------------------------------------

def test_builtin_apos_entity_resolves(tmp_path):
    """&apos; is a built-in XML entity (not DTD-declared) and must resolve
    to a plain apostrophe without any preprocessing needed."""
    path = _write(tmp_path, "apos.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <Title>Bishop&apos;s Castle Borough Collection</Title>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, _ = read_calm_xml(path)

    assert rows[0]["Title"] == "Bishop's Castle Borough Collection"


def test_dtd_entity_pound_resolves(tmp_path):
    """DTD-declared entities like &pound; must resolve to correct Unicode
    (£, U+00A3), NOT to the Windows-1252 numeric code point the DTD itself
    uses (&#163;). The stdlib parser cannot resolve these without our
    preprocessing pass because we deliberately strip the external DTD."""
    path = _write(tmp_path, "pound.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <!DOCTYPE DScribeDatabase SYSTEM "cca.dtd">
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB/E/1</RefNo>
                <Title>Rent book &pound;5 per annum</Title>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    rows, _ = read_calm_xml(path)

    assert rows[0]["Title"] == "Rent book \u00A35 per annum"


def test_all_dtd_entities_have_valid_unicode():
    """Sanity check: every DSCRIBE_ENTITIES value must be a real Unicode
    string (not the invalid Windows-1252 numeric references the DTD uses)."""
    for name, value in DSCRIBE_ENTITIES.items():
        assert isinstance(value, str) and len(value) == 1, (
            f"Entity '{name}' should map to a single Unicode character, "
            f"got: {value!r}"
        )


# ---------------------------------------------------------------------------
# Archon code extraction
# ---------------------------------------------------------------------------

def test_archon_code_from_first_populated_record():
    """The Archon code is drawn from the first record that has BOTH
    <CountryCode> and <RepositoryCode> populated. Records missing one or
    the other are skipped."""
    rows = [
        {"RefNo": "XBCB/A/1"},                          # neither → skip
        {"CountryCode": "GB"},                          # missing repo → skip
        {"RepositoryCode": "166"},                      # missing country → skip
        {"CountryCode": "GB", "RepositoryCode": "166"}, # ← this one
        {"CountryCode": "GB", "RepositoryCode": "999"}, # earlier match wins
    ]

    assert _extract_archon_code(rows) == "GB 166"


def test_archon_code_absent_returns_none():
    rows = [
        {"RefNo": "XBCB"},
        {"RefNo": "XBCB/A", "Title": "Charters"},
    ]

    assert _extract_archon_code(rows) is None


def test_archon_code_missing_when_only_country_present(tmp_path):
    """End-to-end: if the XML has <CountryCode> but no <RepositoryCode>,
    the reader must return archon_code=None rather than a partial value."""
    path = _write(tmp_path, "partial.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <CountryCode>GB</CountryCode>
            </DScribeRecord>
        </DScribeDatabase>
    """)

    _, metadata = read_calm_xml(path)

    assert metadata["archon_code"] is None


# ---------------------------------------------------------------------------
# Contract compatibility with the CSV reader
# ---------------------------------------------------------------------------

def test_returns_same_metadata_keys_as_csv_reader(tmp_path):
    """core.convert_rows treats readers as interchangeable. Whatever keys
    the CSV reader puts in metadata, the XML reader must expose too."""
    from readers.csv_reader import read_calm_csv

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("RefNo,Title\nXBCB,Test\n", encoding="utf-8")
    _, csv_meta = read_calm_csv(str(csv_path))

    xml_path = _write(tmp_path, "sample.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
            <DScribeRecord>
                <RefNo>XBCB</RefNo>
                <Title>Test</Title>
            </DScribeRecord>
        </DScribeDatabase>
    """)
    _, xml_meta = read_calm_xml(xml_path)

    # XML populates more keys, but every key the CSV reader promises must
    # be present in the XML reader's output too.
    for key in csv_meta:
        assert key in xml_meta, (
            f"XML reader missing metadata key {key!r} that CSV reader provides"
        )


def test_empty_input_returns_empty_rows(tmp_path):
    """A well-formed <DScribeDatabase/> with no records must round-trip as
    an empty list — not raise. This mirrors the CSV reader's behaviour on
    a header-only file."""
    path = _write(tmp_path, "empty.xml", """\
        <?xml version="1.0" encoding="UTF-8" ?>
        <DScribeDatabase Name="Catalog">
        </DScribeDatabase>
    """)

    rows, metadata = read_calm_xml(path)

    assert rows == []
    assert metadata["record_count"] == 0
    assert metadata["archon_code"] is None
    assert metadata["database_name"] == "Catalog"