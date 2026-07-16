"""
Blacklight - BAM/DAM Reader (Phase 1, read-only)

BAM (Background Activity Moderator) + DAM (Desktop Activity Moderator) record
the full path and LAST-RUN time of programs, per user. Unlike UserAssist/GDID
this lives in HKLM (machine-wide) -> needs an ADMIN prompt to read.

Location:
  HKLM\\SYSTEM\\CurrentControlSet\\Services\\bam\\State\\UserSettings\\{SID}
  (also legacy ...\\bam\\UserSettings\\{SID} and the DAM equivalent)

Each value: name = executable path, data = REG_BINARY whose first 8 bytes are a
FILETIME (last execution, UTC). Read-only. Pure Python standard library + ctypes.
"""

import winreg
import struct
import datetime
import ctypes

# BAM/DAM key roots (checked in order; missing ones are skipped)
BAM_ROOTS = [
    r"SYSTEM\CurrentControlSet\Services\bam\State\UserSettings",
    r"SYSTEM\CurrentControlSet\Services\bam\UserSettings",        # legacy (pre-1709)
    r"SYSTEM\CurrentControlSet\Services\dam\State\UserSettings",  # DAM sibling
]

# SIDs that never appear in ProfileList - name them directly
WELL_KNOWN_SIDS = {
    "S-1-5-18": "SYSTEM",
    "S-1-5-19": "LOCAL SERVICE",
    "S-1-5-20": "NETWORK SERVICE",
}


def is_admin():
    """True if this process is elevated (needed to read HKLM BAM)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def filetime_to_utc(ft):
    """Windows FILETIME (100ns ticks since 1601-01-01) -> UTC datetime, or None."""
    if not ft:
        return None
    try:
        return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ft / 10)
    except (OverflowError, OSError):
        return None


def build_drive_map():
    """Map \\Device\\HarddiskVolumeN -> drive letter (C:, D:, ...). Best effort."""
    drive_map = {}
    try:
        buf = ctypes.create_unicode_buffer(1024)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            dos = f"{letter}:"
            if ctypes.windll.kernel32.QueryDosDeviceW(dos, buf, 1024):
                drive_map[buf.value] = dos  # buf.value e.g. \Device\HarddiskVolume4
    except Exception:
        pass
    return drive_map


def translate_path(nt_path, drive_map):
    """Turn \\Device\\HarddiskVolume4\\... into C:\\... when we can."""
    for device, letter in drive_map.items():
        if nt_path.startswith(device + "\\"):
            return letter + nt_path[len(device):]
    return nt_path  # leave untouched if we can't match it


def sid_to_user(sid):
    """Resolve a SID to a readable account name (well-known -> ProfileList -> raw)."""
    if sid in WELL_KNOWN_SIDS:
        return WELL_KNOWN_SIDS[sid]
    try:
        path = rf"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\{sid}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        try:
            img, _ = winreg.QueryValueEx(key, "ProfileImagePath")
            return img.rstrip("\\").split("\\")[-1]  # last folder = username
        finally:
            winreg.CloseKey(key)
    except OSError:
        return sid  # fall back to the raw SID


def read_bam():
    """
    Returns (entries, access_denied). entries = list of dicts:
    {source, sid, user, path, last_run_utc}. This is the function the Tauri
    app will call later; main() just prints it.
    """
    drive_map = build_drive_map()
    entries = []
    access_denied = False

    for base in BAM_ROOTS:
        source = "DAM" if r"\dam\\" in base or r"\dam\ " in base or "dam" in base.split("\\")[3:4] else "BAM"
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
        except FileNotFoundError:
            continue
        except PermissionError:
            access_denied = True
            continue
        except OSError:
            access_denied = True
            continue

        try:
            i = 0
            while True:
                try:
                    sid = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1

                user = sid_to_user(sid)
                try:
                    sidkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{sid}")
                except OSError:
                    continue
                try:
                    j = 0
                    while True:
                        try:
                            name, data, vtype = winreg.EnumValue(sidkey, j)
                        except OSError:
                            break
                        j += 1

                        # Real entries are REG_BINARY paths; skip SequenceNumber/Version DWORDs
                        if vtype != winreg.REG_BINARY:
                            continue
                        if not isinstance(data, bytes) or len(data) < 8:
                            continue

                        ft = struct.unpack_from("<Q", data, 0)[0]
                        entries.append({
                            "source": source,
                            "sid": sid,
                            "user": user,
                            "path": translate_path(name, drive_map),
                            "last_run_utc": filetime_to_utc(ft),
                        })
                finally:
                    winreg.CloseKey(sidkey)
        finally:
            winreg.CloseKey(root)

    return entries, access_denied


def main():
    print("\n" + "=" * 92)
    print(" BLACKLIGHT - BAM/DAM  (programs run per user, with last-run time)")
    print(" Source: HKLM Services\\bam   |   Read-only   |   ADMIN required")
    print("=" * 92)

    if not is_admin():
        print(" [!] Not running as admin - the BAM key is protected, so results may")
        print("     be blocked or empty. Re-run from an ADMIN PowerShell/cmd.\n")

    entries, denied = read_bam()

    if denied and not entries:
        print(" Access denied reading BAM. Please run this from an ADMIN terminal:")
        print("   (right-click Terminal/cmd -> Run as administrator)\n")
        return

    entries.sort(key=lambda e: e["last_run_utc"] or datetime.datetime.min, reverse=True)
    print(f" Entries found: {len(entries)}\n")

    print(f'{"LAST RUN (UTC)":<20} {"SRC":<4} {"USER":<16} PROGRAM')
    print("-" * 92)
    for e in entries:
        when = e["last_run_utc"].strftime("%Y-%m-%d %H:%M:%S") if e["last_run_utc"] else "-"
        print(f'{when:<20} {e["source"]:<4} {e["user"][:15]:<16} {e["path"]}')
    print("-" * 92)
    print(" BAM/DAM records the LAST run of background-capable programs, per user,")
    print(" and can linger ~7 days even after an app is deleted.\n")


if __name__ == "__main__":
    main()