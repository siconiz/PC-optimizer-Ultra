; NSIS installer. Build: makensis -DVERSION=0.1.0 installer.nsi  (after python build.py)
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!define APP "PC Optimizer"
!define EXE "PCOptimizer.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\PCOptimizer"

Name "${APP}"
OutFile "dist/PCOptimizer-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} Setup"
VIAddVersionKey "CompanyName" "PC Optimizer contributors"
VIAddVersionKey "LegalCopyright" "MIT License"

!define MUI_ICON "assets/icon.ico"
!define MUI_UNICON "assets/icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "${APP} requires 64-bit Windows."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

; Every earlier version (0.1 - 0.4) used this same uninstall key. Remove it silently before installing, but keep
; the user's settings: the old uninstallers delete %APPDATA%\PCOptimizer, so it is copied aside and put back.
Function RemoveOldVersion
  ReadRegStr $0 HKLM "${UNINST_KEY}" "InstallLocation"
  ReadRegStr $1 HKLM "${UNINST_KEY}" "DisplayVersion"
  StrCmp $0 "" done
  IfFileExists "$0\uninstall.exe" 0 done
  DetailPrint "Removing PC Optimizer $1"
  nsExec::Exec 'taskkill /F /IM ${EXE}'
  SetShellVarContext current
  CreateDirectory "$TEMP\pco-keep"
  CopyFiles /SILENT "$APPDATA\PCOptimizer\*.*" "$TEMP\pco-keep"
  ExecWait '"$0\uninstall.exe" /S _?=$0'
  Delete "$0\uninstall.exe"
  RMDir "$0"
  CreateDirectory "$APPDATA\PCOptimizer"
  CopyFiles /SILENT "$TEMP\pco-keep\*.*" "$APPDATA\PCOptimizer"
  RMDir /r "$TEMP\pco-keep"
  done:
FunctionEnd

Section "${APP}" SecMain
  SectionIn RO
  Call RemoveOldVersion
  SetOutPath "$INSTDIR"
  File /r "dist\PCOptimizer\*"  ; backslashes: makensis on Windows splits File /r paths only at backslashes
  File "LICENSE"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  SetShellVarContext all
  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\${EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "PC Optimizer contributors"
  WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "https://github.com/worldhistorysim/pc-optimizer"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Desktop shortcut" SecDesktop
  SetShellVarContext all
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\${EXE}"
SectionEnd

Section "Uninstall"
  SetRegView 64
  ; remove only what the installer created, never the whole parent folder
  RMDir /r "$INSTDIR\_internal"
  RMDir /r "$INSTDIR\tools"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  SetShellVarContext all
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  SetShellVarContext current
  RMDir /r "$APPDATA\PCOptimizer"
  RMDir /r "$LOCALAPPDATA\PCOptimizer"  ; icon cache and downloaded widgets
  ExecWait 'schtasks /Delete /F /TN "PCOptimizer game boot"'
  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
