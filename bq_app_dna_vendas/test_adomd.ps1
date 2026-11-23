$dllPath = "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll"
$bytes = [System.IO.File]::ReadAllBytes($dllPath)
[System.Reflection.Assembly]::Load($bytes) | Out-Null

$port = 61181
$connStr = "Data Source=localhost:$port;"
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection($connStr)
try {
    $conn.Open()
    Write-Output "Successfully connected to Power BI Desktop SSAS!"
    
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
    $reader = $cmd.ExecuteReader()
    $catalogs = @()
    while ($reader.Read()) {
        $cat = $reader[0].ToString()
        $catalogs += $cat
        Write-Output "Catalog: $cat"
    }
    $reader.Close()

    if ($catalogs.Count -gt 0) {
        $conn.ChangeDatabase($catalogs[0])
        
        Write-Output "`n=== TABLES ==="
        $cmdTables = $conn.CreateCommand()
        $cmdTables.CommandText = "SELECT [ID], [Name], [Description] FROM `$SYSTEM.TMSCHEMA_TABLES"
        $rTables = $cmdTables.ExecuteReader()
        $tableMap = @{}
        while ($rTables.Read()) {
            $id = $rTables["ID"]
            $name = $rTables["Name"]
            $tableMap[$id] = $name
            Write-Output "Table [$id]: $name"
        }
        $rTables.Close()

        Write-Output "`n=== MEASURES ==="
        $cmdMeasures = $conn.CreateCommand()
        $cmdMeasures.CommandText = "SELECT [TableID], [Name], [Expression] FROM `$SYSTEM.TMSCHEMA_MEASURES"
        $rMeasures = $cmdMeasures.ExecuteReader()
        $measureCount = 0
        while ($rMeasures.Read()) {
            $measureCount++
            $tid = $rMeasures["TableID"]
            $tName = if ($tableMap.ContainsKey($tid)) { $tableMap[$tid] } else { $tid }
            $mName = $rMeasures["Name"]
            $expr = $rMeasures["Expression"]
            Write-Output "Measure: [$tName].[$mName] = $expr"
        }
        $rMeasures.Close()
        Write-Output "Total measures found: $measureCount"

        Write-Output "`n=== PARTITIONS / M EXPRESSIONS ==="
        $cmdPart = $conn.CreateCommand()
        $cmdPart.CommandText = "SELECT [TableID], [Name], [QueryDefinition] FROM `$SYSTEM.TMSCHEMA_PARTITIONS"
        $rPart = $cmdPart.ExecuteReader()
        while ($rPart.Read()) {
            $tid = $rPart["TableID"]
            $tName = if ($tableMap.ContainsKey($tid)) { $tableMap[$tid] } else { $tid }
            $pName = $rPart["Name"]
            $qDef = $rPart["QueryDefinition"]
            Write-Output "Partition: [$tName] ($pName)"
            Write-Output "$qDef"
            Write-Output "----------------------------------------"
        }
        $rPart.Close()
    }
} catch {
    Write-Error $_
} finally {
    if ($conn) { $conn.Close() }
}
