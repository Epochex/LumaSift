# Packaging

Build a Windows portable package:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
```

Outputs:

```text
dist/LumaSift/LumaSift.exe
dist/LumaSift-Windows-Portable.zip
dist/installer/LumaSiftSetup.exe
```

The script tries to build an Inno Setup installer. If `iscc` is missing, it attempts to install Inno Setup with `winget`. If that is unavailable, the portable package is still built and the installer script remains reproducible.

Friend-test recommendation:

```text
Send dist/installer/LumaSiftSetup.exe first.
Use dist/LumaSift-Windows-Portable.zip only when the user does not want to install software.
```
