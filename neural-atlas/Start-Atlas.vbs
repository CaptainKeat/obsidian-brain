Set atlasShell = CreateObject("WScript.Shell")
Set atlasFS = CreateObject("Scripting.FileSystemObject")
atlasRoot = atlasFS.GetParentFolderName(WScript.ScriptFullName)
atlasPwsh = "pwsh.exe"
atlasShell.Run """" & atlasPwsh & """ -NoProfile -ExecutionPolicy Bypass -File """ & atlasRoot & "\Start-Atlas.ps1""", 0, False
