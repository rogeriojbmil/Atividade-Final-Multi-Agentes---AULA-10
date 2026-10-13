"""
conferir.py -- mostra, etapa por etapa, o que do exercício já está pronto e o que falta.

    python conferir.py              # todas as etapas, SEM chamar o LLM (rápido, não gasta tokens)
    python conferir.py 5            # só a Etapa 5 (pode passar várias: python conferir.py 5 7)
    python conferir.py --llm        # inclui as conferências que chamam o modelo de verdade (Etapas 1, 2, 3 e 6)
    python conferir.py --opcionais  # inclui os itens opcionais 🆕 A, B e C

Como funciona: as conferências do grafo (Etapas 7 a 10) trocam as respostas do LLM por respostas FIXAS, como num teste.
Assim o resultado não depende do modelo, e o que é conferido é o SEU código: caminhos, decisões, pausas, retomadas,
chamadas ao MCP. Nada do que este arquivo grava fica em saidas/ (as gravações de teste são apagadas no fim).

Marcas:  [OK] passou | [PENDENTE] a lacuna ainda tem o NotImplementedError | [FALHOU] rodou, mas o resultado está
errado (a mensagem diz o que veio e o que se esperava) | [ERRO] deu exceção (a mensagem diz qual).

Este arquivo não faz parte do exercício: não precisa ler nem mudar.
"""
import asyncio
import contextlib
import io
import json
import os
import re
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA))
os.chdir(PASTA)
with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(encoding="utf-8")

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
COM_LLM = "--llm" in sys.argv
COM_OPCIONAIS = "--opcionais" in sys.argv

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PASTA / ".env")
if not COM_LLM:
    # Sem --llm nenhuma conferência chama o modelo. Isto só deixa os módulos serem importados mesmo sem chave/Ollama.
    os.environ["PROVEDOR"] = "openai"
    os.environ.setdefault("OPENAI_API_KEY", "sk-conferir-sem-llm")
    if not os.environ["OPENAI_API_KEY"].startswith("sk-"):
        os.environ["OPENAI_API_KEY"] = "sk-conferir-sem-llm"
os.environ["FERIADOS_OFFLINE"] = "1"  # feriados do arquivo local: o resultado não depende da internet


# ===================================================================== infraestrutura das conferências
class Etapa:
    def __init__(self, numero: str, titulo: str, referencia: str):
        self.numero, self.titulo, self.referencia = numero, titulo, referencia
        self.resultados: list[str] = []  # "ok" | "pendente" | "falhou" | "erro"

    def conferir(self, descricao: str, funcao) -> None:
        saida = io.StringIO()
        try:
            with contextlib.redirect_stdout(saida):
                detalhe = funcao()
            self.resultados.append("ok")
            print(f"  [OK]       {descricao}" + (f"  ({detalhe})" if detalhe else ""))
        except NotImplementedError as e:
            self.resultados.append("pendente")
            print(f"  [PENDENTE] {descricao}: falta a {str(e).split(':')[0] or 'lacuna'}")
        except AssertionError as e:
            self.resultados.append("falhou")
            print(f"  [FALHOU]   {descricao}: {e}")
        except SystemExit as e:
            self.resultados.append("erro")
            print(f"  [ERRO]     {descricao}: {str(e).splitlines()[0]}")
        except Exception as e:  # noqa: BLE001 - o aluno precisa ver qualquer erro
            self.resultados.append("erro")
            local = _onde(e)
            print(f"  [ERRO]     {descricao}: {type(e).__name__}: {str(e)[:160]}{local}")

    def situacao(self) -> str:
        r = self.resultados
        if r and all(x == "ok" for x in r):
            return "✅ completa"
        if r and all(x == "pendente" for x in r):
            return "⬜ não iniciada"
        return "🟡 em andamento"


def _onde(erro: Exception) -> str:
    """O último ponto do traceback que está no código do aluno (para saber onde olhar)."""
    for quadro in reversed(traceback.extract_tb(erro.__traceback__)):
        if Path(quadro.filename).resolve().parent == PASTA and Path(quadro.filename).name != "conferir.py":
            return f"  [em {Path(quadro.filename).name}, linha {quadro.lineno}]"
    return ""


def mcp(tool: str, argumentos: dict) -> dict:
    """chamar_mcp do aluno, traduzindo 'erro dentro do server' em PENDENTE quando a lacuna ainda não foi feita."""
    from etapa05_cliente_mcp import chamar_mcp
    try:
        return chamar_mcp(tool, argumentos)
    except RuntimeError as erro:
        servidor = (PASTA / "etapa05_mcp_rh.py").read_text(encoding="utf-8")
        for etapa in ("5.1", "5.2"):
            if f'NotImplementedError("ETAPA {etapa}: {tool}")' in servidor:
                raise NotImplementedError(f"ETAPA {etapa} ({tool} no etapa05_mcp_rh.py)") from erro
        raise AssertionError(f"{erro}") from erro


def igual(obtido, esperado, o_que: str) -> None:
    assert obtido == esperado, f"{o_que}: veio {obtido!r}, esperado {esperado!r}"


ETAPAS: list[Etapa] = []


def etapa(numero: str, titulo: str, referencia: str):
    """Decorador: registra a função que confere uma etapa."""
    def registrar(funcao):
        e = Etapa(numero, titulo, referencia)
        e.rodar = lambda: funcao(e)
        ETAPAS.append(e)
        return funcao
    return registrar


# ===================================================================== apoio: casos e "LLM fixo"
from dados.casos import CASOS  # noqa: E402

PEDIDOS_FIXOS = {  # o que um extrator CORRETO devolve para cada caso (usado no lugar do LLM)
    "C1": dict(tipo="abono", matricula="1001", data_inicio="2027-04-09", data_fim="2027-04-09"),
    "C2": dict(tipo="ferias", matricula="1002", data_inicio="2027-04-12", data_fim="2027-04-26", dias_vendidos=10),
    "C5": dict(tipo="ferias", matricula=None, data_inicio=None, data_fim=None),
    "C6": dict(tipo="ferias", matricula="1004", data_inicio="2027-07-12", data_fim="2027-07-26"),
    "C11": dict(tipo="diaria", matricula="1003", data_inicio="2027-06-08", data_fim="2027-06-11",
                destino="Buenos Aires", tipo_destino="exterior"),
    "C12": dict(tipo="ferias", matricula="1003", data_inicio="2027-04-30", data_fim="2027-05-14"),
}
NOTAS_FIXAS = {"C4": 0.95, "C7": 0.95, "C10": 0.55}  # nota do classificador de escopo; o resto: 0.05
INDEFERIDOS = {"C6", "C12"}


def _caso_do_texto(texto: str) -> str:
    for nome, caso in CASOS.items():
        if caso["pedido"] in texto:
            return nome.split("_")[0]
    return "?"


class _PedidoFixo:
    def __init__(self, dados: dict):
        self.dados = {"dias_vendidos": 0, "destino": None, "tipo_destino": None, "justificativa": "", **dados}
        self.tipo = SimpleNamespace(value=self.dados["tipo"])
        for chave, valor in self.dados.items():
            if chave != "tipo":
                setattr(self, chave, valor)

    def model_dump(self, mode=None):
        return dict(self.dados)


class GrafoComLLMFixo:
    """Monta o grafo do aluno trocando só o LLM por respostas fixas e interceptando a gravação no MCP."""

    def __init__(self, triagem: bool = False):
        import etapa06_agentes as agentes
        import etapa07_grafo as grafo
        from langgraph.checkpoint.memory import MemorySaver

        self.grafo, self.gravacoes, self.caso_atual = grafo, [], "?"
        chamar_mcp_real = grafo.chamar_mcp

        def chamar_mcp(tool, argumentos):
            if tool == "registrar_decisao":  # não grava de verdade: só registra o que o grafo pediu
                self.gravacoes.append(dict(argumentos))
                return {"sucesso": True, "protocolo": argumentos.get("protocolo")}
            return chamar_mcp_real(tool, argumentos)

        def extrair(texto):
            self.caso_atual = _caso_do_texto(texto)
            return _PedidoFixo(PEDIDOS_FIXOS.get(self.caso_atual, PEDIDOS_FIXOS["C5"]))

        async def extrair_com_votacao(texto):
            return extrair(texto), False, []

        def rodar(agente, entrada, **kwargs):
            p = PEDIDOS_FIXOS.get(self.caso_atual, {})
            decisao = "INDEFERIDO" if self.caso_atual in INDEFERIDOS else "DEFERIDO"
            ini = p.get("data_inicio") or ""
            ini_br = "/".join(reversed(ini.split("-"))) if ini else ""
            texto = (f"Despacho: matrícula {p.get('matricula')}, período de {ini} ({ini_br}) a {p.get('data_fim')}. "
                     f"Decisão: {decisao}.")
            return SimpleNamespace(final_output=texto, context_wrapper=SimpleNamespace(usage=SimpleNamespace(total_tokens=0)))

        grafo.chamar_mcp = chamar_mcp
        grafo.extrair, grafo.extrair_com_votacao = extrair, extrair_com_votacao
        grafo.nota_escopo = lambda texto: (NOTAS_FIXAS.get(_caso_do_texto(texto), 0.05), "fixo")
        grafo.rodar_com_limites_sync = rodar
        for nome in ("criar_normas", "criar_escala", "criar_financeiro", "criar_redator"):
            setattr(agentes, nome, lambda nome=nome: SimpleNamespace(name=nome))
        grafo.GUARDRAIL_LIGADO = True
        grafo.USAR_VOTACAO = False
        grafo.USAR_TRIAGEM_HUMANA = triagem
        self.checkpointer = MemorySaver()
        self.app = grafo.construir(self.checkpointer)

    def rodar(self, nome_caso: str) -> dict:
        self.caso_atual = nome_caso.split("_")[0]
        thread = f"conferir-{nome_caso}"
        estado = self.app.invoke({"thread_id": thread, "texto": CASOS[nome_caso]["pedido"]}, self.grafo.config_de(thread))
        return estado

    def proximo(self, nome_caso: str) -> tuple:
        return self.app.get_state(self.grafo.config_de(f"conferir-{nome_caso}")).next


TRIO = {"normas", "escala", "financeiro"}


def _normaliza(caminho: list[str]) -> list:
    """Os três ramos paralelos podem aparecer em qualquer ordem: junta-os num único item."""
    saida, i = [], 0
    while i < len(caminho):
        if caminho[i] in TRIO and set(caminho[i:i + 3]) == TRIO:
            saida.append("normas|escala|financeiro")
            i += 3
        else:
            saida.append(caminho[i])
            i += 1
    return saida


COMPLETO = ["receber", "proteger_entrada", "extrair", "identificar_servidor", "calcular_periodo",
            "normas|escala|financeiro", "consolidar", "redigir_despacho", "validar"]


def conferir_caminho(estado: dict, esperado: list[str]) -> None:
    obtido = _normaliza(estado.get("caminho", []))
    assert obtido == esperado, (f"caminho {' -> '.join(obtido)}\n             esperado {' -> '.join(esperado)}\n"
                                "             (veja a tabela de referência no fim do PASSO_A_PASSO.md)")


# ===================================================================== limpeza do que o conferir gravou
def limpar_saidas() -> None:
    registros = PASTA / "saidas" / "registros.json"
    if registros.exists():
        dados = json.loads(registros.read_text(encoding="utf-8"))
        limpos = {k: v for k, v in dados.items() if not k.startswith("conferir-")}
        if limpos != dados:
            registros.write_text(json.dumps(limpos, ensure_ascii=False, indent=2), encoding="utf-8")
    for nome in ("auditoria.jsonl", "metricas.jsonl"):
        arquivo = PASTA / "saidas" / nome
        if arquivo.exists():
            linhas = arquivo.read_text(encoding="utf-8").splitlines(keepends=True)
            filtradas = [l for l in linhas if '"conferir-' not in l]
            if filtradas != linhas:
                arquivo.write_text("".join(filtradas), encoding="utf-8")


# ===================================================================== as etapas
@etapa("0", "Preparação e tabela N1–N10", "PASSO_A_PASSO.md, Etapa 0")
def etapa0(e: Etapa):
    def dados():
        from dados_rh import carregar_servidores, normas
        igual(len(carregar_servidores()), 9, "servidores no cadastro")
        igual(len(normas()), 10, "regras na norma")

    def tabela():
        linhas = [l for l in (PASTA / "ENTREGA.md").read_text(encoding="utf-8").splitlines() if re.match(r"\|\s*N\d+\s*\|", l)]
        preenchidas = [l for l in linhas if l.split("|")[3].strip()]
        if not preenchidas:
            raise NotImplementedError("Etapa 0 (tabela N1–N10 do ENTREGA.md)")
        assert len(preenchidas) == 10, f"{len(preenchidas)} de 10 regras com a coluna 'Quem verifica' preenchida no ENTREGA.md"
        return "10 de 10"

    e.conferir("arquivos de dados/ carregam", dados)
    e.conferir("tabela N1–N10 preenchida no ENTREGA.md", tabela)


@etapa("1", "Primeiro agente com tool", "etapa01_agente.py; aula1/segundo_agente.py")
def etapa1(e: Etapa):
    async def chamar(tool, argumentos: dict) -> str:
        from agents.tool_context import ToolContext
        texto = json.dumps(argumentos)
        ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="conferir", tool_arguments=texto)
        return str(await tool.on_invoke_tool(ctx, texto))

    def tool_1_1():
        import etapa01_agente as m
        saida = asyncio.run(chamar(m.consultar_servidor, {"matricula": "1002"}))
        if "NotImplementedError" in saida or "ETAPA 1.1" in saida:
            raise NotImplementedError("ETAPA 1.1")
        assert "TODO" not in (m.consultar_servidor.description or ""), "a docstring da tool ainda tem TODO"
        assert "Bruno" in saida and "30" in saida, f"para 1002 esperava nome e saldo 30, veio: {saida[:120]}"
        assert "9500" not in saida and "salario" not in saida.lower(), "a tool está devolvendo o salário (não pode)"
        saida = asyncio.run(chamar(m.consultar_servidor, {"matricula": "9999"}))
        assert "encontrad" in saida.lower() or "erro" in saida.lower(), f"para 9999 veio: {saida[:120]}"

    def agente_1_2():
        import etapa01_agente as m
        agente = m.criar_atendente()
        assert "consultar_servidor" in [t.name for t in agente.tools], "o AtendenteRH não tem a tool consultar_servidor"

    def llm_1_3():
        from agents import Runner
        import etapa01_agente as m
        resposta = Runner.run_sync(m.criar_atendente(), "Quantos dias de férias a matrícula 1002 ainda tem?").final_output
        assert "30" in resposta, f"a resposta não fala em 30 dias: {resposta[:120]}"

    e.conferir("1.1 tool consultar_servidor (1002 sem salário; 9999 não encontrada)", tool_1_1)
    e.conferir("1.2 AtendenteRH com a tool", agente_1_2)
    if COM_LLM:
        e.conferir("1.3 [LLM] o agente responde o saldo da 1002", llm_1_3)


@etapa("2", "Extração estruturada", "etapa02_extracao.py; aula2/agente_output2.py")
def etapa2(e: Etapa):
    def modelo_2_1():
        from etapa02_extracao import Pedido
        faltam = {"matricula", "data_inicio", "data_fim", "dias_vendidos", "destino", "tipo_destino", "justificativa"} - set(Pedido.model_fields)
        if len(faltam) == 7:
            raise NotImplementedError("ETAPA 2.1")
        assert not faltam, f"faltam campos no Pedido: {sorted(faltam)}"
        sem = [n for n, f in Pedido.model_fields.items() if not f.description]
        assert not sem, f"campos sem Field(description=...): {sem}"

    def extrator_2_2():
        import etapa02_extracao as extracao
        agente = extracao.criar_extrator(extracao.INSTRUCOES_EXTRATOR)
        igual(agente.output_type, extracao.Pedido, "output_type do extrator")
        assert "TODO" not in extracao.INSTRUCOES_EXTRATOR, "INSTRUCOES_EXTRATOR ainda tem o TODO"

    def llm_2_3():
        import etapa02_extracao as extracao
        erros = []
        for nome, chaves in [("C1_abono_simples", ("tipo", "matricula", "data_inicio", "data_fim")),
                             ("C2_ferias_com_venda", ("tipo", "matricula", "data_inicio", "data_fim", "dias_vendidos")),
                             ("C5_sem_matricula", ("matricula", "data_inicio")),
                             ("C11_diaria_exterior", ("tipo", "matricula", "tipo_destino"))]:
            obtido = extracao.extrair(CASOS[nome]["pedido"]).model_dump(mode="json")
            esperado = PEDIDOS_FIXOS[nome.split("_")[0]]
            for chave in chaves:
                if obtido.get(chave) != esperado.get(chave, 0 if chave == "dias_vendidos" else None):
                    erros.append(f"{nome}.{chave}={obtido.get(chave)!r}")
        assert not erros, "campos diferentes do esperado: " + ", ".join(erros)

    e.conferir("2.1 modelo Pedido com todos os campos e descrições", modelo_2_1)
    e.conferir("2.2 extrator com output_type=Pedido e instruções completas", extrator_2_2)
    if COM_LLM:
        e.conferir("2.3 [LLM] extração de C1, C2, C5 e C11", llm_2_3)


@etapa("3", "Guardrails de entrada", "etapa03_guardrails.py; aula2/agente_guardrail.py")
def etapa3(e: Etapa):
    def regex_3_1():
        from etapa03_guardrails import encontrar_dado_sensivel as f
        igual(f("Meu CPF é 123.456.789-09"), "cpf", "CPF com pontos")
        igual(f("cpf 12345678909"), "cpf", "CPF sem pontos")
        igual(f("Estou com CID F32.1"), "cid", "CID com ponto")
        igual(f("diagnóstico J11"), "cid", "CID sem ponto")
        igual(f("férias de 12/04/2027 a 26/04/2027, matrícula 1002"), None, "texto com datas e matrícula (não é dado sensível)")
        for nome, caso in CASOS.items():
            esperado = "cpf" if nome.startswith("C3_") else None
            igual(f(caso["pedido"]), esperado, f"{nome}")

    def classificador_3_2():
        import etapa03_guardrails as guardrails
        igual(guardrails.criar_classificador().output_type, guardrails.AvaliacaoEscopo, "output_type do classificador")

    def guardrails_3_4():
        from agents import InputGuardrail
        import etapa03_guardrails as guardrails
        for nome in ("barrar_dado_sensivel", "barrar_fora_do_escopo"):
            assert isinstance(getattr(guardrails, nome), InputGuardrail), f"{nome} precisa do @input_guardrail"
        rodar = guardrails.barrar_dado_sensivel.guardrail_function
        com_cpf = asyncio.run(rodar(None, None, CASOS["C3_dado_de_saude"]["pedido"]))
        sem = asyncio.run(rodar(None, None, CASOS["C2_ferias_com_venda"]["pedido"]))
        igual((com_cpf.tripwire_triggered, sem.tripwire_triggered), (True, False),
              "barrar_dado_sensivel dispara no C3 e não no C2")
        assert "cpf" in json.dumps(com_cpf.output_info, ensure_ascii=False, default=str).lower(), \
            "o output_info do bloqueio do C3 deveria dizer o motivo (cpf)"

    def llm_3_3():
        import etapa03_guardrails as guardrails
        n1, _ = guardrails.nota_escopo(CASOS["C1_abono_simples"]["pedido"])
        n4, _ = guardrails.nota_escopo(CASOS["C4_fora_do_escopo"]["pedido"])
        n7, _ = guardrails.nota_escopo(CASOS["C7_autoaprovacao"]["pedido"])
        assert n1 < guardrails.LIMIAR, f"C1 (pedido legítimo) teve nota {n1} >= LIMIAR {guardrails.LIMIAR}"
        assert n4 >= guardrails.LIMIAR, f"C4 (fora do escopo) teve nota {n4} < LIMIAR"
        assert n7 >= guardrails.LIMIAR, f"C7 (manipulação) teve nota {n7} < LIMIAR: dê exemplos de 'mudar as regras' ao classificador"
        return f"notas C1={n1} C4={n4} C7={n7}"

    e.conferir("3.1 regex de CPF e CID (pronta: não mexa nela)", regex_3_1)
    e.conferir("3.2 classificador com output_type=AvaliacaoEscopo", classificador_3_2)
    e.conferir("3.4 os @input_guardrail (o de dado sensível dispara no C3 e não no C2)", guardrails_3_4)
    if COM_LLM:
        e.conferir("3.3 [LLM] notas do classificador: C1 passa, C4 e C7 bloqueiam", llm_3_3)


@etapa("4", "APIs com resiliência (pronta)", "etapa04_ferramentas.py")
def etapa4(e: Etapa):
    def pronta():
        import etapa04_ferramentas as f
        igual(f.inicio_permitido("2027-04-12"), True, "inicio_permitido(2027-04-12)")
        igual(f.inicio_permitido("2027-04-30"), False, "inicio_permitido(2027-04-30)")
        igual(f.dias_uteis("2027-04-12", "2027-04-26"), 10, "dias úteis 12 a 26/04/2027")
        igual(f.gerar_protocolo("1001", "abono", "2027-04-09", "2027-04-09"), "ae788d33", "protocolo do C1")

    e.conferir("etapa04_ferramentas.py responde como esperado (é a peça pronta: não mexa nela)", pronta)


@etapa("5", "MCP Server do RH", "etapa05_mcp_rh.py e etapa05_cliente_mcp.py; aula6/desafio2/mcp_unidades.py")
def etapa5(e: Etapa):

    def cliente_5_4():
        servidor = mcp("consultar_servidor", {"matricula": "1002"})
        assert isinstance(servidor, dict), f"chamar_mcp deveria devolver um dict, veio {type(servidor).__name__}"

    def leitura_5_1():
        s = mcp("consultar_servidor", {"matricula": "1002"})
        igual(s.get("nome"), "Bruno Castro", "consultar_servidor(1002).nome")
        assert "salario_base" not in s, "consultar_servidor está devolvendo o salário (não pode)"
        igual(mcp("consultar_servidor", {"matricula": "9999"}).get("erro") is not None, True, "matrícula 9999 devolve erro")
        esc = mcp("consultar_escala", {"equipe": "Cartório", "inicio": "2027-07-12", "fim": "2027-07-26"})
        igual((esc.get("tamanho_equipe"), esc.get("limite_afastados"), len(esc.get("afastamentos", []))), (4, 1, 1),
              "consultar_escala(Cartório): tamanho, limite, afastamentos")
        n = mcp("consultar_normas", {"tema": "diária"})
        igual([r["codigo"] for r in n.get("regras", [])], ["N7"], "consultar_normas('diária')")
        d = mcp("tabela_diarias", {"tipo_destino": "exterior"})
        igual((d.get("moeda"), d.get("valor_diaria")), ("USD", 320.0), "tabela_diarias('exterior')")
        igual(mcp("consultar_remuneracao", {"matricula": "1002"}).get("salario_base"), 9500.0, "consultar_remuneracao(1002)")

    def escrita_5_2():
        base = {"protocolo": "conferir-5", "matricula": "1001", "tipo": "abono", "inicio": "2027-04-09", "fim": "2027-04-09",
                "decisao": "deferido", "aprovador": "sistema", "despacho": "teste do conferir.py",
                "token": os.getenv("TOKEN_REGISTRO", ""), "thread_id": "conferir-5"}
        try:
            r1 = mcp("registrar_decisao", base)
            r2 = mcp("registrar_decisao", base)
        finally:
            limpar_saidas()
        assert r1.get("sucesso"), f"a 1ª gravação falhou: {r1} (o TOKEN_REGISTRO do .env está certo?)"
        assert r2.get("sucesso") and r2.get("duplicado"), f"a 2ª gravação do mesmo protocolo deveria dizer duplicado: {r2}"

    e.conferir("chamar_mcp (pronto) fala com o seu server", cliente_5_4)
    e.conferir("5.1 as 5 tools de leitura", leitura_5_1)
    e.conferir("5.2 registrar_decisao grava e não duplica", escrita_5_2)


@etapa("6", "Especialistas e fluxo linear (Marco mínimo)", "etapa06_agentes.py e etapa06_linear.py; aula4/ex03_agente_as_tool.py")
def etapa6(e: Etapa):
    def nomes(agente) -> set[str]:
        return {t.name for t in agente.tools}

    def especialistas_6_1():
        import etapa06_agentes as agentes
        igual(nomes(agentes.criar_normas()), {"consultar_normas"}, "tools do Normas")
        igual(nomes(agentes.criar_escala()), {"consultar_escala"}, "tools do Escala")
        fin = nomes(agentes.criar_financeiro())
        assert {"tabela_diarias", "consultar_remuneracao"} <= fin, f"o Financeiro precisa de tabela_diarias e consultar_remuneracao: {fin}"
        igual(nomes(agentes.criar_redator()), set(), "tools do Redator (nenhuma)")

    def coordenador_6_2():
        import etapa06_agentes as agentes
        tools = nomes(agentes.criar_coordenador())
        assert {"parecer_normas", "parecer_escala", "parecer_financeiro"} <= tools, f"o Coordenador deve ter os 3 especialistas como tools: {tools}"
        proibidas = tools & {"consultar_remuneracao", "registrar_decisao", "consultar_normas", "consultar_escala"}
        assert not proibidas, f"o Coordenador não deve ter estas tools direto: {proibidas}"

    def regras_6_0():
        from etapa06_regras import precisa_chefia, violacoes_objetivas
        servidor = {"matricula": "1004", "saldo_ferias_dias": 30, "abonos_restantes": 5}
        escala = {"limite_afastados": 1, "afastamentos": [{"matricula": "1006", "inicio": "2027-07-05", "fim": "2027-07-19"}]}
        from etapa06_regras import resumo_periodo
        v = violacoes_objetivas({"tipo": "ferias", "data_inicio": "2027-07-12", "data_fim": "2027-07-26", "dias_vendidos": 0},
                                servidor, resumo_periodo("2027-07-12", "2027-07-26"), escala)
        igual([x.split(":")[0] for x in v], ["N5"], "violações do C6")
        igual(precisa_chefia({"tipo": "ferias"}, []), True, "férias sem violação precisam de chefia")

    def llm_6_4():
        import etapa06_linear as etapa06_linear
        gravacoes, real = [], etapa06_linear.chamar_mcp

        def interceptar(tool, argumentos):
            if tool == "registrar_decisao":
                gravacoes.append(argumentos)
                return {"sucesso": True, "protocolo": argumentos.get("protocolo")}
            return real(tool, argumentos)

        etapa06_linear.chamar_mcp = interceptar
        r = etapa06_linear.processar(CASOS["C6_conflito_de_escala"]["pedido"])
        assert gravacoes, f"o C6 não chegou a registrar: {r.get('resultado')}"
        igual((gravacoes[-1].get("protocolo"), gravacoes[-1].get("decisao")), ("6f1b47d7", "indeferido"), "registro do C6")

    e.conferir("6.0 etapa06_regras.py (pronta)", regras_6_0)
    e.conferir("6.1 cada especialista só com as suas tools", especialistas_6_1)
    e.conferir("6.2 Coordenador com os especialistas como as_tool", coordenador_6_2)
    if COM_LLM:
        e.conferir("6.4 [LLM] processar(C6) chega ao indeferimento com o protocolo certo", llm_6_4)


@etapa("7", "O grafo", "etapa07_grafo.py; aula6/desafio2/main.py e aula7/exemplos/08_paralelismo/main.py")
def etapa7(e: Etapa):
    teste = {}

    def montar():
        teste["g"] = GrafoComLLMFixo()
        nos = set(teste["g"].app.get_graph().nodes)
        faltam = {"receber", "proteger_entrada", "extrair", "identificar_servidor", "calcular_periodo", "normas", "escala",
                  "financeiro", "consolidar", "redigir_despacho", "validar", "registrar", "recusar", "pedir_dados"} - nos
        assert not faltam, f"nós que não estão no grafo: {sorted(faltam)}"

    def caso(nome, esperado_caminho, protocolo=None, decisao=None):
        def conferir():
            g = teste.get("g") or GrafoComLLMFixo()
            antes = len(g.gravacoes)
            estado = g.rodar(nome)
            conferir_caminho(estado, esperado_caminho)
            if protocolo:
                assert len(g.gravacoes) > antes, "o nó registrar não chamou registrar_decisao no MCP"
                gravado = g.gravacoes[-1]
                igual((gravado.get("protocolo"), gravado.get("decisao")), (protocolo, decisao), "o que foi gravado")
        return conferir

    e.conferir("7.5 o grafo compila com todos os nós", montar)
    e.conferir("C3 dado sensível -> recusar", caso("C3_dado_de_saude", ["receber", "proteger_entrada", "recusar"]))
    e.conferir("C4 fora do escopo -> recusar", caso("C4_fora_do_escopo", ["receber", "proteger_entrada", "recusar"]))
    e.conferir("C5 sem matrícula -> pedir_dados", caso("C5_sem_matricula", ["receber", "proteger_entrada", "extrair", "pedir_dados"]))
    e.conferir("C1 abono -> registra deferido (paralelismo + ciclo)", caso("C1_abono_simples", COMPLETO + ["registrar"], "ae788d33", "deferido"))
    e.conferir("C6 conflito de escala -> registra indeferido (N5)", caso("C6_conflito_de_escala", COMPLETO + ["registrar"], "6f1b47d7", "indeferido"))
    e.conferir("C12 início proibido -> registra indeferido (N3)", caso("C12_inicio_proibido", COMPLETO + ["registrar"], "7c458e62", "indeferido"))


@etapa("8", "Persistência e aprovação da chefia", "etapa07_grafo.py; aula7/exemplos/07_aprovacao_revisao/main.py")
def etapa8(e: Etapa):
    teste = {}

    def pausa():
        g = GrafoComLLMFixo()
        estado = g.rodar("C2_ferias_com_venda")
        conferir_caminho(estado, COMPLETO)
        igual(g.proximo("C2_ferias_com_venda"), ("aprovacao_chefia",), "onde o C2 parou")
        assert not g.gravacoes, "o C2 gravou ANTES da aprovação da chefia"
        teste["g"] = g

    def depende():
        if "g" not in teste:
            raise NotImplementedError("ETAPA 8.2 (este item depende do anterior)")
        return teste["g"]

    def pendentes():
        g = depende()
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            g.grafo.listar_pendentes(g.app, g.checkpointer)
        texto = saida.getvalue()
        assert "conferir-C2_ferias_com_venda" in texto and "aprovacao_chefia" in texto, f"--pendentes não mostrou o C2 pausado: {texto[:200]}"

    def rejeita_e_aprova():
        g = depende()
        with contextlib.redirect_stdout(io.StringIO()):
            g.grafo.retomar(g.app, "conferir-C2_ferias_com_venda", "nao:confirme o valor da venda", "1010")
        igual(g.proximo("C2_ferias_com_venda"), ("aprovacao_chefia",), "depois de rejeitar, o C2 deveria pausar de novo na chefia")
        with contextlib.redirect_stdout(io.StringIO()):
            g.grafo.retomar(g.app, "conferir-C2_ferias_com_venda", "sim", "1010")
        igual(g.proximo("C2_ferias_com_venda"), (), "depois de aprovar, o C2 deveria terminar")
        assert g.gravacoes, "a aprovação não chegou ao registrar"
        gravado = g.gravacoes[-1]
        igual((gravado.get("protocolo"), gravado.get("decisao"), gravado.get("aprovador")), ("b7b6f485", "deferido", "1010"),
              "o que foi gravado (protocolo, decisão, aprovador)")

    def duas_rejeicoes():
        g = GrafoComLLMFixo()
        g.rodar("C11_diaria_exterior")
        with contextlib.redirect_stdout(io.StringIO()):
            g.grafo.retomar(g.app, "conferir-C11_diaria_exterior", "nao:primeira", "1011")
            g.grafo.retomar(g.app, "conferir-C11_diaria_exterior", "nao:segunda", "1011")
        igual(g.proximo("C11_diaria_exterior"), (), "depois de 2 rejeições o fluxo deveria terminar")
        igual(g.gravacoes[-1].get("decisao") if g.gravacoes else None, "indeferido_pela_chefia", "decisão gravada")

    e.conferir("8.2 o C2 pausa na chefia sem gravar nada", pausa)
    e.conferir("8.4 --pendentes mostra o C2 pausado", pendentes)
    e.conferir("8.3/8.4 rejeita, refaz, aprova (1010) e grava", rejeita_e_aprova)
    e.conferir("8.3 duas rejeições -> indeferido_pela_chefia", duas_rejeicoes)


@etapa("9", "Segurança (Marco completo)", "etapa05_mcp_rh.py e etapa07_grafo.py; aula5/exemplos/10_seguranca/server_seguro.py")
def etapa9(e: Etapa):
    token = os.getenv("TOKEN_REGISTRO", "")
    base = {"protocolo": "conferir-9", "matricula": "1002", "tipo": "ferias", "inicio": "2027-04-12", "fim": "2027-04-26",
            "decisao": "deferido", "aprovador": "1010", "despacho": "teste do conferir.py", "token": token, "thread_id": "conferir-9"}

    def negacoes_9_2():
        try:
            casos = {
                "sem token": mcp("registrar_decisao", {**base, "token": "errado"}),
                "decisão fora do enum": mcp("registrar_decisao", {**base, "decisao": "aprovadissimo"}),
                "autoaprovação (1002)": mcp("registrar_decisao", {**base, "aprovador": "1002"}),
                "chefia errada (1011)": mcp("registrar_decisao", {**base, "aprovador": "1011"}),
            }
            certo = mcp("registrar_decisao", base)
        finally:
            teste_auditoria["linhas"] = [l for l in _linhas_auditoria() if '"conferir-9"' in l]
            limpar_saidas()
        passaram = [nome for nome, r in casos.items() if r.get("sucesso")]
        if len(passaram) == 4:
            raise NotImplementedError("ETAPA 9.2")
        assert not passaram, f"o server deveria NEGAR: {passaram}"
        assert certo.get("sucesso"), f"a chefia certa (1010) com o token certo deveria gravar: {certo}"

    teste_auditoria = {}

    def _linhas_auditoria():
        arquivo = PASTA / "saidas" / "auditoria.jsonl"
        return arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []

    def auditoria_9_3():
        linhas = teste_auditoria.get("linhas", [])
        if not linhas:
            raise NotImplementedError("ETAPA 9.3")
        registros = [json.loads(l) for l in linhas]
        acessos = {r.get("decisao_acesso") for r in registros}
        assert {"ALLOW", "DENY"} <= acessos, f"esperava linhas ALLOW e DENY, achei {acessos}"
        assert not (token and any(token in l for l in linhas)), "o TOKEN aparece na auditoria (não pode)"

    def saida_9_4():
        g = GrafoComLLMFixo()
        estado = {"thread_id": "conferir-9-4", "pedido": PEDIDOS_FIXOS["C1"], "decisao": "deferido", "rejeicoes": 0,
                  "aprovador": "sistema", "despacho": "Defiro. CPF do servidor: 123.456.789-09.", "caminho": []}
        r = g.grafo.registrar(estado)
        assert not g.gravacoes, "um despacho com CPF foi enviado para gravação"
        igual(r.get("resultado"), "bloqueado_na_saida", "resultado do registrar com CPF no despacho")

    e.conferir("9.2 o server nega: sem token, enum, autoaprovação, chefia errada", negacoes_9_2)
    e.conferir("9.3 auditoria com ALLOW e DENY, sem o token", auditoria_9_3)
    e.conferir("9.4 guardrail de saída: despacho com CPF não é gravado", saida_9_4)


@etapa("10", "Observabilidade", "etapa10_governanca.py e etapa10_observabilidade.py; aula5/exemplos/11_observabilidade/")
def etapa10(e: Etapa):
    def hook_10_1():
        from etapa10_governanca import Governanca
        g = Governanca(verbose=False)
        agente = SimpleNamespace(name="Financeiro")
        ctx = SimpleNamespace(tool_arguments='{"tipo_destino": "exterior"}', usage=SimpleNamespace(total_tokens=321))
        asyncio.run(g.on_tool_end(ctx, agente, SimpleNamespace(name="tabela_diarias"), '{"moeda": "USD"}'))
        asyncio.run(g.on_agent_end(ctx, agente, "ok"))
        if not g.eventos:
            raise NotImplementedError("ETAPA 10.1")
        texto = json.dumps(g.eventos, ensure_ascii=False, default=str)
        assert "tabela_diarias" in texto and "321" in texto, f"os eventos deveriam ter a tool e os tokens: {texto[:200]}"

    def medido_10_2():
        import etapa10_observabilidade as o
        def no_teste(estado):
            return {"caminho": ["teste"]}
        embrulhado = o.medido("no_teste", no_teste)
        if embrulhado is no_teste:
            raise NotImplementedError("ETAPA 10.2")
        try:
            igual(embrulhado({"thread_id": "conferir-10"}), {"caminho": ["teste"]}, "o nó embrulhado devolve o mesmo dicionário")
            linhas = [l for l in o.ARQUIVO_METRICAS.read_text(encoding="utf-8").splitlines() if '"conferir-10"' in l]
            assert linhas, "nenhuma linha com o thread_id em saidas/metricas.jsonl"
            r = o.resumo("conferir-10")
        finally:
            limpar_saidas()
        faltam = {"nos", "segundos_total", "mais_lento", "tokens_total"} - set(r)
        assert not faltam, f"resumo() sem as chaves {sorted(faltam)}"

    e.conferir("10.1 o hook registra tool, argumentos e tokens", hook_10_1)
    e.conferir("10.2/10.3 medido() grava a métrica e resumo() resume", medido_10_2)


@etapa("11", "Demonstração e entrega", "ENTREGA.md")
def etapa11(e: Etapa):
    def tabela():
        linhas = [l for l in (PASTA / "ENTREGA.md").read_text(encoding="utf-8").splitlines() if re.match(r"\|\s*C\d+_", l)]
        cheias = [l for l in linhas if l.split("|")[2].strip() and l.split("|")[3].strip()]
        if not cheias:
            raise NotImplementedError("Etapa 11 (tabela dos 12 casos do ENTREGA.md)")
        assert len(cheias) == 12, f"{len(cheias)} de 12 casos com caminho e resultado no ENTREGA.md"

    e.conferir("tabela dos 12 casos preenchida no ENTREGA.md", tabela)


# ===================================================================== opcionais
@etapa("🆕A", "Votação em paralelo (opcional)", "etapa02_extracao.py")
def opcional_a(e: Etapa):
    def instrucoes_a1():
        import etapa02_extracao as x
        if not x.INSTRUCOES_VOTANTES:
            raise NotImplementedError("🆕 A.1")
        igual(len(set(x.INSTRUCOES_VOTANTES)), 3, "quantidade de instruções DIFERENTES em INSTRUCOES_VOTANTES")

    def paralelo_a2():
        import etapa02_extracao as x
        base = dict(tipo="ferias", matricula="1002", data_inicio="2027-04-12", data_fim="2027-04-26", dias_vendidos=10,
                    destino=None, tipo_destino=None, justificativa="x")
        chamados = []

        class RunnerFixo:  # no lugar do LLM: cada extrator "vota" uma data_fim diferente só no 3º voto
            @staticmethod
            async def run(agente, texto, **kwargs):
                chamados.append(agente.instructions)
                fim = "2027-04-25" if len(chamados) == 3 else "2027-04-26"  # decidido ANTES do await
                await asyncio.sleep(0.2)  # se for em paralelo, os 3 juntos levam ~0,2 s
                return SimpleNamespace(final_output=x.Pedido(**{**base, "data_fim": fim}))

        real, x.Runner = x.Runner, RunnerFixo
        try:
            import time
            inicio = time.perf_counter()
            pedido, divergencia, votos = asyncio.run(x.extrair_com_votacao("texto qualquer"))
            segundos = time.perf_counter() - inicio
        finally:
            x.Runner = real
        igual(len(votos), 3, "quantidade de votos")
        igual(len(set(chamados)), 3, "extratores com instruções diferentes chamados")
        igual((pedido.data_fim, divergencia), ("2027-04-26", False), "decisão por maioria (2 de 3)")
        assert segundos < 0.5, f"os 3 extratores levaram {segundos:.1f}s: estão rodando em SEQUÊNCIA, não em paralelo (asyncio.gather)"
        return f"3 votos em {segundos:.2f}s"

    e.conferir("🆕 A.1 três instruções diferentes", instrucoes_a1)
    e.conferir("🆕 A.2 os 3 extratores rodam em paralelo e a votação decide", paralelo_a2)


@etapa("🆕B", "Hooks que barram (opcional)", "etapa10_governanca.py")
def opcional_b(e: Etapa):
    def barra():
        from etapa10_governanca import Governanca, LimiteExcedido, PERMISSOES
        if not PERMISSOES:
            raise NotImplementedError("🆕 B.1")
        g = Governanca(verbose=False)
        try:
            asyncio.run(g.on_tool_start(None, SimpleNamespace(name="Coordenador"), SimpleNamespace(name="consultar_remuneracao")))
            raise AssertionError("o Coordenador usou consultar_remuneracao e o hook não barrou")
        except LimiteExcedido:
            pass
        g = Governanca(max_tools=1, verbose=False)
        asyncio.run(g.on_tool_start(None, SimpleNamespace(name="Normas"), SimpleNamespace(name="consultar_normas")))
        try:
            asyncio.run(g.on_tool_start(None, SimpleNamespace(name="Normas"), SimpleNamespace(name="consultar_normas")))
            raise AssertionError("a 2ª tool com max_tools=1 não foi barrada")
        except LimiteExcedido:
            pass

    e.conferir("🆕 B barra tool fora da lista e orçamento estourado", barra)


@etapa("🆕C", "Humano na entrada (opcional)", "etapa07_grafo.py")
def opcional_c(e: Etapa):
    def triagem():
        g = GrafoComLLMFixo(triagem=True)
        estado = g.rodar("C10_zona_cinzenta")
        conferir_caminho(estado, ["receber", "proteger_entrada"])
        igual(g.proximo("C10_zona_cinzenta"), ("triagem_humana",), "onde o C10 parou")
        with contextlib.redirect_stdout(io.StringIO()):
            g.grafo.retomar(g.app, "conferir-C10_zona_cinzenta", "nao:procure a junta médica", "rh")
        igual(g.proximo("C10_zona_cinzenta"), (), "depois do 'nao' o fluxo deveria terminar")

    e.conferir("🆕 C o C10 pausa na triagem e o 'nao' recusa", triagem)


# ===================================================================== execução
def main() -> None:
    print(f"conferir.py  ({'com' if COM_LLM else 'sem'} LLM{', com opcionais' if COM_OPCIONAIS else ''})")
    escolhidas = [e for e in ETAPAS if (not ARGS or e.numero in ARGS)
                  and (COM_OPCIONAIS or not e.numero.startswith("🆕") or e.numero in ARGS)]
    try:
        for e in escolhidas:
            print(f"\nEtapa {e.numero}: {e.titulo}   (onde olhar: {e.referencia})")
            e.rodar()
    finally:
        limpar_saidas()

    print("\n" + "=" * 70)
    for e in escolhidas:
        print(f"  Etapa {e.numero:<4} {e.situacao():<17} {e.titulo}")
    feitas = {e.numero for e in escolhidas if e.situacao().startswith("✅")}
    if {"0", "1", "2", "3", "4", "5", "6"} <= feitas:
        print("\n  🎯 Marco mínimo atingido (Etapas 0 a 6).")
    if {str(n) for n in range(10)} <= feitas:
        print("  🏁 Marco completo atingido (Etapas 0 a 9).")
    if not COM_LLM:
        print("\n  Dica: rode também `python conferir.py --llm` para conferir as partes que dependem do modelo.")


if __name__ == "__main__":
    main()
