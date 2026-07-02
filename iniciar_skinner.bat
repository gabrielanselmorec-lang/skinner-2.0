@echo off
title 🧠 Skinner Project - Inicializador

echo ===================================================
echo   Iniciando o Skinner Project (API + Dashboard)
echo ===================================================
echo.

:: Vai para a pasta raiz (se necessário)
cd /d "%~dp0"

echo 1. Ligando o Cerebro (FastAPI)...
start "Skinner - API (Backend)" cmd /k ".\.venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000"

echo Aguardando a API respirar...
timeout /t 3 /nobreak > NUL

echo 2. Ligando a Vitrine (Streamlit)...
:: Entra na pasta app/web antes de rodar o dashboard
cd app\web
start "Skinner - Painel (Frontend)" cmd /k "..\..\.venv\Scripts\python.exe -m streamlit run dashboard.py"

echo.
echo Tudo pronto!
pause