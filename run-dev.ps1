<#
.SYNOPSIS
  Shortcut so you can run the backend from the project root. The real script is backend\run-dev.ps1.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run-dev.ps1 -VoiceDemo
#>
param(
  [int]$Port = 8000,
  [switch]$Demo,
  [switch]$VoiceDemo,
  [switch]$Stop,
  [switch]$NoServer
)
& (Join-Path $PSScriptRoot "backend\run-dev.ps1") @PSBoundParameters
exit $LASTEXITCODE
