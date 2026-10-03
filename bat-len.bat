@echo off
rem Bat Tro ly ao: Docker (PostgreSQL + ChromaDB + backend) + giao dien web, roi mo trinh duyet.
cd /d "%~dp0"

docker info >nul 2>&1
if not errorlevel 1 goto docker_san_sang
echo Dang bat Docker Desktop...
start "" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
:cho_docker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto cho_docker

:docker_san_sang
echo Dang bat PostgreSQL, ChromaDB va backend...
docker compose --env-file server\.env -f docker-compose.dev.yml up -d postgres chroma server
if errorlevel 1 goto loi_docker

curl -s -o nul http://localhost:5173
if not errorlevel 1 goto web_san_sang
echo Dang bat giao dien web...
start "sa - web" cmd /k "cd /d %~dp0client && npm run dev"
:cho_web
timeout /t 2 /nobreak >nul
curl -s -o nul http://localhost:5173
if errorlevel 1 goto cho_web

:web_san_sang
start "" http://localhost:5173
echo Xong. Dong cua so "sa - web" de tat giao dien.
timeout /t 5 >nul
exit /b 0

:loi_docker
echo Khong bat duoc Docker. Xem thong bao loi o tren.
pause
exit /b 1
