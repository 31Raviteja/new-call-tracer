from pathlib import Path
import ast


# ============================================================
# SOURCE: ORIGINAL LARGE LOGS
# ============================================================

SOURCE = Path(
    r"Z:\Downloads\event_logs_10_08_2026\EVENT_LOG"
)


# ============================================================
# DESTINATION: SMALLER LOGS
# ============================================================

DEST = Path(
    r"Z:\Downloads\event_logs_10_08_2026\EVENT_LOG_SMALL"
)

DEST.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# EVENTS WE NEED FOR CALL TRACE
# ============================================================

KEEP_EVENTS = {
    "CHANNEL_CREATE",
    "CHANNEL_ANSWER",
    "CHANNEL_BRIDGE",
    "CHANNEL_UNBRIDGE",
    "CHANNEL_HANGUP",
    "CHANNEL_HANGUP_COMPLETE",
    "CHANNEL_DESTROY",
    "CHANNEL_STATE",
    "CHANNEL_EXECUTE",
    "CHANNEL_EXECUTE_COMPLETE",
    "CUSTOM",
}


# ============================================================
# CHECK WHETHER A LOG LINE SHOULD BE KEPT
# ============================================================

def keep_line(line: str) -> bool:

    if "#:EVENT[" not in line:
        return False

    try:

        _, event_text = line.split(
            "#:EVENT['freeswitch']:",
            1,
        )

        data = ast.literal_eval(
            event_text.strip()
        )

        if not isinstance(data, dict):
            return False

        event_name = str(
            data.get("Event-Name", "")
        ).strip()

        if event_name in KEEP_EVENTS:
            return True

        return False

    except Exception:
        return False


# ============================================================
# PROCESS ONE FILE
# ============================================================

def process_file(
    source: Path,
    destination: Path,
):

    total = 0
    kept = 0

    with source.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as src, destination.open(
        "w",
        encoding="utf-8",
    ) as dst:

        for line in src:

            total += 1

            if keep_line(line):

                dst.write(line)

                kept += 1

    return total, kept


# ============================================================
# MAIN
# ============================================================

def main():

    if not SOURCE.exists():

        print(
            f"ERROR: Source directory does not exist:"
        )

        print(SOURCE)

        return

    files = sorted(
        SOURCE.glob("*.log")
    )

    print("=" * 70)
    print("XLOGIX SMALL LOG GENERATOR")
    print("=" * 70)

    print()
    print(f"Source      : {SOURCE}")
    print(f"Destination : {DEST}")
    print(f"Files       : {len(files)}")
    print()

    total_original_bytes = 0
    total_small_bytes = 0
    total_lines = 0
    total_kept = 0

    for number, source in enumerate(
        files,
        1,
    ):

        destination = (
            DEST / source.name
        )

        print(
            f"[{number}/{len(files)}] "
            f"{source.name}"
        )

        total, kept = process_file(
            source,
            destination,
        )

        original_bytes = (
            source.stat().st_size
        )

        small_bytes = (
            destination.stat().st_size
        )

        total_original_bytes += (
            original_bytes
        )

        total_small_bytes += (
            small_bytes
        )

        total_lines += total
        total_kept += kept

        original_mb = (
            original_bytes
            / 1024
            / 1024
        )

        small_mb = (
            small_bytes
            / 1024
            / 1024
        )

        print(
            f"    Lines : {total:,}"
        )

        print(
            f"    Kept  : {kept:,}"
        )

        print(
            f"    Size  : "
            f"{original_mb:.2f} MB -> "
            f"{small_mb:.2f} MB"
        )

        print()

    original_gb = (
        total_original_bytes
        / 1024
        / 1024
        / 1024
    )

    small_gb = (
        total_small_bytes
        / 1024
        / 1024
        / 1024
    )

    if total_original_bytes > 0:

        reduction = (
            1
            - (
                total_small_bytes
                / total_original_bytes
            )
        ) * 100

    else:

        reduction = 0

    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Original size : "
        f"{original_gb:.2f} GB"
    )

    print(
        f"Small size    : "
        f"{small_gb:.2f} GB"
    )

    print(
        f"Reduction     : "
        f"{reduction:.2f}%"
    )

    print(
        f"Total lines   : "
        f"{total_lines:,}"
    )

    print(
        f"Lines kept    : "
        f"{total_kept:,}"
    )

    print()

    print(
        f"Small logs are here:"
    )

    print(DEST)


if __name__ == "__main__":
    main()