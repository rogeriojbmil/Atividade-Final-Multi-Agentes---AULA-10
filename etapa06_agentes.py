"""
ETAPA 6 -- Os especialistas, cada um com UMA responsabilidade e SÓ as tools de que precisa.

ESQUELETO:
  ETAPA 6.1 -- criar_normas(), criar_escala(), criar_financeiro(), criar_redator()
  ETAPA 6.2 -- criar_coordenador(): usa Normas, Escala e Financeiro como TOOLS (as_tool)

As tools abaixo (PRONTAS) só repassam a chamada ao MCP Server do RH (cliente_mcp.chamar_mcp_async). Dar a cada agente
só as tools dele é o PRIVILÉGIO MÍNIMO (Etapa 9.1); o hook do 🆕 B (etapa10_governanca.py) confere isso em tempo de execução.

REFERÊNCIAS NAS AULAS
  aula4/ex03_agente_as_tool.py                         Coordenador que chama especialistas como tools    <- o mais parecido
  aula2/agente_handoff2.py                             as_tool com tool_name e tool_description
  aula4/ex02_handoff_roteamento.py                     handoff: compare (quem responde no fim?)
  aula7/exemplos/02_agentes_especializados/main.py     uma responsabilidade por agente
  aula7/agentes.py                                     ModelSettings(temperature=0) para respostas mais estáveis
  aula8/exemplos/06_excessive_agency/1_codigo_pronto/main.py   o problema de dar tools DEMAIS a um agente
"""
import json
import os

import httpx
from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel, RunHooks, function_tool
from openai import AsyncOpenAI

from etapa05_cliente_mcp import chamar_mcp_async
from etapa04_ferramentas import cotacao_usd_brl

CONFIG = ModelSettings(temperature=0)


# Modelo de CADA agente, com um cliente HTTP só dele. No grafo (Etapa 7), Normas, Escala e Financeiro rodam ao mesmo
# tempo em threads diferentes; se dividissem o cliente padrão, o pool de conexões do httpx quebra
# ("ValueError: list.remove(x): x not in list"). Usa o nome EXATO do modelo, gravado pelo configurar() do provedor.py
# (sem ele, o SDK passa o nome para minúsculas e o servidor responde 404 -- lição da Etapa 2).
def _modelo():
    nome = os.getenv("OPENAI_DEFAULT_MODEL")
    http = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=0), timeout=180)
    if os.getenv("PROVEDOR", "openai").strip().lower() == "ollama":
        cliente = AsyncOpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama",
                              http_client=http)
        return OpenAIChatCompletionsModel(model=nome, openai_client=cliente)  # o Ollama não tem a Responses API
    cliente = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http)
    return OpenAIResponsesModel(model=nome, openai_client=cliente)


# ------------------------------------------------------------------ tools (PRONTAS)
@function_tool
async def consultar_normas(tema: str) -> str:
    """Regras da norma interna sobre um tema: férias, prazos, escala, abono, diária, aprovação, saúde ou dados."""
    return json.dumps(await chamar_mcp_async("consultar_normas", {"tema": tema}), ensure_ascii=False)


@function_tool
async def consultar_escala(equipe: str, inicio: str, fim: str) -> str:
    """Afastamentos da equipe que se sobrepõem ao período (AAAA-MM-DD) e o limite de afastados da regra N5."""
    return json.dumps(await chamar_mcp_async("consultar_escala", {"equipe": equipe, "inicio": inicio, "fim": fim}),
                      ensure_ascii=False)


@function_tool
async def tabela_diarias(tipo_destino: str) -> str:
    """Moeda e valor da diária para o tipo de destino: capital, interior ou exterior."""
    return json.dumps(await chamar_mcp_async("tabela_diarias", {"tipo_destino": tipo_destino}), ensure_ascii=False)


@function_tool
async def consultar_remuneracao(matricula: str) -> str:
    """[RESTRITA] Salário-base de um servidor. Só para calcular a venda de férias (N2)."""
    print(f"[tool] consultar_remuneracao({matricula}) EXECUTOU")  # o 🆕 B prova que, barrada, ela NÃO executa
    return json.dumps(await chamar_mcp_async("consultar_remuneracao", {"matricula": matricula}), ensure_ascii=False)


@function_tool
def cotacao_dolar() -> str:
    """Cotação atual do dólar em reais (USD->BRL). Devolve 'indisponível' se a API falhar: nunca invente o câmbio."""
    cotacao = cotacao_usd_brl()
    return f"{cotacao:.4f}" if cotacao else "indisponível"


# ------------------------------------------------------------------ ETAPA 6.1: especialistas
# ETAPA 6.1 -- Normas: diz QUAIS regras se aplicam e as explica. Não calcula valores nem consulta a escala.
def criar_normas() -> Agent:
    return Agent(
        name="Normas",
        model=_modelo(),
        model_settings=CONFIG,
        instructions=(
            "Você é o especialista em NORMAS do RH. Sua única responsabilidade: dizer quais regras da norma interna "
            "se aplicam ao pedido e explicá-las em linguagem simples, em português do Brasil. "
            "Use a tool consultar_normas com o tema do pedido ('ferias', 'abono' ou 'diaria'; se precisar, também "
            "'prazos', 'escala' e 'aprovacao'). Liste as regras CUMPRIDAS e as VIOLADAS, citando o código (N1, N2...). "
            "As violações objetivas que você receber foram calculadas por código e são definitivas: explique-as, "
            "nunca as contradiga. Não calcule valores e não consulte a escala. Seja breve."
        ),
        tools=[consultar_normas],
    )


# ETAPA 6.1 -- Escala: confere a N5 e, havendo conflito, SUGERE outro período.
def criar_escala() -> Agent:
    return Agent(
        name="Escala",
        model=_modelo(),
        model_settings=CONFIG,
        instructions=(
            "Você é o especialista em ESCALA do RH. Sua única responsabilidade: conferir a regra N5 (afastados ao "
            "mesmo tempo na equipe) com a tool consultar_escala (datas no formato AAAA-MM-DD). Desconsidere o "
            "afastamento do próprio servidor do pedido. Se não houver conflito, diga isso em uma frase. "
            "Se houver conflito, diga quem já está afastado e SUGIRA outro período com o MESMO número de dias, "
            "começando DEPOIS do fim do afastamento que conflita, numa segunda, terça ou quarta-feira que não seja "
            "véspera de feriado (regra N3), e confira a sugestão com consultar_escala. Responda em português do "
            "Brasil, de forma breve, com as datas em AAAA-MM-DD."
        ),
        tools=[consultar_escala],
    )


# ETAPA 6.1 -- Financeiro: calcula a venda de férias (N2) e as diárias (N7). É o ÚNICO agente que vê o salário.
def criar_financeiro() -> Agent:
    return Agent(
        name="Financeiro",
        model=_modelo(),
        model_settings=CONFIG,
        instructions=(
            "Você é o especialista FINANCEIRO do RH. Sua única responsabilidade: calcular valores, mostrando a conta.\n"
            "- Venda de férias (N2): use consultar_remuneracao e calcule dias_vendidos x salario_base / 30. "
            "Ex.: 10 dias com salário de R$ 9.500 = 10 x 9500 / 30 = R$ 3.166,67.\n"
            "- Diárias (N7): use tabela_diarias com o tipo de destino. Conte uma diária por pernoite (noites entre a "
            "data de início e a de fim) mais MEIA diária no dia do retorno. Ex.: de 08/06 a 11/06 = 3 pernoites + "
            "meia = 3,5 diárias. No exterior, o valor é em USD: use cotacao_dolar e converta para reais; se a "
            "cotação vier 'indisponível', informe o valor em USD e escreva 'valor em reais: a calcular'. "
            "Nunca invente o câmbio.\n"
            "- Abono e pedidos sem venda nem diária: responda 'sem valor a calcular'.\n"
            "Informe só o resultado do cálculo; não repita o salário em outras partes da resposta. "
            "Responda em português do Brasil, de forma breve."
        ),
        tools=[tabela_diarias, consultar_remuneracao, cotacao_dolar],
    )


# ETAPA 6.1 -- Redator: escreve o despacho só com os fatos recebidos. Sem tools: não busca nada, só redige.
def criar_redator() -> Agent:
    return Agent(
        name="Redator",
        model=_modelo(),
        model_settings=CONFIG,
        instructions=(
            "Você é o REDATOR do RH. Escreva o DESPACHO do pedido em português do Brasil, em um parágrafo formal, "
            "usando SOMENTE os fatos recebidos (não invente nada). O despacho DEVE conter:\n"
            "- a matrícula do servidor;\n"
            "- o período com as datas no formato AAAA-MM-DD (ex.: 2027-04-09);\n"
            "- a decisão, com a palavra exata 'deferido' ou 'indeferido';\n"
            "- as regras citadas (N1, N2...) e os valores calculados, quando houver;\n"
            "- no indeferimento, o motivo e a sugestão de outro período, se houver.\n"
            "Nunca escreva CPF, CID, diagnóstico ou outro dado de saúde, nem o salário do servidor (regra N10). "
            "Se receber um FEEDBACK (da validação ou da chefia), corrija o despacho conforme o feedback."
        ),
    )


# ------------------------------------------------------------------ ETAPA 6.2: coordenador
def criar_coordenador(hooks: RunHooks | None = None, tools_extras: list | None = None) -> Agent:
    # ETAPA 6.2 -- Agent(name="Coordenador", instructions=..., tools=[
    #       criar_normas().as_tool(tool_name="parecer_normas", tool_description=..., hooks=hooks,
    #                              failure_error_function=None),
    #       criar_escala().as_tool(tool_name="parecer_escala", ..., hooks=hooks, failure_error_function=None),
    #       criar_financeiro().as_tool(tool_name="parecer_financeiro", ..., hooks=hooks, failure_error_function=None),
    #       *(tools_extras or [])])
    #   O Coordenador decide QUAIS especialistas consultar (abono não precisa do Financeiro) e junta os pareceres.
    #   hooks=hooks nas as_tool faz o hook do 🆕 B enxergar também as tools DENTRO de cada especialista.
    #   failure_error_function=None: sem isso, um erro dentro do especialista (inclusive o bloqueio do 🆕 B) vira só
    #   um texto de erro para o Coordenador, que segue em frente. Com None, o erro interrompe a execução.
    #   tools_extras serve só para o teste do 🆕 B (dar de propósito consultar_remuneracao ao Coordenador).
    #   Referência: aula4/ex03_agente_as_tool.py
    return Agent(
        name="Coordenador",
        model=_modelo(),
        model_settings=CONFIG,
        instructions=(
            "Você é o COORDENADOR da análise de pedidos do RH. Consulte os especialistas certos e junte os pareceres "
            "num parecer único, em português do Brasil, dizendo o que cada especialista concluiu.\n"
            "- Sempre consulte parecer_normas e parecer_escala.\n"
            "- Consulte parecer_financeiro SÓ quando houver valor a calcular: férias com dias vendidos ou diária. "
            "Abono não precisa do Financeiro.\n"
            "Ao chamar cada especialista, envie os dados do pedido de que ele precisa (tipo, matrícula, equipe, "
            "datas em AAAA-MM-DD, dias vendidos, destino, tipo de destino e as violações objetivas). "
            "As violações objetivas recebidas são definitivas: não as contradiga. Não invente dados."
        ),
        tools=[
            criar_normas().as_tool(
                tool_name="parecer_normas",
                tool_description="Especialista em Normas: quais regras se aplicam ao pedido, cumpridas e violadas.",
                hooks=hooks, failure_error_function=None),
            criar_escala().as_tool(
                tool_name="parecer_escala",
                tool_description="Especialista em Escala: confere a regra N5 e sugere outro período se houver conflito.",
                hooks=hooks, failure_error_function=None),
            criar_financeiro().as_tool(
                tool_name="parecer_financeiro",
                tool_description="Especialista Financeiro: valor da venda de férias (N2) ou das diárias (N7).",
                hooks=hooks, failure_error_function=None),
            *(tools_extras or []),
        ],
    )