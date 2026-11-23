$bytes = [System.IO.File]::ReadAllBytes("C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll")
$asm = [System.Reflection.Assembly]::Load($bytes)
$asm.GetExportedTypes() | Where-Object { $_.Name -like "*Connection*" } | Select-Object FullName
