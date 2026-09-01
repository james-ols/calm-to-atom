
"""
DSCribe XML reader for CALM exports.

CALM exports XML that conforms to the DSCribe schema. Every export has this
shape:

    <?xml version="1.0" encoding="..." ?>
    <!DOCTYPE DScribeDatabase SYSTEM "some.dtd">
    <DScribeDatabase Name="Catalog">
        <DScribeRecord>
            <RefNo>...</RefNo>
            <Title>...</Title>
            ...
        </DScribeRecord>
        <DScribeRecord>...</DScribeRecord>
        ...
    </DScribeDatabase>

Every field element is (#PCDATA) — plain text, no children, no attributes.
Records are flat siblings; hierarchy is expressed by the <RefNo> string
(which is exactly the same convention the CSV reader already relies on).

Two real-world quirks the reader handles:

1. The DTD declares HTML-style named entities (&lsquo;, &pound;, &eacute;
   …) that map to Windows-1252 code points. Python's stdlib XML parser
   deliberately does NOT load external DTDs (that's a security posture,
   not a bug — it defuses XXE attacks). If those entities are present in
   the XML body, the parser raises "undefined entity". We pre-resolve them
   to their correct Unicode equivalents before parsing.

2. The XML declaration sometimes claims 'UTF-8' when the file is really
   Windows-1252. We sniff the declaration, try it, and fall back to
   cp1252/latin-1 if decoding fails, so real-world exports parse cleanly.

The reader returns the same (rows, metadata) contract as readers.csv_reader,
so core.convert_rows is source-agnostic.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# DTD-declared entity substitutions.
#
# These mirror the <!ENTITY ...> declarations shipped in dtds/calm.dtd, but
# we map them to their correct Unicode equivalents rather than the invalid
# Windows-1252 numeric code points the DTD itself uses (e.g. &#145; is not a
# legal Unicode code point). This makes the resulting CSV genuinely UTF-8
# clean.
# ---------------------------------------------------------------------------
DSCRIBE_ENTITIES: Dict[str, str] = {
    "lsquo":  "\u2018",  # ‘
    "rsquo":  "\u2019",  # ’
    "ldquo":  "\u201C",  # “
    "rdquo":  "\u201D",  # ”
    "ndash":  "\u2013",  # –
    "mdash":  "\u2014",  # —
    "trade":  "\u2122",  # ™
    "nbsp":   "\u00A0",  # non-breaking space
    "cent":   "\u00A2",  # ¢
    "pound":  "\u00A3",  # £
    "brkbar": "\u00A6",  # ¦
    "uml":    "\u00A8",  # ¨
    "copy":   "\u00A9",  # ©
    "not":    "\u00AC",  # ¬
    "deg":    "\u00B0",  # °
    "sup3":   "\u00B3",  # ³
    "middot": "\u00B7",  # ·
    "sup1":   "\u00B9",  # ¹
    "ordm":   "\u00BA",  # º
    "frac14": "\u00BC",  # ¼
    "frac12": "\u00BD",  # ½
    "frac34": "\u00BE",  # ¾
    "Acirc":  "\u00C2",  # Â
    "Atilde": "\u00C3",  # Ã
    "Aring":  "\u00C5",  # Å
    "AElig":  "\u00C6",  # Æ
    "agrave": "\u00E0",  # à
    "egrave": "\u00E8",  # è
    "eacute": "\u00E9",  # é
    "ucirc":  "\u00FB",  # û
    "uuml":   "\u00FC",  # ü
}

# Precompile a single alternation to substitute all DTD entities in one pass.
_ENTITY_RE = re.compile(
    r"&(" + "|".join(re.escape(name) for name in DSCRIBE_ENTITIES) + r");"
)

# Matches the XML declaration at the top of the file, e.g.
#   <?xml version="1.0" encoding="UTF-8" ?>
_XML_DECL_RE = re.compile(r"^\s*<\?xml[^?]*\?>", re.DOTALL)

# Matches the DOCTYPE line so we can strip it before handing the text to the
# stdlib parser. ElementTree will happily parse without a DOCTYPE, and this
# avoids any attempt to fetch an external DTD.
_DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.DOTALL)


def _decode_bytes(raw: bytes) -> str:
    """Decode a CALM XML byte stream, tolerating declared/actual encoding
    mismatches that occur in real exports.

    Order of attempts:
        1. The encoding declared in the <?xml ... encoding="..." ?> header.
        2. utf-8 (the modern default).
        3. cp1252 (the encoding CALM legacy tools actually produce).
        4. latin-1 (never fails; last-resort byte-preserving fallback).
    """
    head = raw[:200].decode("ascii", errors="ignore").lower()
    m = re.search(r'encoding\s*=\s*["\']([^"\']+)["\']', head)
    declared = (m.group(1) if m else "utf-8").lower()

    for enc in (declared, "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 'replace' is unreachable in practice because latin-1 never fails,
    # but keep it as a defence-in-depth safety net.
    return raw.decode("utf-8", errors="replace")


def _preprocess(text: str) -> str:
    """Resolve DTD-declared entities and strip the DOCTYPE line.

    We also normalise the XML declaration to advertise UTF-8, since the
    string handed to ET.fromstring is a Python str at that point and the
    original 'encoding=...' attribute is no longer meaningful.
    """
    # 1. Resolve DTD-declared entities to real Unicode. Built-in entities
    #    (&amp; &lt; &gt; &quot; &apos;) are left alone — the parser handles
    #    those natively.
    text = _ENTITY_RE.sub(lambda m: DSCRIBE_ENTITIES[m.group(1)], text)

    # 2. Rewrite the XML declaration so it doesn't mislead downstream
    #    tooling about the encoding of the in-memory string.
    text = _XML_DECL_RE.sub('<?xml version="1.0" encoding="UTF-8"?>', text, count=1)

    # 3. Drop the DOCTYPE so the stdlib parser doesn't have to think about it.
    text = _DOCTYPE_RE.sub("", text, count=1)

    return text


def _record_to_dict(record: ET.Element) -> Dict[str, str]:
    """Turn one <DScribeRecord> element into a flat dict keyed by tag name.

    - Empty elements are dropped (matches DEFAULT_MAPPING's assumption that
      absent fields are absent, not empty strings).
    - Repeated elements within a record are concatenated with '\\n\\n', the
      same convention core.convert_rows uses when multiple CALM fields map
      to the same AtoM field. This keeps downstream behaviour identical to
      the CSV path.
    """
    row: Dict[str, str] = {}
    for field in record:
        # Every DSCribe element is (#PCDATA) per the DTD, so .text carries
        # the entire value. There are no child elements to worry about.
        value = (field.text or "").strip()
        if not value:
            continue

        tag = field.tag
        if tag in row:
            row[tag] = f"{row[tag]}\n\n{value}"
        else:
            row[tag] = value
    return row


def _extract_archon_code(rows: List[Dict[str, str]]) -> Optional[str]:
    """Return the ISAD(G) 3.1.1 Archon code (e.g. 'GB 123') if the export
    carries one.

    CALM XML exports include <CountryCode> + <RepositoryCode> on the
    collection-level record. We find the first record that has both
    populated and combine them with a single space, matching the canonical
    form used by TNA's Archon Directory and ISAD(G) examples.
    """
    for row in rows:
        country = row.get("CountryCode", "").strip()
        repo = row.get("RepositoryCode", "").strip()
        if country and repo:
            return f"{country} {repo}"
    return None


def read_calm_xml(input_path: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Parse a CALM DSCribe XML export into the same (rows, metadata) shape
    as readers.csv_reader.read_calm_csv.

    :param input_path: Path to the CALM XML export.
    :returns: (rows, metadata). rows is a list of dicts keyed by CALM
              element name (e.g. 'RefNo', 'Title'). metadata carries
              export-level context:
                  archon_code   : 'GB 123' or None
                  database_name : root <DScribeDatabase Name="..."> attribute
                  record_count  : number of <DScribeRecord> elements parsed
    :raises FileNotFoundError: If the input file does not exist.
    :raises xml.etree.ElementTree.ParseError: If the XML is malformed.
    """
    logging.info(f"Reading CALM XML from {input_path}")

    raw = Path(input_path).read_bytes()
    text = _preprocess(_decode_bytes(raw))
    root = ET.fromstring(text)

    if root.tag != "DScribeDatabase":
        logging.warning(
            "Root element is <%s>, expected <DScribeDatabase>; "
            "will still collect any <DScribeRecord> descendants.",
            root.tag,
        )

    # root.iter walks the whole tree; in the flat DSCribe layout the direct
    # children ARE the records, but using .iter() also handles the (highly
    # unusual) case of records nested one level deeper.
    rows: List[Dict[str, str]] = [
        _record_to_dict(record) for record in root.iter("DScribeRecord")
    ]

    metadata: Dict[str, Any] = {
        "archon_code": _extract_archon_code(rows),
        "database_name": root.attrib.get("Name"),
        "record_count": len(rows),
    }

    logging.info(
        "Parsed %d records from XML (database=%r, archon_code=%r)",
        metadata["record_count"],
        metadata["database_name"],
        metadata["archon_code"],
    )
    return rows, metadata