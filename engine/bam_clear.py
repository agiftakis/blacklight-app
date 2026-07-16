"""
Blacklight - BAM/DAM Clear + Auto-Backup (Phase 1, privacy hygiene)

WHAT THIS DOES (plain English):
  1. FIRST exports the BAM/DAM keys to timestamped .reg files
     (double-click Windows restore files) so nothing is unrecoverable.
  2. THEN - only after you type CLEAR (interactive) or the app passes --yes -
     deletes the recorded program-run values under each user's BAM/DAM key,
     resetting the "last time each program ran" history.

WHAT IT DOES NOT DO:
  - Never fabricates or fakes entries (that would be evidence tampering).
    It only clears YOUR OWN real data.
  - Does NOT delete the bookkeeping values (SequenceNumber / Version) or the
    key structure - it removes only the REG_BINARY program-run records.
  - A cleared BAM can look conspicuously empty. This is "clear my traces,"
    NOT "become invisible / beat forensics." NOTE: Windows naturally rebuilds
    BAM within ~7 days from normal use anyway.

HKLM = machine-wide hive -> this script MUST run from an ELEVATED (admin)
terminal, unlike the UserAssist clear. Reversible via the backups.
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

# Reuse the proven reader so we preview/target exactly what we're about to clear.
# BAM_ROOTS = the per-user "UserSettings" key roots (no HKLM\ prefix; winreg
# already knows the hive). is_admin() / read_bam() are reused verbatim.
from bam_reader import read_bam, is_admin, BAM_ROOTS

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


def _label_for(base):
    """Short filename tag so each backup .reg is identifiable."""
    b = base.lower()
    if "\\dam\\" in b:
        return "dam_state"
    if "\\state\\" in b:
        return "bam_state"
    return "bam_legacy"


def backup_bam():
    """
    Export every EXISTING BAM/DAM root to its own timestamped .reg file.
    Returns a LIST of backup paths (BAM spans more than one key, unlike
    UserAssist which was a single key -> single file).

    Missing roots (e.g. legacy/DAM keys absent on this Windows build) are
    skipped quietly. If NOTHING could be exported, we raise -> clear aborts.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = []
    errors = []

    for base in BAM_ROOTS:
        reg_path = "HKLM\\" + base  # reg.exe wants the hive prefix spelled out
        label = _label_for(base)
        out_path = os.path.join(BACKUP_DIR, f"bam_backup_{label}_{stamp}.reg")
        # reg.exe export = Windows' own native registry export tool (.reg file)
        result = subprocess.run(
            ["reg", "export", reg_path, out_path, "/y"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            paths.append(out_path)
        else:
            # Most common cause: the key simply doesn't exist on this build.
            errors.append(f"{reg_path}: {result.stderr.strip() or result.stdout.strip() or 'export failed'}")

    if not paths:
        raise RuntimeError("No BAM/DAM keys could be exported. " + " | ".join(errors))
    return paths


def clear_bam():
    """
    Delete the REG_BINARY program-run values under every user's BAM/DAM key.
    Skips SequenceNumber/Version (non-BINARY bookkeeping) so the key structure
    stays intact - we only wipe the run records.

    Returns (deleted, permission_denied):
      deleted           = how many values were removed
      permission_denied = True if Windows blocked a write even though we're
                          elevated (BAM's ACL [the key's Windows permission
                          list] can require SYSTEM-level access, not just admin)
    """
    deleted = 0
    permission_denied = False

    for base in BAM_ROOTS:
        # Open the root read-only just to list the per-user {SID} subkeys.
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
        except FileNotFoundError:
            continue
        except PermissionError:
            permission_denied = True
            continue
        except OSError:
            continue

        try:
            sids = []
            i = 0
            while True:
                try:
                    sids.append(winreg.EnumKey(root, i))
                except OSError:
                    break
                i += 1
        finally:
            winreg.CloseKey(root)

        for sid in sids:
            subkey = f"{base}\\{sid}"
            try:
                # Open each {SID} key WITH write access (needs elevation).
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0,
                                     winreg.KEY_READ | winreg.KEY_SET_VALUE)
            except PermissionError:
                permission_denied = True
                continue
            except FileNotFoundError:
                continue
            except OSError:
                continue

            try:
                # Collect target names first - can't delete safely while
                # enumerating by index. Only REG_BINARY run-records qualify.
                names = []
                j = 0
                while True:
                    try:
                        n, data, vtype = winreg.EnumValue(key, j)
                    except OSError:
                        break
                    j += 1
                    if vtype != winreg.REG_BINARY:
                        continue  # skip SequenceNumber / Version DWORDs
                    if not isinstance(data, bytes) or len(data) < 8:
                        continue
                    names.append(n)

                for n in names:
                    try:
                        winreg.DeleteValue(key, n)
                        deleted += 1
                    except PermissionError:
                        permission_denied = True
                    except OSError:
                        pass  # skip anything that refuses to delete
            finally:
                winreg.CloseKey(key)

    return deleted, permission_denied


# ----------------------------------------------------------------------
# Headless JSON modes (used by the Blacklight app)
# These print EXACTLY ONE JSON object to stdout and nothing else, so the
# app can parse the result cleanly.
# ----------------------------------------------------------------------

def _preview_json():
    """Dry run: report how many entries WOULD be cleared. Changes nothing."""
    admin = is_admin()
    try:
        entries, denied = read_bam()
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "read", "error": str(e)}))
        return 1
    print(json.dumps({
        "ok": True,
        "dry_run": True,
        "would_clear": len(entries),
        "admin": admin,
        "access_denied": denied,
        "message": (f"{len(entries)} entries would be cleared. "
                    "Nothing was changed (dry run).")
    }))
    return 0


def _clear_json():
    """Backup first, then clear. Aborts (and reports) if the backup fails."""
    # Gate on elevation up front - HKLM writes need admin; fail cleanly if not.
    if not is_admin():
        print(json.dumps({
            "ok": False,
            "stage": "admin",
            "error": "admin_required",
            "message": ("BAM lives in HKLM (machine-wide) and needs an elevated "
                        "(admin) process. Nothing was changed.")
        }))
        return 1

    try:
        before, _denied = read_bam()
        before_count = len(before)
    except Exception:
        before_count = None

    # 1) Backup FIRST - if this fails, nothing is cleared.
    try:
        backup_paths = backup_bam()
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
        cleared, perm_denied = clear_bam()
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "stage": "clear",
            "backup_paths": backup_paths,
            "error": str(e),
            "message": ("Backup was saved, but clearing failed. "
                        "You can restore from the backup.")
        }))
        return 1

    result = {
        "ok": True,
        "backup_paths": backup_paths,
        "cleared": cleared,
        "before_count": before_count,
        "message": f"Cleared {cleared} entries. Backup saved."
    }

    # Elevated but Windows still blocked the deletes -> the known BAM ACL wall.
    if perm_denied and cleared == 0:
        result["ok"] = False
        result["stage"] = "clear"
        result["error"] = "permission_denied"
        result["message"] = ("Backup saved, but Windows blocked deletion of BAM "
                             "values even though this process is elevated. BAM may "
                             "require SYSTEM-level access (not just admin).")
    elif perm_denied:
        result["message"] += " (Some values were blocked by Windows and left in place.)"

    print(json.dumps(result))
    return 0 if result["ok"] else 1


def main():
    parser = argparse.ArgumentParser(
        description="Blacklight - clear BAM/DAM history (with automatic backup)."
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

    # ---- Interactive path ----------------------------------------------
    print("\n" + "=" * 72)
    print(" BLACKLIGHT - Clear BAM/DAM history (with automatic backup)")
    print("=" * 72)

    if not is_admin():
        print(" [!] NOT running as admin. BAM lives in HKLM (machine-wide) and is")
        print("     protected - reading/clearing will be blocked. Re-run from an")
        print("     ADMIN terminal (right-click Terminal/cmd -> Run as administrator).\n")
        return

    entries, _denied = read_bam()
    print(f" Current BAM/DAM entries: {len(entries)}")
    print(" These record the LAST run of background-capable programs, per user.\n")

    print(" What will happen:")
    print("   1) Backup of the BAM/DAM keys -> .reg restore file(s)")
    print("   2) The recorded run-values are deleted (history reset)")
    print("   3) Windows records fresh from normal use (BAM self-rebuilds ~7 days)\n")
    print(" Clears YOUR OWN real data only. No fake entries are ever created.")
    print(" A cleared history can look conspicuously empty - hygiene, not")
    print(" 'forensic invisibility'.\n")

    confirm = input(" Type CLEAR (all caps) to proceed, anything else to cancel: ").strip()
    if confirm != "CLEAR":
        print("\n Cancelled. Nothing was changed.\n")
        return

    print("\n [1/2] Backing up...")
    try:
        backup_paths = backup_bam()
    except Exception as e:
        print(f" ABORTED - backup did not succeed, so nothing was cleared.\n   {e}\n")
        return
    for p in backup_paths:
        print(f"       Backup saved: {p}")

    print(" [2/2] Clearing entries...")
    count, perm_denied = clear_bam()
    print(f"       Cleared {count} entries.")
    if perm_denied and count == 0:
        print("       [!] Windows blocked the deletes even though you're elevated.")
        print("           BAM may require SYSTEM-level access (not just admin).")
    elif perm_denied:
        print("       [!] Some values were blocked by Windows and left in place.")
    print()

    print(" Done. To undo: double-click the .reg file(s) above and accept the")
    print(' Windows prompt (or run:  reg import "<path>"  ).\n')


if __name__ == "__main__":
    main()