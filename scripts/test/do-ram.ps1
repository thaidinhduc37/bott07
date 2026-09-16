<#
  Đo mức chiếm dụng bộ nhớ thật của toàn hệ thống (Ngày 13).

  Kế hoạch đặt ràng buộc phần cứng: một máy 16 GB RAM, không GPU. Con số duy
  nhất có ý nghĩa với ràng buộc đó là **tổng của tất cả các tiến trình**, không
  phải RSS của riêng tiến trình Node.js — hai mô hình nặng (BGE-M3 và
  cross-encoder int8) nằm trong tiến trình Python của dịch vụ RAG, còn PostgreSQL
  và Qdrant nằm trong container Docker.

  Script chỉ đọc, không thay đổi gì.

    pwsh scripts/test/do-ram.ps1
    pwsh scripts/test/do-ram.ps1 -Truoc      # đo trước khi nạp mô hình
#>

param(
  [switch]$Truoc
)

$ErrorActionPreference = 'SilentlyContinue'

function MB([double]$bytes) { [math]::Round($bytes / 1MB, 0) }

Write-Host "`n=== Bộ nhớ theo tiến trình ===" -ForegroundColor Cyan

# --- tiến trình trên máy chủ (ngoài Docker) ---
$rows = @()

foreach ($p in Get-Process -Name node -ErrorAction SilentlyContinue) {
  $rows += [pscustomobject]@{ ThanhPhan = 'API (Node.js)'; PID = $p.Id; RamMB = MB $p.WorkingSet64 }
}
foreach ($p in Get-Process -Name python, pythonw -ErrorAction SilentlyContinue) {
  # Chỉ tính tiến trình Python của rag-service, không tính python khác trên máy.
  $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($p.Id)").CommandLine
  if ($cmd -match 'uvicorn|rag-service') {
    $rows += [pscustomobject]@{ ThanhPhan = 'Dịch vụ RAG (Python)'; PID = $p.Id; RamMB = MB $p.WorkingSet64 }
  }
}

# --- container Docker ---
$dockerOk = $false
try {
  $stats = docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}' 2>$null
  if ($LASTEXITCODE -eq 0 -and $stats) {
    $dockerOk = $true
    foreach ($line in $stats) {
      $parts = $line -split '\|'
      if ($parts.Count -lt 2) { continue }
      # "412.3MiB / 1.5GiB" → lấy vế trái
      $used = ($parts[1] -split '/')[0].Trim()
      $mb = switch -Regex ($used) {
        '([\d.]+)GiB' { [double]$Matches[1] * 1024; break }
        '([\d.]+)MiB' { [double]$Matches[1]; break }
        '([\d.]+)KiB' { [double]$Matches[1] / 1024; break }
        default { 0 }
      }
      $rows += [pscustomobject]@{
        ThanhPhan = "Docker: $($parts[0])"
        PID       = '—'
        RamMB     = [math]::Round($mb, 0)
      }
    }
  }
} catch { }

if (-not $dockerOk) {
  Write-Host "  (không đọc được docker stats — số liệu dưới đây thiếu PostgreSQL và Qdrant)" -ForegroundColor Yellow
}

if ($rows.Count -eq 0) {
  Write-Host "  Không tìm thấy tiến trình nào. Hệ thống chưa chạy?" -ForegroundColor Yellow
  exit 1
}

$rows | Sort-Object RamMB -Descending | Format-Table -AutoSize

$total = ($rows | Measure-Object -Property RamMB -Sum).Sum

# --- bộ nhớ toàn máy ---
$os = Get-CimInstance Win32_OperatingSystem
$totalMachine = MB ($os.TotalVisibleMemorySize * 1KB)
$freeMachine = MB ($os.FreePhysicalMemory * 1KB)

Write-Host "=== Tổng kết ===" -ForegroundColor Cyan
Write-Host ("  Tổng các thành phần của hệ thống : {0,6} MB" -f $total)
Write-Host ("  RAM toàn máy                     : {0,6} MB" -f $totalMachine)
Write-Host ("  RAM còn trống                    : {0,6} MB" -f $freeMachine)
Write-Host ("  Tỉ lệ hệ thống chiếm              : {0,5:N1} %" -f ($total / $totalMachine * 100))

Write-Host ""
if ($Truoc) {
  Write-Host "  Đây là số đo TRƯỚC khi nạp mô hình. Chạy một truy vấn rồi đo lại:" -ForegroundColor DarkGray
  Write-Host "  encoder và cross-encoder chỉ được nạp ở lần dùng đầu tiên." -ForegroundColor DarkGray
} else {
  $budget = 16384
  $margin = $budget - $total
  Write-Host ("  Ràng buộc của kế hoạch là máy 16 GB. Còn dư {0} MB cho hệ điều hành," -f $margin)
  Write-Host "  trình duyệt và mọi thứ khác." -ForegroundColor DarkGray
  if ($total -gt $budget * 0.75) {
    Write-Host "  CẢNH BÁO: đã dùng quá 75% ngân sách 16 GB." -ForegroundColor Red
  }
}
Write-Host ""
