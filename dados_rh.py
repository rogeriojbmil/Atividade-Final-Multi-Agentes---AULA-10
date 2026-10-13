"""
dados_rh.py -- (PRONTO) leitura dos arquivos de dados/. Não é o foco do exercício: use à vontade.

    servidores = carregar_servidores()        # {"1002": {"nome": "Bruno Castro", "equipe": "Plantão A", ...}}
    carregar_escala()                         # [{"matricula": "1006", "equipe": "Cartório", "inicio": "2027-07-05", ...}]
    carregar_diarias()                        # {"exterior": {"moeda": "USD", "valor_diaria": 320.0}, ...}
    carregar_feriados_locais()                # {"2027-04-21": "Tiradentes", ...}  (plano B da API)
    normas("ferias")                          # [{"codigo": "N1", "tema": "férias", "regra": "..."}]

Consultas prontas para as tools do MCP Server (Etapa 5): servidor_publico(), escala_da_equipe(), diaria(),
remuneracao(). Elas só cuidam dos DADOS; declarar a tool e escrever a docstring é com você.
"""
import csv
import json
import unicodedata
from pathlib import Path

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados"
SAIDAS = PASTA / "saidas"
SAIDAS.mkdir(exist_ok=True)


def sem_acento(texto: str) -> str:
    """'Férias' -> 'ferias'. Útil para comparar temas e nomes digitados de jeitos diferentes."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower().strip()


def carregar_servidores() -> dict[str, dict]:
    """Cadastro indexado pela matrícula. Números já convertidos; `chefia` vazia vira None."""
    with open(DADOS / "servidores.csv", encoding="utf-8", newline="") as arquivo:
        servidores = {}
        for linha in csv.DictReader(arquivo):
            linha["saldo_ferias_dias"] = int(linha["saldo_ferias_dias"])
            linha["abonos_restantes"] = int(linha["abonos_restantes"])
            linha["salario_base"] = float(linha["salario_base"])
            linha["chefia"] = linha["chefia"] or None
            servidores[linha["matricula"]] = linha
    return servidores


def carregar_escala() -> list[dict]:
    """Afastamentos já marcados (datas no formato AAAA-MM-DD)."""
    with open(DADOS / "escala.csv", encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def carregar_diarias() -> dict[str, dict]:
    """Tabela de diárias por tipo de destino (capital, interior, exterior)."""
    with open(DADOS / "diarias.csv", encoding="utf-8", newline="") as arquivo:
        return {l["tipo_destino"]: {"moeda": l["moeda"], "valor_diaria": float(l["valor_diaria"])}
                for l in csv.DictReader(arquivo)}


def carregar_feriados_locais() -> dict[str, str]:
    """Cópia local dos feriados de 2027, no formato da BrasilAPI: {data: nome}."""
    with open(DADOS / "feriados_2027.json", encoding="utf-8") as arquivo:
        return {f["date"]: f["name"] for f in json.load(arquivo)}


def normas(tema: str | None = None) -> list[dict]:
    """As regras N1..N10 de dados/normas.md. Com `tema`, só as daquele tema (sem diferenciar acento/maiúscula)."""
    regras = []
    for linha in (DADOS / "normas.md").read_text(encoding="utf-8").splitlines():
        partes = [p.strip() for p in linha.strip().strip("|").split("|")]
        if len(partes) == 3 and partes[0].startswith("N") and partes[0][1:].isdigit():
            regras.append({"codigo": partes[0], "tema": partes[1], "regra": partes[2]})
    if tema:
        regras = [r for r in regras if sem_acento(r["tema"]) == sem_acento(tema)]
    return regras



# ------------------------------------------------------------------ consultas usadas pelo MCP Server (Etapa 5)
CAMPOS_PUBLICOS = ("matricula", "nome", "cargo", "equipe", "saldo_ferias_dias", "abonos_restantes", "chefia")


def servidor_publico(matricula: str) -> dict:
    """Cadastro de UM servidor SEM o salário, ou {"erro": ...} se a matrícula não existe."""
    servidor = carregar_servidores().get(str(matricula).strip())
    if servidor is None:
        return {"erro": "matrícula não encontrada"}
    return {campo: servidor[campo] for campo in CAMPOS_PUBLICOS}


def escala_da_equipe(equipe: str, inicio: str, fim: str) -> dict:
    """Afastamentos da equipe que se sobrepõem a [inicio, fim] e o limite da regra N5 (30%, mínimo 1)."""
    tamanho = sum(1 for s in carregar_servidores().values() if sem_acento(s["equipe"]) == sem_acento(equipe))
    if tamanho == 0:
        return {"erro": f"equipe não encontrada: {equipe}"}
    afastamentos = [a for a in carregar_escala()
                    if sem_acento(a["equipe"]) == sem_acento(equipe) and a["inicio"] <= fim and inicio <= a["fim"]]
    return {"equipe": equipe, "tamanho_equipe": tamanho, "limite_afastados": max(1, int(tamanho * 0.3)),
            "afastamentos": afastamentos}


def diaria(tipo_destino: str) -> dict:
    """Moeda e valor da diária do tipo de destino, ou {"erro": ...}."""
    return carregar_diarias().get(sem_acento(tipo_destino), {"erro": "use capital, interior ou exterior"})


def remuneracao(matricula: str) -> dict:
    """Salário-base de um servidor (dado RESTRITO), ou {"erro": ...}."""
    servidor = carregar_servidores().get(str(matricula).strip())
    if servidor is None:
        return {"erro": "matrícula não encontrada"}
    return {"matricula": servidor["matricula"], "salario_base": servidor["salario_base"]}

if __name__ == "__main__":
    print(len(carregar_servidores()), "servidores;", len(carregar_escala()), "afastamentos;",
          len(carregar_feriados_locais()), "feriados locais;", len(normas()), "regras")
    print(normas("férias"))
