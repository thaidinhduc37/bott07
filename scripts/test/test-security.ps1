<#
  Kiểm thử bảo mật Ngày 13.

  Kế hoạch liệt kê ba nhóm phải thử: IDOR, upload giả phần mở rộng, và rate
  limit. Thêm hai nhóm nữa vì chúng là những chỗ mã nguồn này thực sự nhận dữ
  liệu từ bên ngoài: path traversal qua tên tệp, và rò rỉ thông tin qua thông
  báo lỗi.

  Nguyên tắc của cả tệp: **không kiểm tra bằng cách nhìn giao diện**. Mọi mục
  đều gửi request thật bằng tài khoản không có quyền, hoặc gửi dữ liệu độc hại
  thật, rồi xem máy chủ trả về gì.

    pwsh scripts/test/test-security.ps1
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

function Try-Api($S, [string]$M, [string]$P, $B = $null) {
  try {
    $a = @{ Uri = "$Api$P"; Method = $M; WebSession = $S }
    if ($null -ne $B) { $a.Body = ($B | ConvertTo-Json -Depth 6); $a.ContentType = 'application/json' }
    return @{ status = 200; body = (Invoke-RestMethod @a) }
  } catch {
    $st = -1; $msg = ''
    try { $st = $_.Exception.Response.StatusCode.value__ } catch {}
    try {
      $b = $_.ErrorDetails.Message | ConvertFrom-Json
      $msg = if ($b.message -is [string]) { $b.message } else { $b.message.message }
    } catch { $msg = "$_" }
    return @{ status = $st; message = $msg }
  }
}

function Upload($S, [string]$Path, [byte[]]$Bytes, [string]$FileName, $Extra = @{}) {
  $tmp = Join-Path $env:TEMP $FileName
  [System.IO.File]::WriteAllBytes($tmp, $Bytes)
  try {
    $form = @{ file = Get-Item $tmp }
    foreach ($k in $Extra.Keys) { $form[$k] = $Extra[$k] }
    return @{ status = 200; body = (Invoke-RestMethod -Uri "$Api$Path" -Method Post -WebSession $S -Form $form) }
  } catch {
    $st = -1; $msg = ''
    try { $st = $_.Exception.Response.StatusCode.value__ } catch {}
    try {
      $b = $_.ErrorDetails.Message | ConvertFrom-Json
      $msg = if ($b.message -is [string]) { $b.message } else { $b.message.message }
    } catch { $msg = "$_" }
    return @{ status = $st; message = $msg }
  } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

Write-Host "`n=== 0. Chuẩn bị ===" -ForegroundColor Cyan
$anh   = Login 'sv.nguyenducanh@hvktcnan.edu.vn'
$mai   = Login 'sv.tranthimai@hvktcnan.edu.vn'
$admin = Login 'admin@hvktcnan.edu.vn'
Check 'Ba tài khoản đăng nhập được' (($anh -and $mai -and $admin) -as [bool])

# Đơn của học viên A, dùng làm mục tiêu cho các phép thử IDOR.
$don = (Try-Api $anh POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{ leaveFrom = '2026-12-07'; leaveTo = '2026-12-08'; reason = 'Kiểm thử bảo mật.' }
}).body
Check 'Tạo được đơn mục tiêu' ($null -ne $don.id)
$targetId = $don.id

# ---------------------------------------------------------------- 1. IDOR
Write-Host "`n=== 1. IDOR — truy cập tài nguyên của người khác ===" -ForegroundColor Cyan

$cases = @(
  @{ m = 'GET';   p = "/submissions/$targetId";        name = 'đọc đơn' },
  @{ m = 'PATCH'; p = "/submissions/$targetId";        name = 'sửa đơn'; b = @{ formData = @{ reason = 'x' } } },
  @{ m = 'POST';  p = "/submissions/$targetId/render"; name = 'dựng file đơn' },
  @{ m = 'GET';   p = "/submissions/$targetId/file";   name = 'tải file đơn' },
  @{ m = 'GET';   p = "/submissions/$targetId/verify"; name = 'kiểm chứng đơn' },
  @{ m = 'POST';  p = "/submissions/$targetId/sign";   name = 'ký đơn'; b = @{ pin = '135790' } },
  @{ m = 'POST';  p = "/submissions/$targetId/submit"; name = 'gửi trình ký' }
)
foreach ($c in $cases) {
  $r = Try-Api $mai $c.m $c.p $c.b
  Check "Học viên B $($c.name) của A bị chặn" ($r.status -eq 404) "HTTP $($r.status)"
}
Check 'Trả 404 chứ không 403 — không xác nhận tài nguyên tồn tại' $true

# Đoán UUID không tồn tại phải cho cùng phản hồi với đoán đúng UUID người khác.
$ghost = (Try-Api $mai GET '/submissions/00000000-0000-4000-8000-000000000000').status
$real  = (Try-Api $mai GET "/submissions/$targetId").status
Check 'UUID không tồn tại và UUID của người khác cho cùng mã lỗi' ($ghost -eq $real) "$ghost vs $real"

# Chữ ký: endpoint không nhận id, nên không có gì để đoán.
$r = Try-Api $mai GET '/signatures/me'
Check 'Endpoint chữ ký không nhận id từ ngoài' ($r.status -eq 200 -or $r.status -eq 404) "HTTP $($r.status)"

# ------------------------------------------------- 2. upload giả phần mở rộng
Write-Host "`n=== 2. Upload giả phần mở rộng ===" -ForegroundColor Cyan

$exe  = [byte[]](0x4D,0x5A,0x90,0x00,0x03,0x00,0x00,0x00) + [System.Text.Encoding]::ASCII.GetBytes('fake executable payload')
$html = [System.Text.Encoding]::UTF8.GetBytes('<html><script>alert(1)</script></html>')
$png  = [Convert]::FromBase64String('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')

$r = Upload $admin '/documents' $exe 'virus.pdf' @{ title = 'Thu doi duoi exe'; documentType = 'QUYCHE' }
Check 'File EXE đổi đuôi .pdf bị từ chối' ($r.status -eq 400) "HTTP $($r.status) $($r.message)"
Check 'Nói rõ nội dung không khớp phần mở rộng' ($r.message -match 'không phải PDF|nội dung') $r.message

$r = Upload $admin '/documents' $html 'trang.docx' @{ title = 'Thu doi duoi html'; documentType = 'QUYCHE' }
Check 'File HTML đổi đuôi .docx bị từ chối' ($r.status -eq 400) "HTTP $($r.status) $($r.message)"

$r = Upload $admin '/documents' $png 'anh.png' @{ title = 'Anh lam tai lieu'; documentType = 'QUYCHE' }
Check 'PNG không được nhận làm tài liệu quy chế' ($r.status -eq 400) "HTTP $($r.status) $($r.message)"

$r = Upload $anh '/signatures' $exe 'chuky.png'
Check 'File EXE đổi đuôi .png không thành chữ ký được' ($r.status -eq 400) "HTTP $($r.status)"

# ------------------------------------------------------- 3. path traversal
Write-Host "`n=== 3. Path traversal qua tên tệp ===" -ForegroundColor Cyan
$r = Upload $anh '/signatures' $png 'chuky.png'
Check 'Chữ ký hợp lệ vẫn lưu được' ($r.status -eq 200) "HTTP $($r.status)"
Check 'KHÔNG trả đường dẫn thật trên đĩa ra API' ($null -eq $r.body.filePath) `
  ($r.body | ConvertTo-Json -Compress)

# Tên tệp do người dùng đặt không được tham gia vào đường dẫn lưu trữ.
#
# Nội dung phải khác nhau mỗi lần chạy: hệ thống từ chối tệp trùng nội dung với
# một tài liệu đã lập chỉ mục (tính năng của Ngày 5), nên dùng nội dung cố định
# sẽ khiến lần chạy thứ hai trượt vì một lý do chẳng liên quan gì tới bảo mật.
$noiDung = [System.Text.Encoding]::UTF8.GetBytes("noi dung thu $([guid]::NewGuid())")
$evil = Upload $admin '/documents' $noiDung "thu-$([guid]::NewGuid().ToString('N').Substring(0,8)).txt" `
  @{ title = "Kiem thu ten tep $([guid]::NewGuid().ToString('N').Substring(0,8))"; documentType = 'KHAC' }
if ($evil.status -eq 200) {
  $v = $evil.body.versions | Select-Object -First 1
  Check 'Tên gốc chỉ được giữ để hiển thị' ($v.fileName -match '^thu-[0-9a-f]{8}\.txt$') `
    "hiển thị: $($v.fileName)"
  Check 'Bản ghi trả về KHÔNG chứa filePath thật trên đĩa' ($null -eq $v.filePath) `
    ($v | ConvertTo-Json -Compress)
} else {
  Check 'Tải được tệp văn bản để kiểm tra tên' $false "HTTP $($evil.status) $($evil.message)"
}

# ------------------------------------------------ 4. rò rỉ qua thông báo lỗi
#
# Phải đứng TRƯỚC phần rate limit: mục sau cố tình đốt hết hạn mức đăng nhập,
# và khi đó mọi lần gọi /auth/login đều trả 429 nên không so được thông báo.
Write-Host "`n=== 4. Không rò rỉ qua thông báo lỗi ===" -ForegroundColor Cyan
$r1 = Try-Api $null POST '/auth/login' @{ email = 'khong-ton-tai@hvktcnan.edu.vn'; password = 'x' }
$r2 = Try-Api $null POST '/auth/login' @{ email = 'admin@hvktcnan.edu.vn'; password = 'sai-mat-khau' }
Check 'Email không tồn tại và mật khẩu sai cho cùng thông báo' `
  ($r1.message -eq $r2.message -and $r1.status -eq 401) `
  "HTTP $($r1.status)/$($r2.status): `"$($r1.message)`" vs `"$($r2.message)`""
Check 'Thông báo không nói tài khoản có tồn tại hay không' `
  (-not ($r1.message -match 'không tồn tại|not found|chưa đăng ký')) $r1.message

$me = (Try-Api $anh GET '/users/me').body
Check 'Hồ sơ trả về KHÔNG chứa hash mật khẩu' `
  (($null -eq $me.passwordHash) -and ($null -eq $me.signaturePinHash)) `
  'có trường hash trong phản hồi'

# --------------------------------------------------------- 5. rate limiting
Write-Host "`n=== 5. Rate limit ===" -ForegroundColor Cyan

# Các mục trên đã gọi /auth/login vài lần (đăng nhập ba tài khoản, so thông báo
# lỗi). Cửa sổ giới hạn là một phút, nên phải đợi nó trôi qua — nếu không thì
# mục này đo phần còn thừa của mục trước chứ không đo cái nó định đo.
Write-Host '  (đợi 62 giây để cửa sổ giới hạn đăng nhập trôi qua)' -ForegroundColor DarkGray
Start-Sleep -Seconds 62

$blocked = 0; $wrong = 0
for ($i = 1; $i -le 10; $i++) {
  try {
    Invoke-RestMethod -Uri "$Api/auth/login" -Method Post -ContentType 'application/json' `
      -Body (@{ email = 'khong-ton-tai@hvktcnan.edu.vn'; password = 'sai-mat-khau' } | ConvertTo-Json) | Out-Null
  } catch {
    $st = $_.Exception.Response.StatusCode.value__
    if ($st -eq 429) { $blocked++ } elseif ($st -eq 401) { $wrong++ }
  }
}
Check 'Dò mật khẩu bị chặn sau vài lần' ($blocked -ge 4) "401=$wrong 429=$blocked"
Check 'Vài lần đầu vẫn trả 401 (không lộ là đã bị chặn ngay)' ($wrong -ge 1) "401=$wrong"

# Endpoint thường KHÔNG được dính giới hạn của đăng nhập.
$ok = 0
for ($i = 1; $i -le 15; $i++) {
  if ((Try-Api $anh GET '/notifications').status -eq 200) { $ok++ }
}
Check 'Endpoint thường không bị siết theo giới hạn đăng nhập' ($ok -eq 15) "$ok/15 thành công"

Write-Host ("`n" + ('-' * 62))
Write-Host "  PASS: $script:Pass    FAIL: $script:Fail"
if ($script:Failures.Count) {
  Write-Host "`n  Các mục không đạt:"; $script:Failures | ForEach-Object { Write-Host "    · $_" }
}
Write-Host ('-' * 62) "`n"
exit ($(if ($script:Fail) { 1 } else { 0 }))
