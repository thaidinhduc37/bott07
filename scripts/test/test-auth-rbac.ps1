# Kiểm thử thủ công RBAC — tiêu chí nghiệm thu Ngày 3
$ErrorActionPreference = "Continue"
$API = "http://localhost:4000/api"
$pass = 0; $fail = 0

function Check($name, $cond, $detail = "") {
  if ($cond) { Write-Host "  PASS  $name" -ForegroundColor Green; $script:pass++ }
  else { Write-Host "  FAIL  $name  $detail" -ForegroundColor Red; $script:fail++ }
}

function Req($method, $path, $body, $session) {
  try {
    $p = @{ Uri = "$API$path"; Method = $method; UseBasicParsing = $true; WebSession = $session }
    if ($body) { $p.Body = ($body | ConvertTo-Json -Compress); $p.ContentType = "application/json" }
    $r = Invoke-WebRequest @p
    return @{ ok = $true; code = $r.StatusCode; body = ($r.Content | ConvertFrom-Json) }
  } catch {
    $code = 0
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    return @{ ok = $false; code = $code; body = $null }
  }
}

function Login($email, $password) {
  # Thu lai khi gap 429.
  #
  # Dang nhap bi gioi han 5 lan/phut cho moi dia chi. Bo kiem thu nay CO Y dot
  # het han muc do o muc 11, va no khong chay mot minh: bo chay hang loat goi
  # nhieu bo lien tiep, con nguoi phat trien thi vua bam thu tren trinh duyet.
  #
  # Hau qua khi khong thu lai: mot lan dang nhap bi 429 lam token rong, roi moi
  # kiem tra dung token do deu truot voi ly do sai — "GV -> khoa tai khoan admin
  # = 403" bao "got 401". Nguoi doc ket qua se di tim lo hong phan quyen khong
  # he ton tai.
  #
  # Cho theo cua so that (60 giay) chu khong lui dan: han muc nay tinh theo
  # phut, nen lui 1s roi 2s chi ton them hai lan that bai.
  for ($attempt = 1; $attempt -le 3; $attempt++) {
    $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $r = Req "POST" "/auth/login" @{ email = $email; password = $password } $s
    if ($r.ok) { return @{ session = $s; user = $r.body.user; token = $r.body.accessToken } }
    if ($r.code -ne 429 -or $attempt -eq 3) { return $null }
    Write-Host "    (429 khi dang nhap $email — cho 62s roi thu lai)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 62
  }
  return $null
}

Write-Host "`n=== 1. Dang nhap ===" -ForegroundColor Cyan
$sv = Login "sv.nguyenducanh@hvktcnan.edu.vn" "Demo@2026"
Check "Sinh vien dang nhap duoc" ($null -ne $sv)
$admin = Login "admin@hvktcnan.edu.vn" "Demo@2026"
Check "Admin dang nhap duoc" ($null -ne $admin)
$gv = Login "gv.lehoanganh@hvktcnan.edu.vn" "Demo@2026"
Check "Giao vien dang nhap duoc" ($null -ne $gv)

Write-Host "`n=== 2. Sai thong tin dang nhap ===" -ForegroundColor Cyan
$bad = Req "POST" "/auth/login" @{ email = "sv.nguyenducanh@hvktcnan.edu.vn"; password = "SaiMatKhau1" } (New-Object Microsoft.PowerShell.Commands.WebRequestSession)
Check "Sai mat khau -> 401" ($bad.code -eq 401) "got $($bad.code)"
$noone = Req "POST" "/auth/login" @{ email = "khongtontai@hvktcnan.edu.vn"; password = "Demo@2026" } (New-Object Microsoft.PowerShell.Commands.WebRequestSession)
Check "Email khong ton tai -> 401" ($noone.code -eq 401) "got $($noone.code)"

Write-Host "`n=== 3. Khong dang nhap ===" -ForegroundColor Cyan
$anon = Req "GET" "/users/me" $null (New-Object Microsoft.PowerShell.Commands.WebRequestSession)
Check "GET /users/me khong token -> 401" ($anon.code -eq 401) "got $($anon.code)"
$anonAdmin = Req "GET" "/admin/users" $null (New-Object Microsoft.PowerShell.Commands.WebRequestSession)
Check "GET /admin/users khong token -> 401" ($anonAdmin.code -eq 401) "got $($anonAdmin.code)"
$health = Req "GET" "/health" $null (New-Object Microsoft.PowerShell.Commands.WebRequestSession)
Check "GET /health public -> 200" ($health.code -eq 200) "got $($health.code)"

Write-Host "`n=== 4. RBAC: sinh vien KHONG goi duoc API quan tri ===" -ForegroundColor Cyan
$r = Req "GET" "/admin/users" $null $sv.session
Check "SV -> GET /admin/users = 403" ($r.code -eq 403) "got $($r.code)"
$r = Req "POST" "/admin/users" @{ email = "x@y.z"; fullName = "Hacker"; password = "Abcd1234"; roles = @("ADMIN") } $sv.session
Check "SV -> POST /admin/users = 403" ($r.code -eq 403) "got $($r.code)"
$r = Req "GET" "/admin/audit-logs" $null $sv.session
Check "SV -> GET /admin/audit-logs = 403" ($r.code -eq 403) "got $($r.code)"
$r = Req "GET" "/health/detail" $null $sv.session
Check "SV -> GET /health/detail = 403" ($r.code -eq 403) "got $($r.code)"

Write-Host "`n=== 5. RBAC: giao vien KHONG sua duoc tai khoan quan tri ===" -ForegroundColor Cyan
$adminList = Req "GET" "/admin/users?role=ADMIN" $null $admin.session
$adminId = $adminList.body.items[0].id
$r = Req "PATCH" "/admin/users/$adminId/status" @{ status = "DISABLED" } $gv.session
Check "GV -> khoa tai khoan admin = 403" ($r.code -eq 403) "got $($r.code)"
$r = Req "PUT" "/admin/users/$adminId/roles" @{ roles = @("STUDENT") } $gv.session
Check "GV -> doi vai tro admin = 403" ($r.code -eq 403) "got $($r.code)"

Write-Host "`n=== 6. Admin lam duoc viec cua minh ===" -ForegroundColor Cyan
$r = Req "GET" "/admin/users" $null $admin.session
Check "Admin -> GET /admin/users = 200" ($r.code -eq 200) "got $($r.code)"
Check "Danh sach co 7 tai khoan" ($r.body.total -eq 7) "got $($r.body.total)"
Check "Response KHONG chua password_hash" (-not ($r.body.items[0].PSObject.Properties.Name -contains "passwordHash"))
$r = Req "GET" "/health/detail" $null $admin.session
Check "Admin -> GET /health/detail = 200" ($r.code -eq 200) "got $($r.code)"

Write-Host "`n=== 7. Ho so ca nhan ===" -ForegroundColor Cyan
$r = Req "GET" "/users/me" $null $sv.session
Check "SV xem duoc ho so cua minh" ($r.code -eq 200) "got $($r.code)"
Check "Ho so co ma sinh vien B3D15001" ($r.body.studentProfile.studentCode -eq "B3D15001") "got $($r.body.studentProfile.studentCode)"
Check "Ho so KHONG lo signaturePinHash" (-not ($r.body.PSObject.Properties.Name -contains "signaturePinHash"))
Check "hasSignaturePin = true (seed da dat PIN)" ($r.body.hasSignaturePin -eq $true)

Write-Host "`n=== 8. Sinh vien KHONG sua duoc ho ten / ma SV ===" -ForegroundColor Cyan
$r = Req "PATCH" "/users/me" @{ fullName = "Ten Gia Mao" } $sv.session
Check "PATCH fullName -> 400 (whitelist DTO chan)" ($r.code -eq 400) "got $($r.code)"
$r = Req "PATCH" "/users/me" @{ studentCode = "B3D15999" } $sv.session
Check "PATCH studentCode -> 400" ($r.code -eq 400) "got $($r.code)"
$r = Req "PATCH" "/users/me" @{ roles = @("ADMIN") } $sv.session
Check "PATCH roles -> 400 (khong the tu nang quyen)" ($r.code -eq 400) "got $($r.code)"
$r = Req "PATCH" "/users/me" @{ phone = "0987654321" } $sv.session
Check "PATCH phone hop le -> 200" ($r.code -eq 200) "got $($r.code)"
Check "Phone da doi" ($r.body.phone -eq "0987654321") "got $($r.body.phone)"
$r = Req "PATCH" "/users/me" @{ phone = "abc" } $sv.session
Check "PATCH phone sai dinh dang -> 400" ($r.code -eq 400) "got $($r.code)"

Write-Host "`n=== 9. Refresh token xoay vong ===" -ForegroundColor Cyan
# Muc 1-2 da dung het quota dang nhap (5/phut/IP). Cho cua so rate limit troi qua,
# neu khong thi login o day tra 429 va ca muc 9-10 kiem tra nham.
Write-Host "  (cho 62s de cua so rate limit dang nhap reset)" -ForegroundColor DarkGray
Start-Sleep -Seconds 62
$s2 = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$l = Req "POST" "/auth/login" @{ email = "sv.tranthimai@hvktcnan.edu.vn"; password = "Demo@2026" } $s2
Check "Dang nhap lai duoc sau khi rate limit reset" ($l.code -eq 200) "got $($l.code)"
$oldRefresh = ($s2.Cookies.GetCookies("http://localhost:4000/api/auth/refresh") | Where-Object { $_.Name -eq "sa_refresh" }).Value
$r1 = Req "POST" "/auth/refresh" $null $s2
Check "Refresh lan 1 -> 200" ($r1.code -eq 200) "got $($r1.code)"
$newRefresh = ($s2.Cookies.GetCookies("http://localhost:4000/api/auth/refresh") | Where-Object { $_.Name -eq "sa_refresh" }).Value
Check "Refresh token da bi xoay" ($oldRefresh -ne $newRefresh)

# Dung lai token cu -> phai bi tu choi va thu hoi toan bo phien
$s3 = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$c = New-Object System.Net.Cookie("sa_refresh", $oldRefresh, "/api/auth", "localhost")
$s3.Cookies.Add($c)
$r2 = Req "POST" "/auth/refresh" $null $s3
Check "Dung lai refresh token cu -> 401" ($r2.code -eq 401) "got $($r2.code)"
$r3 = Req "POST" "/auth/refresh" $null $s2
Check "Sau khi phat hien tai su dung, phien moi cung bi thu hoi -> 401" ($r3.code -eq 401) "got $($r3.code)"

Write-Host "`n=== 10. Dang xuat ===" -ForegroundColor Cyan
$sv2 = Login "sv.nguyenducanh@hvktcnan.edu.vn" "Demo@2026"
Check "Dang nhap de kiem tra logout" ($null -ne $sv2)
$r = Req "POST" "/auth/logout" $null $sv2.session
Check "Logout -> 200" ($r.code -eq 200) "got $($r.code)"
$r = Req "POST" "/auth/refresh" $null $sv2.session
Check "Refresh sau logout -> 401" ($r.code -eq 401) "got $($r.code)"

Write-Host "`n=== 11. Rate limit dang nhap (5 lan/phut) ===" -ForegroundColor Cyan
$s4 = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$codes = @()
for ($i = 1; $i -le 8; $i++) {
  $rr = Req "POST" "/auth/login" @{ email = "sv.nguyenducanh@hvktcnan.edu.vn"; password = "SaiMatKhau$i" } $s4
  $codes += $rr.code
}
Check "Co request bi chan 429" ($codes -contains 429) "codes: $($codes -join ',')"

Write-Host "`n=== 12. Bao ve tai khoan admin cuoi cung ===" -ForegroundColor Cyan
$r = Req "PATCH" "/admin/users/$adminId/status" @{ status = "DISABLED" } $admin.session
Check "Admin tu khoa minh -> 400" ($r.code -eq 400) "got $($r.code)"

Write-Host "`n--------------------------------------------"
Write-Host "  PASS: $pass    FAIL: $fail" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "--------------------------------------------`n"

# Ma thoat, khong chi in ra man hinh.
#
# Thieu dong nay, bo kiem thu luon thoat 0 va `chay-tat-ca.ps1` bao DAT du co
# bao nhieu muc truot. Da xay ra that: mot lan chay bao "Tat ca cac bo deu dat"
# trong khi bo nay ghi FAIL: 5 ngay tren cung mot man hinh. Mot bo kiem thu
# khong the truot thi te hon la khong co bo kiem thu nao.
exit $(if ($fail) { 1 } else { 0 })
