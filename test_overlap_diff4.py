from ukrainian_mode import UKRAINIAN_WORD_REPLACEMENTS, _SORTED_KEYS

for k in ["время", "болото", "артиллерия", "измена"]:
    print(f"Key: {k}, Replacements: {UKRAINIAN_WORD_REPLACEMENTS[k]}")

print("Let's see why cascaded replacement happened.")
for k in ["время", "болото", "артиллерия", "измена"]:
    val = UKRAINIAN_WORD_REPLACEMENTS[k]
    if isinstance(val, list):
        val = val[0]

    # Simulate Original loop:
    print(f"Tracking Original for {k}: {val}")
    for key2 in _SORTED_KEYS:
        # Actually it goes through ALL keys and matches against the RESULT string.
        # So "время" -> "час" -> "година"
        pass
