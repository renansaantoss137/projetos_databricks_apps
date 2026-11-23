$port = 61181
$connString = "Provider=MSOLAP;Data Source=localhost:$port;"
$conn = New-Object System.Data.OleDb.OleDbConnection($connString)
try {
    $conn.Open()
    Write-Output "Connection Successful!"
    
    # Query databases
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmd)
    $ds = New-Object System.Data.DataSet
    $adapter.Fill($ds) | Out-Null
    $catalogName = $ds.Tables[0].Rows[0]["CATALOG_NAME"]
    Write-Output "Catalog: $catalogName"

    # Set Catalog
    $conn.ChangeDatabase($catalogName)

    # Tables
    $cmdTables = $conn.CreateCommand()
    $cmdTables.CommandText = "SELECT [ID], [Name], [Description] FROM `$SYSTEM.TMSCHEMA_TABLES"
    $dtTables = New-Object System.Data.DataTable
    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmdTables)
    $adapter.Fill($dtTables) | Out-Null
    Write-Output "`n=== TABLES ($($dtTables.Rows.Count)) ==="
    $dtTables | Format-Table -AutoSize | Out-String | Write-Output

    # Measures
    $cmdMeasures = $conn.CreateCommand()
    $cmdMeasures.CommandText = "SELECT [TableID], [Name], [Expression], [Description] FROM `$SYSTEM.TMSCHEMA_MEASURES"
    $dtMeasures = New-Object System.Data.DataTable
    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmdMeasures)
    $adapter.Fill($dtMeasures) | Out-Null
    Write-Output "`n=== MEASURES ($($dtMeasures.Rows.Count)) ==="
    $dtMeasures | Select-Object TableID, Name, Expression | Format-Table -AutoSize | Out-String | Write-Output

    # Partitions / M queries (Data sources)
    $cmdPart = $conn.CreateCommand()
    $cmdPart.CommandText = "SELECT [TableID], [Name], [QueryDefinition] FROM `$SYSTEM.TMSCHEMA_PARTITIONS"
    $dtPart = New-Object System.Data.DataTable
    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmdPart)
    $adapter.Fill($dtPart) | Out-Null
    Write-Output "`n=== PARTITIONS / M QUERIES ($($dtPart.Rows.Count)) ==="
    $dtPart | Select-Object TableID, Name, QueryDefinition | Format-Table -AutoSize | Out-String | Write-Output

    # Relationships
    $cmdRel = $conn.CreateCommand()
    $cmdRel.CommandText = "SELECT [FromTableID], [FromColumnID], [ToTableID], [ToColumnID], [IsActive] FROM `$SYSTEM.TMSCHEMA_RELATIONSHIPS"
    $dtRel = New-Object System.Data.DataTable
    $adapter = New-Object System.Data.OleDb.OleDbDataAdapter($cmdRel)
    $adapter.Fill($dtRel) | Out-Null
    Write-Output "`n=== RELATIONSHIPS ($($dtRel.Rows.Count)) ==="
    $dtRel | Format-Table -AutoSize | Out-String | Write-Output

} catch {
    Write-Error $_
} finally {
    $conn.Close()
}
