import csv
import logging
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x # Fallback if tqdm not installed

# AtoM ISAD(G) CSV templates vary significantly by version.
ATOM_VERSIONS = {
    "2.8": [
        "legacyId", "parentId", "qubitParentSlug", "accessionNumber", "identifier", "title",
        "levelOfDescription", "extentAndMedium", "repository", "archivalHistory", "acquisition",
        "scopeAndContent", "appraisal", "accruals", "arrangement", "accessConditions",
        "reproductionConditions", "language", "script", "languageNote", "physicalCharacteristics",
        "findingAids", "locationOfOriginals", "locationOfCopies", "relatedUnitsOfDescription",
        "publicationNote", "digitalObjectPath", "digitalObjectURI", "generalNote",
        "subjectAccessPoints", "placeAccessPoints", "nameAccessPoints", "genreAccessPoints",
        "descriptionIdentifier", "institutionIdentifier", "rules", "descriptionStatus",
        "levelOfDetail", "revisionHistory", "languageOfDescription", "scriptOfDescription",
        "sources", "archivistNote", "publicationStatus", "physicalObjectName",
        "physicalObjectLocation", "physicalObjectType", "alternativeIdentifiers",
        "alternativeIdentifierLabels", "eventDates", "eventTypes", "eventStartDates",
        "eventEndDates", "eventActors", "eventActorHistories", "culture"
    ],
    "2.6": [
        "legacyId", "parentId", "qubitParentSlug", "accessionNumber", "identifier", "title",
        "levelOfDescription", "extentAndMedium", "repository", "archivalHistory", "acquisition",
        "scopeAndContent", "appraisal", "accruals", "arrangement", "accessConditions",
        "reproductionConditions", "language", "script", "languageNote", "physicalCharacteristics",
        "findingAids", "locationOfOriginals", "locationOfCopies", "relatedUnitsOfDescription",
        "publicationNote", "digitalObjectPath", "digitalObjectURI", "generalNote",
        "subjectAccessPoints", "placeAccessPoints", "nameAccessPoints", "genreAccessPoints",
        "descriptionIdentifier", "institutionIdentifier", "rules", "descriptionStatus",
        "levelOfDetail", "revisionHistory", "languageOfDescription", "scriptOfDescription",
        "sources", "archivistNote", "publicationStatus", "physicalObjectName",
        "physicalObjectLocation", "physicalObjectType", "alternativeIdentifiers",
        "alternativeIdentifierLabels", "eventDates", "eventTypes", "eventStartDates",
        "eventEndDates", "eventActors", "eventActorHistories", "culture"
    ],
    "2.3": [
        "legacyId", "parentId", "qubitParentSlug", "identifier", "accessionNumber", "title",
        "levelOfDescription", "extentAndMedium", "repository", "archivalHistory", "acquisition",
        "scopeAndContent", "appraisal", "accruals", "arrangement", "accessConditions",
        "reproductionConditions", "language", "script", "languageNote", "physicalCharacteristics",
        "findingAids", "locationOfOriginals", "locationOfCopies", "relatedUnitsOfDescription",
        "publicationNote", "digitalObjectURI", "generalNote", "subjectAccessPoints", 
        "placeAccessPoints", "nameAccessPoints", "genreAccessPoints", "descriptionIdentifier", 
        "institutionIdentifier", "rules", "descriptionStatus", "levelOfDetail", "revisionHistory", 
        "languageOfDescription", "scriptOfDescription", "sources", "archivistNote", 
        "publicationStatus", "physicalObjectName", "physicalObjectLocation", "physicalObjectType", 
        "alternativeIdentifiers", "alternativeIdentifierLabels", "eventDates", "eventTypes", 
        "eventStartDates", "eventEndDates", "eventActors", "eventActorHistories", "culture"
    ],
    # 2.9 and 2.10 headers verified identical to 2.8 via artefactual/atom stable/2.10.x
    "2.10": [], # populated below
    "2.9": [],
    "heratio": [], # Heratio (by AHG) natively consumes 2.8 ISAD(G) schema
     
    "2.1": [
        "legacyId", "parentId", "accessionNumber", "qubitParentSlug", "identifier", "title",
        "creators", "creatorHistories", "creatorDates", "creatorDatesStart", "creatorDatesEnd",
        "creatorDateNotes", "levelOfDescription", "extentAndMedium", "repository", "archivalHistory",
        "acquisition", "scopeAndContent", "appraisal", "accruals", "arrangement", "accessConditions",
        "reproductionConditions", "language", "script", "languageNote", "physicalCharacteristics",
        "findingAids", "locationOfOriginals", "locationOfCopies", "relatedUnitsOfDescription",
        "publicationNote", "generalNote", "subjectAccessPoints", "placeAccessPoints", "nameAccessPoints",
        "descriptionIdentifier", "institutionIdentifier", "rules", "descriptionStatus", "levelOfDetail",
        "revisionHistory", "languageOfDescription", "scriptOfDescription", "sources", "archivistNote",
        "digitalObjectPath", "digitalObjectURI", "publicationStatus", "physicalObjectName",
        "physicalObjectLocation", "physicalObjectType", "culture"
    ]
}
ATOM_VERSIONS["2.10"] = ATOM_VERSIONS["2.8"]
ATOM_VERSIONS["2.9"] = ATOM_VERSIONS["2.8"]
ATOM_VERSIONS["heratio"] = ATOM_VERSIONS["2.8"]

DEFAULT_MAPPING = {
    "RefNo": "identifier",            # Will also be copied to legacyId
    "AltRefNo": "alternativeIdentifiers",
    "Title": "title",
    "Date": "eventDates",             # Handled specially for < 2.3 where it maps to 'creatorDates' or 'eventDates'
    "Description": "scopeAndContent",
    "Level": "levelOfDescription",
    "Extent": "extentAndMedium",
    "CreatorName": "eventActors",     # Handled specially for < 2.3 where it maps to 'creators'
    "AccessStatus": "accessConditions",
    "AccessConditions": "accessConditions",
    "ClosedUntil": "accessConditions", 
    "AdminHistory": "archivalHistory",
    "CustodialHistory": "archivalHistory",
    "Acquisition": "acquisition",
    "Arrangement": "arrangement",
    "Notes": "generalNote",
    "RelatedMaterial": "relatedUnitsOfDescription",
    "Language": "language",
    "PhysicalDescription": "physicalCharacteristics",
    "FindingAids": "findingAids",
    "PubInNotes": "publicationNote",
    "Rules": "rules",
    "Filename": "digitalObjectPath",    # Commonly used for linking digital objects
    "URL": "digitalObjectURI",          # Commonly used for remote digital objects
}

LEVEL_MAPPING = {
    "fonds": "fonds", "subfonds": "subfonds", "sub-fonds": "subfonds",
    "series": "series", "subseries": "subseries", "sub-series": "subseries",
    "file": "file", "item": "item", "piece": "item", "collection": "collection",
    "part": "part",
}

def clean_level(calm_level: str) -> str:
    if not calm_level:
        return "item"
    return LEVEL_MAPPING.get(calm_level.strip().lower(), "otherlevel")

def compute_parent_id(ref_no: str, all_legacy_ids: set) -> Optional[str]:
    """
    Heuristic to find the parent RefNo based on hierarchical reference codes.
    E.g. parent of 'ABCD/1/2/3' is 'ABCD/1/2'.
    Checks against the known set of all legacyIds to ensure the parent actually exists.
    """
    if not ref_no:
        return None
        
    parts = re.split(r'([/\-\s]+)', ref_no.strip())
    
    while len(parts) > 1:
        parts = parts[:-2]
        candidate = "".join(parts)
        if candidate in all_legacy_ids:
            return candidate
            
    for i in range(len(ref_no)-1, 0, -1):
        candidate = ref_no[:i].strip()
        if candidate in all_legacy_ids:
            return candidate
            
    return None

def resolve_version(atom_version: str) -> tuple:
    """Resolve the AtoM version string into a numeric tuple for comparison."""
    if atom_version == "heratio":
        return (2, 8)
    return tuple(int(p) for p in atom_version.split("."))

def extract_leaf_identifier(val: str) -> str:
    """Extract just the last segment of the reference number by splitting on the strict hierarchy delimiter '/'"""
    return val.split("/")[-1].strip()


# ---------------------------------------------------------------------------
# Archon (repository) code handling
#
# UK archives are registered in TNA's Archon Directory with codes like
# 'GB 166' (Shropshire Archives). ISAD(G) 3.1.1 wants the country and
# repository codes as a prefix on the reference code, i.e. 'GB 166 XBCB/A/1'
# instead of the bare 'XBCB/A/1'. When --prefix-archon is passed on the CLI,
# we prepend the code to every identifier and legacyId at write time so
# hierarchy resolution (which is calculated against the RAW RefNos) stays
# intact.
#
# The fallback code 'GB 000' is deliberately invalid (no archive is
# registered under 000) so it stands out as "please supply a real code"
# rather than silently producing plausible-looking data.
# ---------------------------------------------------------------------------
ARCHON_FALLBACK = "GB 000"


def archon_to_slug(code: str) -> str:
    """Turn a canonical Archon code into an AtoM repository slug.

    Examples:
        'GB 166'  -> 'gb-166'
        'GB  166' -> 'gb-166'   (tolerant of stray whitespace)
        'GB-166'  -> 'gb-166'   (tolerant of the TNA Discovery URL form)
        'GB 000'  -> 'gb-000'   (the fallback code)
        ''        -> ''
    """
    if not code:
        return ""
    # Split on any whitespace or '-' so both 'GB 166' and 'GB-166' normalise
    # to the same slug. Empty parts (from double separators) are dropped.
    parts = [p for p in re.split(r"[\s\-]+", code) if p]
    return "-".join(part.lower() for part in parts)


def _resolve_effective_archon(
    cli_archon_code: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> str:
    """Choose which Archon code to use, applying the fallback if needed.

    Precedence (most specific first):
        1. --archon-code on the CLI.
        2. archon_code carried in reader metadata (extracted from XML).
        3. ARCHON_FALLBACK ('GB 000') — well-formed but obviously invalid,
           so problems are visible in the AtoM import rather than silent.
    """
    if cli_archon_code:
        return cli_archon_code.strip()
    if metadata and metadata.get("archon_code"):
        return metadata["archon_code"]
    logging.warning(
        "No Archon code found in input or supplied via --archon-code; "
        "using fallback %r. Repository/identifier prefixing will still work "
        "but the placeholder must be replaced before AtoM import.",
        ARCHON_FALLBACK,
    )
    return ARCHON_FALLBACK


def _prefix_ref(ref: str, archon_code: str) -> str:
    """Prepend the Archon code to a reference, avoiding double-prefixing.

    'GB 166' + 'XBCB/A/1'          -> 'GB 166 XBCB/A/1'
    'GB 166' + 'GB 166 XBCB/A/1'   -> 'GB 166 XBCB/A/1'   (idempotent)
    """
    if not ref:
        return ref
    if ref.startswith(f"{archon_code} "):
        return ref
    return f"{archon_code} {ref}"


def audit_data(rows: List[Dict], target_headers: List[str]) -> bool:
    """Run strict validation on the processed rows."""
    logging.info("--- RUNNING PRE-FLIGHT AUDIT ---")
    errors = 0
    warnings = 0

    legacy_ids = {r.get("legacyId") for r in rows if r.get("legacyId")}

    for idx, row in enumerate(rows, start=2): # +2 for header and 1-index
        ref = row.get("legacyId", f"Row {idx}")

        # 1. Check for orphans
        parent_id = row.get("parentId")
        if parent_id and parent_id not in legacy_ids:
            logging.error(f"[{ref}] ORPHAN RECORD: parentId '{parent_id}' does not exist in the dataset.")
            errors += 1

        # 2. Check for required ISAD(G) fields (title or identifier)
        if not row.get("title") and not row.get("identifier"):
            logging.error(f"[{ref}] MISSING REQUIRED FIELD: AtoM requires either a 'title' or 'identifier'.")
            errors += 1

        # 3. Check Date validity (very basic warning)
        event_dates = row.get("eventDates", "")
        if event_dates and len(event_dates) > 50:
            logging.warning(f"[{ref}] UNUSUAL DATE: 'eventDates' is very long, consider cleaning: {event_dates[:30]}...")
            warnings += 1

    logging.info(f"--- AUDIT COMPLETE: {errors} Errors, {warnings} Warnings ---")
    if errors > 0:
        logging.error("Audit failed. Fix errors before importing to AtoM to prevent silently dropped records.")
        return False
    return True

def _resolve_mapping(mapping: Union[Dict[str, str], str, None]) -> Optional[Dict[str, str]]:
    """Turn the mapping argument (dict, JSON file path, or None) into a dict.

    Returns None on failure (JSON load error) so callers can bail out early
    matching the previous convert_csv behaviour.
    """
    if mapping is None:
        return DEFAULT_MAPPING
    if isinstance(mapping, str):
        logging.info(f"Loading custom mapping from {mapping}")
        try:
            with open(mapping, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load custom mapping JSON: {e}")
            return None
    return mapping


def convert_rows(
    calm_rows: List[Dict[str, str]],
    output_path: str,
    mapping: Union[Dict[str, str], str, None] = None,
    atom_version: str = "2.8",
    chunk_size: int = 0,
    audit: bool = False,
    identifier_mode: str = "full",
    metadata: Optional[Dict[str, Any]] = None,
    prefix_archon: bool = False,
    archon_code: Optional[str] = None,
    repository_slug: Optional[str] = None,
) -> None:
    """Convert already-parsed CALM rows to an AtoM-compatible CSV.

    This is the source-agnostic half of the pipeline. It expects `calm_rows`
    in the shape produced by any reader in the `readers` package: a list of
    dicts keyed by CALM field name.

    :param calm_rows: Parsed CALM records (from CSV, XML, …).
    :param output_path: Destination path for the AtoM CSV.
    :param mapping: Optional CALM → AtoM field mapping. May be a dict, a path
                    to a JSON file, or None to use DEFAULT_MAPPING.
    :param atom_version: Target AtoM CSV template version (see ATOM_VERSIONS).
    :param chunk_size: If > 0, split output into files of this many rows.
    :param audit: If True, run pre-flight validation before writing.
    :param identifier_mode: 'full' (default) or 'leaf'.
    :param metadata: Reader-supplied export metadata (e.g. archon_code from XML).
    :param prefix_archon: If True, prepend the Archon code to identifiers,
                          legacyIds and parentIds. Falls back to 'GB 000' if
                          no code can be resolved from CLI or metadata.
    :param archon_code: Explicit Archon code (e.g. 'GB 166'). Overrides
                        anything found in metadata.
    :param repository_slug: Explicit AtoM repository slug (e.g. 'gb-166' or
                            'shropshire-archives'). Overrides anything
                            derived from the Archon code.
    """
    resolved_mapping = _resolve_mapping(mapping)
    if resolved_mapping is None:
        # JSON load failed; the helper already logged the error.
        return
    mapping = resolved_mapping

    if atom_version not in ATOM_VERSIONS:
        raise ValueError(
            f"Unsupported AtoM version: {atom_version}. "
            f"Supported versions: {list(ATOM_VERSIONS.keys())}"
        )

    if not calm_rows:
        logging.warning("No rows found in input.")
        return

    effective_version = resolve_version(atom_version)
    target_headers = ATOM_VERSIONS[atom_version]

    all_legacy_ids = {row.get("RefNo").strip() for row in calm_rows if row.get("RefNo")}

    # Resolve the effective Archon code and repository slug up front so
    # we can log the decision once, not per-row. Only do the resolution
    # work if either feature is actually requested — CSV callers using
    # neither should see no change from the pre-Step-3 behaviour.
    effective_archon = None
    effective_slug = repository_slug
    if prefix_archon or archon_code or repository_slug:
        effective_archon = _resolve_effective_archon(archon_code, metadata)
        if not effective_slug:
            effective_slug = archon_to_slug(effective_archon)
        logging.info(
            "Repository handling: archon_code=%r, slug=%r, prefix_archon=%s",
            effective_archon,
            effective_slug,
            prefix_archon,
        )

    logging.info(f"Converting {len(calm_rows)} rows to AtoM {atom_version} format...")
    atom_rows = []

    for row in tqdm(calm_rows, desc="Converting Rows"):
        atom_row = {col: "" for col in target_headers}

        ref_no = row.get("RefNo", "").strip()
        if ref_no:
            atom_row["legacyId"] = ref_no
            parent_id = compute_parent_id(ref_no, all_legacy_ids)
            if parent_id:
                atom_row["parentId"] = parent_id

        # In AtoM >= 2.3, creators and dates are events. In AtoM 2.1 and below they are creators/creatorDates.
        if effective_version >= (2, 3):
            if row.get("Date") or row.get("CreatorName"):
                atom_row["eventTypes"] = "Creation"

        for calm_field, atom_field in mapping.items():
            val = row.get(calm_field, "").strip()
            if not val:
                continue

            # Adjust mappings for legacy AtoM versions (e.g. 2.1)
            if effective_version < (2, 3):
                if atom_field == "eventActors":
                    atom_field = "creators"
                elif atom_field == "eventDates":
                    atom_field = "creatorDates" # Simplification for legacy

            if atom_field not in target_headers:
                continue

            if calm_field == "Level":
                val = clean_level(val)

            # Identifier mode logic
            if atom_field == "identifier" and identifier_mode == "leaf":
                val = extract_leaf_identifier(val)

            if atom_row[atom_field]:
                atom_row[atom_field] += f"\n\n{val}"
            else:
                atom_row[atom_field] = val

        # Apply repository handling AFTER the mapping loop so parentage
        # (computed against raw RefNos above) links correctly BEFORE we
        # prefix identifiers.
        if effective_slug and "repository" in target_headers:
            atom_row["repository"] = effective_slug

        if prefix_archon and effective_archon:
            for field in ("legacyId", "identifier", "parentId"):
                if field in atom_row and atom_row[field]:
                    atom_row[field] = _prefix_ref(atom_row[field], effective_archon)

        atom_rows.append(atom_row)

    if audit:
        audit_data(atom_rows, target_headers)

    out_path = Path(output_path)

    if chunk_size > 0 and chunk_size < len(atom_rows):
        logging.info(f"Splitting output into chunks of {chunk_size} rows...")
        total_chunks = (len(atom_rows) + chunk_size - 1) // chunk_size

        for i in range(total_chunks):
            start_idx = i * chunk_size
            end_idx = start_idx + chunk_size
            chunk_rows = atom_rows[start_idx:end_idx]

            chunk_path = out_path.with_name(f"{out_path.stem}_part{i+1}{out_path.suffix}")
            logging.info(f"Writing chunk {i+1}/{total_chunks} to {chunk_path}")

            with open(chunk_path, mode="w", encoding="utf-8", newline="") as outfile:
                writer = csv.DictWriter(outfile, fieldnames=target_headers)
                writer.writeheader()
                writer.writerows(chunk_rows)
    else:
        logging.info(f"Writing {len(atom_rows)} rows to {output_path}")
        with open(output_path, mode="w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=target_headers)
            writer.writeheader()
            writer.writerows(atom_rows)

    logging.info(f"Conversion complete for AtoM {atom_version}!")


def convert_csv(
    input_path: str,
    output_path: str,
    mapping: Union[Dict[str, str], str, None] = None,
    atom_version: str = "2.8",
    chunk_size: int = 0,
    audit: bool = False,
    identifier_mode: str = "full",
    prefix_archon: bool = False,
    archon_code: Optional[str] = None,
    repository_slug: Optional[str] = None,
) -> None:
    """Read a CALM CSV export and convert it to an AtoM-compatible CSV.

    Thin wrapper: delegates parsing to readers.csv_reader and mapping to
    convert_rows. Existing signature preserved for backwards compatibility;
    the three Archon-related kwargs are optional additions.
    """
    from readers.csv_reader import read_calm_csv

    try:
        calm_rows, metadata = read_calm_csv(input_path)
    except Exception as e:
        logging.error(f"Failed to read input CSV: {e}")
        return

    convert_rows(
        calm_rows,
        output_path,
        mapping=mapping,
        atom_version=atom_version,
        chunk_size=chunk_size,
        audit=audit,
        identifier_mode=identifier_mode,
        metadata=metadata,
        prefix_archon=prefix_archon,
        archon_code=archon_code,
        repository_slug=repository_slug,
    )


def convert_xml(
    input_path: str,
    output_path: str,
    mapping: Union[Dict[str, str], str, None] = None,
    atom_version: str = "2.8",
    chunk_size: int = 0,
    audit: bool = False,
    identifier_mode: str = "full",
    prefix_archon: bool = False,
    archon_code: Optional[str] = None,
    repository_slug: Optional[str] = None,
) -> None:
    """Read a CALM DSCribe XML export and convert it to an AtoM-compatible CSV.

    Symmetric to convert_csv but reads via readers.xml_reader. The Archon code
    embedded in the XML (from <CountryCode> + <RepositoryCode>) is passed
    through in metadata and used by convert_rows unless overridden by
    --archon-code / --repository-slug on the CLI.
    """
    from readers.xml_reader import read_calm_xml

    try:
        calm_rows, metadata = read_calm_xml(input_path)
    except Exception as e:
        logging.error(f"Failed to read input XML: {e}")
        return

    convert_rows(
        calm_rows,
        output_path,
        mapping=mapping,
        atom_version=atom_version,
        chunk_size=chunk_size,
        audit=audit,
        identifier_mode=identifier_mode,
        metadata=metadata,
        prefix_archon=prefix_archon,
        archon_code=archon_code,
        repository_slug=repository_slug,
    )