Option Explicit
Dim shell, fs, root, runtime, script
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
runtime = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
script = root & "\scripts\launch_admin.py"
If fs.FileExists(runtime) Then
    shell.Run Chr(34) & runtime & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
Else
    MsgBox "Python runtime was not found. Please ask Sol to fix the launcher.", 48, "Campus Activities"
End If
