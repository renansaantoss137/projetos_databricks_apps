$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    $filePath = 'C:\Users\renan.ferreira\Downloads\Lista de fornecedores sem OC.xlsx'
    $wb = $excel.Workbooks.Open($filePath)
    Write-Output "Sheets count: $($wb.Sheets.Count)"
    foreach ($sh in $wb.Sheets) {
        Write-Output "Sheet: $($sh.Name)"
        $used = $sh.UsedRange
        Write-Output "Rows: $($used.Rows.Count) Cols: $($used.Columns.Count)"
        for ($r = 1; $r -le [Math]::Min(15, $used.Rows.Count); $r++) {
            $rowVals = @()
            for ($c = 1; $c -le [Math]::Min(15, $used.Columns.Count); $c++) {
                $rowVals += [string]$sh.Cells.Item($r, $c).Text
            }
            $line = $rowVals -join ' | '
            Write-Output "Row ${r}: $line"
        }
    }
    $wb.Close($false)
} catch {
    Write-Error $_
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
