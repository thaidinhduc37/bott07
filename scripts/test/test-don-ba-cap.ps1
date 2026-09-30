<#
  Nghiệm thu Đơn xin học bổ sung — biểu mẫu ba cấp duy nhất.

  Tiêu chí §5.4 và §5.5 của
  docs/superpowers/specs/2026-08-12-mo-sau-bieu-mau-design.md:

    4. đơn đi trọn ba cấp; bỏ qua một cấp thì bị từ chối
    5. tài khoản DEPARTMENT_HEAD chỉ duyệt được bước của mình

  Tiêu chí 4 mới là tiêu chí thật, và nó chỉ có nghĩa khi được kiểm bằng cách
  *cố tình* cho cấp 3 xử lý lúc đơn còn ở cấp 1. Máy duyệt vốn tổng quát theo
  `approval_flow`, nên bộ này thực chất hỏi: dữ liệu ba cấp có làm máy duyệt
  chạy đúng ba cấp không, hay có chỗ nào trong mã vẫn ngầm giả định hai cấp.

  LƯU Ý VỀ THỨ TỰ KÝ. Lãnh đạo Khoa mang `order` 3 (ký sau cùng) vì bảng chữ ký
  bản gốc xếp LĐ KHOA ngoài cùng trái, mà cột in theo `order` giảm dần. Thứ tự
  này CHƯA được Phòng Đào tạo xác nhận — xem chú thích của HOC_BO_SUNG_FLOW
  trong server/api/prisma/seed.ts.

    pwsh scripts/test/test-don-ba-cap.ps1
#>

$ErrorActionPreference = 'Stop'
$Api = $env:API_URL; if (-not $Api) { $Api = 'http://localhost:5000/api' }

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

Write-Host "`n=== 0. Bốn bên ===" -ForegroundColor Cyan
$sv   = Login 'sv.nguyenducanh@hvktcnan.edu.vn'
$qlhv = Login 'qlhv@hvktcnan.edu.vn'          # APPROVER        — cấp 1
$qldt = Login 'qldt@hvktcnan.edu.vn'          # ACADEMIC_MANAGER — cấp 2
$khoa = Login 'khoa@hvktcnan.edu.vn'          # DEPARTMENT_HEAD  — cấp 3
Check 'Tài khoản Lãnh đạo Khoa đăng nhập được' ($null -ne $khoa)
EnsureSignature $sv; EnsureSignature $qlhv; EnsureSignature $qldt; EnsureSignature $khoa

$me = Api $khoa GET '/auth/me'
Check 'Lãnh đạo Khoa mang đúng vai trò DEPARTMENT_HEAD' `
  (@($me.roles) -contains 'DEPARTMENT_HEAD') "$($me.roles -join ',')"
Check 'và KHÔNG kiêm vai trò của hai cấp kia' `
  (-not (@($me.roles) -contains 'APPROVER') -and -not (@($me.roles) -contains 'ACADEMIC_MANAGER')) `
  "$($me.roles -join ',')"

Write-Host "`n=== 1. Biểu mẫu khai đúng ba cấp ===" -ForegroundColor Cyan
$tpl = Api $sv GET '/form-templates/DON_XIN_HOC_BO_SUNG'
Check 'Luồng duyệt có ba bước' (@($tpl.approvalFlow).Count -eq 3) "$(@($tpl.approvalFlow).Count) bước"
$cap3 = @($tpl.approvalFlow | Where-Object { $_.order -eq 3 })[0]
Check 'Bước 3 thuộc Lãnh đạo Khoa' ($cap3.roleCode -eq 'DEPARTMENT_HEAD') "$($cap3.roleCode)"

Write-Host "`n=== 2. Học viên lập, ký, gửi ===" -ForegroundColor Cyan
$don = Api $sv POST '/submissions' @{
  templateCode = 'DON_XIN_HOC_BO_SUNG'
  formData     = @{
    tenKhoa = 'Khoa An toàn thông tin'; hocPhan = 'Cơ sở dữ liệu'
    soTietQuyDinh = '45'; soTietDaHoc = '30'; soTietNghi = '15'
    lyDo = 'Em bị ốm phải nằm viện dài ngày.'
  }
}
$id = $don.id
Api $sv POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null
$g = Api $sv POST "/submissions/$id/submit"
Check 'Đơn gửi được và dừng ở cấp 1' ($g.status -eq 'SUBMITTED' -and $g.currentStepOrder -eq 1) `
  "$($g.status) / bước $($g.currentStepOrder)"

# ---------------------------- 3. TIÊU CHÍ: không nhảy cóc được cấp nào
Write-Host "`n=== 3. Không nhảy cóc cấp duyệt ===" -ForegroundColor Cyan
# Dùng RECEIVE chứ không phải APPROVE: APPROVE bị chặn ngay ở kiểm tra trạng
# thái, nên nó không chứng minh được gì về kiểm tra vai trò. RECEIVE hợp lệ với
# trạng thái hiện tại, nên thứ duy nhất còn chặn được chính là "bước này không
# phải của bạn".
$e = ErrOf { Api $khoa POST "/approvals/$id/action" @{ action = 'RECEIVE' } }
Check 'Cấp 3 xử lý khi đơn đang ở cấp 1 bị chặn' ($e.status -eq 403) "HTTP $($e.status) $($e.message)"
$e = ErrOf { Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } }
Check 'Cấp 2 xử lý khi đơn đang ở cấp 1 bị chặn' ($e.status -eq 403) "HTTP $($e.status) $($e.message)"

$inbox = Api $khoa GET '/approvals'
Check 'Đơn CHƯA vào hộp thư của Lãnh đạo Khoa' (@($inbox.items | Where-Object { $_.id -eq $id }).Count -eq 0)

Write-Host "`n=== 4. Đi trọn ba cấp ===" -ForegroundColor Cyan
Api $qlhv POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
$r = Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
Check 'Cấp 1 duyệt xong chuyển sang cấp 2' ($r.currentStepOrder -eq 2) "$($r.currentStepOrder)"
Check 'Đơn CHƯA phải Đã duyệt sau cấp 1' ($r.status -ne 'APPROVED') $r.status

$e = ErrOf { Api $khoa POST "/approvals/$id/action" @{ action = 'RECEIVE' } }
Check 'Cấp 3 vẫn bị chặn khi đơn đang ở cấp 2' ($e.status -eq 403) "HTTP $($e.status)"

Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
$r = Api $qldt POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
Check 'Cấp 2 duyệt xong chuyển sang cấp 3' ($r.currentStepOrder -eq 3) "$($r.currentStepOrder)"
Check 'Đơn VẪN chưa phải Đã duyệt sau cấp 2' ($r.status -ne 'APPROVED') $r.status

$inbox = Api $khoa GET '/approvals'
Check 'Giờ đơn mới vào hộp thư của Lãnh đạo Khoa' (@($inbox.items | Where-Object { $_.id -eq $id }).Count -eq 1)

Api $khoa POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
$r = Api $khoa POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
Check 'Cấp 3 duyệt xong đơn mới thành Đã duyệt' ($r.status -eq 'APPROVED') $r.status
Check 'Không còn bước nào đang chờ' ($null -eq $r.currentStepOrder) "$($r.currentStepOrder)"

# ------------------- 5. TIÊU CHÍ: DEPARTMENT_HEAD không lấn sân đơn khác
Write-Host "`n=== 5. Lãnh đạo Khoa không duyệt được đơn hai cấp ===" -ForegroundColor Cyan
$don2 = Api $sv POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{ leaveFrom = '2026-12-21'; leaveTo = '2026-12-22'; reason = 'Kiểm thử phân quyền.' }
}
Api $sv POST "/submissions/$($don2.id)/sign" @{ pin = '135790' } | Out-Null
Api $sv POST "/submissions/$($don2.id)/submit" | Out-Null
$e = ErrOf { Api $khoa POST "/approvals/$($don2.id)/action" @{ action = 'RECEIVE' } }
Check 'Lãnh đạo Khoa không xử lý được đơn không có cấp của mình' ($e.status -eq 403) `
  "HTTP $($e.status) $($e.message)"

Write-Host "`n=== 6. Bản in có bốn ô ký ===" -ForegroundColor Cyan
$tmp = Join-Path $env:TEMP "don-ba-cap-$id.docx"
Invoke-WebRequest -Uri "$Api/approvals/$id/file" -WebSession $khoa -OutFile $tmp | Out-Null
$bytes = [System.IO.File]::ReadAllBytes($tmp)
Remove-Item $tmp -ErrorAction SilentlyContinue
$text = DocxText $bytes

Check 'Tải được DOCX' ($bytes.Length -gt 5000) "$($bytes.Length) byte"
Check 'Bản in có đúng tiêu đề' ($text.Contains('ĐƠN XIN HỌC BỔ SUNG'))
Check 'Tên khoa học viên điền hiện trong phần Kính gửi' `
  ($text.Contains('Lãnh đạo Khoa Khoa An toàn thông tin'))
Check 'Bản in có lý do đã nhập' ($text.Contains('Em bị ốm phải nằm viện dài ngày.'))
$soO = ([regex]::Matches($text, [regex]::Escape('(Ký và ghi rõ họ tên)'))).Count
Check 'Có đúng BỐN ô ký (ba cấp + học viên)' ($soO -eq 4) "$soO ô"
Check 'Có ô Lãnh đạo Khoa' ($text -match 'LÃNH ĐẠO KHOA|Lãnh đạo Khoa')
# Cột in theo order giảm dần, nên LĐ Khoa (order 3) phải đứng TRƯỚC QLĐT trong
# luồng văn bản — đây là điều làm bản in khớp bản gốc.
$viTriKhoa = $text.IndexOf('LÃNH ĐẠO KHOA')
$viTriQldt = $text.IndexOf('LÃNH ĐẠO PHÒNG QUẢN LÝ ĐÀO TẠO')
Check 'Cột Lãnh đạo Khoa đứng ngoài cùng trái như bản gốc' `
  ($viTriKhoa -ge 0 -and $viTriQldt -ge 0 -and $viTriKhoa -lt $viTriQldt) `
  "khoa@$viTriKhoa qldt@$viTriQldt"

Write-Host "`n--------------------------------------------------------------"
if ($script:Fail -eq 0) {
  Write-Host "  PASS: $($script:Pass)    FAIL: 0" -ForegroundColor Green
} else {
  Write-Host "  PASS: $($script:Pass)    FAIL: $($script:Fail)" -ForegroundColor Red
  $script:Failures | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
Write-Host "--------------------------------------------------------------`n"
if ($script:Fail -gt 0) { exit 1 }
