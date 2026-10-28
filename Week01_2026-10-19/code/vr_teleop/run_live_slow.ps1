# Run in a visible console: the operator must answer the existing spotter prompt.
$ErrorActionPreference = 'Stop'
& "$env:USERPROFILE\venvs\xarm\Scripts\python.exe" -u "$PSScriptRoot\vr_teleop.py" --live --slow
