import sqlite3
from pathlib import Path

from app.config import settings


NUMBER = "553950678"

print("\n=== CHECK SQLITE INDEX ===")

connection = sqlite3.connect("call_trace_index.db")

rows = connection.execute(
    "SELECT DISTINCT number FROM numbers WHERE number LIKE ?",
    (f"%{NUMBER}%",),
).fetchall()

print("Matching indexed numbers:")
print(rows)

count = connection.execute(
    "SELECT COUNT(*) FROM numbers WHERE number LIKE ?",
    (f"%{NUMBER}%",),
).fetchone()[0]

print("Indexed occurrences:", count)

connection.close()


print("\n=== CHECK LOG FILES ===")

log_dir = Path(settings.log_dir)

files = [
    file
    for file in log_dir.iterdir()
    if file.is_file()
    and file.suffix.lower() in {".log", ".txt"}
]

print("Files:", len(files))
print("Searching for:", NUMBER)

matches = []

for file in files:
    try:
        with file.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as handle:
            for line_number, line in enumerate(handle, 1):
                if NUMBER in line:
                    matches.append(
                        (
                            file.name,
                            line_number,
                            line.strip()[:500],
                        )
                    )
                    break

    except OSError as exc:
        print("Could not read:", file, exc)

print("\nMatching files:", len(matches))

for filename, line_number, line in matches:
    print("\nFILE:", filename)
    print("LINE:", line_number)
    print("CONTENT:", line)