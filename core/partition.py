"""Partition layout and resizing through the Windows Storage module (MSFT_Disk / MSFT_Partition). Only NTFS
partitions with a drive letter are changed, within the sizes Windows itself reports as possible."""
import json, subprocess

NO_WINDOW = 0x08000000
LAYOUT = r"""
$d = Get-Disk | % { [pscustomobject]@{n=$_.Number; name=$_.FriendlyName; size=$_.Size; style="$($_.PartitionStyle)";
                                        free=$_.LargestFreeExtent} }
$p = Get-Partition | % { $v = $null; try { $v = $_ | Get-Volume -ErrorAction Stop } catch {}
  [pscustomobject]@{disk=$_.DiskNumber; num=$_.PartitionNumber; letter="$($_.DriveLetter)".Trim([char]0);
    offset=$_.Offset; size=$_.Size; type="$($_.Type)"; system=$_.IsSystem; boot=$_.IsBoot; hidden=$_.IsHidden;
    fs=$v.FileSystem; free=$v.SizeRemaining; label=$v.FileSystemLabel} }
@{disks=@($d); parts=@($p)} | ConvertTo-Json -Depth 4 -Compress
"""

def _ps(script, timeout=600):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, timeout=timeout, creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else
                           "PowerShell error")
    return r.stdout.strip()

def layout():
    """{'disks': [...], 'parts': [...]} sorted by disk and position on the disk."""
    d = json.loads(_ps(LAYOUT))
    d["parts"].sort(key=lambda x: (x["disk"], x["offset"]))
    return d

def changeable(p):
    """None if the partition may be resized here, else the reason it is left alone."""
    if p["system"] or p["hidden"] or p["type"] in ("System", "Recovery", "Reserved", "Unknown"):
        return "Used by Windows to start or repair the PC."
    if (p.get("fs") or "").upper() != "NTFS":
        return "Windows can resize only NTFS partitions."
    if not p.get("letter"):
        return "No drive letter."
    return None

def supported(disk, num):
    """(smallest, largest) size in bytes Windows allows now (Get-PartitionSupportedSize)."""
    r = json.loads(_ps(f"Get-PartitionSupportedSize -DiskNumber {int(disk)} -PartitionNumber {int(num)} | "
                       "ConvertTo-Json -Compress", 300))
    return int(r["SizeMin"]), int(r["SizeMax"])

def bitlocker_on(letter):
    try:
        return _ps(f"(Get-BitLockerVolume -MountPoint '{letter[0]}:').ProtectionStatus", 60) == "On"
    except Exception:
        return False

def resize(disk, num, size):
    lo, hi = supported(disk, num)
    if not lo <= size <= hi:
        raise ValueError("Size out of range")
    _ps(f"Resize-Partition -DiskNumber {int(disk)} -PartitionNumber {int(num)} -Size {int(size)}", 3600)

def new_drive(disk, label="Data"):
    """New NTFS drive in the largest free space of the disk; returns its letter."""
    safe = "".join(ch for ch in label if ch.isalnum() or ch in " -_")[:32] or "Data"
    return _ps(f"$p = New-Partition -DiskNumber {int(disk)} -UseMaximumSize -AssignDriveLetter; "
               f"$p | Format-Volume -FileSystem NTFS -NewFileSystemLabel '{safe}' -Confirm:$false | Out-Null; "
               "$p.DriveLetter", 1800)
