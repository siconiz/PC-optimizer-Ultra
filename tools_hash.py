"""Writes the SHA-256 of every file in widgets/ into core/addons.py. Run before a release (build.py does it)."""
import hashlib, re
from pathlib import Path

def update():
    src = Path("core/addons.py").read_bytes().decode("utf-8")
    for f in Path("widgets").glob("*.py"):
        h = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        src = re.sub(rf'(\("{re.escape(f.name)}", None, ")[0-9a-f]{{64}}(")', rf"\g<1>{h}\g<2>", src)
    Path("core/addons.py").write_bytes(src.encode("utf-8"))  # keep line endings as they are

if __name__ == "__main__":
    update()
