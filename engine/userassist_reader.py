"""
Blacklight - UserAssist Reader (Phase 1, read-only)
Shows which GUI programs you launched, how many times, total focus time,
and the last-run timestamp - for your current user account.
HKCU = current-user registry hive -> NO admin needed. Read-only.
Pure Python standard library - no pip installs.
"""

import winreg
import struct
import datetime

# Registry location (HKCU = your current-user settings; safe, no admin)
USERASSIST_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"

# The two GUID subkeys that matter on Win7+ (per forensic references)
GUIDS = {
    "{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}": "Executables (.exe)",
    "{F4E57C4B-2036-45F0-A9AB-443BCFE33D9F}": "Shortcuts (.lnk)",
}

# Windows stores some paths as folder-GUIDs (KNOWNFOLDERID). We translate the
# common ones; anything not listed is shown as-is. We'll expand this map later.
KNOWN_FOLDERS = {
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": "System32",
    "{6D809377-6AF0-444B-8957-A3773F02200E}": "Program Files",
    "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}": "Program Files (x86)",
    "{F38BF404-1D43-42F2-9305-67DE0B28FC23}": "Windows",
    "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}": "Desktop",
}

# Windows' own session/control bookkeeping - NOT programs you launched.
# (These produce junk rows like the '1641' date; we hide them.)
CONTROL_PREFIXES = ("UEME_CTLSESSION", "UEME_CTLCUACount")

# On some machines real entries carry one of these prefixes; we strip it.
RUN_PREFIXES = ("UEME_RUNPATH:", "UEME_RUNPIDL:")


def rot13(text):
    """Undo the ROT13 cipher Windows uses on UserAssist value names."""
    out = []
    for ch in text:
        c = ord(ch)
        if 65 <= c <= 90:        # A-Z
            out.append(chr((c - 65 + 13) % 26 + 65))
        elif 97 <= c <= 122:     # a-z
            out.append(chr((c - 97 + 13) % 26 + 97))
        else:
            out.append(ch)
    return "".join(out)


def prettify_path(name):
    """Swap a leading KNOWNFOLDERID GUID for its readable folder name."""
    for guid, folder in KNOWN_FOLDERS.items():
        if name.upper().startswith(guid.upper()):
            return folder + name[len(guid):]
    return name


def filetime_to_utc(ft):
    """Convert Windows FILETIME (100ns ticks since 1601-01-01) to a UTC datetime."""
    if not ft:
        return None
    try:
        return datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ft / 10)
    except (OverflowError, OSError):
        return None


def read_userassist():
    """
    Returns a list of dicts (one per entry). This is the function the Tauri
    app will call later; main() below is only for testing in the terminal.
    """
    results = []
    for guid, label in GUIDS.items():
        subkey = f"{USERASSIST_PATH}\\{guid}\\Count"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
        except FileNotFoundError:
            continue  # this GUID subkey isn't present on this machine
        try:
            index = 0
            while True:
                try:
                    value_name, value_data, _ = winreg.EnumValue(key, index)
                except OSError:
                    break  # ran out of values
                index += 1

                raw = rot13(value_name)

                # Hide Windows' session/control bookkeeping (not real programs)
                if raw.startswith(CONTROL_PREFIXES):
                    continue

                # Strip a UEME_RUNPATH:/UEME_RUNPIDL: prefix if this machine uses one
                for prefix in RUN_PREFIXES:
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):]
                        break

                decoded = prettify_path(raw)
                if not decoded.strip():
                    continue  # skip the empty default value

                run_count = focus_ms = 0
                last_run = None
                if isinstance(value_data, bytes) and len(value_data) >= 68:
                    run_count = struct.unpack_from("<I", value_data, 4)[0]
                    focus_ms = struct.unpack_from("<I", value_data, 12)[0]
                    last_ft = struct.unpack_from("<Q", value_data, 60)[0]
                    last_run = filetime_to_utc(last_ft)

                results.append({
                    "guid_label": label,
                    "name": decoded,
                    "run_count": run_count,
                    "focus_time_ms": focus_ms,
                    "last_run_utc": last_run,
                })
        finally:
            winreg.CloseKey(key)
    return results


def main():
    entries = read_userassist()
    entries.sort(key=lambda e: e["last_run_utc"] or datetime.datetime.min, reverse=True)

    print("\n" + "=" * 80)
    print(" BLACKLIGHT - UserAssist  (GUI programs YOU launched, this user account)")
    print(" Source: HKCU UserAssist   |   Read-only   |   No admin")
    print("=" * 80)
    print(f" Entries found: {len(entries)}\n")

    print(f'{"LAST RUN (UTC)":<20} {"RUNS":>5} {"FOCUS(s)":>9}  PROGRAM')
    print("-" * 80)
    for e in entries:
        when = e["last_run_utc"].strftime("%Y-%m-%d %H:%M:%S") if e["last_run_utc"] else "-"
        focus_s = e["focus_time_ms"] / 1000 if e["focus_time_ms"] else 0
        print(f'{when:<20} {e["run_count"]:>5} {focus_s:>9.1f}  {e["name"]}')
    print("-" * 80)
    print(" Note: Windows session-bookkeeping rows (UEME_*) are now hidden.")
    print(" 'RUNS 0 / -' entries are usually installers or Store/UWP apps")
    print(" Windows lists but doesn't count - that's normal.\n")


if __name__ == "__main__":
    main()