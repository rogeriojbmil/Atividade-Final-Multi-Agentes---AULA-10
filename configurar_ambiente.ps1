# configurar_ambiente.ps1 -- prepara o ambiente do exercício final no Windows. Rode UMA vez, antes da aula.
#
#   cd C:\pcdf\aula10
#   powershell -ExecutionPolicy Bypass -File .\configurar_ambiente.ps1
#
# O que faz: confere o Python, cria o .venv, instala o requirements.txt, cria o .env (com um TOKEN_REGISTRO aleatório),
# pede a sua OPENAI_API_KEY (opcional) e roda o verificar_ambiente.py. Pode rodar de novo sem problema: o que já
# existe é mantido.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }

# Grava o .env em UTF-8 SEM BOM (o Set-Content do Windows PowerShell 5.1 colocaria um BOM no início do arquivo).
function Gravar-Env($linhas) {
    $utf8SemBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), [string[]]$linhas, $utf8SemBom)
}

# 1) Python -----------------------------------------------------------------------------------------------------
Passo "1/5 Procurando o Python (3.10 a 3.13)"
$python = $null
$candidatos = @(
    @{ exe = "py"; args = @("-3.12") }, @{ exe = "py"; args = @("-3.11") }, @{ exe = "py"; args = @("-3.13") },
    @{ exe = "py"; args = @("-3.10") }, @{ exe = "python"; args = @() }
)
foreach ($c in $candidatos) {
    if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $versao = & $c.exe @($c.args + @("-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])")) 2>$null
        if ($LASTEXITCODE -eq 0 -and "$versao" -match "^3\.(1[0-3])\.\d+$" -and "$versao" -ne "3.11.0") {
            $python = $c
            Write-Host "    Python $versao ($($c.exe) $($c.args -join ' '))"
            break
        }
    } catch { }
}
if (-not $python) {
    Write-Host "    Não achei Python 3.10 a 3.13 (o 3.11.0 não serve). Instale em https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "    e marque 'Add python.exe to PATH' na instalação. Depois rode este script de novo." -ForegroundColor Red
    exit 1
}

# 2) Ambiente virtual -------------------------------------------------------------------------------------------
Passo "2/5 Ambiente virtual (.venv)"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "    .venv já existe: mantido"
} else {
    & $python.exe @($python.args + @("-m", "venv", ".venv"))
    Write-Host "    .venv criado"
}

# 3) Dependências -----------------------------------------------------------------------------------------------
Passo "3/5 Instalando as dependências (pode levar alguns minutos na primeira vez)"
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "    Falha no pip install. Leia a mensagem acima." -ForegroundColor Red; exit 1 }
Write-Host "    dependências instaladas"

# 4) .env -------------------------------------------------------------------------------------------------------
Passo "4/5 Arquivo .env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "    .env criado a partir do .env.example"
}
$linhas = Get-Content ".env" -Encoding UTF8
if ($linhas -match "^TOKEN_REGISTRO=troque-este-valor$") {
    $token = -join ((48..57) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $linhas = $linhas -replace "^TOKEN_REGISTRO=troque-este-valor$", "TOKEN_REGISTRO=$token"
    Write-Host "    TOKEN_REGISTRO gerado (aleatório)"
}
if ($linhas -match "^PROVEDOR=openai$" -and $linhas -match "^OPENAI_API_KEY=$") {
    Write-Host "    Cole a sua OPENAI_API_KEY e tecle Enter (ou só Enter para preencher depois no .env):"
    $chave = Read-Host "    OPENAI_API_KEY"
    if ($chave.Trim()) {
        $linhas = $linhas -replace "^OPENAI_API_KEY=$", "OPENAI_API_KEY=$($chave.Trim())"
        Write-Host "    chave gravada no .env (o .env não vai para o git)"
    }
}
Gravar-Env $linhas

# 5) Verificação ------------------------------------------------------------------------------------------------
Passo "5/5 Verificando o ambiente"
& $venvPython verificar_ambiente.py
$resultado = $LASTEXITCODE

Write-Host ""
Write-Host "Para trabalhar no exercício, em cada terminal novo:" -ForegroundColor Green
Write-Host "    cd $PSScriptRoot"
Write-Host "    .venv\Scripts\Activate.ps1"
Write-Host "(Se o PowerShell bloquear a ativação, rode uma vez: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned)"
exit $resultado
