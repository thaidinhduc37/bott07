$API = "http://localhost:5000/api"
$pass = 0; $fail = 0
function Check($n, $c, $d = "") {
  if ($c) { Write-Host "  PASS  $n" -ForegroundColor Green; $script:pass++ }
  else { Write-Host "  FAIL  $n  $d" -ForegroundColor Red; $script:fail++ }
}
function Code($m, $p, $s) {
  try { (Invoke-WebRequest -Uri "$API$p" -Method $m -WebSession $s -UseBasicParsing).StatusCode }
  catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 } }
}
# Doc cookie theo dung path ma server dat (/api/auth), khong phai "/".
function Refresh-Cookie($s) {
  ($s.Cookies.GetCookies("http://localhost:5000/api/auth/refresh") |
    Where-Object { $_.Name -eq "sa_refresh" }).Value
}

Write-Host "`n=== Xoay vong refresh token va phat hien tai su dung ===" -ForegroundColor Cyan

$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-WebRequest -Uri "$API/auth/login" -Method POST -UseBasicParsing -WebSession $s `
  -Body (@{ email = "sv.tranthimai@hvktcnan.edu.vn"; password = "Demo@2026" } | ConvertTo-Json) `
  -ContentType "application/json"
Check "Dang nhap -> 200" ($login.StatusCode -eq 200)

$t0 = Refresh-Cookie $s
Check "Cookie sa_refresh duoc dat sau login" ($t0.Length -gt 20) "len=$($t0.Length)"

Check "Refresh lan 1 -> 200" ((Code "POST" "/auth/refresh" $s) -eq 200)
$t1 = Refresh-Cookie $s
Check "Token da xoay sau lan 1" ($t0 -ne $t1 -and $t1.Length -gt 20)

Check "Refresh lan 2 -> 200" ((Code "POST" "/auth/refresh" $s) -eq 200)
$t2 = Refresh-Cookie $s
Check "Token da xoay sau lan 2" ($t1 -ne $t2 -and $t2.Length -gt 20)

Write-Host "`n--- Dung lai token da thu hoi (t1) ---"
$sOld = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$sOld.Cookies.Add((New-Object System.Net.Cookie("sa_refresh", $t1, "/api/auth", "localhost")))
Check "Token cu t1 -> 401" ((Code "POST" "/auth/refresh" $sOld) -eq 401)

Write-Host "`n--- Phat hien tai su dung phai thu hoi CA phien dang hoat dong ---"
$after = Code "POST" "/auth/refresh" $s
Check "Token dang hop le t2 cung bi thu hoi -> 401" ($after -eq 401) "got $after"

Write-Host "`n--------------------------------------------"
Write-Host "  PASS: $pass    FAIL: $fail" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Red" })
Write-Host "--------------------------------------------`n"

# Ma thoat — xem ghi chu cung loai o cuoi test-auth-rbac.ps1.
exit $(if ($fail) { 1 } else { 0 })
