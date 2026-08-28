import csv
from core import ATOM_VERSIONS
from authorities import AUTHORITY_VERSIONS

def get_headers(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        return next(reader)

isad_2_10 = get_headers('isad_2.10.csv')
isad_2_9 = get_headers('isad_2.9.csv')
isaar_2_10 = get_headers('isaar_2.10.csv')
isaar_2_9 = get_headers('isaar_2.9.csv')

print("=== ISAD 2.8 ===")
print("Count:", len(ATOM_VERSIONS["2.8"]))

print("=== ISAD 2.9 ===")
print("Count:", len(isad_2_9))
diff_2_8_vs_2_9 = set(isad_2_9) ^ set(ATOM_VERSIONS["2.8"])
print("Differences 2.8 vs 2.9:", diff_2_8_vs_2_9)
if not diff_2_8_vs_2_9 and isad_2_9 != ATOM_VERSIONS["2.8"]:
    print("Order changed!")

print("=== ISAD 2.10 ===")
print("Count:", len(isad_2_10))
diff_2_8_vs_2_10 = set(isad_2_10) ^ set(ATOM_VERSIONS["2.8"])
print("Differences 2.8 vs 2.10:", diff_2_8_vs_2_10)

print("=== ISAAR 2.8 ===")
print("Count:", len(AUTHORITY_VERSIONS["2.8"]))

print("=== ISAAR 2.9 ===")
print("Count:", len(isaar_2_9))
diff_auth_2_8_vs_2_9 = set(isaar_2_9) ^ set(AUTHORITY_VERSIONS["2.8"])
print("Differences Auth 2.8 vs 2.9:", diff_auth_2_8_vs_2_9)

print("=== ISAAR 2.10 ===")
print("Count:", len(isaar_2_10))
diff_auth_2_8_vs_2_10 = set(isaar_2_10) ^ set(AUTHORITY_VERSIONS["2.8"])
print("Differences Auth 2.8 vs 2.10:", diff_auth_2_8_vs_2_10)

print("\nISAD 2.10 Headers:")
print(repr(isad_2_10))
print("\nISAAR 2.10 Headers:")
print(repr(isaar_2_10))

