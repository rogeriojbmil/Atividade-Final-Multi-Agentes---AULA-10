"""
ETAPA 10 -- Observabilidade (15 min): onde o tempo foi gasto e quanto custou, por nó do grafo.

ESQUELETO:
  ETAPA 10.2 -- medido(): embrulha um nó, mede o tempo e grava uma linha em saidas/metricas.jsonl
  (PRONTO)   -- resumo(): nós percorridos, tempo total, nó mais lento e tokens totais de uma execução
  (ETAPA 10.1 fica em etapa10_governanca.py: o hook do 🆕 B ganha um segundo papel, registrar)

Até você fazer a 10.2, medido() devolve o nó sem mudar nada: o grafo funciona igual.

REFERÊNCIAS NAS AULAS
  aula5/exemplos/11_observabilidade/agente_observavel.py        ler o que aconteceu numa execução (result.new_items)
  aula3/agente_hook2.py, aula3/agente_hook3.py                  RunHooks para enxergar o loop do agente
  aula8/exemplos/03_observabilidade/1_codigo_pronto/passo1_trace.py   trace e spans (o Langfuse do passo 2 é opcional)

Rodar:
    python etapa10_observabilidade.py <thread_id>     # imprime o resumo de uma execução já feita
"""
import functools
import json
import sys
import threading
import time

from dados_rh import SAIDAS

ARQUIVO_METRICAS = SAIDAS / "metricas.jsonl"

# O que o hook Governanca (etapa10_governanca.py) anota durante o nó que está rodando NESTA thread. Os ramos paralelos
# do grafo (normas, escala, financeiro) rodam em threads diferentes, então um não mistura os números do outro.
_no_atual = threading.local()

# Trava única para gravar no arquivo: os ramos paralelos do grafo terminam ao mesmo tempo e, sem ela,
# uma linha pode sair por cima da outra (JSON quebrado no metricas.jsonl).
_trava_arquivo = threading.Lock()


# Chamado pelo hook no fim de cada agente: guarda o total de tokens daquela execução (uma chave por Runner.run, para
# não contar duas vezes a mesma execução).
def anotar_tokens(chave: int, total: int) -> None:
    tokens = getattr(_no_atual, "tokens", None)
    if tokens is not None:
        tokens[chave] = total


# Chamado pelo hook no fim de cada tool: guarda o nome da tool e o resultado (para saber se o câmbio veio da API).
def anotar_evento(evento: dict) -> None:
    eventos = getattr(_no_atual, "eventos", None)
    if eventos is not None:
        eventos.append(evento)


# ETAPA 10.2 -- Embrulha um nó do grafo: mede o tempo, junta os tokens e as tools anotados pelo hook e grava UMA linha
# em saidas/metricas.jsonl. Devolve o MESMO dicionário do nó, então o grafo não percebe a diferença.
def medido(nome: str, no):
    @functools.wraps(no)
    def medido_no(estado):
        _no_atual.tokens, _no_atual.eventos = {}, []
        inicio = time.perf_counter()
        resultado = no(estado)
        linha = {"thread_id": estado.get("thread_id", ""), "no": nome,
                 "segundos": round(time.perf_counter() - inicio, 2)}
        tokens = sum(_no_atual.tokens.values())
        if tokens:
            linha["tokens"] = tokens
        if isinstance(resultado, dict) and isinstance(resultado.get("periodo"), dict):
            linha["fonte_feriados"] = resultado["periodo"].get("fonte_feriados")
        if _no_atual.eventos:
            linha["tools"] = [e["tool"] for e in _no_atual.eventos]  # só os nomes: o resultado pode ter o salário
            cambio = [e for e in _no_atual.eventos if e["tool"] == "cotacao_dolar"]
            if cambio:
                linha["cambio_api"] = "indispon" not in str(cambio[-1].get("resultado", ""))
        ARQUIVO_METRICAS.parent.mkdir(parents=True, exist_ok=True)
        with _trava_arquivo, ARQUIVO_METRICAS.open("a", encoding="utf-8") as arquivo:  # um nó por vez no arquivo
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
        return resultado
    return medido_no


def resumo(thread_id: str) -> dict:
    """(PRONTO) Junta as linhas de ARQUIVO_METRICAS de uma execução. Só funciona depois que o medido() (10.2) grava."""
    if not ARQUIVO_METRICAS.exists():
        return {"erro": "saidas/metricas.jsonl ainda não existe: faça a ETAPA 10.2 e rode o grafo"}
    linhas = [json.loads(l) for l in ARQUIVO_METRICAS.read_text(encoding="utf-8").splitlines() if l.strip()]
    linhas = [l for l in linhas if l.get("thread_id") == thread_id]
    if not linhas:
        return {"erro": f"nenhuma métrica com thread_id={thread_id!r}"}
    lento = max(linhas, key=lambda l: l.get("segundos", 0))
    return {"nos": [l.get("no") for l in linhas],
            "segundos_total": round(sum(l.get("segundos", 0) for l in linhas), 2),
            "mais_lento": (lento.get("no"), lento.get("segundos")),
            "tokens_total": sum(l.get("tokens", 0) or 0 for l in linhas)}


if __name__ == "__main__":
    print(json.dumps(resumo(sys.argv[1]), ensure_ascii=False, indent=2))