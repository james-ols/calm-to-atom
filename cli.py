import argparse
import sys
import logging
from core import convert_csv, ATOM_VERSIONS
from authorities import convert_authorities

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def main():
    parser = argparse.ArgumentParser(
        description="Convert CALM catalogue exports (CSV) to AtoM compatible CSVs."
    )
    parser.add_argument(
        "input",
        help="Path to the input CALM CSV file"
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
        "--atom-version",
        choices=list(ATOM_VERSIONS.keys()),
        default="2.8",
        help="Target AtoM version for the CSV template (default: 2.8)"
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
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        if args.type == "isad":
            convert_csv(
                args.input, 
                args.output, 
                mapping=args.mapping, 
                atom_version=args.atom_version,
                chunk_size=args.chunk_size,
                audit=args.audit,
                identifier_mode=args.identifier_mode
            )
        elif args.type == "isaar":
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
