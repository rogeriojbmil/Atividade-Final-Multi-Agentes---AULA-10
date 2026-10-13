"""
ETAPA 5 (continuação) -- Usando o MCP Server do RH de dois jeitos.

  ETAPA 5.3 -- por um AGENTE: o AtendenteRH com MCPServerStdio (o LLM escolhe a tool)
  (PRONTO)  -- por CÓDIGO: chamar_mcp(tool, argumentos), sem LLM (é o que os nós do grafo e as tools dos
               especialistas vão usar: quem decide a tool é o SEU código). Leia: é o mesmo cliente do aula6/desafio2.

REFERÊNCIAS NAS AULAS
  aula5/exemplos/04_agente_mcp/agente.py      MCPServerStdio + Agent(mcp_servers=[...])        (5.3)
  aula5/exemplos/07_multiplos_mcp/agente.py   o agente escolhendo tools sozinho
  aula6/desafio2/main.py                      chamar_mcp() com ClientSession, sem agente (o mesmo deste arquivo)
  aula5/exemplos/02_mcp_basico/cliente.py     cliente MCP "cru" (initialize, call_tool)

Rodar:
    python etapa05_cliente_mcp.py            # chama as tools direto e registra o C1 duas vezes (idempotência, 5.2)
    python etapa05_cliente_mcp.py --agente   # 5.3: o AtendenteRH responde usando o server

Pronto quando: o agente responde "A equipe Cartório tem alguém de férias entre 12 e 26/07/2027?" usando o server, e
registrar o C1 duas vezes gera um único registro.
"""
import asyncio
import json
import os
import sys

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dados_rh import PASTA

load_dotenv(PASTA / ".env")
SERVER = str(PASTA / "etapa05_mcp_rh.py")


async def chamar_mcp_async(tool: str, argumentos: dict) -> dict:
    """(PRONTO) Sobe o MCP Server por stdio, abre a sessão e chama UMA tool pelo nome. Como no aula6/desafio2/main.py.
    Toda tool do etapa05_mcp_rh.py devolve UM dict, que chega como texto JSON no primeiro item de resposta.content."""
    params = StdioServerParameters(command=sys.executable, args=[SERVER])
    with open(os.devnull, "w") as silencio:                               # descarta os logs do server
        async with stdio_client(params, errlog=silencio) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()                                  # o "aperto de mão" do protocolo
                resposta = await sessao.call_tool(tool, argumentos)
    # O erro é levantado DEPOIS de fechar a sessão (dentro dela, viraria um ExceptionGroup difícil de ler).
    if resposta.is_error:
        detalhe = resposta.content[0].text if resposta.content else ""
        raise RuntimeError(f"a tool {tool!r} deu erro DENTRO do server ({detalhe}). "
                           f"Para ver o traceback: npx @modelcontextprotocol/inspector python etapa05_mcp_rh.py")
    return json.loads(resposta.content[0].text)


def chamar_mcp(tool: str, argumentos: dict) -> dict:
    """(PRONTO) Versão síncrona, para os nós do grafo (Etapa 7) e o fluxo linear (Etapa 6).
    Dentro de código async (tools dos agentes), use `await chamar_mcp_async(...)`."""
    return asyncio.run(chamar_mcp_async(tool, argumentos))


# ETAPA 5.3 -- O AtendenteRH da Etapa 1, agora sem a tool local: ele recebe o MCP Server inteiro (mcp_servers=[...])
# e o LLM escolhe sozinho qual tool chamar. O server sobe como subprocesso, com o mesmo Python da .venv.
async def perguntar_ao_atendente(pergunta: str) -> str:
    async with MCPServerStdio(params={"command": sys.executable, "args": [SERVER]}, name="rh",
                              client_session_timeout_seconds=60) as servidor:
        agente = Agent(
            name="AtendenteRH",
            # Nome EXATO do modelo, que o configurar() gravou no ambiente (o SDK passaria para minúsculas: 404).
            model=os.getenv("OPENAI_DEFAULT_MODEL"),
            instructions=(
                "Você é o atendente do setor de Gestão de Pessoas e responde dúvidas dos servidores, em português "
                "do Brasil e de forma breve. Para dados de servidores, escala de equipes, normas ou diárias, use as "
                "tools do servidor MCP e responda com base no resultado; nunca invente dados. "
                "As datas das tools usam o formato AAAA-MM-DD. Não informe salários."
            ),
            mcp_servers=[servidor],
        )
        return (await Runner.run(agente, pergunta)).final_output


if __name__ == "__main__":
    if "--agente" in sys.argv:
        from provedor import configurar
        print(f"[modelo] {configurar()}")
        print(asyncio.run(perguntar_ao_atendente("A equipe Cartório tem alguém de férias entre 12 e 26/07/2027?")))
    else:
        print(chamar_mcp("consultar_servidor", {"matricula": "1002"}))
        print(chamar_mcp("consultar_escala", {"equipe": "Cartório", "inicio": "2027-07-12", "fim": "2027-07-26"}))
        print(chamar_mcp("consultar_normas", {"tema": "abono"}))
        registro = {"protocolo": "teste001", "matricula": "1001", "tipo": "abono", "inicio": "2027-04-09",
                    "fim": "2027-04-09", "decisao": "deferido", "aprovador": "sistema",
                    "despacho": "Despacho de teste.", "token": os.getenv("TOKEN_REGISTRO", "")}
        print("1ª gravação:", chamar_mcp("registrar_decisao", registro))
        print("2ª gravação:", chamar_mcp("registrar_decisao", registro), " <- deve dizer duplicado")
        print(json.dumps({"sem_token": chamar_mcp("registrar_decisao", {**registro, "token": "errado"})},
                         ensure_ascii=False), " <- depois da Etapa 9.2, deve ser negado")