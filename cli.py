import argparse
import sys
import logging
from core import convert_csv, convert_xml, ATOM_VERSIONS
from authorities import convert_authorities

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def _sniff_format(input_path: str) -> str:
    """Auto-detect input format from the file extension.

    Falls back to 'csv' for anything that isn't obviously XML, matching
    the tool's original behaviour of assuming CSV.
    """
    lower = input_path.lower()
    if lower.endswith((".xml", ".dscribe")):
        return "xml"
    return "csv"


def main():
    parser = argparse.ArgumentParser(
        description="Convert CALM catalogue exports (CSV or DSCribe XML) to AtoM compatible CSVs."
    )
    parser.add_argument(
        "input",
        help="Path to the input CALM export (CSV or XML)"
    )
    parser.add_argument(
        "output",
        help="Path to save the AtoM compatible CSV file"
    )
    parser.add_argument(
        "-t", "--type",
        choices=["isad", "isaar"],
        default="isad",
        help="Template type to generate: 'isad' for Descriptions, 'isaar' for Authority records (default: isad)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["auto", "csv", "xml"],
        default="auto",
        help="Input format. 'auto' (default) picks by file extension: .xml/.dscribe -> XML, everything else -> CSV."
    )
    parser.add_argument(
        "--atom-version",
        choices=list(ATOM_VERSIONS.keys()),
        default="2.10",
        help="Target AtoM version for the CSV template (default: 2.10)"
    )
    parser.add_argument(
        "-m", "--mapping",
        help="Path to a custom JSON mapping file (e.g. mapping.json)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="Split output into chunks of N rows to prevent AtoM import crashes (default: 0, no chunking)"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run strict validation on the data (checks for orphans, missing titles, etc.) before converting"
    )
    parser.add_argument(
        "--identifier-mode",
        choices=["full", "leaf"],
        default="full",
        help="How to map the identifier (RefNo). 'full' uses the entire string. 'leaf' extracts just the final segment."
    )
    parser.add_argument(
        "--prefix-archon",
        action="store_true",
        help=(
            "Prepend the ISAD(G) 3.1.1 Archon code (e.g. 'GB 166') to "
            "legacyId, identifier and parentId in the output. Uses the code "
            "from --archon-code, or from the XML if present, or the "
            "placeholder 'GB 000' if neither is available."
        )
    )
    parser.add_argument(
        "--archon-code",
        help=(
            "Explicit Archon code for the repository (e.g. 'GB 166'). "
            "Overrides any code auto-discovered in the input XML. Handy for "
            "CSV inputs, which do not carry the code natively."
        )
    )
    parser.add_argument(
        "--repository-slug",
        help=(
            "AtoM repository slug (e.g. 'gb-166' or 'shropshire-archives'). "
            "Overrides the slug otherwise derived from the Archon code."
        )
    )

    parser.add_argument(
        "--culture",
        default="en",
        help=(
            "ISO 639-1 code for the LANGUAGE OF DESCRIPTION (not of the "
            "material itself). Written to every output row's 'culture' "
            "column. AtoM requires this on every information object row; "
            "leaving it blank causes SQL errors and translation-row "
            "misclassification at import. Default: 'en'."
        )
    )

    parser.add_argument(
        "--dedupe-legacy-ids",
        choices=["first-wins"],
        default=None,
        help="Drop CALM records with duplicate RefNos. 'first-wins' keeps the first, drops the rest."
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    resolved_format = args.format if args.format != "auto" else _sniff_format(args.input)
    logging.info("Using input format: %s", resolved_format)

    try:
        if args.type == "isad":
            if resolved_format == "xml":
                convert_xml(
                    args.input,
                    args.output,
                    mapping=args.mapping,
                    atom_version=args.atom_version,
                    chunk_size=args.chunk_size,
                    audit=args.audit,
                    identifier_mode=args.identifier_mode,
                    prefix_archon=args.prefix_archon,
                    archon_code=args.archon_code,
                    repository_slug=args.repository_slug,
                    culture=args.culture,
                    dedupe_legacy_ids=args.dedupe_legacy_ids,
                )
            else:
                convert_csv(
                    args.input,
                    args.output,
                    mapping=args.mapping,
                    atom_version=args.atom_version,
                    chunk_size=args.chunk_size,
                    audit=args.audit,
                    identifier_mode=args.identifier_mode,
                    prefix_archon=args.prefix_archon,
                    archon_code=args.archon_code,
                    repository_slug=args.repository_slug,
                    culture=args.culture,
                    dedupe_legacy_ids=args.dedupe_legacy_ids,
                )
        elif args.type == "isaar":
            # ISAAR (authority) path — XML support to be added in Step 4.
            if resolved_format == "xml":
                logging.error(
                    "ISAAR (--type isaar) conversion from XML is not yet supported. "
                    "For now, please convert your CALM Persons export to CSV first."
                )
                sys.exit(1)
            convert_authorities(
                args.input,
                args.output,
                mapping=args.mapping,
                atom_version=args.atom_version,
                chunk_size=args.chunk_size
            )
    except FileNotFoundError:
        logging.error("Input file not found: %s", args.input)
        sys.exit(1)
    except ValueError as e:
        logging.error(str(e))
        sys.exit(1)
    except Exception as e:
        logging.error("An error occurred during conversion: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()