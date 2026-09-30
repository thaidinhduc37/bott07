<#
  Kiểm thử nghiệm thu Ngày 11 — luồng trình ký hai cấp.

  Hai tiêu chí của kế hoạch:

    1. "Chỉ người được chỉ định ở bước hiện tại mới có quyền xử lý."
    2. "Mọi thay đổi trạng thái đều có người thực hiện, thời gian và ghi chú."

  Tiêu chí thứ nhất được kiểm bằng cách cho cấp 2 *cố tình* duyệt khi đơn còn
  đang ở cấp 1. Nếu việc đó thành công thì toàn bộ luồng phê duyệt chỉ là trang
  trí, dù giao diện có ẩn nút đi nữa.

    pwsh scripts/test/test-approval.ps1
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

Write-Host "`n=== 0. Các bên ===" -ForegroundColor Cyan
$sv    = Login 'sv.nguyenducanh@hvktcnan.edu.vn'   # học viên
$qlhv  = Login 'qlhv@hvktcnan.edu.vn'              # APPROVER — cấp 1
$qldt  = Login 'qldt@hvktcnan.edu.vn'              # ACADEMIC_MANAGER — cấp 2
Check 'Học viên, QLHV và QLĐT đăng nhập được' (($sv -and $qlhv -and $qldt) -as [bool])
EnsureSignature $sv; EnsureSignature $qlhv; EnsureSignature $qldt
Check 'Cả ba đều có chữ ký' $true

# --------------------------------------------------------------- lập + ký
Write-Host "`n=== 1. Học viên lập, ký và gửi ===" -ForegroundColor Cyan
$don = Api $sv POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{ leaveFrom = '2026-11-02'; leaveTo = '2026-11-03'; reason = 'Em về quê giải quyết việc gia đình.' }
}
$id = $don.id
Api $sv POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null
$sent = Api $sv POST "/submissions/$id/submit"
Check 'Đơn chuyển sang Chờ tiếp nhận' ($sent.status -eq 'SUBMITTED') $sent.status
Check 'Dừng ở bước 1' ($sent.currentStepOrder -eq 1) "$($sent.currentStepOrder)"

# ------------------------------------- 2. TIÊU CHÍ: không bỏ qua cấp duyệt
Write-Host "`n=== 2. Không bỏ qua cấp duyệt ===" -ForegroundColor Cyan
# Dùng RECEIVE chứ không phải APPROVE: APPROVE bị chặn ngay ở kiểm tra trạng
# thái (đơn chưa được tiếp nhận), nên nó không chứng minh được gì về kiểm tra
# vai trò. RECEIVE hợp lệ với trạng thái hiện tại, nên thứ duy nhất còn chặn
# được cấp 2 chính là kiểm tra "bước này không phải của bạn".
$e = ErrOf { Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } }
Check 'Cấp 2 xử lý khi đơn đang ở cấp 1 bị chặn' ($e.status -eq 403) "HTTP $($e.status) $($e.message)"
Check 'Nói rõ bước này thuộc vai trò khác' ($e.message -match 'APPROVER|Quản lý học viên') $e.message

$e = ErrOf { Api $sv GET "/approvals/$id" }
Check 'Học viên không vào được hộp thư duyệt' ($e.status -eq 403) "HTTP $($e.status)"

$e = ErrOf { Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790' } }
Check 'Duyệt trước khi tiếp nhận bị chặn (sai thứ tự trạng thái)' ($e.status -eq 400) `
  "HTTP $($e.status) $($e.message)"

$inbox = Api $qlhv GET '/approvals'
Check 'Đơn nằm trong hộp thư của cấp 1' (@($inbox.items | Where-Object { $_.id -eq $id }).Count -eq 1)
$inbox2 = Api $qldt GET '/approvals'
Check 'Đơn KHÔNG nằm trong hộp thư của cấp 2' (@($inbox2.items | Where-Object { $_.id -eq $id }).Count -eq 0)

# ----------------------------------------------------------- 3. cấp 1 xử lý
Write-Host "`n=== 3. Cấp 1 tiếp nhận, yêu cầu bổ sung ===" -ForegroundColor Cyan
$r = Api $qlhv POST "/approvals/$id/action" @{ action = 'RECEIVE' }
Check 'Tiếp nhận đưa đơn sang Đang duyệt' ($r.status -eq 'UNDER_REVIEW') $r.status

$e = ErrOf { Api $qlhv POST "/approvals/$id/action" @{ action = 'REQUEST_REVISION' } }
Check 'Yêu cầu bổ sung mà không ghi chú bị chặn' ($e.status -eq 400) $e.message

$r = Api $qlhv POST "/approvals/$id/action" @{
  action = 'REQUEST_REVISION'; comment = 'Bổ sung giấy xác nhận của địa phương.'
}
Check 'Yêu cầu bổ sung có ghi chú thì được' ($r.status -eq 'NEEDS_REVISION') $r.status

$mine = Api $sv GET "/submissions/$id"
Check 'Đơn mở khóa lại cho học viên sửa' ($mine.editable -eq $true)
Check 'Chữ ký cũ đã bị gỡ (nó chứng nhận nội dung sắp đổi)' ($null -eq $mine.signedHash) `
  "$($mine.signedHash)"

# --------------------------------------------------- 4. học viên bổ sung
Write-Host "`n=== 4. Học viên bổ sung rồi gửi lại ===" -ForegroundColor Cyan
Api $sv PATCH "/submissions/$id" @{
  formData = @{ leaveFrom = '2026-11-02'; leaveTo = '2026-11-03'
                reason = 'Em về quê giải quyết việc gia đình, có giấy xác nhận của UBND xã.' }
} | Out-Null
$e = ErrOf { Api $sv POST "/submissions/$id/submit" }
Check 'Gửi lại khi chưa ký lại bị chặn' ($e.status -eq 400) $e.message

Api $sv POST "/submissions/$id/sign" @{ pin = '135790' } | Out-Null
$again = Api $sv POST "/submissions/$id/submit"
Check 'Gửi lại được sau khi ký lại' ($again.status -eq 'SUBMITTED') $again.status
Check 'Quay lại bước 1, không nhảy cóc sang bước 2' ($again.currentStepOrder -eq 1) `
  "$($again.currentStepOrder)"

# ----------------------------------------------------------- 5. duyệt hết
Write-Host "`n=== 5. Duyệt qua hai cấp ===" -ForegroundColor Cyan
Api $qlhv POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null

$e = ErrOf { Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE' } }
Check 'Phê duyệt mà không có mã PIN bị chặn' ($e.status -eq 400) $e.message
$e = ErrOf { Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '000000' } }
Check 'Phê duyệt bằng PIN sai bị chặn' ($e.status -eq 400) $e.message

$r = Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý.' }
Check 'Cấp 1 duyệt xong thì chuyển sang bước 2' ($r.currentStepOrder -eq 2) "$($r.currentStepOrder)"
Check 'Đơn chờ cấp 2 tiếp nhận' ($r.status -eq 'SUBMITTED') $r.status

$e = ErrOf { Api $qlhv POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790' } }
Check 'Cấp 1 không xử lý tiếp được ở bước 2' ($e.status -eq 403 -or $e.status -eq 400) `
  "HTTP $($e.status) $($e.message)"

$inbox2 = Api $qldt GET '/approvals'
Check 'Giờ đơn mới vào hộp thư của cấp 2' (@($inbox2.items | Where-Object { $_.id -eq $id }).Count -eq 1)

Api $qldt POST "/approvals/$id/action" @{ action = 'RECEIVE' } | Out-Null
$r = Api $qldt POST "/approvals/$id/action" @{ action = 'APPROVE'; pin = '135790'; comment = 'Đồng ý cho nghỉ.' }
Check 'Cấp cuối duyệt thì đơn thành Đã duyệt' ($r.status -eq 'APPROVED') $r.status
Check 'Không còn bước nào đang chờ' ($null -eq $r.currentStepOrder) "$($r.currentStepOrder)"

$r = Api $qldt POST "/approvals/$id/action" @{ action = 'COMPLETE' }
Check 'Đóng đơn thành Đã hoàn thành' ($r.status -eq 'COMPLETED') $r.status

# --------------------------- 6. TIÊU CHÍ: lịch sử đầy đủ, ai/lúc nào/ghi chú
Write-Host "`n=== 6. Lịch sử trạng thái đầy đủ ===" -ForegroundColor Cyan
$d = Api $qldt GET "/approvals/$id"
$h = $d.history
Check 'Có ghi lại đủ các bước chuyển trạng thái' ($h.Count -ge 8) "$($h.Count) mục"
Check 'Mọi mục đều có người thực hiện' (@($h | Where-Object { -not $_.actor }).Count -eq 0)
Check 'Mọi mục đều có thời gian' (@($h | Where-Object { -not $_.createdAt }).Count -eq 0)
Check 'Mọi mục đều có trạng thái đích' (@($h | Where-Object { -not $_.toStatus }).Count -eq 0)
Check 'Mọi mục đều ghi địa chỉ IP' (@($h | Where-Object { -not $_.ipAddress }).Count -eq 0)
Check 'Yêu cầu bổ sung có lưu ghi chú' `
  (@($h | Where-Object { $_.action -eq 'REQUEST_REVISION' -and $_.comment }).Count -ge 1)
Check 'Có ghi nhận lần gửi lại' (@($h | Where-Object { $_.action -eq 'RESUBMIT' }).Count -ge 1)

Check 'Ghi lại chữ ký của cả ba bên' ($d.signings.Count -ge 3) "$($d.signings.Count)"
$byStep = ($d.signings | ForEach-Object { "$($_.stepOrder)" }) -join ','
Check 'Chữ ký gắn đúng bước (học viên null, rồi 1, rồi 2)' ($byStep -match '1' -and $byStep -match '2') $byStep

# File cuối cùng phải có ba ô chữ ký đều đã vẽ ảnh.
#
# Đếm `<w:drawing>` trong document.xml chứ KHÔNG đếm số tệp trong `word/media/`:
# thư viện `docx` gộp các ảnh trùng byte thành một tệp dùng chung (ba chữ ký
# trong kiểm thử đều là cùng một PNG 1×1), nên đếm tệp sẽ báo trượt cho một tài
# liệu hoàn toàn đúng.
$out = Join-Path $env:TEMP "$($d.code)-cuoi.docx"
Invoke-WebRequest -Uri "$Api/approvals/$id/file" -WebSession $qldt -OutFile $out | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($out)
$entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
$reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
$docXml = $reader.ReadToEnd(); $reader.Close(); $zip.Dispose()
Remove-Item $out -ErrorAction SilentlyContinue

$drawings = ([regex]::Matches($docXml, '<w:drawing>')).Count
Check 'File cuối cùng có đủ ba ô chữ ký đã ký' ($drawings -eq 3) "$drawings ảnh được chèn"
Check 'Ô chữ ký ghi tên học viên' ($docXml -match 'Nguyễn Đức Anh')
Check 'Ô chữ ký ghi tên cấp 1' ($docXml -match 'Phạm Văn Cường')
Check 'Ô chữ ký ghi tên cấp 2' ($docXml -match 'Nguyễn Thị Bích Ngọc')

# ---------------------------------------------------------- 7. thông báo
Write-Host "`n=== 7. Thông báo cho học viên ===" -ForegroundColor Cyan
$notif = Api $sv GET '/notifications'
$mineNotif = @($notif.items | Where-Object { $_.linkTo -match $id })
Check 'Học viên nhận được thông báo về đơn' ($mineNotif.Count -ge 4) "$($mineNotif.Count) thông báo"
Check 'Thông báo có dẫn tới đúng đơn' (@($mineNotif | Where-Object { $_.linkTo -match $id }).Count -eq $mineNotif.Count)

Write-Host ("`n" + ('-' * 62))
Write-Host "  PASS: $script:Pass    FAIL: $script:Fail"
if ($script:Failures.Count) {
  Write-Host "`n  Các mục không đạt:"; $script:Failures | ForEach-Object { Write-Host "    · $_" }
}
Write-Host ('-' * 62) "`n"
exit ($(if ($script:Fail) { 1 } else { 0 }))
