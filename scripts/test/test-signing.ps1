<#
  Kiểm thử nghiệm thu Ngày 10 — chữ ký điện tử nội bộ.

  Hai tiêu chí của kế hoạch:

    1. "Người dùng không thể ký thay tài khoản khác."
    2. "Thay đổi file sau khi ký làm hash không còn khớp."

  Tiêu chí thứ hai được kiểm bằng cách *thật sự sửa* file đã ký trên đĩa rồi
  gọi endpoint kiểm chứng. Một cơ chế băm chỉ có giá trị nếu có ai đó từng thử
  phá nó và thấy nó kêu.

    pwsh scripts/test/test-signing.ps1
#>

$ErrorActionPreference = 'Stop'
$Api = $env:API_URL; if (-not $Api) { $Api = 'http://localhost:4000/api' }
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$script:Pass = 0
$script:Fail = 0
$script:Failures = @()

function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
  if ($Ok) { Write-Host "  PASS  $Name" -ForegroundColor Green; $script:Pass++ }
  else {
    Write-Host "  FAIL  $Name  $Detail" -ForegroundColor Red
    $script:Fail++; $script:Failures += "$Name — $Detail"
  }
}

function Login([string]$Email, [string]$Password) {
  $session = $null
  Invoke-RestMethod -Uri "$Api/auth/login" -Method Post -SessionVariable session `
    -Body (@{ email = $Email; password = $Password } | ConvertTo-Json) `
    -ContentType 'application/json' | Out-Null
  return $session
}

function Api($S, [string]$Method, [string]$Path, $Body = $null) {
  $a = @{ Uri = "$Api$Path"; Method = $Method; WebSession = $S }
  if ($null -ne $Body) { $a.Body = ($Body | ConvertTo-Json -Depth 6); $a.ContentType = 'application/json' }
  return Invoke-RestMethod @a
}

# Ảnh PNG 1x1 hợp lệ, đủ để đóng vai nét chữ ký trong kiểm thử.
$PngBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

function UploadSignature($S, [byte[]]$Bytes, [string]$FileName = 'chu-ky.png') {
  $tmp = Join-Path $env:TEMP $FileName
  [System.IO.File]::WriteAllBytes($tmp, $Bytes)
  try {
    $form = @{ file = Get-Item $tmp }
    return Invoke-RestMethod -Uri "$Api/signatures" -Method Post -WebSession $S -Form $form
  } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

Write-Host "`n=== 0. Đăng nhập ===" -ForegroundColor Cyan
$anh = Login 'sv.nguyenducanh@hvktcnan.edu.vn' 'Demo@2026'
$mai = Login 'sv.tranthimai@hvktcnan.edu.vn' 'Demo@2026'
Check 'Hai học viên đăng nhập được' (($null -ne $anh) -and ($null -ne $mai))

# ------------------------------------------------------------ 1. chữ ký mẫu
Write-Host "`n=== 1. Đăng ký chữ ký ===" -ForegroundColor Cyan
$png = [Convert]::FromBase64String($PngBase64)
$sig = UploadSignature $anh $png
Check 'Đăng ký được chữ ký' ($null -ne $sig.id)
Check 'Có mã băm của ảnh chữ ký' ($sig.fileHash -match '^[0-9a-f]{64}$') $sig.fileHash
Check 'KHÔNG trả đường dẫn file ra API' ($null -eq $sig.filePath) `
  "trả về: $($sig | ConvertTo-Json -Compress)"

# Đổi tên .exe thành .png không qua được: nội dung mới quyết định, không phải đuôi.
$fake = [System.Text.Encoding]::ASCII.GetBytes('MZ this is not a png at all')
$rejected = $false
try { UploadSignature $anh $fake 'chu-ky-gia.png' | Out-Null } catch { $rejected = $true }
Check 'File không phải PNG bị từ chối dù đuôi là .png' $rejected

$mine = Api $anh GET '/signatures/me'
Check 'Đọc lại được chữ ký đang dùng' ($mine.id -eq $sig.id)

# ------------------------------------------------------------------ 2. đơn
Write-Host "`n=== 2. Lập đơn để ký ===" -ForegroundColor Cyan
$don = Api $anh POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{
    leaveFrom = '2026-09-07'; leaveTo = '2026-09-08'
    reason    = 'Em về quê chịu tang bà nội, có xác nhận của địa phương.'
  }
}
Check 'Tạo được đơn' ($null -ne $don.id)
Check 'Đơn mới còn sửa được' ($don.editable -eq $true)
$id = $don.id

# ------------------------------------------------- 3. TIÊU CHÍ: không ký thay
Write-Host "`n=== 3. Không ký thay tài khoản khác ===" -ForegroundColor Cyan
$status = 0
try { Api $mai POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null }
catch { $status = $_.Exception.Response.StatusCode.value__ }
Check 'Học viên B ký đơn của A bị chặn' ($status -eq 404) "HTTP $status"

$msg = ''
try { Api $anh POST "/submissions/$id/sign" @{ pin = '000000' } | Out-Null }
catch { $msg = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'PIN sai bị từ chối' ($msg -match 'PIN') $msg

$still = Api $anh GET "/submissions/$id"
Check 'PIN sai KHÔNG để lại chữ ký nào' ($null -eq $still.signedHash)

# ------------------------------------------------------------------- 4. ký
Write-Host "`n=== 4. Ký bằng mã PIN đúng ===" -ForegroundColor Cyan
$signed = Api $anh POST "/submissions/$id/sign" @{ pin = '135790' }
Check 'Ký thành công' ($signed.signedHash -match '^[0-9a-f]{64}$') $signed.signedHash
Check 'Đơn đã ký thì khóa nội dung' ($signed.editable -eq $false)

$blocked = ''
try { Api $anh PATCH "/submissions/$id" @{ formData = @{ reason = 'sửa sau khi ký' } } | Out-Null }
catch { $blocked = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Sửa nội dung sau khi ký bị chặn' ($blocked -match 'đã ký') $blocked

$dup = ''
try { Api $anh POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null }
catch { $dup = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Không ký lại lần hai' ($dup -match 'đã được ký') $dup

# ------------------------------------------------- 5. bằng chứng của chữ ký
Write-Host "`n=== 5. Bằng chứng lưu lại ===" -ForegroundColor Cyan
$v = Api $anh GET "/submissions/$id/verify"
Check 'Kiểm chứng báo đã ký' ($v.signed -eq $true)
Check 'Mã băm khớp ngay sau khi ký' ($v.matches -eq $true) $v.message
Check 'Có đúng một lần ký được ghi' ($v.signings.Count -eq 1) "$($v.signings.Count)"
$sg = $v.signings[0]
Check 'Ghi lại hash TRƯỚC khi ký' ($sg.hashBefore -match '^[0-9a-f]{64}$')
Check 'Ghi lại hash SAU khi ký' ($sg.hashAfter -match '^[0-9a-f]{64}$')
Check 'Hash trước và sau khác nhau (chữ ký đã thực sự vào file)' `
  ($sg.hashBefore -ne $sg.hashAfter)
Check 'Ghi lại địa chỉ IP' ($null -ne $sg.ipAddress) "$($sg.ipAddress)"
Check 'Ghi lại dấu vết phiên' ($null -ne $sg.sessionId) "$($sg.sessionId)"

# File đã ký phải chứa ảnh — DOCX nhúng ảnh dưới dạng entry trong ZIP.
$out = Join-Path $env:TEMP "$($signed.code)-signed.docx"
Invoke-WebRequest -Uri "$Api/submissions/$id/file" -WebSession $anh -OutFile $out | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($out)
$hasImage = @($zip.Entries | Where-Object { $_.FullName -like 'word/media/*' }).Count -gt 0
$zip.Dispose()
Check 'File tải về có nhúng ảnh chữ ký' $hasImage
Remove-Item $out -ErrorAction SilentlyContinue

# -------------------------------- 6. TIÊU CHÍ: sửa file thì hash không khớp
Write-Host "`n=== 6. Sửa file sau khi ký thì hash không còn khớp ===" -ForegroundColor Cyan
$onDisk = Join-Path $RepoRoot "storage/generated-forms/$($signed.code)-signed.docx"
Check 'Tìm thấy file đã ký trên đĩa' (Test-Path $onDisk) $onDisk

$backup = [System.IO.File]::ReadAllBytes($onDisk)
try {
  # Sửa đúng một byte — đủ để chứng minh cơ chế nhạy tới mức nào.
  $tampered = $backup.Clone()
  $tampered[$tampered.Length - 1] = $tampered[$tampered.Length - 1] -bxor 0xFF
  [System.IO.File]::WriteAllBytes($onDisk, $tampered)

  $v2 = Api $anh GET "/submissions/$id/verify"
  Check 'Đổi MỘT byte đã làm hash không khớp' ($v2.matches -eq $false) $v2.message
  Check 'Nói rõ file đã bị thay đổi' ($v2.message -match 'KHÔNG khớp') $v2.message
  Check 'Vẫn giữ hash gốc để đối chiếu' ($v2.expectedHash -eq $signed.signedHash)
} finally {
  [System.IO.File]::WriteAllBytes($onDisk, $backup)
}

$v3 = Api $anh GET "/submissions/$id/verify"
Check 'Khôi phục file thì hash khớp trở lại' ($v3.matches -eq $true) $v3.message

# ---------------------------------------------------------- 7. gửi trình ký
Write-Host "`n=== 7. Gửi trình ký ===" -ForegroundColor Cyan
$sent = Api $anh POST "/submissions/$id/submit"
Check 'Gửi được đơn đã ký' ($sent.status -eq 'SUBMITTED') $sent.status
Check 'Đơn dừng ở bước duyệt đầu tiên' ($sent.currentStepOrder -eq 1) "$($sent.currentStepOrder)"

$again = ''
try { Api $anh POST "/submissions/$id/submit" | Out-Null }
catch { $again = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Không gửi lại lần hai' ($again -match 'không gửi lại được') $again

# Đơn chưa ký thì không gửi được.
$chuaKy = Api $anh POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{ leaveFrom = '2026-09-14'; leaveTo = '2026-09-14'; reason = 'Khám sức khỏe định kỳ.' }
}
$noSign = ''
try { Api $anh POST "/submissions/$($chuaKy.id)/submit" | Out-Null }
catch { $noSign = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Đơn chưa ký thì không gửi trình ký được' ($noSign -match 'ký đơn trước') $noSign

Write-Host ("`n" + ('-' * 62))
Write-Host "  PASS: $script:Pass    FAIL: $script:Fail"
if ($script:Failures.Count) {
  Write-Host "`n  Các mục không đạt:"
  $script:Failures | ForEach-Object { Write-Host "    · $_" }
}
Write-Host ('-' * 62) "`n"
exit ($(if ($script:Fail) { 1 } else { 0 }))
