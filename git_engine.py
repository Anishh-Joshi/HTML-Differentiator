import subprocess
import tempfile
import unicodedata

def normalize_line(line: str) -> str:
    """Normalize for comparison: strip spaces + normalize unicode."""
    return unicodedata.normalize("NFKC", line.strip())

def generate_diff(old_text: str, new_text: str) -> str:
    """Generate a diff between two plain text strings using git diff.
       Returns only meaningful added (+) and removed (-) lines,
       skipping no-op replacements."""
    
    with tempfile.NamedTemporaryFile("w+", delete=False) as f1, \
         tempfile.NamedTemporaryFile("w+", delete=False) as f2:
        f1.write(old_text)
        f2.write(new_text)
        f1.flush()
        f2.flush()

        result = subprocess.run(
            ["git", "diff", "--no-index", f1.name, f2.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    # Raw changes (excluding headers)
    raw_changes = []
    for line in result.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            raw_changes.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            raw_changes.append(line)

    # Filter out redundant -/+ pairs
    filtered = []
    i = 0
    while i < len(raw_changes):
        if raw_changes[i].startswith("-") and i+1 < len(raw_changes) and raw_changes[i+1].startswith("+"):
            old_line = normalize_line(raw_changes[i][1:])
            new_line = normalize_line(raw_changes[i+1][1:])
            if old_line == new_line:
                # skip both
                i += 2
                continue
        filtered.append(raw_changes[i])
        i += 1

    return "\n".join(filtered)
