"""Offline LibreOffice UNO read of the initial Calc selection; not a Guest smoke."""
from __future__ import annotations
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> None:
    import uno
    from com.sun.star.beans import PropertyValue
    from .fixtures import build_fixture
    with tempfile.TemporaryDirectory(prefix="codesk-case6-v12-uno-") as directory:
        root = Path(directory)
        build_fixture(root / "public")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        cmd = ["libreoffice", f"-env:UserInstallation={(root / 'profile').as_uri()}", "--headless",
               f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext",
               "--norestore", "--nodefault", "--nofirststartwizard"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            local = uno.getComponentContext()
            resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
            for _ in range(100):
                try:
                    context = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
                    break
                except Exception:
                    time.sleep(0.1)
            else:
                raise RuntimeError("LibreOffice UNO did not become ready")
            desktop = context.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", context)
            for filename, expected in (("forecast_input.ods", (7, 2)), ("order_template.ods", (5, 2))):
                hidden = PropertyValue(); hidden.Name = "Hidden"; hidden.Value = True
                doc = desktop.loadComponentFromURL((root / "public" / filename).as_uri(), "_blank", 0, (hidden,))
                if not doc:
                    raise RuntimeError(f"LibreOffice could not open {filename}")
                addr = doc.CurrentController.Selection.RangeAddress
                actual = (addr.StartColumn, addr.StartRow)
                widths = [doc.Sheets.getByIndex(0).Columns.getByIndex(i).Width for i in range(9)]
                print(f"{filename}: selected={actual}, expected={expected}, column_widths_100th_mm={widths}")
                doc.close(True)
                if actual != expected:
                    raise RuntimeError(f"Initial selection mismatch for {filename}")
                if any(width < 3700 for width in widths):
                    raise RuntimeError(f"Column width mismatch for {filename}: {widths}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()


if __name__ == "__main__":
    main()
