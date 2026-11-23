$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    $filePath = 'C:\Users\renan.ferreira\Downloads\Lista de fornecedores sem OC.xlsx'
    $wb = $excel.Workbooks.Open($filePath)
    $sh = $wb.Sheets.Item(1)
    $used = $sh.UsedRange
    $rows = $used.Rows.Count
    $cols = $used.Columns.Count
    Write-Output "Total rows: $rows, cols: $cols"
    
    $outCsv = Join-Path $PSScriptRoot "lista_sem_oc_dump.csv"
    $lines = @()
    for ($r = 1; $r -le $rows; $r++) {
        $c1 = [string]$sh.Cells.Item($r, 1).Text
        $c2 = [string]$sh.Cells.Item($r, 2).Text
        $c1 = ($c1 -replace '[\r\n]+', ' ').Trim()
        $c2 = ($c2 -replace '[\r\n]+', ' ').Trim()
        $lines += "$c1;$c2"
    }
    Set-Content -Path $outCsv -Value $lines -Encoding UTF8
    Write-Output "Saved to $outCsv with $($lines.Count) lines"
    $wb.Close($false)
} catch {
    Write-Error $_
} finally {
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
}
