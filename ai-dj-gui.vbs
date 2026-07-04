' AI DJ GUI launcher (no console window)
' Double-click this to start the app with DJ selector silently

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
strScriptPath = WScript.ScriptFullName
strScriptDir = objFSO.GetParentFolderName(strScriptPath)

' Build the command
strPythonExe = strScriptDir & "\venv\Scripts\python.exe"
strAppScript = strScriptDir & "\app.py"

' Run with no window (0 = hidden, False = don't wait)
objShell.Run """" & strPythonExe & """ """ & strAppScript & """", 0, False
