@echo off
REM ABRIR SITE - inicia o servidor local e abre o site no navegador.
REM Este e o unico arquivo que voce precisa executar.

cd /d "%~dp0"

if not exist "__offline\servidor.py" (
  echo.
  echo   Nao encontrei __offline\servidor.py.
  echo   Execute este atalho de dentro da pasta que a extensao gerou.
  echo.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "__offline\servidor.py" %*
  goto fim
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "__offline\servidor.py" %*
  goto fim
)

echo.
echo   Python 3 nao encontrado.
echo   Instale em https://www.python.org/downloads/
echo   marcando a opcao "Add Python to PATH", e rode este arquivo de novo.
echo.

:fim
echo.
pause
