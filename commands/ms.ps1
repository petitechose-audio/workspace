#!/usr/bin/env pwsh
# MIDI Studio CLI wrapper for PowerShell

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir

$env:WORKSPACE_ROOT = $WorkspaceRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv not found in PATH"
    Write-Host "install: https://docs.astral.sh/uv/" -ForegroundColor Yellow
    exit 2
}

Set-Location $WorkspaceRoot
& uv run ms @args
exit $LASTEXITCODE
