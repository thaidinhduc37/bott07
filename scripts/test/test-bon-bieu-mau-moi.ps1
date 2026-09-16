<#
  Nghiệm thu bốn biểu mẫu hai cấp mới mở.

  Tiêu chí §5 của docs/superpowers/specs/2026-08-12-mo-sau-bieu-mau-design.md:

    2. mỗi chỗ trống trong bản gốc đều ứng với một trường trong `field_schema`
    3. mỗi đơn dựng ra DOCX đúng số ô ký
    7. giao diện không còn đơn nào "bấm vào rồi gặp trang lỗi"

  Tiêu chí 7 mới là tiêu chí thật, và nó không kiểm được bằng cách đọc mã. Đơn
  được bật trong CSDL nhưng thiếu đặc tả in thì mọi thứ vẫn xanh cho tới lúc
  người dùng bấm "Tải file" — nên bộ này đi trọn đường: lập đơn, ký, gửi, duyệt
  hai cấp, tải DOCX về và ĐỌC nội dung bên trong.

  Chạy lại được nhiều lần: mỗi lần chạy tạo đơn mới, không sửa đơn cũ.

    pwsh scripts/test/test-bon-bieu-mau-moi.ps1
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
  if ($null -ne $B) { $a.Body = ($B | ConvertTo-Json -Depth 6); $a.ContentType = 'application/json' }
  return Invoke-RestMethod @a
}

$Png = [Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
function EnsureSignature($S) {
  $tmp = Join-Path $env:TEMP "ck-$([guid]::NewGuid()).png"
  [System.IO.File]::WriteAllBytes($tmp, $Png)
  try { Invoke-RestMethod -Uri "$Api/signatures" -Method Post -WebSession $S -Form @{ file = Get-Item $tmp } | Out-Null }
  finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

<#
  Đọc text thô trong một .docx đã tải về.

  Dùng System.IO.Compression thay vì thư viện ngoài: .docx là một file zip, và
  `word/document.xml` là XML UTF-8. Bỏ hết thẻ đi thì còn lại đúng phần chữ.
#>
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
Check 'Học viên, QLHV và QLĐT đăng nhập được' (($sv -and $qlhv -and $qldt) -as [bool])
EnsureSignature $sv; EnsureSignature $qlhv; EnsureSignature $qldt

# ------------------------------------------------------ 1. đơn nào đang mở
Write-Host "`n=== 1. Danh sách biểu mẫu đang mở ===" -ForegroundColor Cyan
$mau = Api $sv GET '/form-templates'
$dsMa = @($mau.items | ForEach-Object { $_.code })
foreach ($ma in @('DON_XIN_NGHI_HOC_TREN_3', 'DON_XIN_HOAN_THI', 'DON_BO_SUNG_LI_DO_HOAN_THI', 'DON_XIN_HOC_LAI')) {
  Check "Học viên thấy $ma trong danh sách" ($dsMa -contains $ma) ($dsMa -join ',')
}
$bs = @($mau.items | Where-Object { $_.code -eq 'DON_BO_SUNG_LI_DO_HOAN_THI' })[0]
Check 'Đơn thi bổ sung mang tên theo bản gốc' ($bs.name -eq 'Đơn xin thi bổ sung') "$($bs.name)"

# ------------------------------------------------ 2. đi trọn đường từng đơn
$CAC_DON = @(
  @{
    ma    = 'DON_XIN_NGHI_HOC_TREN_3'
    ten   = 'nghỉ học trên 03 ngày'
    data  = @{ leaveFrom = '2026-11-02'; leaveTo = '2026-11-20'; reason = 'Em phải điều trị dài ngày.' }
    phai  = @('ĐƠN XIN NGHỈ HỌC', '- Ban Giám đốc;', '02/11/2026', '20/11/2026', 'Em phải điều trị dài ngày.')
    cam   = @('BAN GIÁM ĐỐC')
  },
  @{
    ma    = 'DON_XIN_HOAN_THI'
    ten   = 'hoãn thi kết thúc học phần'
    data  = @{ hocKy = '2'; namHoc = '2025-2026'; ngayThi = '2026-11-25'; hocPhan = 'Cơ sở dữ liệu'
               lyDo = 'Em phải nhập viện.' }
    phai  = @('ĐƠN XIN HOÃN THI KẾT THÚC HỌC PHẦN', 'Cơ sở dữ liệu', '25/11/2026', 'Em phải nhập viện.')
    cam   = @('Khóa:', 'Hệ đào tạo:')
  },
  @{
    ma    = 'DON_BO_SUNG_LI_DO_HOAN_THI'
    ten   = 'thi bổ sung'
    data  = @{ hocPhan = 'Cơ sở dữ liệu'; ngayThi = '2026-11-25' }
    phai  = @('ĐƠN XIN THI BỔ SUNG', 'Cơ sở dữ liệu', '25/11/2026', 'Nay em đã bố trí được thời gian thi')
    cam   = @()
  },
  @{
    ma    = 'DON_XIN_HOC_LAI'
    ten   = 'học lại'
    data  = @{ lanThuMayXinHoc = '1'; hocPhan = 'Cơ sở dữ liệu'; lanThi = '2'; lanHoc = '1'; diemThi = '4.0' }
    phai  = @('ĐƠN XIN HỌC LẠI', 'Lần thứ:', 'Cơ sở dữ liệu', '4.0', 'nộp đầy đủ kinh phí học lại theo quy định')
    cam   = @()
  }
)

foreach ($don in $CAC_DON) {
  Write-Host "`n=== 2.$($CAC_DON.IndexOf($don) + 1) Đơn $($don.ten) ===" -ForegroundColor Cyan

  $d = Api $sv POST '/submissions' @{ templateCode = $don.ma; formData = $don.data }
  $id = $d.id
  Check "[$($don.ten)] lập được đơn" ($null -ne $id) "$($d | ConvertTo-Json -Compress)"

  Api $sv POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null
  $g = Api $sv POST "/submissions/$id/submit"
  Check "[$($don.ten)] gửi trình ký được" ($g.status -eq 'SUBMITTED') $g.status
  Check "[$($don.ten)] dừng ở cấp 1" ($g.currentStepOrder -eq 1) "$($g.currentStepOrder)"

  Api $qlhv POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
  $r = Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
  Check "[$($don.ten)] cấp 1 duyệt xong chuyển sang cấp 2" ($r.currentStepOrder -eq 2) "$($r.currentStepOrder)"

  Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
  $r = Api $qldt POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
  Check "[$($don.ten)] cấp 2 duyệt xong đơn thành Đã duyệt" ($r.status -eq 'APPROVED') $r.status

  # Đây là bước không thể bỏ: đơn được bật nhưng thiếu đặc tả in thì mọi thứ
  # phía trên vẫn xanh, và chỉ chỗ này mới lộ ra.
  $tmp = Join-Path $env:TEMP "don-$id.docx"
  Invoke-WebRequest -Uri "$Api/approvals/$id/file" -WebSession $qldt -OutFile $tmp | Out-Null
  $bytes = [System.IO.File]::ReadAllBytes($tmp)
  Remove-Item $tmp -ErrorAction SilentlyContinue
  Check "[$($don.ten)] tải được DOCX" ($bytes.Length -gt 5000) "$($bytes.Length) byte"

  $text = DocxText $bytes
  foreach ($p in $don.phai) {
    Check "[$($don.ten)] bản in có '$p'" ($text.Contains($p)) 'không tìm thấy'
  }
  foreach ($c in $don.cam) {
    Check "[$($don.ten)] bản in KHÔNG có '$c'" (-not $text.Contains($c)) 'lại có mặt'
  }

  # Hai ô cán bộ + một ô học viên. Bản gốc của cả bốn đơn đều hai cấp ký.
  $soO = ([regex]::Matches($text, [regex]::Escape('(Ký và ghi rõ họ tên)'))).Count
  Check "[$($don.ten)] có đúng ba ô ký" ($soO -eq 3) "$soO ô"
  Check "[$($don.ten)] có ô HỌC VIÊN VIẾT ĐƠN" ($text.Contains('HỌC VIÊN VIẾT ĐƠN'))
}

# ------------------------------- 3. hai đơn nghỉ học không chồng lấn nhau
#
# Trần "01–03 ngày" trước đây bám vào sự có mặt của leaveFrom/leaveTo chứ không
# bám vào mã đơn, nên khi mở đơn nghỉ trên 03 ngày thì MỌI đơn hợp lệ của nó đều
# bị chặn. Hai phép kiểm dưới đây khóa cả hai chiều lại.
Write-Host "`n=== 3. Hai đơn nghỉ học không chồng lấn ===" -ForegroundColor Cyan

function ErrOf($ScriptBlock) {
  try { & $ScriptBlock | Out-Null; return @{ status = 200; message = '' } }
  catch {
    $st = 0; $msg = ''
    try { $st = $_.Exception.Response.StatusCode.value__ } catch {}
    try { $msg = ($_.ErrorDetails.Message | ConvertFrom-Json).message } catch {}
    return @{ status = $st; message = $msg }
  }
}

$e = ErrOf { Api $sv POST '/submissions' @{ templateCode = 'DON_XIN_NGHI_HOC'
  formData = @{ leaveFrom = '2026-12-01'; leaveTo = '2026-12-19'; reason = 'x' } } }
Check 'Nghỉ 19 ngày trên biểu mẫu 01-03 ngày bị chặn' ($e.status -eq 400) "HTTP $($e.status)"
Check '  và nói rõ phải dùng biểu mẫu riêng' ($e.message -match 'trên 03 ngày') $e.message

$e = ErrOf { Api $sv POST '/submissions' @{ templateCode = 'DON_XIN_NGHI_HOC_TREN_3'
  formData = @{ leaveFrom = '2026-12-01'; leaveTo = '2026-12-02'; reason = 'x' } } }
Check 'Nghỉ 2 ngày trên biểu mẫu trên-03-ngày bị chặn' ($e.status -eq 400) "HTTP $($e.status)"
Check '  và nói rõ phải dùng biểu mẫu riêng' ($e.message -match '01 đến 03 ngày') $e.message

# -------------------------------------------- 4. hai đơn còn lại nay đã mở
#
# Trước đây mục này khẳng định DON_XIN_HOC_BO_SUNG và DON_HOC_CAI_THIEN vẫn đóng.
# Cả hai đã mở, nên khẳng định đó không còn đúng — và hai đơn ấy có bộ nghiệm thu
# riêng vì mỗi cái cần một thứ bốn đơn ở trên không cần:
#
#   * test-don-ba-cap.ps1  — DON_XIN_HOC_BO_SUNG, luồng ba cấp
#   * test-don-co-bang.ps1 — DON_HOC_CAI_THIEN, bảng lặp dòng
#
# Ở đây chỉ giữ lại phép kiểm rẻ mà vẫn có ích: không còn đơn nào ở trạng thái
# chờ, tức không còn chỗ nào học viên bấm vào rồi phải quay ra.
Write-Host "`n=== 4. Không còn biểu mẫu nào ở trạng thái chờ ===" -ForegroundColor Cyan
$chuaMo = @($mau.items | Where-Object { -not $_.isActive })
Check 'Cả bảy biểu mẫu đều đang nhận đơn' ($chuaMo.Count -eq 0) `
  "còn chờ: $($chuaMo.code -join ', ')"
Check 'Danh sách có đúng bảy biểu mẫu' (@($mau.items).Count -eq 7) "$(@($mau.items).Count)"

Write-Host "`n--------------------------------------------------------------"
if ($script:Fail -eq 0) {
  Write-Host "  PASS: $($script:Pass)    FAIL: 0" -ForegroundColor Green
} else {
  Write-Host "  PASS: $($script:Pass)    FAIL: $($script:Fail)" -ForegroundColor Red
  $script:Failures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
Write-Host "--------------------------------------------------------------`n"
if ($script:Fail -gt 0) { exit 1 }
