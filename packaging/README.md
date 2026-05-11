# Packaging

Build a Windows portable package:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
```

Output:

```text
dist/LumaSift/LumaSift.exe
dist/LumaSift-Windows-Portable.zip
```

The portable package is the current friend-test distribution format. A signed installer can be added later with Inno Setup or MSIX once the UI and product behavior stabilize.
