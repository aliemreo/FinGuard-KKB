@echo off
REM Set Windows console to UTF-8 encoding for Turkish characters
chcp 65001 > nul

REM Connect to PostgreSQL database
psql -U postgres -d gazette_db

REM Restore original code page when done
chcp 1252 > nul
