"""
Blacklight - Engine Entry Point (Phase 1)

The single entry point the Tauri desktop app will call. It imports the proven
artifact readers and returns ONE combined JSON document describing every
artifact - exactly what a Tauri "sidecar" (a helper process the app launches
and talks to) needs: one process, one JSON reply.

Once frozen into a single .exe, this ONE file serves BOTH jobs, chosen by a
command word passed as the first argument:

  blacklight_engine.py scan               -> combined artifact JSON (default)
  blacklight_engine.py scan --pretty      -> human-readable summary
  blacklight_engine.py scan --reveal      -> include the REAL GDID (de-anonymizing)
  blacklight_engine.py clear-userassist            -> backup + clear, one JSON result
  blacklight_engine.py clear-userassist --dry-run  -> preview only, change nothing

Backward compatible: if NO command word is given, it defaults to `scan`
(so `blacklight_engine.py --pretty` still works for standalone testing).

Sensitive values (GDID) are MASKED unless --reveal is passed.
Pure Python standard library.
"""

import sys
import json
import datetime

# Import the proven readers (their own main() only runs when run directly)
from userassist_reader import read_userassist
from gdid_reader import read_gdid, mask_hex, classify, to_g_form
from bam_reader import read_bam


def _iso(dt):
    """datetime -> ISO 8601 string, or None (JSON can't serialize datetime)."""
    return dt.isoformat() if dt else None


def collect(reveal=False):
    """Gather every artifact into one JSON-serializable dict."""
    data = {
        "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "artifacts": {},
    }

    # ---- GDID ----
    try:
        hexval, source = read_gdid()
        if hexval:
            g = {
                "present": True,
                "type": classify(hexval),
                "length": len(hexval),
                "location": source,
                "value_masked": mask_hex(hexval),
            }
            if reveal:
                g["value"] = hexval
                g["server_form"] = to_g_form(hexval)
            data["artifacts"]["gdid"] = g
        else:
            data["artifacts"]["gdid"] = {"present": False}
    except Exception as e:
        data["artifacts"]["gdid"] = {"error": str(e)}

    # ---- UserAssist ----
    try:
        ua = read_userassist()
        data["artifacts"]["userassist"] = {
            "count": len(ua),
            "entries": [
                {
                    "name": e["name"],
                    "guid_label": e["guid_label"],
                    "run_count": e["run_count"],
                    "focus_time_ms": e["focus_time_ms"],
                    "last_run_utc": _iso(e["last_run_utc"]),
                }
                for e in ua
            ],
        }
    except Exception as e:
        data["artifacts"]["userassist"] = {"error": str(e)}

    # ---- BAM/DAM ----
    try:
        bam, denied = read_bam()
        data["artifacts"]["bam"] = {
            "admin_required": bool(denied and not bam),
            "count": len(bam),
            "entries": [
                {
                    "source": e["source"],
                    "user": e["user"],
                    "sid": e["sid"],
                    "path": e["path"],
                    "last_run_utc": _iso(e["last_run_utc"]),
                }
                for e in bam
            ],
        }
    except Exception as e:
        data["artifacts"]["bam"] = {"error": str(e)}

    return data


def print_pretty(data):
    """Quick human summary (for testing; the app consumes the JSON instead)."""
    a = data["artifacts"]
    print("\n" + "=" * 70)
    print(" BLACKLIGHT ENGINE - artifact summary")
    print("=" * 70)

    g = a.get("gdid", {})
    if g.get("present"):
        print(f" GDID       : PRESENT  [{g['type']}]  {g['value_masked']}")
    elif g.get("present") is False:
        print(" GDID       : not found")
    else:
        print(f" GDID       : error - {g.get('error')}")

    ua = a.get("userassist", {})
    print(f" UserAssist : {ua['count']} entries" if "count" in ua
          else f" UserAssist : error - {ua.get('error')}")

    bam = a.get("bam", {})
    if bam.get("admin_required"):
        print(" BAM/DAM    : admin required (re-run from an elevated terminal)")
    elif "count" in bam:
        print(f" BAM/DAM    : {bam['count']} entries")
    else:
        print(f" BAM/DAM    : error - {bam.get('error')}")
    print("=" * 70 + "\n")


def run_scan(argv):
    """The scan job (formerly main()). Reads flags out of argv."""
    reveal = "--reveal" in argv
    pretty = "--pretty" in argv
    data = collect(reveal=reveal)
    if pretty:
        print_pretty(data)
    else:
        print(json.dumps(data, indent=2))
    return 0


def run_clear_userassist(argv):
    """The UserAssist clear job. Delegates to userassist_clear's proven JSON
    helpers so the .exe emits EXACTLY the same JSON the app already expects."""
    # Imported here (not at top) so a plain `scan` never needs the clear module.
    from userassist_clear import _preview_json, _clear_json
    if "--dry-run" in argv:
        return _preview_json()   # preview only, changes nothing
    return _clear_json()         # backup first, then clear


# Command word -> handler. First non-flag argument selects the job.
COMMANDS = {
    "scan": run_scan,
    "clear-userassist": run_clear_userassist,
}


def main():
    argv = sys.argv[1:]

    # First argument that isn't a --flag is the command word.
    command = "scan"  # default keeps `blacklight_engine.py --pretty` working
    rest = []
    for i, tok in enumerate(argv):
        if not tok.startswith("-"):
            command = tok
            rest = argv[:i] + argv[i + 1:]  # everything except the command word
            break
    else:
        rest = argv  # no command word found -> all tokens are flags for `scan`

    handler = COMMANDS.get(command)
    if handler is None:
        print(json.dumps({
            "ok": False,
            "error": "unknown_command",
            "message": f"Unknown command '{command}'. Valid: {', '.join(COMMANDS)}."
        }))
        sys.exit(2)

    sys.exit(handler(rest))


if __name__ == "__main__":
    main()