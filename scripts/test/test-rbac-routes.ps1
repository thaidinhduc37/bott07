<#
  Kiểm thử nghiệm thu Ngày 12 — phân quyền ở backend.

  Tiêu chí của kế hoạch:

    "Không có route quản trị nào chỉ được ẩn ở frontend mà thiếu kiểm tra quyền
     ở backend."

  Cách kiểm duy nhất trung thực là **gõ thẳng vào endpoint** bằng tài khoản
  không có quyền, chứ không phải xem menu có hiện nút hay không. Ẩn nút là trải
  nghiệm người dùng; chặn request mới là phân quyền.

    pwsh scripts/test/test-rbac-routes.ps1
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

function StatusOf($S, [string]$M, [string]$P, $B = $null) {
  try {
    $a = @{ Uri = "$Api$P"; Method = $M; WebSession = $S }
    if ($null -ne $B) { $a.Body = ($B | ConvertTo-Json -Depth 5); $a.ContentType = 'application/json' }
    Invoke-RestMethod @a | Out-Null
    return 200
  } catch {
    try { return $_.Exception.Response.StatusCode.value__ } catch { return -1 }
  }
}

Write-Host "`n=== 0. Đăng nhập ba vai trò ===" -ForegroundColor Cyan
$sv    = Login 'sv.nguyenducanh@hvktcnan.edu.vn'
$gv    = Login 'gv.nguyenvanminh@hvktcnan.edu.vn'
$admin = Login 'admin@hvktcnan.edu.vn'
Check 'Học viên, giáo viên và quản trị viên đăng nhập được' (($sv -and $gv -and $admin) -as [bool])

# Đường dẫn quản trị: chỉ ADMIN được vào. Với các vai trò khác phải là 403.
$adminRoutes = @(
  @{ m = 'GET';   p = '/admin/users' },
  @{ m = 'GET';   p = '/admin/audit-logs' },
  @{ m = 'GET';   p = '/health/detail' }
)

Write-Host "`n=== 1. Route quản trị chặn học viên và giáo viên ===" -ForegroundColor Cyan
foreach ($r in $adminRoutes) {
  $a = StatusOf $sv $r.m $r.p
  Check "Học viên gọi $($r.m) $($r.p)" ($a -eq 403) "HTTP $a"
  $b = StatusOf $gv $r.m $r.p
  Check "Giáo viên gọi $($r.m) $($r.p)" ($b -eq 403) "HTTP $b"
  $c = StatusOf $admin $r.m $r.p
  Check "Quản trị viên gọi $($r.m) $($r.p)" ($c -eq 200) "HTTP $c"
}

Write-Host "`n=== 2. Route nghiệp vụ theo vai trò ===" -ForegroundColor Cyan
# Hộp thư duyệt: cán bộ vào được, học viên không.
$a = StatusOf $sv 'GET' '/approvals'
Check 'Học viên gọi GET /approvals' ($a -eq 403) "HTTP $a"

# Quản lý tài liệu: giáo viên vào được danh sách (của mình), học viên không.
$a = StatusOf $sv 'GET' '/documents'
Check 'Học viên gọi GET /documents' ($a -eq 403) "HTTP $a"
$b = StatusOf $gv 'GET' '/documents'
Check 'Giáo viên gọi GET /documents' ($b -eq 200) "HTTP $b"

# Nạp lịch: chỉ ADMIN và ACADEMIC_MANAGER.
$a = StatusOf $gv 'GET' '/classes'
Check 'Giáo viên xem được danh sách lớp' ($a -eq 200) "HTTP $a"
$b = StatusOf $sv 'GET' '/classes'
Check 'Học viên gọi GET /classes' ($b -eq 403) "HTTP $b"

# Lập đơn: chỉ học viên.
$a = StatusOf $gv 'GET' '/submissions'
Check 'Giáo viên gọi GET /submissions' ($a -eq 403) "HTTP $a"

Write-Host "`n=== 3. Không có route nào lọt khi chưa đăng nhập ===" -ForegroundColor Cyan
$anon = New-Object Microsoft.PowerShell.Commands.WebRequestSession
foreach ($p in @('/admin/users', '/admin/audit-logs', '/health/detail', '/approvals', '/documents', '/submissions', '/notifications', '/users/me')) {
  $a = StatusOf $anon 'GET' $p
  Check "Chưa đăng nhập gọi GET $p" ($a -eq 401) "HTTP $a"
}

Write-Host "`n=== 4. Healthcheck công khai cố tình nghèo thông tin ===" -ForegroundColor Cyan
$h = Invoke-RestMethod -Uri "$Api/health"
Check 'Healthcheck công khai gọi được không cần đăng nhập' ($h.service -eq 'api')
Check 'KHÔNG lộ phiên bản, URL nội bộ hay số liệu' `
  (($null -eq $h.dependencies) -and ($null -eq $h.counters) -and ($null -eq $h.memoryMb)) `
  ($h | ConvertTo-Json -Compress)

Write-Host ("`n" + ('-' * 62))
Write-Host "  PASS: $script:Pass    FAIL: $script:Fail"
if ($script:Failures.Count) {
  Write-Host "`n  Các mục không đạt:"; $script:Failures | ForEach-Object { Write-Host "    · $_" }
}
Write-Host ('-' * 62) "`n"
exit ($(if ($script:Fail) { 1 } else { 0 }))
