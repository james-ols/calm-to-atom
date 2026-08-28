import csv
import logging
from typing import Dict, Union, Optional
import json
from pathlib import Path
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, **kwargs: x


# AtoM ISAAR(CPF) CSV templates for Authority records
AUTHORITY_VERSIONS = {
    "2.8": [
        "culture", "typeOfEntity", "authorizedFormOfName", "parallelFormsOfName", 
        "standardizedFormsOfName", "otherFormsOfName", "corporateBodyIdentifiers", 
        "datesOfExistence", "history", "places", "legalStatus", "functions", "mandates", 
        "internalStructures", "generalContext", "descriptionIdentifier", "institutionIdentifier", 
        "rules", "status", "levelOfDetail", "revisionHistory", "sources", "maintenanceNotes", 
        "actorOccupations", "actorOccupationNotes", "subjectAccessPoints", "placeAccessPoints", 
        "digitalObjectPath", "digitalObjectURI"
    ],
    "2.3": [
        "culture", "typeOfEntity", "authorizedFormOfName", "corporateBodyIdentifiers", 
        "datesOfExistence", "history", "places", "legalStatus", "functions", "mandates", 
        "internalStructures", "generalContext", "descriptionIdentifier", "institutionIdentifier", 
        "rules", "status", "levelOfDetail", "revisionHistory", "sources", "maintenanceNotes"
    ]
}

# Alias 2.6 and 2.4 to their nearest templates
AUTHORITY_VERSIONS["2.6"] = AUTHORITY_VERSIONS["2.8"]
AUTHORITY_VERSIONS["2.1"] = AUTHORITY_VERSIONS["2.3"]

# Typical CALM 'Persons' or 'Organizations' database fields
DEFAULT_AUTH_MAPPING = {
    "Name": "authorizedFormOfName",
    "PersonName": "authorizedFormOfName",
    "CorpName": "authorizedFormOfName",
    "Type": "typeOfEntity",           # E.g. Person, Corporate body, Family
    "Epithet": "actorOccupations", 
    "Dates": "datesOfExistence",
    "AdminHistory": "history",
    "BiogHistory": "history",
    "Description": "history",
    "Place": "places",
    "Function": "functions",
}

def clean_entity_type(calm_type: str) -> str:
    """Normalize CALM authority type to AtoM entity type."""
    if not calm_type:
        return "Person" # Default assumption
    val = calm_type.strip().lower()
    if "person" in val: return "Person"
    if "corp" in val or "org" in val: return "Corporate body"
    if "family" in val: return "Family"
    return "Person"

def convert_authorities(input_path: str, output_path: str, mapping: Union[Dict[str, str], str, None] = None, atom_version: str = "2.8", chunk_size: int = 0) -> None:
    """Convert CALM Persons/Organizations CSV export to AtoM ISAAR(CPF) format."""
    # Import locally to avoid circular dependency if needed, but it should be fine here
    from core import resolve_version
    
    if mapping is None:
        mapping = DEFAULT_AUTH_MAPPING
    elif isinstance(mapping, str):
        try:
            with open(mapping, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load custom mapping JSON: {e}")
            return

    # Fallback for version grouping
    effective_version = resolve_version(atom_version)
    target_version = "2.8" if effective_version >= 2.6 else "2.3"
    target_headers = AUTHORITY_VERSIONS[target_version]

    logging.info(f"Reading CALM Authority data from {input_path}")
    
    try:
        with open(input_path, mode='r', encoding='utf-8-sig') as infile:
            calm_rows = list(csv.DictReader(infile))
    except Exception as e:
        logging.error(f"Failed to read input CSV: {e}")
        return
        
    atom_rows = []
    
    for row in tqdm(calm_rows, desc="Converting Authorities"):
        atom_row = {col: "" for col in target_headers}
        
        for calm_field, atom_field in mapping.items():
            val = row.get(calm_field, "").strip()
            if not val or atom_field not in target_headers:
                continue
                
            if calm_field == "Type":
                val = clean_entity_type(val)
                
            if atom_row[atom_field]:
                atom_row[atom_field] += f"\n\n{val}"
            else:
                atom_row[atom_field] = val
                
        # Enforce required type if empty
        if not atom_row.get("typeOfEntity"):
            atom_row["typeOfEntity"] = "Person"
            
        atom_rows.append(atom_row)

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
            
            with open(chunk_path, mode='w', encoding='utf-8', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=target_headers)
                writer.writeheader()
                writer.writerows(chunk_rows)
    else:
        logging.info(f"Writing AtoM {atom_version} Authority data to {output_path}")
        with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=target_headers)
            writer.writeheader()
            writer.writerows(atom_rows)
        
    logging.info("Authority conversion complete!")
