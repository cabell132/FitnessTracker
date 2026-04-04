@echo off
REM Hook script wrapper for Windows - calls the Node.js version
node "%~dp0lint.js" < con
