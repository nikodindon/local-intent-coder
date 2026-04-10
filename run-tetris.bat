@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python -u main.py "create a playable Tetris clone in the browser, with colors and sounds" --max_cycles 12 --output output/tetris-test
