$dllPath = "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll"
$bytes = [System.IO.File]::ReadAllBytes($dllPath)
[System.Reflection.Assembly]::Load($bytes) | Out-Null

$port = 61181
$connStr = "Data Source=localhost:$port;"
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection($connStr)
$conn.Open()

$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
$r = $cmd.ExecuteReader()
$r.Read() | Out-Null
$cat = $r[0].ToString()
$r.Close()
$conn.ChangeDatabase($cat)

function Query-DMV($query) {
    try {
        $c = $conn.CreateCommand()
        $c.CommandText = $query
        $reader = $c.ExecuteReader()
        $rows = @()
        while ($reader.Read()) {
            $row = [ordered]@{}
            for ($i = 0; $i -lt $reader.FieldCount; $i++) {
                $name = $reader.GetName($i)
                $val = $reader.GetValue($i)
                if ($val -eq [DBNull]::Value) { $val = $null }
                $row[$name] = $val
            }
            $rows += $row
        }
        $reader.Close()
        return $rows
    } catch {
        Write-Warning "Error in query $query : $_"
        return @()
    }
}

Write-Output "Extracting tables..."
$tables = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_TABLES"

Write-Output "Extracting columns..."
$columns = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_COLUMNS"

Write-Output "Extracting measures..."
$measures = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_MEASURES"

Write-Output "Extracting partitions..."
$partitions = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_PARTITIONS"

Write-Output "Extracting relationships..."
$relationships = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_RELATIONSHIPS"

Write-Output "Extracting data sources..."
$dataSources = Query-DMV "SELECT * FROM `$SYSTEM.TMSCHEMA_DATA_SOURCES"

$result = [ordered]@{
    tables = $tables
    columns = $columns
    measures = $measures
    partitions = $partitions
    relationships = $relationships
    dataSources = $dataSources
}

$json = $result | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText("export_model.json", $json, [System.Text.Encoding]::UTF8)

Write-Output "Done! Exported to export_model.json"
$conn.Close()
