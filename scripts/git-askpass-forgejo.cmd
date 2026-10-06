@echo off
for /f "tokens=1,* delims=: " %%a in ('findstr /b /c:"user:" "%USERPROFILE%\.config\rule-warden\forgejo-admin.txt"') do set U=%%b
for /f "tokens=1,* delims=: " %%a in ('findstr /b /c:"pass:" "%USERPROFILE%\.config\rule-warden\forgejo-admin.txt"') do set P=%%b
echo %1 | findstr /i "username" >nul
if %errorlevel%==0 (echo %U%) else (echo %P%)
