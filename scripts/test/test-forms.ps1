<#
  Kiểm thử nghiệm thu Ngày 9 — biểu mẫu hành chính.

  Hai tiêu chí của kế hoạch:

    1. "Không cho phép sinh viên sửa họ tên hoặc mã sinh viên của người khác."
    2. "File xuất ra đúng dữ liệu đã nhập và không mất dấu tiếng Việt."

  Tiêu chí thứ nhất mới là tiêu chí thật. Nó được kiểm bằng cách *cố tình* gửi
  lên họ tên và mã học viên của một người khác rồi kiểm tra rằng đơn tạo ra vẫn
  mang thông tin của người đang đăng nhập — chứ không phải bằng cách kiểm tra
  giao diện có khóa ô nhập hay không.

    pwsh scripts/test/test-forms.ps1
#>

$ErrorActionPreference = 'Stop'
$Api = $env:API_URL; if (-not $Api) { $Api = 'http://localhost:5000/api' }

$script:Pass = 0
$script:Fail = 0
$script:Failures = @()

function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
  if ($Ok) {
    Write-Host "  PASS  $Name" -ForegroundColor Green
    $script:Pass++
  } else {
    Write-Host "  FAIL  $Name  $Detail" -ForegroundColor Red
    $script:Fail++
    $script:Failures += "$Name — $Detail"
  }
}

function Login([string]$Email, [string]$Password) {
  $session = $null
  $body = @{ email = $Email; password = $Password } | ConvertTo-Json
  Invoke-RestMethod -Uri "$Api/auth/login" -Method Post -Body $body `
    -ContentType 'application/json' -SessionVariable session | Out-Null
  return $session
}

function Api([Microsoft.PowerShell.Commands.WebRequestSession]$S, [string]$Method, [string]$Path, $Body = $null) {
  $args = @{ Uri = "$Api$Path"; Method = $Method; WebSession = $S }
  if ($null -ne $Body) {
    $args.Body = ($Body | ConvertTo-Json -Depth 6)
    $args.ContentType = 'application/json'
  }
  return Invoke-RestMethod @args
}

# ---------------------------------------------------------------- đăng nhập
Write-Host "`n=== 0. Đăng nhập ===" -ForegroundColor Cyan
$anh = Login 'sv.nguyenducanh@hvktcnan.edu.vn' 'Demo@2026'
Check 'Học viên A đăng nhập được' ($null -ne $anh)
$mai = Login 'sv.tranthimai@hvktcnan.edu.vn' 'Demo@2026'
Check 'Học viên B đăng nhập được' ($null -ne $mai)

# ------------------------------------------------------------- biểu mẫu
Write-Host "`n=== 1. Biểu mẫu và dữ liệu điền sẵn ===" -ForegroundColor Cyan
$tpl = Api $anh GET '/form-templates/DON_XIN_NGHI_HOC'
Check 'Lấy được biểu mẫu Đơn xin nghỉ học' ($tpl.code -eq 'DON_XIN_NGHI_HOC')
Check 'Hồ sơ không thiếu trường bắt buộc nào' ($tpl.missingProfileFields.Count -eq 0) `
  "thiếu: $($tpl.missingProfileFields.label -join ', ')"
Check 'Điền sẵn đúng họ tên từ hồ sơ' ($tpl.autofill.fullName -eq 'Nguyễn Đức Anh') $tpl.autofill.fullName
Check 'Điền sẵn đúng mã học viên' ($tpl.autofill.studentCode -eq 'B3D15001') $tpl.autofill.studentCode
Check 'Điền sẵn đúng lớp' ($tpl.autofill.className -eq 'B3D15') $tpl.autofill.className

$editable = @($tpl.fields | Where-Object { -not $_.autofill })
Check 'Chỉ hỏi các trường hồ sơ không có' ($editable.Count -eq 4) `
  "đang hỏi: $($editable.key -join ', ')"

# Phép kiểm "biểu mẫu chưa mở bị từ chối" ĐÃ CHUYỂN sang
# server/api/src/forms/forms.service.spec.ts. Nó từng trỏ vào một biểu mẫu còn
# đóng trong seed, nhưng nay cả bảy đều đã mở nên ở tầng này không còn mẫu thử.
# Chuyển xuống kiểm thử đơn vị thay vì bỏ: quản trị viên tắt một biểu mẫu là
# chuyện có thật, và lúc đó phải từ chối chứ không được trả schema rỗng.
#
# Ở tầng này giữ lại phép kiểm còn dựng được: mã đơn không tồn tại phải ra 404
# gọn gàng, không phải lỗi 500.
$notFound = 0
try { Api $anh GET '/form-templates/KHONG_CO_DON_NAY' | Out-Null }
catch { try { $notFound = $_.Exception.Response.StatusCode.value__ } catch {} }
Check 'Mã biểu mẫu không tồn tại trả về 404, không phải lỗi máy chủ' ($notFound -eq 404) `
  "HTTP $notFound"

Check 'Cả bảy biểu mẫu đều đang nhận đơn' `
  (@((Api $anh GET '/form-templates').items | Where-Object { $_.isActive }).Count -eq 7) `
  "$(@((Api $anh GET '/form-templates').items | Where-Object { $_.isActive }).Count)/7"

# ------------------------------------------- 2. TIÊU CHÍ CHÍNH: giả mạo hồ sơ
Write-Host "`n=== 2. Không mượn được hồ sơ người khác ===" -ForegroundColor Cyan
# Gửi kèm họ tên và mã học viên của học viên B. Nếu máy chủ tin client thì đơn
# tạo ra sẽ mang tên người khác — đúng thứ tiêu chí nghiệm thu cấm.
$res = Api $anh POST '/submissions' @{
  templateCode = 'DON_XIN_NGHI_HOC'
  formData     = @{
    fullName    = 'Trần Thị Mai'
    studentCode = 'B3D15002'
    className   = 'XXXXX'
    leaveFrom   = '2026-08-17'
    leaveTo     = '2026-08-19'
    reason      = 'Em bị sốt xuất huyết, có giấy khám của Bệnh viện Đa khoa tỉnh Bắc Ninh.'
  }
}
Check 'Tạo được đơn' ($null -ne $res.code)
Check 'Đơn mang tên người đang đăng nhập, không phải tên gửi lên' `
  ($res.profileSnapshot.fullName -eq 'Nguyễn Đức Anh') $res.profileSnapshot.fullName
Check 'Mã học viên là của người đang đăng nhập' `
  ($res.profileSnapshot.studentCode -eq 'B3D15001') $res.profileSnapshot.studentCode
Check 'Lớp là của người đang đăng nhập' `
  ($res.profileSnapshot.className -eq 'B3D15') $res.profileSnapshot.className
Check 'Các khóa autofill bị loại khỏi formData' `
  ($null -eq $res.formData.fullName -and $null -eq $res.formData.studentCode) `
  "formData còn: $($res.formData | ConvertTo-Json -Compress)"

$id = $res.id
$code = $res.code

# ------------------------------------------------------------- 3. IDOR
Write-Host "`n=== 3. Không xem/sửa được đơn của người khác ===" -ForegroundColor Cyan
$status = 0
try { Api $mai GET "/submissions/$id" | Out-Null }
catch { $status = $_.Exception.Response.StatusCode.value__ }
Check 'Học viên B đọc đơn của A bị chặn' ($status -eq 404) "HTTP $status"
Check 'Trả 404 chứ không 403 (không xác nhận đơn tồn tại)' ($status -eq 404) "HTTP $status"

$status = 0
try { Api $mai PATCH "/submissions/$id" @{ formData = @{ reason = 'sửa trộm' } } | Out-Null }
catch { $status = $_.Exception.Response.StatusCode.value__ }
Check 'Học viên B sửa đơn của A bị chặn' ($status -eq 404) "HTTP $status"

# ------------------------------------------------------- 4. kiểm tra dữ liệu
Write-Host "`n=== 4. Kiểm tra dữ liệu nhập ===" -ForegroundColor Cyan
$msg = ''
try {
  Api $anh POST '/submissions' @{
    templateCode = 'DON_XIN_NGHI_HOC'
    formData     = @{ leaveFrom = '2026-08-17'; leaveTo = '2026-08-30'; reason = 'x' }
  } | Out-Null
} catch {
  $msg = (($_.ErrorDetails.Message | ConvertFrom-Json).message)
}
Check 'Nghỉ quá 03 ngày bị từ chối (sai phạm vi biểu mẫu)' ($msg -match '03 ngày') $msg

$msg = ''
try {
  Api $anh POST '/submissions' @{
    templateCode = 'DON_XIN_NGHI_HOC'
    formData     = @{ leaveFrom = '2026-08-19'; leaveTo = '2026-08-17'; reason = 'x' }
  } | Out-Null
} catch { $msg = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Ngày kết thúc trước ngày bắt đầu bị từ chối' ($msg -match 'không được trước') $msg

$msg = ''
try {
  Api $anh POST '/submissions' @{
    templateCode = 'DON_XIN_NGHI_HOC'
    formData     = @{ leaveFrom = '2026-08-17'; leaveTo = '2026-08-18' }
  } | Out-Null
} catch { $msg = (($_.ErrorDetails.Message | ConvertFrom-Json).message) }
Check 'Thiếu lý do bị từ chối' ($msg -match 'Lý do') $msg

# ----------------------------------------------------------- 5. render DOCX
Write-Host "`n=== 5. Dựng file và tải về ===" -ForegroundColor Cyan
$render = Api $anh POST "/submissions/$id/render"
Check 'Dựng được file' ($render.bytes -gt 2000) "$($render.bytes) byte"
Check 'Có hash SHA-256 của file' ($render.hash -match '^[0-9a-f]{64}$') $render.hash

$out = Join-Path $env:TEMP "$code.docx"
Invoke-WebRequest -Uri "$Api/submissions/$id/file" -WebSession $anh -OutFile $out | Out-Null
Check 'Tải về được file' (Test-Path $out)

# DOCX là ZIP: 4 byte đầu phải là PK\x03\x04.
$head = [System.IO.File]::ReadAllBytes($out)[0..3]
Check 'File tải về đúng là DOCX' (($head[0] -eq 0x50) -and ($head[1] -eq 0x4B)) `
  ("bytes: {0}" -f ($head -join ','))

# Hash file tải về phải khớp hash máy chủ ghi lại.
$dl = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Check 'Hash file tải về khớp hash đã lưu' ($dl -eq $render.hash) "$dl vs $($render.hash)"

# Đọc text bên trong để kiểm dấu tiếng Việt.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($out)
$entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
$reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
$xml = $reader.ReadToEnd()
$reader.Close(); $zip.Dispose()

Check 'Giữ nguyên dấu tiếng Việt trong họ tên' ($xml -match 'Nguyễn Đức Anh')
Check 'Giữ nguyên dấu ở quốc hiệu' ($xml -match 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM')
Check 'Giữ nguyên dấu trong lý do người dùng nhập' ($xml -match 'sốt xuất huyết')
Check 'In đúng ngày nghỉ đã nhập' ($xml -match '17/08/2026' -and $xml -match '19/08/2026')
Check 'KHÔNG in tên người khác vào đơn' (-not ($xml -match 'Trần Thị Mai'))
Check 'KHÔNG in mã học viên người khác' (-not ($xml -match 'B3D15002'))
Check 'Có đủ ba ô chữ ký' ($xml -match 'HỌC VIÊN VIẾT ĐƠN')

Remove-Item $out -ErrorAction SilentlyContinue

# ------------------------------------------------------------------- tổng
Write-Host ("`n" + ('-' * 62))
Write-Host "  PASS: $script:Pass    FAIL: $script:Fail"
if ($script:Failures.Count) {
  Write-Host "`n  Các mục không đạt:"
  $script:Failures | ForEach-Object { Write-Host "    · $_" }
}
Write-Host ('-' * 62) "`n"
exit ($(if ($script:Fail) { 1 } else { 0 }))
