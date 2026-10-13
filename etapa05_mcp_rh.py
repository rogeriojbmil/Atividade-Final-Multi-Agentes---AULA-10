"""
ETAPA 5 -- MCP Server do RH (30 min). Volta aqui na ETAPA 9 (token, regra N8 e auditoria).

Os dados saem de dentro do agente e passam a morar num PROCESSO SEPARADO, que fala MCP. O agente (Etapa 5.3) e os
nós do grafo (Etapa 7, via cliente_mcp.chamar_mcp) só enxergam as tools abaixo: nunca os CSVs.

ESQUELETO: implemente as etapas na ordem (troque cada raise NotImplementedError pelo código da etapa).
  ETAPA 5.1 -- as 5 tools de LEITURA: declare cada uma com @mcp.tool(), escreva a DOCSTRING (é o "schema" que o LLM
               lê) e devolva o resultado da consulta pronta de dados_rh.py. Toda tool devolve UM dict.
  ETAPA 5.2 -- a tool de ESCRITA registrar_decisao, IDEMPOTENTE (protocolo repetido não duplica)
  ETAPA 9.2 -- autorização NO SERVER: token + regra N8 (chefia certa, nunca o próprio servidor) + decisão num enum
  ETAPA 9.3 -- auditoria: toda tentativa de escrita (ALLOW ou DENY) vira uma linha em saidas/auditoria.jsonl

REFERÊNCIAS NAS AULAS
  aula6/desafio2/mcp_unidades.py               MCP Server que lê um CSV                          <- o mais parecido (5.1)
  aula5/exemplos/03_mcp_parametros/server.py   tool com parâmetros opcionais
  aula5/exemplos/05_multiplas_tools/server.py  várias tools no mesmo server, tool de "descoberta"
  aula3/agente_retry3.py                       idempotência (5.2)
  aula5/exemplos/10_seguranca/server_seguro.py token, enum fechado e auditoria NO SERVER        <- o mais parecido (9.2/9.3)

Testar sem agente (MCP Inspector, precisa de Node.js):
    npx @modelcontextprotocol/inspector python etapa05_mcp_rh.py

Pronto quando: o Inspector lista as 6 tools; registrar C1 duas vezes gera um único registro.
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from dados_rh import PASTA, SAIDAS, carregar_servidores, diaria, escala_da_equipe, normas, remuneracao, servidor_publico

# O server roda como SUBPROCESSO: ele não herda o ambiente de quem o chamou. Por isso carrega o .env sozinho
# (mesmo cuidado de aula5/exemplos/02_mcp_basico/database.py).
load_dotenv(PASTA / ".env")

mcp = MCPServer("rh-mcp")

ARQUIVO_REGISTROS = SAIDAS / "registros.json"
ARQUIVO_AUDITORIA = SAIDAS / "auditoria.jsonl"
TOKEN_REGISTRO = os.getenv("TOKEN_REGISTRO", "")
DECISOES_VALIDAS = {"deferido", "indeferido", "indeferido_pela_chefia"}
TIPOS_COM_CHEFIA = {"ferias", "diaria"}  # regra N8


def _ler_registros() -> dict:
    """(PRONTO) {protocolo: registro} gravados até agora."""
    if ARQUIVO_REGISTROS.exists():
        return json.loads(ARQUIVO_REGISTROS.read_text(encoding="utf-8"))
    return {}


def _gravar_registros(registros: dict) -> None:
    """(PRONTO)"""
    ARQUIVO_REGISTROS.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ ETAPA 5.1: leitura
# ETAPA 5.1 -- Cadastro de UM servidor, sem o salário (a consulta pronta já tira o dado restrito).
@mcp.tool()
def consultar_servidor(matricula: str) -> dict:
    """Consulta o cadastro de UM servidor pela matrícula, SEM o salário.

    Use para saber nome, equipe, saldo de férias, abonos restantes e chefia imediata de um servidor.

    Args:
        matricula: matrícula do servidor, só os dígitos (ex.: "1002").

    Returns:
        Um dict com os dados do cadastro (sem salário) ou, se a matrícula não existir, um aviso de
        "matrícula não encontrada".
    """
    return servidor_publico(matricula)


# ETAPA 5.1 -- Afastamentos da equipe no período e o limite da regra N5 (30% da equipe, mínimo 1).
@mcp.tool()
def consultar_escala(equipe: str, inicio: str, fim: str) -> dict:
    """Consulta a escala de uma equipe num período: quem já está afastado e quantos podem se afastar (regra N5).

    Use para conferir se um novo afastamento cabe na escala da equipe.

    Args:
        equipe: nome da equipe, como está no cadastro do servidor (ex.: "Cartório").
        inicio: primeiro dia do período, no formato AAAA-MM-DD (ex.: "2027-07-12").
        fim: último dia do período, no formato AAAA-MM-DD (ex.: "2027-07-26").

    Returns:
        Um dict com o tamanho da equipe, o limite de afastados ao mesmo tempo (30% da equipe, mínimo 1) e a lista
        de afastamentos já marcados que se sobrepõem ao período (quem, de quando a quando).
    """
    return escala_da_equipe(equipe, inicio, fim)


# ETAPA 5.1 -- As regras da Norma Interna (dados/normas.md) sobre um tema. A lista vai embrulhada num dict: uma tool
# MCP que devolve LISTA manda cada item separado, e quem chama não distingue "lista com 1 regra" de "1 dict".
@mcp.tool()
def consultar_normas(tema: str) -> dict:
    """Consulta as regras da Norma Interna do RH sobre um tema.

    Use para saber o que a norma diz antes de analisar um pedido. Não invente regras: consulte esta tool.

    Args:
        tema: assunto das regras, em minúsculas e sem acento: "ferias", "prazos", "escala", "abono", "diaria",
            "aprovacao", "saude" ou "dados".

    Returns:
        Um dict {"tema": tema, "regras": [...]} com as regras (N1 a N10) daquele tema; lista vazia se o tema não
        existir.
    """
    return {"tema": tema, "regras": normas(tema)}


# ETAPA 5.1 -- Valor da diária por tipo de destino (regra N7).
@mcp.tool()
def tabela_diarias(tipo_destino: str) -> dict:
    """Consulta o valor da diária de viagem a serviço por tipo de destino (regra N7).

    Args:
        tipo_destino: "capital" (capital de estado brasileiro), "interior" (outra cidade do Brasil) ou
            "exterior" (fora do Brasil).

    Returns:
        Um dict com a moeda (BRL no Brasil, USD no exterior) e o valor de UMA diária.
    """
    return diaria(tipo_destino)


# ETAPA 5.1 -- [RESTRITA] Salário-base: dado sensível, só o Financeiro usa (Etapa 9 e 🆕 B).
@mcp.tool()
def consultar_remuneracao(matricula: str) -> dict:
    """[RESTRITA] Consulta o salário-base de um servidor. Só o agente Financeiro deve usar, para calcular a venda de
    férias (regra N2). Não use para responder perguntas gerais nem repasse o valor ao servidor sem necessidade.

    Args:
        matricula: matrícula do servidor, só os dígitos (ex.: "1002").

    Returns:
        Um dict com o salário-base do servidor ou, se a matrícula não existir, um aviso de "matrícula não encontrada".
    """
    return remuneracao(matricula)


# ------------------------------------------------------------------ ETAPA 5.2 / 9.2 / 9.3: escrita
# ETAPA 9.3 -- Auditoria: toda tentativa de escrita (ALLOW ou DENY) vira UMA linha JSON em saidas/auditoria.jsonl.
# Nunca grava o token (é credencial) nem o despacho (pode ter dado pessoal): os parâmetros já chegam sem os dois.
def _auditar(protocolo: str, decisao_acesso: str, motivo: str, parametros: dict) -> None:
    linha = {
        "quando": datetime.now().isoformat(),
        "thread_id": parametros.get("thread_id", ""),
        "quem": parametros.get("aprovador", ""),
        "tool": "registrar_decisao",
        "protocolo": protocolo,
        "decisao_acesso": decisao_acesso,
        "motivo": motivo,
        "parametros": parametros,
    }
    ARQUIVO_AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
    with ARQUIVO_AUDITORIA.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


# ETAPA 9.2 -- Nega a gravação: registra DENY na auditoria e devolve o erro. Quem nega é o SERVER, não o agente.
def _negar(protocolo: str, motivo: str, parametros: dict) -> dict:
    _auditar(protocolo, "DENY", motivo, parametros)
    return {"sucesso": False, "erro": motivo}


# ETAPA 5.2 + 9.2 -- Única tool de ESCRITA: confere token, decisão e regra N8 ANTES de gravar; grava sem duplicar.
@mcp.tool()
def registrar_decisao(protocolo: str, matricula: str, tipo: str, inicio: str, fim: str, decisao: str,
                      aprovador: str, despacho: str, token: str, thread_id: str = "") -> dict:
    """[ESCRITA -- requer autorização] Grava a decisão final de um pedido. IDEMPOTENTE: se o protocolo já foi
    registrado, não grava de novo e devolve duplicado=True.

    Quem grava é o nó `registrar` do grafo; nenhum agente recebe esta tool (privilégio mínimo, Etapa 9).

    Args:
        protocolo: protocolo idempotente do pedido (ferramentas.gerar_protocolo).
        matricula: matrícula do servidor que fez o pedido (ex.: "1002").
        tipo: tipo do pedido: "ferias", "abono" ou "diaria".
        inicio: primeiro dia do período, AAAA-MM-DD.
        fim: último dia do período, AAAA-MM-DD.
        decisao: "deferido", "indeferido" ou "indeferido_pela_chefia".
        aprovador: matrícula de quem aprovou (a chefia, quando a regra N8 exige).
        despacho: texto do despacho, sem CPF nem dado de saúde (regra N10).
        token: token de registro. Sem ele, a gravação é negada.
        thread_id: identificador da execução do grafo, para ligar o registro à auditoria.

    Returns:
        {"sucesso": True, "protocolo": ...} quando grava; {"sucesso": True, "duplicado": True, ...} quando o
        protocolo já existia; {"sucesso": False, "erro": ...} quando a gravação é negada.
    """
    parametros = {"matricula": matricula, "tipo": tipo, "inicio": inicio, "fim": fim, "decisao": decisao,
                  "aprovador": aprovador, "thread_id": thread_id}

    # ETAPA 9.2 -- autorização NO SERVER, antes de gravar
    if not TOKEN_REGISTRO or token != TOKEN_REGISTRO:
        return _negar(protocolo, "token inválido", parametros)
    if decisao not in DECISOES_VALIDAS:
        return _negar(protocolo, f"decisão inválida: {decisao!r}", parametros)
    if aprovador == matricula:
        return _negar(protocolo, "autoaprovação (N8)", parametros)
    if decisao == "deferido" and tipo in TIPOS_COM_CHEFIA:
        chefia = servidor_publico(matricula).get("chefia")
        if aprovador != chefia:
            return _negar(protocolo, f"aprovador não é a chefia {chefia} (N8)", parametros)

    # ETAPA 5.2 -- idempotência: olhar ANTES de gravar
    registros = _ler_registros()
    if protocolo in registros:
        _auditar(protocolo, "ALLOW", "duplicado", parametros)
        return {"sucesso": True, "duplicado": True, "protocolo": protocolo}

    registros[protocolo] = {**parametros, "despacho": despacho, "registrado_em": datetime.now().isoformat()}
    ARQUIVO_REGISTROS.parent.mkdir(parents=True, exist_ok=True)  # garante a pasta saidas/
    _gravar_registros(registros)
    _auditar(protocolo, "ALLOW", "gravado", parametros)
    return {"sucesso": True, "protocolo": protocolo}


if __name__ == "__main__":
    mcp.run(transport="stdio")