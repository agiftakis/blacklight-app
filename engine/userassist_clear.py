"""
Blacklight - UserAssist Clear + Auto-Backup (Phase 1, privacy hygiene)

WHAT THIS DOES (plain English):
  1. FIRST exports your entire UserAssist key to a timestamped .reg file
     (a double-click Windows restore file) so nothing is unrecoverable.
  2. THEN - only after you type CLEAR - deletes the recorded entries under
     both UserAssist Count keys, resetting your app-launch history.

WHAT IT DOES NOT DO:
  - Never fabricates or fakes entries (that would be evidence tampering).
    It only clears YOUR OWN real data.
  - A cleared UserAssist can look conspicuously empty. This is
    "clear my traces," NOT "become invisible / beat forensics."

HKCU = current-user hive -> NO admin needed. Reversible via the backup.
Pure Python standard library.

USAGE:
  (no args)            interactive mode - human types CLEAR to confirm
  --json --dry-run     preview only: report what WOULD clear, change nothing
  --json --yes         headless: backup then clear, print one JSON result
                       (--yes means the CALLER already got the user's confirm;
                        this is how the Blacklight app triggers a clear)
  --json               refuses - confirmation_required
"""

import os
import sys
import json
import argparse
import winreg
import subprocess
import datetime

# Reuse the proven reader so we preview exactly what we're about to clear.
from userassist_reader import read_userassist, USERASSIST_PATH, GUIDS

# Full key path in the format reg.exe expects (HKCU\...)
HKCU_EXPORT_ROOT = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"


def _backup_root():
    """Where safety-net .reg backups are written.

    FROZEN (shipped .exe): %LOCALAPPDATA%\\Blacklight\\backups - a real,
        always-user-writable, persistent folder. We must NOT use the folder
        next to the program here: a one-file PyInstaller .exe unpacks into a
        temporary directory that Windows deletes on exit, so a backup written
        "next to __file__" would silently vanish - breaking the restore promise.
    DEV (plain .py): engine\\backups next to this script (unchanged behavior,
        stays git-ignored, keeps the sandbox-proven round-trip identical).
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Blacklight", "backups")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


BACKUP_DIR = _backup_root()


def backup_userassist():
    """Export the whole UserAssist key to a timestamped .reg file. Returns its path."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKUP_DIR, f"userassist_backup_{stamp}.reg")
    # reg.exe export = Windows' own registry export tool (native .reg file)
    result = subprocess.run(
        ["reg", "export", HKCU_EXPORT_ROOT, out_path, "/y"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "unknown error")
    return out_path


def clear_userassist():
    """Delete all recorded values under each {GUID}\\Count key. Returns count deleted."""
    deleted = 0
    for guid in GUIDS:
        subkey = f"{USERASSIST_PATH}\\{guid}\\Count"
        try:
            # Open with write access (still HKCU -> no admin)
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0,
                                 winreg.KEY_READ | winreg.KEY_SET_VALUE)
        except FileNotFoundError:
            continue
        try:
            # Collect names first - can't delete safely while enumerating by index
            names = []
            i = 0
            while True:
                try:
                    n, _, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                names.append(n)
                i += 1
            for n in names:
                try:
                    winreg.DeleteValue(key, n)
                    deleted += 1
                except OSError:
                    pass  # skip anything that refuses to delete
        finally:
            winreg.CloseKey(key)
    return deleted


# ----------------------------------------------------------------------
# Headless JSON modes (used by the Blacklight app)
# These print EXACTLY ONE JSON object to stdout and nothing else, so the
# app can parse the result cleanly.
# ----------------------------------------------------------------------

def _preview_json():
    """Dry run: report how many entries WOULD be cleared. Changes nothing."""
    try:
        before = len(read_userassist())
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "read", "error": str(e)}))
        return 1
    print(json.dumps({
        "ok": True,
        "dry_run": True,
        "would_clear": before,
        "message": f"{before} entries would be cleared. Nothing was changed (dry run)."
    }))
    return 0


def _clear_json():
    """Backup first, then clear. Aborts (and reports) if the backup fails."""
    try:
        before = len(read_userassist())
    except Exception:
        before = None

    # 1) Backup FIRST - if this fails, nothing is cleared.
    try:
        backup_path = backup_userassist()
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "stage": "backup",
            "error": str(e),
            "message": "Backup failed - nothing was cleared."
        }))
        return 1

    # 2) Clear.
    try:
        cleared = clear_userassist()
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "stage": "clear",
            "backup_path": backup_path,
            "error": str(e),
            "message": "Backup was saved, but clearing failed. You can restore from the backup."
        }))
        return 1

    print(json.dumps({
        "ok": True,
        "backup_path": backup_path,
        "cleared": cleared,
        "before_count": before,
        "message": f"Cleared {cleared} entries. Backup saved."
    }))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Blacklight - clear UserAssist history (with automatic backup)."
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit a single JSON result (for the app). Suppresses interactive prompts.")
    parser.add_argument("--yes", action="store_true",
                        help="Confirm the clear. The CALLER is responsible for the user's confirmation.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only: report what would clear, change nothing.")
    args = parser.parse_args()

    # ---- Headless / app path -------------------------------------------
    if args.json:
        if args.dry_run:
            sys.exit(_preview_json())
        if not args.yes:
            print(json.dumps({
                "ok": False,
                "error": "confirmation_required",
                "message": "Refusing to clear without explicit --yes."
            }))
            sys.exit(1)
        sys.exit(_clear_json())

    # ---- Interactive path (unchanged, sandbox-validated) ---------------
    print("\n" + "=" * 72)
    print(" BLACKLIGHT - Clear UserAssist history (with automatic backup)")
    print("=" * 72)

    entries = read_userassist()
    print(f" Current UserAssist entries: {len(entries)}")
    print(" These record which GUI programs you launched, run counts, and times.\n")

    print(" What will happen:")
    print("   1) Full backup of the UserAssist key -> a .reg restore file")
    print("   2) The recorded entries are deleted (history reset)")
    print("   3) Windows records fresh from your next launches\n")
    print(" Clears YOUR OWN real data only. No fake entries are ever created.")
    print(" A cleared history can look conspicuously empty - hygiene, not")
    print(" 'forensic invisibility'.\n")

    confirm = input(" Type CLEAR (all caps) to proceed, anything else to cancel: ").strip()
    if confirm != "CLEAR":
        print("\n Cancelled. Nothing was changed.\n")
        return

    print("\n [1/2] Backing up...")
    try:
        backup_path = backup_userassist()
    except Exception as e:
        print(f" ABORTED - backup did not succeed, so nothing was cleared.\n   {e}\n")
        return
    print(f"       Backup saved: {backup_path}")

    print(" [2/2] Clearing entries...")
    count = clear_userassist()
    print(f"       Cleared {count} entries.\n")

    print(" Done. To undo: double-click the .reg file above and accept the")
    print(' Windows prompt (or run:  reg import "<path>"  ).\n')


if __name__ == "__main__":
    main()