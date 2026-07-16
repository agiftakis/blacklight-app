"""
Blacklight - GDID Reader (Phase 1, read-only)

Surfaces your Windows Global Device Identifier (GDID): a 64-bit device ID that
Microsoft's login.live.com ASSIGNS to your Windows install (NOT computed from
your hardware). It survives Windows updates and can correlate a device across
IP addresses / VPNs.

Location (HKCU = current-user hive, NO admin):
  HKCU\\Software\\Microsoft\\IdentityCRL\\ExtendedProperties  ->  value "LID"
  Fallback (if LID empty):
  HKCU\\Software\\Microsoft\\IdentityCRL\\Immersive\\production\\Token\\{GUID}\\DeviceId

*** PRIVACY: your real GDID is a DE-ANONYMIZING identifier. This tool MASKS it
by default. Do NOT screenshot, paste, or share the full value. ***

Pure Python standard library.
"""

import sys
import winreg

EXT_PROPS = r"Software\Microsoft\IdentityCRL\ExtendedProperties"
TOKEN_ROOT = r"Software\Microsoft\IdentityCRL\Immersive\production\Token"

PUID_CLASSES = {
    "0018": "Device PUID (identifies this Windows install)",
    "0003": "User PUID (identifies your Microsoft account)",
}


def _read_value(subkey, name):
    """Read one registry value as text, or None if key/value missing/empty."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
    except FileNotFoundError:
        return None
    try:
        try:
            val, _ = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return str(val).strip() if val else None
    finally:
        winreg.CloseKey(key)


def read_gdid():
    """Return (hex_value, source_label) or (None, None)."""
    lid = _read_value(EXT_PROPS, "LID")
    if lid:
        return lid, r"HKCU\...\IdentityCRL\ExtendedProperties\LID"

    # Fallback: walk Immersive\production\Token\{GUID}\DeviceId
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, TOKEN_ROOT)
    except FileNotFoundError:
        return None, None
    try:
        i = 0
        while True:
            try:
                guid = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            dev = _read_value(f"{TOKEN_ROOT}\\{guid}", "DeviceId")
            if dev:
                return dev, rf"HKCU\...\Token\{guid}\DeviceId"
    finally:
        winreg.CloseKey(root)
    return None, None


def classify(hexstr):
    prefix = hexstr[:4].lower()
    return PUID_CLASSES.get(prefix, f"Unknown class (prefix {prefix})")


def to_g_form(hexstr):
    """The 'g:<decimal>' form Microsoft's servers use."""
    try:
        return "g:" + str(int(hexstr, 16))
    except ValueError:
        return "(could not convert)"


def mask_hex(hexstr):
    """Show class prefix + last 3, hide the unique middle."""
    if not hexstr:
        return "(none)"
    if len(hexstr) <= 8:
        return hexstr[:2] + "X" * (len(hexstr) - 2)
    return hexstr[:4] + "X" * (len(hexstr) - 7) + hexstr[-3:]


def main():
    reveal = "--reveal" in sys.argv

    print("\n" + "=" * 74)
    print(" BLACKLIGHT - GDID  (Global Device Identifier)")
    print(" Source: HKCU IdentityCRL   |   Read-only   |   No admin")
    print("=" * 74)

    hexval, source = read_gdid()

    if not hexval:
        print(" No GDID found in the registry.")
        print(" (Likely a local-only account that never touched the internet,")
        print("  or an MSA hasn't provisioned this device yet.)\n")
        return

    print(" Status   : PRESENT - this device has a server-assigned GDID")
    print(f" Type     : {classify(hexval)}")
    print(f" Length   : {len(hexval)} hex digits")
    print(f" Location : {source}")
    print("-" * 74)

    if reveal:
        print(" !! FULL VALUE (de-anonymizing - do NOT share/screenshot/paste) !!")
        print(f"   Hex     : {hexval}")
        print(f"   Server  : {to_g_form(hexval)}")
    else:
        print(" Value (masked for your safety):")
        print(f"   Hex     : {mask_hex(hexval)}")
        print("   Server  : (hidden)")
        print("\n This ID can de-anonymize you, so it is masked on purpose.")
        print(" To see the real value LOCALLY (and never share it):")
        print("   python gdid_reader.py --reveal")

    print("-" * 74)
    print(" What it means: login.live.com ASSIGNED this ID to your Windows")
    print(" install (not from your hardware). It survives updates and can link")
    print(" this device across IPs and VPNs. A clean reinstall gets a NEW one;")
    print(" the old one isn't erased on Microsoft's side.\n")


if __name__ == "__main__":
    main()