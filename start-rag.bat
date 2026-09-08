@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -u rag_indexer.py
) else (
  python -u rag_indexer.py
)
endlocal
