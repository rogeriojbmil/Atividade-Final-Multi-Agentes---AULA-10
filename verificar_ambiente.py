"""
verificar_ambiente.py -- confere se tudo o que o exercício usa está instalado e funcionando. Rode ANTES da aula.

    python verificar_ambiente.py            # tudo (faz UMA chamada curta ao modelo)
    python verificar_ambiente.py --sem-llm  # pula a chamada ao modelo (não gasta tokens)

[OK] funciona | [FALTA] opcional ou com plano B (o exercício funciona sem) | [ERRO] precisa corrigir antes da aula.

Este arquivo não faz parte do exercício: não precisa ler nem mudar.
"""
import asyncio
import os
import shutil
import sys
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PASTA = Path(__file__).resolve().parent
erros = 0


def ok(msg): print(f"  [OK]    {msg}")
def falta(msg): print(f"  [FALTA] {msg}")


def erro(msg):
    global erros
    erros += 1
    print(f"  [ERRO]  {msg}")


def url_responde(url: str) -> bool:
    try:
        pedido = urllib.request.Request(url, headers={"User-Agent": "curso-pcdf/1.0"})
        with urllib.request.urlopen(pedido, timeout=8) as resposta:
            return resposta.status < 400
    except OSError:
        return False


print("1) Python e pasta")
v = sys.version_info
if (v.major, v.minor, v.micro) == (3, 11, 0):
    erro("Python 3.11.0 tem um bug que impede o openai-agents. Use 3.10, 3.11.1+, 3.12 ou 3.13.")
elif (3, 10) <= (v.major, v.minor) < (3, 14):
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
else:
    erro(f"Python {v.major}.{v.minor} fora da faixa suportada (3.10 a 3.13).")
if Path.cwd().resolve() != PASTA:
    erro(f"rode de dentro da pasta aula10 (você está em {Path.cwd()}). Use: cd {PASTA}")
else:
    ok("rodando de dentro de aula10/")
if sys.prefix == sys.base_prefix:
    falta("o ambiente virtual (.venv) não parece ativado. Windows: .venv\\Scripts\\Activate.ps1 | Linux/Mac: source .venv/bin/activate")
else:
    ok(f"ambiente virtual ativo ({Path(sys.prefix).name})")

print("2) Bibliotecas")
faltando = False
for pacote in ["openai-agents", "openai", "mcp", "langgraph", "langgraph-checkpoint-sqlite", "python-dotenv", "httpx"]:
    try:
        ok(f"{pacote} {version(pacote)}")
    except PackageNotFoundError:
        faltando = True
        erro(f"{pacote} não instalado -> python -m pip install -r requirements.txt")
if faltando:
    print("\nResultado: instale as bibliotecas e rode de novo.")
    sys.exit(1)

from dotenv import load_dotenv  # noqa: E402  (só depois de saber que está instalado)

print("3) Arquivo .env")
if not (PASTA / ".env").exists():
    erro("não existe .env. Windows: copy .env.example .env | Linux/Mac: cp .env.example .env")
load_dotenv(PASTA / ".env")
provedor = os.getenv("PROVEDOR", "openai").strip().lower()
print(f"  PROVEDOR={provedor}")
if provedor == "openai":
    chave = os.getenv("OPENAI_API_KEY", "")
    if chave.startswith("sk-") and len(chave) > 20:
        ok(f"OPENAI_API_KEY preenchida (termina em ...{chave[-4:]})")
    else:
        erro("OPENAI_API_KEY vazia ou com formato estranho no .env")
elif provedor == "ollama":
    ok(f"Ollama em {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')}, modelo {os.getenv('OLLAMA_MODEL', 'llama3.1')}")
else:
    erro(f"PROVEDOR={provedor!r} não existe. Use openai ou ollama.")
token = os.getenv("TOKEN_REGISTRO", "")
if not token:
    erro("TOKEN_REGISTRO vazio no .env (sem ele, toda gravação será negada a partir da Etapa 9)")
elif token == "troque-este-valor":
    falta("TOKEN_REGISTRO ainda é o valor de exemplo: troque por um valor seu (o configurar_ambiente já faz isso)")
else:
    ok("TOKEN_REGISTRO definido")

print("4) Dados do exercício")
try:
    sys.path.insert(0, str(PASTA))
    from dados_rh import carregar_escala, carregar_feriados_locais, carregar_servidores, normas

    ok(f"{len(carregar_servidores())} servidores, {len(carregar_escala())} afastamentos, "
       f"{len(carregar_feriados_locais())} feriados locais, {len(normas())} regras")
except Exception as e:  # noqa: BLE001 - qualquer falha aqui é para o aluno ver
    erro(f"falha ao ler dados/: {type(e).__name__}: {e}")

print("5) MCP Server sobe e lista as tools (sem chamar nenhuma)")
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def listar_tools() -> list[str]:
        params = StdioServerParameters(command=sys.executable, args=[str(PASTA / "etapa05_mcp_rh.py")])
        with open(os.devnull, "w") as silencio:
            async with stdio_client(params, errlog=silencio) as (leitura, escrita):
                async with ClientSession(leitura, escrita) as sessao:
                    await sessao.initialize()
                    return [t.name for t in (await sessao.list_tools()).tools]

    tools = asyncio.run(asyncio.wait_for(listar_tools(), timeout=30))
    if len(tools) == 6:
        ok(f"etapa05_mcp_rh.py no ar com {len(tools)} tools: {', '.join(tools)}")
    else:
        erro(f"etapa05_mcp_rh.py listou {len(tools)} tools (esperado 6): {tools}")
except Exception as e:  # noqa: BLE001
    erro(f"o MCP Server não subiu: {type(e).__name__}: {str(e)[:150]}")

print("6) Node.js (só para o MCP Inspector da Etapa 5)")
if shutil.which("npx"):
    ok("npx encontrado: o MCP Inspector vai funcionar")
else:
    falta("npx não encontrado. Instale o Node.js LTS (nodejs.org) para usar o MCP Inspector; o resto funciona sem ele")

print("7) APIs externas (se falharem, o exercício usa o plano B)")
if url_responde("https://brasilapi.com.br/api/feriados/v1/2027"):
    ok("BrasilAPI (feriados) respondeu")
else:
    falta("BrasilAPI não respondeu: os feriados virão de dados/feriados_2027.json")
if url_responde("https://api.frankfurter.app/latest?from=USD&to=BRL"):
    ok("Frankfurter (câmbio) respondeu")
else:
    falta("Frankfurter não respondeu: a diária no exterior ficará 'a calcular'")

print("8) Modelo de linguagem")
if "--sem-llm" in sys.argv:
    falta("chamada ao modelo pulada (--sem-llm)")
else:
    try:
        from agents import Agent, Runner

        from provedor import configurar

        modelo = configurar()
        resposta = Runner.run_sync(Agent(name="Teste", instructions="Responda só com a palavra: PRONTO"), "Diga a palavra.")
        ok(f"{modelo} respondeu: {resposta.final_output.strip()[:40]!r}")
    except SystemExit as e:
        erro(str(e).splitlines()[0])
    except Exception as e:  # noqa: BLE001 - queremos mostrar qualquer falha de rede/chave
        erro(f"falha ao chamar o modelo: {type(e).__name__}: {str(e)[:150]}")

print()
print("Resultado:", "tudo certo, pode começar pelo PASSO_A_PASSO.md." if erros == 0 else f"{erros} erro(s) para corrigir.")
sys.exit(1 if erros else 0)
