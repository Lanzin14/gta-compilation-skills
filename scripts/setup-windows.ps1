<#
.SYNOPSIS
  Instala as ferramentas usadas pelas skills gta-compilation no Windows.

.DESCRIPTION
  Verifica e, se faltar, instala via winget: Git (exigido pelo Claude Code no Windows),
  Python 3.12 e FFmpeg. Depois instala yt-dlp e Whisper com pip.
  Pode ser executado varias vezes: o que ja estiver instalado e pulado.

.PARAMETER SkipWhisper
  Nao instala o Whisper (o pacote + PyTorch ocupam alguns GB).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
#>
param(
    [switch]$SkipWhisper
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }

function Update-SessionPath {
    # Recarrega o PATH do registro para enxergar programas recem-instalados nesta mesma janela.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-WithWinget($id, $command) {
    if (Test-Command $command) {
        Write-Ok "$command ja instalado"
        return
    }
    Write-Host "  Instalando $id ..."
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    # -1978335189 = APPINSTALLER_CLI_ERROR_PACKAGE_ALREADY_INSTALLED (instalado, mas fora do PATH desta janela)
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        throw "winget falhou ao instalar $id (codigo $LASTEXITCODE)."
    }
    Update-SessionPath
    if (Test-Command $command) {
        Write-Ok "$command instalado"
    } else {
        Write-Warn2 "$id instalado, mas '$command' ainda nao esta no PATH. Feche e abra o terminal e rode o script de novo."
    }
}

# ---------------------------------------------------------------- 1. winget
Write-Step 'Verificando o winget'
if (-not (Test-Command 'winget')) {
    throw 'winget nao encontrado. Instale o "Instalador de Aplicativo" (App Installer) pela Microsoft Store e rode o script de novo.'
}
Write-Ok 'winget disponivel'

# ---------------------------------------------------------------- 2. programas
Write-Step 'Git, Python e FFmpeg'
Install-WithWinget 'Git.Git' 'git'
Install-WithWinget 'Python.Python.3.12' 'py'
Install-WithWinget 'Gyan.FFmpeg' 'ffmpeg'

if (-not (Test-Command 'py')) {
    throw "O lancador 'py' do Python nao foi encontrado. Feche e abra o terminal e rode o script de novo."
}

# ---------------------------------------------------------------- 3. pacotes Python
Write-Step 'Pacotes Python (yt-dlp e Whisper)'
$packages = @('yt-dlp')
if (-not $SkipWhisper) { $packages += 'openai-whisper' }

py -3 -m pip install --user --upgrade pip
py -3 -m pip install --user --upgrade @packages
if ($LASTEXITCODE -ne 0) { throw 'pip falhou ao instalar os pacotes.' }

# Os executaveis do pip --user ficam numa pasta Scripts que nem sempre esta no PATH.
$scripts = (py -3 -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))").Trim()
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($scripts -and (($userPath -split ';') -notcontains $scripts)) {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$scripts", 'User')
    Write-Ok "Adicionado ao PATH do usuario: $scripts"
}
Update-SessionPath

# ---------------------------------------------------------------- 4. verificacao
Write-Step 'Verificacao final'
$checks = [ordered]@{
    'git'     = { git --version }
    'ffmpeg'  = { (ffmpeg -version)[0] }
    'yt-dlp'  = { yt-dlp --version }
}
if (-not $SkipWhisper) { $checks['whisper'] = { whisper --help | Select-Object -First 1 } }

$failed = @()
foreach ($name in $checks.Keys) {
    try {
        $out = & $checks[$name] 2>&1 | Select-Object -First 1
        Write-Ok "$name -> $out"
    } catch {
        Write-Warn2 "$name nao respondeu: $($_.Exception.Message)"
        $failed += $name
    }
}

# drawtext (credito @autor) e subtitles (legendas) precisam estar no ffmpeg
$filters = ffmpeg -hide_banner -filters 2>&1 | Out-String
foreach ($f in @('drawtext', 'subtitles', 'loudnorm')) {
    if ($filters -match "\s$f\s") { Write-Ok "ffmpeg tem o filtro $f" }
    else { Write-Warn2 "ffmpeg SEM o filtro $f"; $failed += "ffmpeg:$f" }
}

if ($failed.Count -gt 0) {
    Write-Host "`nFaltando: $($failed -join ', '). Feche e abra o terminal e rode o script de novo." -ForegroundColor Yellow
    exit 1
}
Write-Host "`nTudo pronto! Proximo passo: siga o checklist em docs\INSTALACAO-WINDOWS.md" -ForegroundColor Green
