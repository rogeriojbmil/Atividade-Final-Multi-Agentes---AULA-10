"""
ETAPAS 7, 8, 9 e 10 (e o opcional 🆕 C) -- O sistema como GRAFO (LangGraph), com persistência, humanos no fluxo e segurança.

Reaproveite TUDO o que você já fez: cada nó só chama funções e agentes das etapas anteriores e devolve O QUE MUDOU
no estado (mais o próprio nome em "caminho").

ESQUELETO: implemente as etapas na ordem (troque cada raise NotImplementedError pelo código da etapa).
  ETAPA 7.1 -- confira o Estado (o reducer de `violacoes`)
  ETAPA 7.2 -- nós e roteadores da ENTRADA: proteger_entrada, extrair, identificar_servidor, calcular_periodo
  ETAPA 7.3 -- PARALELISMO: normas, escala e financeiro (fan-out) e consolidar (fan-in)
  ETAPA 7.4 -- CICLO: redigir_despacho <-> validar, no máximo 3 tentativas
  ETAPA 7.5 -- registrar (MCP) e construir(): nós, arestas fixas e condicionais
  ETAPA 8.1 -- compilar com o checkpointer SQLite (já está em main(); confira)
  ETAPA 8.2 -- aprovacao_chefia com interrupt()
  ETAPA 8.3 -- rotear_chefia: aprovado / rejeitado (máx. 2) / indeferido_pela_chefia
  ETAPA 8.4 -- retomar() com Command(resume=...) (o listar_pendentes() já vem pronto: leia)
  ETAPA 9.4 -- guardrail de SAÍDA no registrar (despacho sem CPF/CID, N10)
  (ETAPA 9.2/9.3 ficam no etapa05_mcp_rh.py; ETAPA 10 em etapa10_observabilidade.py e etapa10_governanca.py)
  --- OPCIONAIS (bônus): o grafo funciona sem eles. Faça só se sobrar tempo, depois da Etapa 9.
  🆕 A     -- ligue USAR_VOTACAO = True (depois de fazer o 🆕 A em etapa02_extracao.py)
  🆕 C.1   -- proteger_entrada com DUAS faixas (ok / dúvida / bloqueado)
  🆕 C.2   -- triagem_humana com interrupt() e rotear_triagem; depois ligue USAR_TRIAGEM_HUMANA = True

REFERÊNCIAS NAS AULAS
  aula6/exemplos/05_multiplos_nos/main.py          nós devolvem só o que mudou
  aula6/exemplos/06_fluxo_condicional/main.py      add_conditional_edges com roteador                      (7.2)
  aula6/exemplos/07_dag/main.py                    ramifica e converge                                     (7.3)
  aula7/exemplos/08_paralelismo/main.py            fan-out / fan-in por LISTA e o conflito de escrita      (7.3)
  aula6/exemplos/08_fluxo_ciclico/main.py          ciclo com condição de parada + recursion_limit          (7.4)
  aula6/exemplos/11_grafo_real/main.py             nós de LLM, MCP, API de feriados e tool local, num DAG + ciclo
  aula6/desafio2/main.py                           LLM + MCP + API + ciclo, com caminho percorrido         <- o mais parecido (7)
  aula7/exemplos/05_equipe_multiagente/main.py     especialistas como NÓS (aqui não há mais Coordenador)
  aula8/exemplos/10_agentes_e_grafo/1_codigo_pronto/main.py   agente decide, grafo controla
  aula7/exemplos/04_persistencia/main.py           SqliteSaver, thread_id, get_state, retomar em outro processo  (8.1)
  aula7/exemplos/06_human_in_the_loop/main.py      interrupt() e Command(resume=...)                       (8.2/8.4, 🆕 C)
  aula7/exemplos/07_aprovacao_revisao/main.py      rejeição com feedback e limite de tentativas            <- o mais parecido (8.3)
  aula7/desafio2/                                  duas pessoas decidindo no mesmo fluxo                   (🆕 C)
  aula8/exemplos/05_guardrail_saida/1_codigo_pronto/main.py   conferir a saída antes de entregar         (9.4)
  aula6/exemplos/04_langgraph_basico/main.py       app.get_graph().draw_mermaid()

Rodar (a partir de aula10/):
    python etapa07_grafo.py C2_ferias_com_venda           # um caso (o nome do caso é o thread_id)
    python etapa07_grafo.py --todos                       # os 12 casos
    python etapa07_grafo.py --pendentes                   # quem está pausado e onde (pronto)
    python etapa07_grafo.py --retomar C2_ferias_com_venda sim 1010             # a chefia 1010 aprova
    python etapa07_grafo.py --retomar C2_ferias_com_venda "nao:mude as datas" 1010
    python etapa07_grafo.py --retomar C10_zona_cinzenta "sim:tratar como abono" rh   # 🆕 C (opcional): o atendente do RH decide
    python etapa07_grafo.py --sem-guardrail C7_autoaprovacao   # ETAPA 9.5: o server ainda nega?
    python etapa07_grafo.py --mermaid                     # o diagrama
"""
import asyncio
import operator
import os
import re
import sys
from typing import Annotated, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import etapa06_agentes as agentes
from etapa05_cliente_mcp import chamar_mcp
from dados.casos import CASOS
from dados_rh import SAIDAS
from etapa02_extracao import extrair, extrair_com_votacao
from etapa04_ferramentas import gerar_protocolo, rodar_com_limites_sync
from etapa03_guardrails import LIMIAR, MENSAGENS, encontrar_dado_sensivel, nota_escopo
from etapa10_governanca import Governanca
from etapa10_observabilidade import medido
from provedor import configurar
from etapa06_regras import precisa_chefia, resumo_periodo, violacoes_objetivas

MODELO = configurar()

MAX_TENTATIVAS = 3     # ciclo redigir <-> validar
MAX_REJEICOES = 2      # ciclo chefia -> redigir
USAR_VOTACAO = False          # 🆕 A (opcional): True usa os 3 extratores com votação (etapa02_extracao.py)
USAR_TRIAGEM_HUMANA = False   # 🆕 C (opcional): True liga as duas faixas e o nó triagem_humana
LIMIAR_OK = 0.4        # 🆕 C: abaixo disto, segue direto
LIMIAR_BLOQUEIO = 0.8  # 🆕 C: a partir disto, bloqueia; entre os dois, um humano decide
GUARDRAIL_LIGADO = "--sem-guardrail" not in sys.argv  # ETAPA 9.5
TEMPO_LIMITE = 300     # segundos por agente: o modelo local leva mais que os 90 s padrão do rodar_com_limites


# ETAPA 10.1 -- Roda um agente com os limites da Etapa 4 e com o hook Governanca, que registra tools e tokens.
# Todo nó com LLM passa por aqui: é assim que o medido() (Etapa 10.2) sabe quantos tokens cada nó gastou.
def _rodar(agente, entrada: str):
    return rodar_com_limites_sync(agente, entrada, timeout_s=TEMPO_LIMITE, hooks=Governanca(verbose=False))


# ------------------------------------------------------------------ ETAPA 7.1: o estado
# Estado: a "memória" que passa de nó em nó. Cada nó lê o que precisa e devolve só as chaves que mudou.
# Campos com reducer (Annotated[..., operator.add]) ACUMULAM o que cada nó devolve, em vez de sobrescrever.
class Estado(TypedDict, total=False):
    thread_id: str
    texto: str
    bloqueado: bool
    motivo_bloqueio: str
    nota_escopo: float
    triagem: dict                 # 🆕 C: {"segue": bool, "orientacao": str, "quem": str}
    pedido: dict                  # Pedido.model_dump(mode="json")
    divergencia: bool             # 🆕 A
    servidor: dict
    periodo: dict
    escala: dict
    parecer_normas: str
    parecer_escala: str
    parecer_financeiro: str
    violacoes: Annotated[list[str], operator.add]  # ETAPA 7.1: reducer -- ramos do mesmo passo ACRESCENTAM, não sobrescrevem
    decisao: str                  # "deferido" | "indeferido" | "indeferido_pela_chefia"
    despacho: str
    tentativas: int
    erro_validacao: str
    rejeicoes: int
    feedback_chefia: str
    aprovador: str
    protocolo: str
    resultado: str                # o desfecho, para a tabela da Etapa 11
    caminho: Annotated[list[str], operator.add]   # cada nó só ACRESCENTA o próprio nome


# ------------------------------------------------------------------ nós PRONTOS
# Nó inicial (PRONTO): limpa o texto e zera os contadores do ciclo (tentativas, rejeições) e as listas.
def receber(estado: Estado) -> dict:
    return {"texto": estado["texto"].strip(), "tentativas": 0, "rejeicoes": 0, "violacoes": [],
            "erro_validacao": "", "feedback_chefia": "", "caminho": ["receber"]}


# Nó final (PRONTO): o pedido foi barrado na entrada; devolve o motivo (ou a orientação do atendente, no 🆕 C).
def recusar(estado: Estado) -> dict:
    orientacao = (estado.get("triagem") or {}).get("orientacao")
    return {"resultado": "recusado", "despacho": orientacao or estado.get("motivo_bloqueio", ""), "caminho": ["recusar"]}


# Nó final (PRONTO): faltou matrícula/datas (ou a leitura ficou ambígua); pede ao servidor que complete.
def pedir_dados(estado: Estado) -> dict:
    faltam = "a matrícula e as datas exatas (AAAA-MM-DD)"
    if estado.get("divergencia"):
        faltam = "as datas e o tipo do pedido (a leitura do seu texto ficou ambígua)"
    return {"resultado": "pediu_dados", "despacho": f"Para seguir, informe {faltam}.", "caminho": ["pedir_dados"]}


# ------------------------------------------------------------------ ETAPA 7.2: entrada
# Nó de ENTRADA: as duas barreiras da Etapa 3 em sequência -- regex de CPF/CID (sem LLM) e nota de escopo (LLM).
# Só marca "bloqueado" no estado; quem decide o caminho é o roteador logo abaixo.
def proteger_entrada(estado: Estado) -> dict:
    # ETAPA 7.2 -- se GUARDRAIL_LIGADO:
    #   encontrar_dado_sensivel(texto) -> {"bloqueado": True, "motivo_bloqueio": MENSAGENS["cpf" ou "cid"]}
    #   nota, motivo = nota_escopo(texto); nota >= LIMIAR -> bloqueado com MENSAGENS["fora_do_escopo"]
    #   Guarde "nota_escopo" no estado. Sempre devolva "caminho": ["proteger_entrada"].
    # 🆕 C.1 (opcional) -- com USAR_TRIAGEM_HUMANA, troque o LIMIAR único por DUAS faixas: < LIMIAR_OK segue;
    #   >= LIMIAR_BLOQUEIO bloqueia; no meio, bloqueado=False com a nota no estado: o roteador manda para triagem_humana.
    if not GUARDRAIL_LIGADO:  # ETAPA 9.5: testa o que ainda segura o sistema sem a barreira de entrada
        return {"bloqueado": False, "caminho": ["proteger_entrada"]}
    texto = estado["texto"]
    sensivel = encontrar_dado_sensivel(texto)  # regex primeiro: o dado sensível nem chega ao LLM
    if sensivel:
        return {"bloqueado": True, "motivo_bloqueio": MENSAGENS[sensivel], "caminho": ["proteger_entrada"]}
    nota, _motivo = nota_escopo(texto)  # o mesmo classificador da Etapa 3 (conferir.py simula esta função)
    # 🆕 C.1: com a triagem humana ligada, só bloqueia a partir de LIMIAR_BLOQUEIO (a faixa do meio vai para um humano)
    bloqueado = nota >= (LIMIAR_BLOQUEIO if USAR_TRIAGEM_HUMANA else LIMIAR)
    return {"bloqueado": bloqueado, "nota_escopo": nota,
            "motivo_bloqueio": MENSAGENS["fora_do_escopo"] if bloqueado else "", "caminho": ["proteger_entrada"]}


# Roteador: só LÊ o estado e devolve um rótulo; o rótulo é a chave do dicionário em add_conditional_edges.
def rotear_entrada(estado: Estado) -> str:
    # ETAPA 7.2 -- "bloqueado" ou "ok".
    #   🆕 C.1 (opcional) -- com USAR_TRIAGEM_HUMANA, também "duvida" (nota entre LIMIAR_OK e LIMIAR_BLOQUEIO)
    if estado.get("bloqueado"):
        return "bloqueado"
    if USAR_TRIAGEM_HUMANA and estado.get("nota_escopo", 0) >= LIMIAR_OK:  # 🆕 C.1: zona cinzenta
        return "duvida"
    return "ok"


# 🆕 C (opcional): um atendente do RH decide se um pedido "em dúvida" segue, pausando o grafo com interrupt().
def triagem_humana(estado: Estado) -> dict:
    # 🆕 C.2 (opcional) -- resposta = interrupt({"pergunta": "Este texto deve seguir como pedido ao RH?",
    #                                  "texto": ..., "nota": ..., "quem_decide": "atendente do RH"})
    #   `resposta` é o que o retomar() entregar: {"segue": bool, "orientacao": str, "quem": str}.
    #   Se segue, ANEXE a orientação ao texto (ex.: "[RH: tratar como abono]") para o extrator usar.
    #   Lembre: na retomada este nó roda DE NOVO desde o início -- nada com efeito colateral antes do interrupt().
    #   Conceito: aula7/exemplos/06_human_in_the_loop/main.py (lá o humano aprova a SAÍDA; aqui decide a ENTRADA)
    resposta = interrupt({"pergunta": "Este texto deve seguir como pedido ao RH?", "texto": estado["texto"],
                          "nota": estado.get("nota_escopo"), "quem_decide": "atendente do RH"})
    # Daqui para baixo só roda na RETOMADA: `resposta` é o que o retomar() entregou.
    if resposta.get("segue"):
        texto = estado["texto"]
        if resposta.get("orientacao"):
            texto += f"\n[RH: {resposta['orientacao']}]"  # a orientação do atendente vai junto para o extrator
        return {"triagem": resposta, "texto": texto, "caminho": ["triagem_humana"]}
    return {"triagem": resposta, "caminho": ["triagem_humana"]}


# 🆕 C (opcional): depois da triagem humana, segue para a extração ou vai para recusar.
def rotear_triagem(estado: Estado) -> str:
    # 🆕 C.2 -- "segue" ou "recusa"
    return "segue" if (estado.get("triagem") or {}).get("segue") else "recusa"


# Nó de LLM: o Extrator da Etapa 2 transforma o texto livre num Pedido estruturado (com votação, no 🆕 A).
def no_extrair(estado: Estado) -> dict:
    # ETAPA 7.2 -- pedido = extrair(texto); divergencia = False
    #   🆕 A (opcional) -- se USAR_VOTACAO: pedido, divergencia, votos = asyncio.run(extrair_com_votacao(texto))
    #   Devolva {"pedido": pedido.model_dump(mode="json"), "divergencia": ..., "caminho": ["extrair"]}
    if USAR_VOTACAO:
        pedido, divergencia, _votos = asyncio.run(extrair_com_votacao(estado["texto"]))
    else:
        pedido, divergencia = extrair(estado["texto"]), False  # o extrator da Etapa 2 (conferir.py simula esta função)
    return {"pedido": pedido.model_dump(mode="json"), "divergencia": divergencia, "caminho": ["extrair"]}


# Roteador: sem matrícula, sem datas exatas, tipo indefinido/saúde ou votação divergente -> pedir_dados.
def rotear_extracao(estado: Estado) -> str:
    # ETAPA 7.2 -- "incompleto" se divergencia, ou sem matrícula, ou sem data_inicio/data_fim; senão "ok".
    #   (pedido de licença de saúde também não segue: N9 -- mande para "incompleto" ou crie um nó próprio)
    pedido = estado["pedido"]
    if (estado.get("divergencia") or not pedido.get("matricula") or not pedido.get("data_inicio")
            or not pedido.get("data_fim") or pedido.get("tipo") in ("licenca_saude", "outro")):
        return "incompleto"
    return "ok"


# Nó de MCP (sem LLM): busca o cadastro do servidor no MCP Server, pelo chamar_mcp da Etapa 5.
def identificar_servidor(estado: Estado) -> dict:
    # ETAPA 7.2 -- servidor = chamar_mcp("consultar_servidor", {"matricula": ...}) -> {"servidor": servidor, ...}
    servidor = chamar_mcp("consultar_servidor", {"matricula": estado["pedido"]["matricula"]})
    return {"servidor": servidor, "caminho": ["identificar_servidor"]}


# Roteador: matrícula que não existe no cadastro -> pedir_dados.
def rotear_servidor(estado: Estado) -> str:
    # ETAPA 7.2 -- "nao_encontrado" se o MCP devolveu {"erro": ...}; senão "ok"
    servidor = estado.get("servidor") or {}
    return "nao_encontrado" if "erro" in servidor or "equipe" not in servidor else "ok"


# Nó de API + MCP (sem LLM): dias úteis e feriados (BrasilAPI ou arquivo local) e a escala da equipe no período.
def calcular_periodo(estado: Estado) -> dict:
    # ETAPA 7.2 -- periodo = resumo_periodo(inicio, fim)  (API de feriados, Etapa 4)
    #              escala  = chamar_mcp("consultar_escala", {"equipe": ..., "inicio": ..., "fim": ...})
    #   Devolva os dois (e "fonte_feriados" se quiser a métrica da Etapa 10).
    pedido = estado["pedido"]
    periodo = resumo_periodo(pedido["data_inicio"], pedido["data_fim"])
    escala = chamar_mcp("consultar_escala", {"equipe": estado["servidor"]["equipe"],
                                             "inicio": pedido["data_inicio"], "fim": pedido["data_fim"]})
    return {"periodo": periodo, "escala": escala, "caminho": ["calcular_periodo"]}


# ------------------------------------------------------------------ ETAPA 7.3: paralelismo
# Auxiliar (PRONTO): o texto com os fatos que os especialistas recebem (o servidor já vem sem salário).
def _fatos(estado: Estado) -> str:
    """(PRONTO) O que os especialistas recebem: pedido, servidor (sem salário), período e escala."""
    return (f"PEDIDO: {estado['pedido']}\nSERVIDOR: {estado['servidor']}\n"
            f"PERÍODO: {estado['periodo']}\nESCALA DA EQUIPE: {estado['escala']}")


# Ramo PARALELO 1 (fan-out): o especialista Normas explica as regras. Escreve SÓ no seu campo (parecer_normas).
def no_normas(estado: Estado) -> dict:
    # ETAPA 7.3 -- rode agentes.criar_normas() com rodar_com_limites_sync(_fatos(estado)) e escreva SÓ
    #   {"parecer_normas": ..., "caminho": ["normas"]}. Os três especialistas rodam no MESMO passo.
    #   Referência: aula7/exemplos/08_paralelismo/main.py (cada ramo escreve no SEU campo)
    resultado = _rodar(agentes.criar_normas(), _fatos(estado))
    return {"parecer_normas": resultado.final_output, "caminho": ["normas"]}


# Ramo PARALELO 2 (fan-out): o especialista Escala confere a N5 e sugere datas. Escreve SÓ em parecer_escala.
def no_escala(estado: Estado) -> dict:
    # ETAPA 7.3 -- idem, agentes.criar_escala() -> {"parecer_escala": ..., "caminho": ["escala"]}
    resultado = _rodar(agentes.criar_escala(), _fatos(estado))
    return {"parecer_escala": resultado.final_output, "caminho": ["escala"]}


# Ramo PARALELO 3 (fan-out): o Financeiro calcula venda/diárias. Sem valor a calcular, nem chama o LLM.
def no_financeiro(estado: Estado) -> dict:
    # ETAPA 7.3 -- idem, agentes.criar_financeiro() -> {"parecer_financeiro": ..., "caminho": ["financeiro"]}
    #   (abono não tem valor: devolva "não se aplica" sem chamar o LLM -- economiza tokens)
    pedido = estado["pedido"]
    if pedido["tipo"] != "diaria" and not pedido.get("dias_vendidos"):  # abono, ou férias sem venda: nada a calcular
        return {"parecer_financeiro": "não se aplica (sem venda de férias nem diária)", "caminho": ["financeiro"]}
    resultado = _rodar(agentes.criar_financeiro(), _fatos(estado))
    return {"parecer_financeiro": resultado.final_output, "caminho": ["financeiro"]}


# FAN-IN: só roda depois dos três ramos. Quem DECIDE é o Python (violacoes_objetivas), não os agentes.
def consolidar(estado: Estado) -> dict:
    # ETAPA 7.3 -- o fan-in: espera os três ramos. Calcule violacoes_objetivas(...) (etapa06_regras.py) e a decisão:
    #   {"violacoes": [...], "decisao": "indeferido" se houver violação, senão "deferido", "caminho": ["consolidar"]}
    #   Experimento (Etapa 7.1): faça no_escala também devolver {"violacoes": ["teste"]}. Sem o reducer em
    #   `violacoes`, o que acontece? E com ele? (aula7/exemplos/08_paralelismo/exercicio.md, item 4)
    violacoes = violacoes_objetivas(estado["pedido"], estado["servidor"], estado["periodo"], estado["escala"])
    return {"violacoes": violacoes, "decisao": "indeferido" if violacoes else "deferido", "caminho": ["consolidar"]}


# ------------------------------------------------------------------ ETAPA 7.4: ciclo
# Nó de LLM do CICLO: o Redator escreve o despacho; numa volta, recebe o erro da validação (ou o feedback da
# chefia, Etapa 8) para corrigir.
def redigir_despacho(estado: Estado) -> dict:
    # ETAPA 7.4 -- monte a entrada do Redator com _fatos(estado), a decisão, as violações, os três pareceres
    #   e, se houver, estado["erro_validacao"] (da validação) e estado["feedback_chefia"] (da Etapa 8).
    #   Devolva {"despacho": ..., "caminho": ["redigir_despacho"]}.
    entrada = (
        f"{_fatos(estado)}\n"
        f"DECISÃO: {estado['decisao']}\nVIOLAÇÕES: {estado.get('violacoes') or 'nenhuma'}\n"
        f"PARECER NORMAS: {estado.get('parecer_normas', '')}\n"
        f"PARECER ESCALA: {estado.get('parecer_escala', '')}\n"
        f"PARECER FINANCEIRO: {estado.get('parecer_financeiro', '')}"
    )
    if estado.get("erro_validacao"):
        entrada += f"\nFEEDBACK DA VALIDAÇÃO (corrija): {estado['erro_validacao']}"
    if estado.get("feedback_chefia"):
        entrada += f"\nFEEDBACK DA CHEFIA (corrija): {estado['feedback_chefia']}"
    resultado = _rodar(agentes.criar_redator(), entrada)
    return {"despacho": resultado.final_output, "caminho": ["redigir_despacho"]}


# Validação (PRONTA): regras objetivas que todo despacho precisa cumprir. Lista vazia = despacho válido.
def problemas_do_despacho(despacho: str, pedido: dict) -> list[str]:
    """(PRONTO) O que falta ou sobra no despacho: precisa citar a matrícula, o início do período (AAAA-MM-DD ou
    DD/MM/AAAA) e a decisão, e não pode ter CPF nem CID (N10). Lista vazia = despacho válido."""
    problemas, texto = [], despacho.lower()
    if pedido.get("matricula") and pedido["matricula"] not in despacho:
        problemas.append(f"cite a matrícula {pedido['matricula']}")
    inicio = pedido.get("data_inicio") or ""
    if inicio and inicio not in despacho and "/".join(reversed(inicio.split("-"))) not in despacho:
        problemas.append(f"cite o início do período ({inicio})")
    if "deferid" not in texto and "indeferid" not in texto:
        problemas.append("diga a decisão (deferido ou indeferido)")
    if encontrar_dado_sensivel(despacho):
        problemas.append("tire o CPF/CID do despacho (N10)")
    return problemas


# Nó do CICLO: confere o despacho e soma 1 em `tentativas` -- é esse contador que garante que o ciclo para.
def validar(estado: Estado) -> dict:
    # ETAPA 7.4 -- use problemas_do_despacho(estado["despacho"], estado["pedido"]) (pronta, logo acima) e devolva
    #   {"tentativas": estado["tentativas"] + 1, "erro_validacao": "; ".join(problemas), "caminho": ["validar"]}
    #   O ponto da etapa é o CICLO: é esta contagem de tentativas que o rotear_validacao usa para parar.
    problemas = problemas_do_despacho(estado["despacho"], estado["pedido"])
    return {"tentativas": estado.get("tentativas", 0) + 1, "erro_validacao": "; ".join(problemas),
            "caminho": ["validar"]}


# Roteador do CICLO: com erro e tentativas < MAX_TENTATIVAS, volta para redigir; senão segue para a chefia
# (quando a N8 exige) ou direto para registrar.
def rotear_validacao(estado: Estado) -> str:
    # ETAPA 7.4 -- erro e tentativas < MAX_TENTATIVAS -> "redigir"
    #              (válido OU estourou as tentativas)   -> "chefia" se precisa_chefia(pedido, violacoes)
    #                                                      senão "registrar"
    #   (antes da Etapa 8, mande "chefia" também para "registrar": ainda não há o nó da chefia)
    if estado.get("erro_validacao") and estado.get("tentativas", 0) < MAX_TENTATIVAS:
        return "redigir"
    return "chefia" if precisa_chefia(estado["pedido"], estado.get("violacoes", [])) else "registrar"


# ------------------------------------------------------------------ ETAPA 8: a chefia
# Etapa 8: a chefia aprova ou rejeita o despacho. interrupt() pausa o grafo, que pode ser retomado dias depois.
def aprovacao_chefia(estado: Estado) -> dict:
    # ETAPA 8.2 -- resposta = interrupt({"pergunta": "Aprova o despacho?", "chefia": estado["servidor"]["chefia"],
    #                                    "resumo": <servidor, período, pareceres, despacho>})
    #   `resposta` = {"aprovado": bool, "aprovador": str, "motivo": str} (o que o retomar() entregar).
    #   Aprovado  -> {"aprovador": ..., "feedback_chefia": ""}
    #   Rejeitado -> {"rejeicoes": +1, "feedback_chefia": motivo, "aprovador": ...}
    #   NADA de gravar antes do interrupt(): na retomada, o nó roda de novo desde o começo.
    #   Referência: aula7/exemplos/07_aprovacao_revisao/main.py
    # Este print prova que, na retomada, o nó roda DE NOVO desde o começo (por isso nada é gravado antes do interrupt).
    print(f"[aprovacao_chefia] ANTES do interrupt ({estado.get('thread_id')})")
    resposta = interrupt({
        "pergunta": "Aprova o despacho?",
        "chefia": estado["servidor"].get("chefia"),
        "resumo": {
            "servidor": f"{estado['servidor'].get('nome')} ({estado['pedido']['matricula']})",
            "periodo": f"{estado['pedido']['data_inicio']} a {estado['pedido']['data_fim']}",
            "parecer_normas": estado.get("parecer_normas", ""),
            "parecer_escala": estado.get("parecer_escala", ""),
            "parecer_financeiro": estado.get("parecer_financeiro", ""),
            "despacho": estado.get("despacho", ""),
        },
    })
    # Daqui para baixo só roda na RETOMADA: `resposta` é o que o retomar() entregou.
    if resposta.get("aprovado"):
        return {"aprovador": resposta.get("aprovador", ""), "feedback_chefia": "", "caminho": ["aprovacao_chefia"]}
    motivo = resposta.get("motivo") or "rejeitado pela chefia, sem motivo informado"
    return {"rejeicoes": estado.get("rejeicoes", 0) + 1, "feedback_chefia": motivo,
            "aprovador": resposta.get("aprovador", ""), "caminho": ["aprovacao_chefia"]}


# Etapa 8: aprovado -> registrar; rejeitado -> redigir de novo (até MAX_REJEICOES; depois, indeferido pela chefia).
def rotear_chefia(estado: Estado) -> str:
    # ETAPA 8.3 -- aprovado -> "registrar"; rejeitado e rejeicoes < MAX_REJEICOES -> "redigir";
    #              rejeitado de novo -> "registrar" (com decisao "indeferido_pela_chefia": ajuste no registrar)
    if not estado.get("feedback_chefia"):  # aprovado: o nó limpou o feedback
        return "registrar"
    if estado.get("rejeicoes", 0) < MAX_REJEICOES:  # rejeitado: o Redator refaz com o motivo da chefia
        return "redigir"
    return "registrar"  # rejeitado de novo: o registrar grava "indeferido_pela_chefia"


# ------------------------------------------------------------------ ETAPA 7.5 / 9.4: registrar
# Nó de ESCRITA (único que grava): guardrail de saída (N10), protocolo idempotente e registrar_decisao no MCP.
# Quem autoriza ou nega a gravação é o SERVER (token e N8, Etapa 9), não o grafo.
def registrar(estado: Estado) -> dict:
    # ETAPA 7.5 -- protocolo = gerar_protocolo(...); chamar_mcp("registrar_decisao", {..., "token":
    #   os.getenv("TOKEN_REGISTRO", ""), "thread_id": estado["thread_id"], "aprovador": estado.get("aprovador")
    #   ou "sistema"}). Se rejeicoes >= MAX_REJEICOES, decisao = "indeferido_pela_chefia".
    #   Devolva {"protocolo": ..., "resultado": "registrado" ou "negado_pelo_server", "caminho": ["registrar"]}.
    # ETAPA 9.4 -- ANTES de gravar: encontrar_dado_sensivel(despacho) -> não grava, resultado "bloqueado_na_saida".
    pedido = estado["pedido"]
    protocolo = gerar_protocolo(pedido["matricula"], pedido["tipo"], pedido["data_inicio"], pedido["data_fim"])
    despacho = estado.get("despacho", "")
    if encontrar_dado_sensivel(despacho):  # ETAPA 9.4: guardrail de SAÍDA (N10) -- não grava CPF/CID
        return {"protocolo": protocolo, "resultado": "bloqueado_na_saida", "caminho": ["registrar"]}
    decisao = "indeferido_pela_chefia" if estado.get("rejeicoes", 0) >= MAX_REJEICOES else estado["decisao"]
    resposta = chamar_mcp("registrar_decisao", {
        "protocolo": protocolo, "matricula": pedido["matricula"], "tipo": pedido["tipo"],
        "inicio": pedido["data_inicio"], "fim": pedido["data_fim"], "decisao": decisao,
        "aprovador": estado.get("aprovador") or "sistema", "despacho": despacho,
        "token": os.getenv("TOKEN_REGISTRO", ""), "thread_id": estado.get("thread_id", ""),
    })
    if not resposta.get("sucesso"):
        resultado = f"negado_pelo_server: {resposta.get('erro', '')}"
    else:
        resultado = "duplicado" if resposta.get("duplicado") else "registrado"
    return {"protocolo": protocolo, "decisao": decisao, "resultado": resultado, "caminho": ["registrar"]}


# ------------------------------------------------------------------ ETAPA 7.5: o grafo
# Monta o grafo: registra os nós e liga as arestas fixas (sempre) e condicionais (decididas pelos roteadores).
# Fan-out: uma aresta para cada especialista; fan-in: add_edge([lista], destino) espera todos da lista.
def construir(checkpointer=None):
    construtor = StateGraph(Estado)
    nos = {
        "receber": receber, "proteger_entrada": proteger_entrada,
        "recusar": recusar, "extrair": no_extrair, "pedir_dados": pedir_dados,
        "identificar_servidor": identificar_servidor, "calcular_periodo": calcular_periodo,
        "normas": no_normas, "escala": no_escala, "financeiro": no_financeiro, "consolidar": consolidar,
        "redigir_despacho": redigir_despacho, "validar": validar, "aprovacao_chefia": aprovacao_chefia,
        "registrar": registrar,
    }
    if USAR_TRIAGEM_HUMANA:  # 🆕 C (opcional): o nó só entra no grafo quando o item está ligado
        nos["triagem_humana"] = triagem_humana
    for nome, funcao in nos.items():
        construtor.add_node(nome, medido(nome, funcao))  # medido(): ETAPA 10.2 (por enquanto, não muda nada)

    # ETAPA 7.5 -- ligue o grafo do ENUNCIADO.md:
    #   add_edge(START, "receber"); add_edge("receber", "proteger_entrada")
    #   add_conditional_edges("proteger_entrada", rotear_entrada, {"bloqueado": "recusar", "ok": "extrair"})
    #   🆕 C (opcional) -- se USAR_TRIAGEM_HUMANA: acrescente "duvida": "triagem_humana" ao dicionário acima e
    #                      add_conditional_edges("triagem_humana", rotear_triagem, {"segue": "extrair", "recusa": "recusar"})
    #   ... extrair, identificar_servidor (condicionais) -> calcular_periodo
    #   fan-out: calcular_periodo -> normas, escala, financeiro
    #   fan-in : add_edge(["normas", "escala", "financeiro"], "consolidar")   (LISTA: espera os três)
    #   consolidar -> redigir_despacho -> validar -> rotear_validacao {"redigir", "chefia", "registrar"}
    #   aprovacao_chefia -> rotear_chefia {"redigir", "registrar"}
    #   recusar, pedir_dados e registrar -> END
    construtor.add_edge(START, "receber")
    construtor.add_edge("receber", "proteger_entrada")
    rotas_entrada = {"bloqueado": "recusar", "ok": "extrair"}
    if USAR_TRIAGEM_HUMANA:
        rotas_entrada["duvida"] = "triagem_humana"
        construtor.add_conditional_edges("triagem_humana", rotear_triagem, {"segue": "extrair", "recusa": "recusar"})
    construtor.add_conditional_edges("proteger_entrada", rotear_entrada, rotas_entrada)
    construtor.add_conditional_edges("extrair", rotear_extracao, {"incompleto": "pedir_dados",
                                                                  "ok": "identificar_servidor"})
    construtor.add_conditional_edges("identificar_servidor", rotear_servidor, {"nao_encontrado": "pedir_dados",
                                                                               "ok": "calcular_periodo"})
    for especialista in ("normas", "escala", "financeiro"):  # fan-out: os três no MESMO passo
        construtor.add_edge("calcular_periodo", especialista)
    construtor.add_edge(["normas", "escala", "financeiro"], "consolidar")  # fan-in por LISTA: espera os três
    construtor.add_edge("consolidar", "redigir_despacho")
    construtor.add_edge("redigir_despacho", "validar")
    # ETAPA 8: "chefia" agora vai para aprovacao_chefia (antes ia direto para registrar).
    construtor.add_conditional_edges("validar", rotear_validacao, {"redigir": "redigir_despacho",
                                                                   "chefia": "aprovacao_chefia",
                                                                   "registrar": "registrar"})
    construtor.add_conditional_edges("aprovacao_chefia", rotear_chefia, {"redigir": "redigir_despacho",
                                                                         "registrar": "registrar"})
    for final in ("recusar", "pedir_dados", "registrar"):
        construtor.add_edge(final, END)
    return construtor.compile(checkpointer=checkpointer)


# ------------------------------------------------------------------ execução
# Configuração de execução (PRONTA): thread_id identifica a execução; recursion_limit impede ciclo infinito.
def config_de(thread_id: str) -> dict:
    """(PRONTO) thread_id identifica a execução no checkpointer; recursion_limit protege contra ciclo infinito."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}


# Saída na tela (PRONTA): caminho percorrido e resultado -- ou, se pausou, onde parou e como retomar.
def mostrar(app, thread_id: str, saida: dict) -> None:
    """(PRONTO) Imprime o caminho, o desfecho e, se pausou, a pergunta feita ao humano."""
    print(f"\n[{thread_id}] caminho: {' -> '.join(saida.get('caminho', []))}")
    if "__interrupt__" in saida:
        pausa = saida["__interrupt__"][0].value
        print(f"[{thread_id}] PAUSADO em {app.get_state(config_de(thread_id)).next}: {pausa.get('pergunta')}")
        print(f"   retome com: python etapa07_grafo.py --retomar {thread_id} sim|\"nao:motivo\" <quem>")
    else:
        print(f"[{thread_id}] resultado: {saida.get('resultado')}  protocolo: {saida.get('protocolo')}")
        print(f"[{thread_id}] despacho: {saida.get('despacho')}")


# Roda um caso do começo (PRONTO): apaga o histórico daquele thread_id antes, para não continuar a execução antiga.
def executar(app, thread_id: str, texto: str) -> None:
    """(PRONTO) Roda um pedido do começo. Apaga antes os checkpoints desse thread_id: sem isso, rodar o mesmo caso
    de novo CONTINUARIA a execução anterior, e os campos com reducer (caminho, violacoes) acumulariam as duas."""
    if app.checkpointer:
        app.checkpointer.delete_thread(thread_id)
    saida = app.invoke({"thread_id": thread_id, "texto": texto}, config_de(thread_id))
    mostrar(app, thread_id, saida)


# Lista as execuções salvas e onde cada uma parou (PRONTO): quem tem `next` está pausado esperando um humano.
def listar_pendentes(app, checkpointer) -> None:
    """(PRONTO) Cada execução (thread_id) que está no checkpointer e onde ela parou. Quem tem `next` não vazio está
    PAUSADO esperando um humano. É o get_state() da aula7/exemplos/04_persistencia/main.py, para todas as execuções."""
    vistos = []
    for checkpoint in checkpointer.list(None):  # todos os checkpoints de todas as execuções
        thread_id = checkpoint.config["configurable"]["thread_id"]
        if thread_id not in vistos:
            vistos.append(thread_id)
    for thread_id in vistos:
        proximo = app.get_state(config_de(thread_id)).next
        print(f"{thread_id}: {'PAUSADO em ' + str(proximo) if proximo else 'concluído'}")


# Etapa 8: retoma uma execução pausada (em OUTRO processo) entregando a resposta do humano com Command(resume=...).
def retomar(app, thread_id: str, resposta: str, quem: str) -> None:
    # ETAPA 8.4 -- veja ONDE a execução parou: app.get_state(config_de(thread_id)).next
    #   - ("aprovacao_chefia",): valor = {"aprovado": resposta == "sim", "aprovador": quem,
    #                                    "motivo": o texto depois de "nao:"}
    #   - ("triagem_humana",)  : valor = {"segue": resposta começa com "sim", "orientacao": o texto depois de ":",
    #                                    "quem": quem}                                    (só com o 🆕 C, opcional)
    #   saida = app.invoke(Command(resume=valor), config_de(thread_id)); mostrar(app, thread_id, saida)
    #   Nada pausado? Diga isso e não faça nada (e se retomarem duas vezes?).
    #   Referência: aula7/exemplos/06_human_in_the_loop/main.py (retomar)
    config = config_de(thread_id)
    proximo = app.get_state(config).next
    if not proximo:  # nada pausado (ex.: retomaram duas vezes): não faz nada
        print(f"\n[{thread_id}] nada pausado")
        return
    texto_depois = resposta.split(":", 1)[1].strip() if ":" in resposta else ""
    if "aprovacao_chefia" in proximo:
        valor = {"aprovado": resposta.strip().lower() == "sim", "aprovador": quem, "motivo": texto_depois}
    elif "triagem_humana" in proximo:  # 🆕 C (opcional)
        valor = {"segue": resposta.strip().lower().startswith("sim"), "orientacao": texto_depois, "quem": quem}
    else:
        print(f"\n[{thread_id}] pausado em {proximo}, que não espera resposta humana")
        return
    saida = app.invoke(Command(resume=valor), config)
    mostrar(app, thread_id, saida)


# Ponto de entrada: abre o checkpointer SQLite (persistência) e escolhe a ação pelos argumentos da linha de comando.
def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--sem-guardrail"]
    # ETAPA 8.1 -- o checkpointer SQLite: é ele que deixa a execução pausada sobreviver ao fim do processo.
    with SqliteSaver.from_conn_string(str(SAIDAS / "checkpoints.db")) as checkpointer:
        app = construir(checkpointer)
        if not args or args[0] == "--mermaid":
            print(app.get_graph().draw_mermaid())
        elif args[0] == "--pendentes":
            listar_pendentes(app, checkpointer)
        elif args[0] == "--retomar":
            retomar(app, args[1], args[2], args[3] if len(args) > 3 else "?")
        elif args[0] == "--todos":
            for nome, caso in CASOS.items():
                executar(app, nome, caso["pedido"])
        else:
            executar(app, args[0], CASOS[args[0]]["pedido"])


if __name__ == "__main__":
    print(f"[modelo] {MODELO}  [guardrail de entrada {'ligado' if GUARDRAIL_LIGADO else 'DESLIGADO'}]")
    main()