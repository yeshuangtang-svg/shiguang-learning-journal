$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --windowed --name '拾光学习日志' --icon "$PSScriptRoot/assets/app.ico" --version-file "$PSScriptRoot/desktop-version.txt" --add-data "${PSScriptRoot}/static:static" --add-data "${PSScriptRoot}/skills:skills" --add-data "${PSScriptRoot}/openapi.json:." --add-data "${PSScriptRoot}/assets/app.ico:." --distpath "$PSScriptRoot" --workpath "$PSScriptRoot/build/desktop" --specpath "$PSScriptRoot/build" "$PSScriptRoot/desktop.py"
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
