@echo off
title Skinner Project - Inicializador

echo ===================================================
echo   Iniciando o Skinner Project (API + Dashboard)
echo ===================================================
echo.

:: Vai para a pasta raiz do projeto
cd /d "%~dp0"

echo 1. Iniciando a API FastAPI...
start "Skinner - API (Backend)" cmd /k ".\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000"

echo Aguardando a API iniciar...
timeout /t 3 /nobreak > NUL

echo 2. Iniciando o dashboard Streamlit...
cd app\web
start "Skinner - Painel (Frontend)" cmd /k "..\..\.venv\Scripts\python.exe -m streamlit run dashboard.py --server.address 127.0.0.1 --server.headless true"

echo.
echo Tudo pronto. Os servicos estao vinculados apenas ao computador local.
pause
