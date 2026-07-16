"""
Blacklight - Engine Entry Point (Phase 1)

The single entry point the Tauri desktop app will call. It imports the proven
artifact readers and returns ONE combined JSON document describing every
artifact - exactly what a Tauri "sidecar" (a helper process the app launches
and talks to) needs: one process, one JSON reply.

Usage:
  python blacklight_engine.py            -> JSON (default; what the app calls)
  python blacklight_engine.py --pretty   -> human-readable summary
  python blacklight_engine.py --reveal   -> include the REAL GDID (de-anonymizing;
                                            the app must gate this behind a click)

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


def main():
    reveal = "--reveal" in sys.argv
    pretty = "--pretty" in sys.argv
    data = collect(reveal=reveal)
    if pretty:
        print_pretty(data)
    else:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()