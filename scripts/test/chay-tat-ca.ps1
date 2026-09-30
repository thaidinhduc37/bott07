<#
  Chạy toàn bộ bộ kiểm thử nghiệm thu (Ngày 13).

  Mỗi ngày trong kế hoạch có một tệp kiểm thử riêng, bám sát tiêu chí nghiệm thu
  của đúng ngày đó. Tệp này chạy tất cả theo thứ tự và tổng kết một lần.

  Giữa các bộ có nghỉ 65 giây: nhiều bộ kết thúc bằng phần cố tình đốt hạn mức
  đăng nhập (5 lần/phút), nên chạy liền nhau sẽ khiến bộ sau trượt vì lý do
  không liên quan gì tới thứ nó định kiểm.

    pwsh scripts/test/chay-tat-ca.ps1
    pwsh scripts/test/chay-tat-ca.ps1 -BoQuaRag    # bỏ phần cần dịch vụ RAG
#>

param(
  [switch]$BoQuaRag,
  [int]$NghiGiay = 65
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

$suites = @(
  @{ ten = 'Ngày 3  — Xác thực và phân quyền';        tep = 'test-auth-rbac.ps1' },
  @{ ten = 'Ngày 3  — Xoay refresh token';            tep = 'test-refresh-rotation.ps1' },
  @{ ten = 'Ngày 9  — Biểu mẫu hành chính';           tep = 'test-forms.ps1' },
  @{ ten = 'Ngày 10 — Chữ ký điện tử nội bộ';         tep = 'test-signing.ps1' },
  @{ ten = 'Ngày 11 — Luồng trình ký hai cấp';        tep = 'test-approval.ps1' },
  @{ ten = 'Ngày 12 — Phân quyền theo route';         tep = 'test-rbac-routes.ps1' },
  @{ ten = 'Ngày 13 — Bảo mật';                       tep = 'test-security.ps1' }
)

$results = @()
$i = 0

foreach ($s in $suites) {
  $path = Join-Path $PSScriptRoot $s.tep
  if (-not (Test-Path $path)) {
    Write-Host "`nBỎ QUA  $($s.ten) — không tìm thấy $($s.tep)" -ForegroundColor Yellow
    $results += [pscustomobject]@{ Bo = $s.ten; KetQua = 'thiếu tệp' }
    continue
  }

  if ($i -gt 0) {
    Write-Host "`n… nghỉ $NghiGiay giây để hạn mức đăng nhập hồi lại`n" -ForegroundColor DarkGray
    Start-Sleep -Seconds $NghiGiay
  }
  $i++

  Write-Host ("`n" + ('=' * 66)) -ForegroundColor Blue
  Write-Host "  $($s.ten)" -ForegroundColor Blue
  Write-Host ('=' * 66) -ForegroundColor Blue

  & pwsh -NoProfile -File $path
  $code = $LASTEXITCODE

  $results += [pscustomobject]@{
    Bo     = $s.ten
    KetQua = $(if ($code -eq 0) { 'ĐẠT' } else { "TRƯỢT (mã $code)" })
  }
}

# --- phần RAG chạy bằng Python, tách riêng vì cần venv của dịch vụ ---
if (-not $BoQuaRag) {
  $py = Join-Path $Root 'server/rag-service/.venv/Scripts/python.exe'
  $ragTest = Join-Path $Root 'scripts/test/test_rag_pipeline.py'
  if ((Test-Path $py) -and (Test-Path $ragTest)) {
    Write-Host ("`n" + ('=' * 66)) -ForegroundColor Blue
    Write-Host "  Ngày 4  — Pipeline RAG (truy xuất + cổng abstention)" -ForegroundColor Blue
    Write-Host ('=' * 66) -ForegroundColor Blue
    & $py -u $ragTest --no-llm
    $results += [pscustomobject]@{
      Bo     = 'Ngày 4  — Pipeline RAG'
      KetQua = $(if ($LASTEXITCODE -eq 0) { 'ĐẠT' } else { "TRƯỢT (mã $LASTEXITCODE)" })
    }
  } else {
    Write-Host "`nBỎ QUA  Pipeline RAG — chưa có venv hoặc tệp kiểm thử" -ForegroundColor Yellow
  }
}

# --- học tập (ôn tập, sổ tay, kế hoạch ôn thi, thống kê): Python hệ thống, gọi API qua HTTP ---
$learning = @(
  @{ ten = 'Học tập — Ôn tập và sổ câu sai';       tep = 'test_learning.py' },
  @{ ten = 'Học tập — Sổ tay và kế hoạch ôn thi';  tep = 'test_notes_exam_plan.py' },
  @{ ten = 'Học tập — Thống kê cho giảng viên';    tep = 'test_insights.py' },
  @{ ten = 'Học tập — Tiến trình của học viên';      tep = 'test_progress.py' },
  @{ ten = 'Lịch — Yêu cầu của giảng viên';        tep = 'test_lecturer_note.py' },
  @{ ten = 'Đào tạo — Lớp, môn học, gán học viên';   tep = 'test_catalog.py' },
  @{ ten = 'Lịch — Sửa lịch và kiểm tra trùng';      tep = 'test_schedule_edit.py' },
  @{ ten = 'Đào tạo — Khoa và phân công';            tep = 'test_faculties.py' },
  @{ ten = 'Đào tạo — Danh mục phòng học';           tep = 'test_rooms.py' },
  @{ ten = 'RAG — Dò số điều trong quy chế';       tep = 'test_article_detection.py' }
)
foreach ($s in $learning) {
  # Mỗi bộ đăng nhập 2-4 tài khoản: nghỉ để không vượt hạn mức 5 lần/phút.
  Write-Host "`n… nghỉ $NghiGiay giây để hạn mức đăng nhập hồi lại`n" -ForegroundColor DarkGray
  Start-Sleep -Seconds $NghiGiay
  Write-Host ("`n" + ('=' * 66)) -ForegroundColor Blue
  Write-Host "  $($s.ten)" -ForegroundColor Blue
  Write-Host ('=' * 66) -ForegroundColor Blue
  & python -u (Join-Path $PSScriptRoot $s.tep)
  $results += [pscustomobject]@{
    Bo     = $s.ten
    KetQua = $(if ($LASTEXITCODE -eq 0) { 'ĐẠT' } else { "TRƯỢT (mã $LASTEXITCODE)" })
  }
}

Write-Host ("`n" + ('=' * 66)) -ForegroundColor Blue
Write-Host '  TỔNG KẾT' -ForegroundColor Blue
Write-Host ('=' * 66) -ForegroundColor Blue
$results | Format-Table -AutoSize

$failed = @($results | Where-Object { $_.KetQua -ne 'ĐẠT' })
if ($failed.Count -eq 0) {
  Write-Host "  Tất cả các bộ đều đạt.`n" -ForegroundColor Green
  exit 0
}
Write-Host "  $($failed.Count) bộ chưa đạt.`n" -ForegroundColor Red
exit 1
