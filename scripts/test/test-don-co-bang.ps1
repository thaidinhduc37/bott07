<#
  Nghiệm thu Đơn xin học, thi cải thiện — biểu mẫu duy nhất có bảng lặp dòng.

  Tiêu chí §5.6 của
  docs/superpowers/specs/2026-08-12-mo-sau-bieu-mau-design.md:

    6. đơn học cải thiện nhập được nhiều dòng học phần và in ra đúng bảng

  Bảng là chỗ duy nhất trong hệ thống mà một trường mang NHIỀU giá trị, nên nó
  đi qua ba tầng chưa từng phải xử lý chuyện đó: kiểm tra dữ liệu, lưu JSONB, và
  renderer. Bộ này kiểm cả ba, cộng hai chỗ dễ hỏng nhất:

    * khóa lạ trong một dòng phải bị VỨT ĐI, đúng như các trường khác;
    * trần số dòng phải chặn thật, không thì một request nhồi 10.000 dòng đi
      thẳng vào CSDL rồi vào renderer.

    pwsh scripts/test/test-don-co-bang.ps1
#>

$ErrorActionPreference = 'Stop'
$Api = $env:API_URL; if (-not $Api) { $Api = 'http://localhost:4000/api' }

$script:Pass = 0; $script:Fail = 0; $script:Failures = @()

function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
  if ($Ok) { Write-Host "  PASS  $Name" -ForegroundColor Green; $script:Pass++ }
  else { Write-Host "  FAIL  $Name  $Detail" -ForegroundColor Red; $script:Fail++; $script:Failures += "$Name — $Detail" }
}

function Login([string]$Email) {
  $s = $null
  Invoke-RestMethod -Uri "$Api/auth/login" -Method Post -SessionVariable s `
    -Body (@{ email = $Email; password = 'Demo@2026' } | ConvertTo-Json) `
    -ContentType 'application/json' | Out-Null
  return $s
}

function Api($S, [string]$M, [string]$P, $B = $null) {
  $a = @{ Uri = "$Api$P"; Method = $M; WebSession = $S }
  if ($null -ne $B) { $a.Body = ($B | ConvertTo-Json -Depth 8); $a.ContentType = 'application/json' }
  return Invoke-RestMethod @a
}

function ErrOf($ScriptBlock) {
  try { & $ScriptBlock | Out-Null; return @{ status = 200; message = '' } }
  catch {
    $st = 0; $msg = ''
    try { $st = $_.Exception.Response.StatusCode.value__ } catch {}
    try {
      $b = $_.ErrorDetails.Message | ConvertFrom-Json
      $msg = if ($b.message -is [string]) { $b.message } else { $b.message.message }
    } catch {}
    return @{ status = $st; message = $msg }
  }
}

$Png = [Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
function EnsureSignature($S) {
  $tmp = Join-Path $env:TEMP "ck-$([guid]::NewGuid()).png"
  [System.IO.File]::WriteAllBytes($tmp, $Png)
  try { Invoke-RestMethod -Uri "$Api/signatures" -Method Post -WebSession $S -Form @{ file = Get-Item $tmp } | Out-Null }
  finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

function DocxText([byte[]]$Bytes) {
  Add-Type -AssemblyName System.IO.Compression | Out-Null
  $ms = New-Object System.IO.MemoryStream(, $Bytes)
  $zip = New-Object System.IO.Compression.ZipArchive($ms, [System.IO.Compression.ZipArchiveMode]::Read)
  try {
    $entry = $zip.GetEntry('word/document.xml')
    if (-not $entry) { return '' }
    $sr = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
    try { $xml = $sr.ReadToEnd() } finally { $sr.Dispose() }
    return ($xml -replace '<[^>]+>', '')
  } finally { $zip.Dispose(); $ms.Dispose() }
}

Write-Host "`n=== 0. Các bên ===" -ForegroundColor Cyan
$sv   = Login 'sv.nguyenducanh@hvktcnan.edu.vn'
$qlhv = Login 'qlhv@hvktcnan.edu.vn'
$qldt = Login 'qldt@hvktcnan.edu.vn'
EnsureSignature $sv; EnsureSignature $qlhv; EnsureSignature $qldt
Check 'Ba bên đăng nhập và có chữ ký' (($sv -and $qlhv -and $qldt) -as [bool])

Write-Host "`n=== 1. Biểu mẫu khai trường dạng bảng ===" -ForegroundColor Cyan
$tpl = Api $sv GET '/form-templates/DON_HOC_CAI_THIEN'
$bang = @($tpl.fields | Where-Object { $_.type -eq 'table' })[0]
Check 'Có đúng một trường dạng bảng' (@($tpl.fields | Where-Object { $_.type -eq 'table' }).Count -eq 1)
Check 'Trường bảng khai đủ ba cột' (@($bang.columns).Count -eq 3) "$(@($bang.columns).Count) cột"
Check 'Trường bảng có trần số dòng' ($bang.maxRows -ge 1) "$($bang.maxRows)"

Write-Host "`n=== 2. Lập đơn với ba dòng học phần ===" -ForegroundColor Cyan
$don = Api $sv POST '/submissions' @{
  templateCode = 'DON_HOC_CAI_THIEN'
  formData     = @{
    hocKy = '2'; namHoc = '2025-2026'; soHocPhanDaThi = '5'; soHocPhanChuaDat = '3'
    hocPhanList = @(
      @{ tenHocPhan = 'Cơ sở dữ liệu'; soTinChi = '3'; diemDaDat = '5.0' },
      @{ tenHocPhan = 'Mạng máy tính'; soTinChi = '2'; diemDaDat = '4.5' },
      @{ tenHocPhan = 'An toàn hệ điều hành'; soTinChi = '3'; diemDaDat = '5.5' }
    )
  }
}
$id = $don.id
Check 'Lập được đơn có bảng' ($null -ne $id)
Check 'Lưu đủ ba dòng' (@($don.formData.hocPhanList).Count -eq 3) "$(@($don.formData.hocPhanList).Count) dòng"
Check 'Dòng thứ ba giữ nguyên dữ liệu' `
  ($don.formData.hocPhanList[2].tenHocPhan -eq 'An toàn hệ điều hành') `
  "$($don.formData.hocPhanList[2].tenHocPhan)"

Write-Host "`n=== 3. Dòng trống bị bỏ, khóa lạ bị vứt ===" -ForegroundColor Cyan
$don2 = Api $sv POST '/submissions' @{
  templateCode = 'DON_HOC_CAI_THIEN'
  formData     = @{
    hocKy = '1'; namHoc = '2025-2026'; soHocPhanDaThi = '4'; soHocPhanChuaDat = '1'
    hocPhanList = @(
      @{ tenHocPhan = 'Trí tuệ nhân tạo'; soTinChi = '3'; diemDaDat = '5.0'; ghiChuLa = 'nen bi vut' },
      @{ tenHocPhan = ''; soTinChi = ''; diemDaDat = '' }
    )
  }
}
Check 'Dòng trống hoàn toàn bị bỏ' (@($don2.formData.hocPhanList).Count -eq 1) `
  "$(@($don2.formData.hocPhanList).Count) dòng"
Check 'Khóa không khai trong cột bị vứt đi' `
  ($null -eq $don2.formData.hocPhanList[0].ghiChuLa) `
  "$($don2.formData.hocPhanList[0].ghiChuLa)"

Write-Host "`n=== 4. Trần số dòng chặn thật ===" -ForegroundColor Cyan
$nhieu = 1..50 | ForEach-Object { @{ tenHocPhan = "Hoc phan $_"; soTinChi = '3'; diemDaDat = '5.0' } }
$e = ErrOf { Api $sv POST '/submissions' @{ templateCode = 'DON_HOC_CAI_THIEN'
  formData = @{ hocKy = '1'; namHoc = '2025-2026'; soHocPhanDaThi = '4'; soHocPhanChuaDat = '1'
                hocPhanList = $nhieu } } }
Check '50 dòng bị từ chối' ($e.status -eq 400) "HTTP $($e.status)"
Check '  và nói rõ trần bao nhiêu dòng' ($e.message -match 'tối đa') $e.message

$e = ErrOf { Api $sv POST '/submissions' @{ templateCode = 'DON_HOC_CAI_THIEN'
  formData = @{ hocKy = '1'; namHoc = '2025-2026'; soHocPhanDaThi = '4'; soHocPhanChuaDat = '1'
                hocPhanList = @() } } }
Check 'Bảng rỗng bị từ chối vì trường bắt buộc' ($e.status -eq 400) "HTTP $($e.status) $($e.message)"

Write-Host "`n=== 5. Duyệt hai cấp rồi đọc bản in ===" -ForegroundColor Cyan
Api $sv POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null
Api $sv POST "/submissions/$id/submit" | Out-Null
Api $qlhv POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' } | Out-Null
Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
$r = Api $qldt POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
Check 'Đơn đi trọn hai cấp' ($r.status -eq 'APPROVED') $r.status

$tmp = Join-Path $env:TEMP "don-bang-$id.docx"
Invoke-WebRequest -Uri "$Api/approvals/$id/file" -WebSession $qldt -OutFile $tmp | Out-Null
$bytes = [System.IO.File]::ReadAllBytes($tmp)
Remove-Item $tmp -ErrorAction SilentlyContinue
$text = DocxText $bytes

Check 'Tải được DOCX' ($bytes.Length -gt 5000) "$($bytes.Length) byte"
Check 'Bản in có đúng tiêu đề bản gốc' ($text.Contains('ĐƠN XIN HỌC, THI CẢI THIỆN'))
Check 'Khối định danh dùng nhãn "Họ và tên"' ($text.Contains('Họ và tên:'))
Check '  và KHÔNG dùng nhãn của đơn nghỉ học 01-03 ngày' (-not $text.Contains('Tên em là'))
foreach ($c in @('STT', 'Tên học phần', 'Số tín chỉ', 'Điểm học phần đã đạt được')) {
  Check "Đầu bảng có cột '$c'" ($text.Contains($c))
}
foreach ($hp in @('Cơ sở dữ liệu', 'Mạng máy tính', 'An toàn hệ điều hành')) {
  Check "Bản in có học phần '$hp'" ($text.Contains($hp))
}
Check 'Bản in có điểm của dòng thứ hai' ($text.Contains('4.5'))
Check 'Bản in có lời cam đoan của bản gốc' `
  ($text.Contains('nộp đầy đủ kinh phí học, thi cải thiện theo quy định'))
$soO = ([regex]::Matches($text, [regex]::Escape('(Ký và ghi rõ họ tên)'))).Count
Check 'Có đúng ba ô ký' ($soO -eq 3) "$soO ô"

Write-Host "`n=== 6. Bảy biểu mẫu đều đã mở ===" -ForegroundColor Cyan
$ds = Api $sv GET '/form-templates'
$dong = @($ds.items | Where-Object { $_.isActive })
Check 'Cả bảy biểu mẫu đang nhận đơn' ($dong.Count -eq 7) "$($dong.Count)/7"

Write-Host "`n--------------------------------------------------------------"
if ($script:Fail -eq 0) {
  Write-Host "  PASS: $($script:Pass)    FAIL: 0" -ForegroundColor Green
} else {
  Write-Host "  PASS: $($script:Pass)    FAIL: $($script:Fail)" -ForegroundColor Red
  $script:Failures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
Write-Host "--------------------------------------------------------------`n"
if ($script:Fail -gt 0) { exit 1 }
