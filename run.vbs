Set WshShell = CreateObject("WScript.Shell")
strScriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strScriptPath
WshShell.Run "pythonw.exe app.py", 0, False
