#!/usr/bin/env bash
# configurar_ambiente.sh -- prepara o ambiente do exercício final no Linux ou no Mac. Rode UMA vez, antes da aula.
#
#   cd material-pcdf/aula10
#   bash configurar_ambiente.sh
#
# O que faz: confere o Python, cria o .venv, instala o requirements.txt, cria o .env (com um TOKEN_REGISTRO aleatório),
# pede a sua OPENAI_API_KEY (opcional) e roda o verificar_ambiente.py. Pode rodar de novo sem problema: o que já
# existe é mantido.
set -euo pipefail
cd "$(dirname "$0")"

passo() { printf '\n==> %s\n' "$1"; }

passo "1/5 Procurando o Python (3.10 a 3.13)"
PYTHON=""
for candidato in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$candidato" >/dev/null 2>&1; then
    versao="$("$candidato" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
    if [[ "$versao" =~ ^3\.(1[0-3])\.[0-9]+$ && "$versao" != "3.11.0" ]]; then
      PYTHON="$candidato"; echo "    Python $versao ($candidato)"; break
    fi
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "    Não achei Python 3.10 a 3.13 (o 3.11.0 não serve). Instale e rode este script de novo." >&2
  exit 1
fi

passo "2/5 Ambiente virtual (.venv)"
if [[ -x .venv/bin/python ]]; then
  echo "    .venv já existe: mantido"
else
  "$PYTHON" -m venv .venv
  echo "    .venv criado"
fi

passo "3/5 Instalando as dependências (pode levar alguns minutos na primeira vez)"
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet
echo "    dependências instaladas"

passo "4/5 Arquivo .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    .env criado a partir do .env.example"
fi
if grep -qx 'TOKEN_REGISTRO=troque-este-valor' .env; then
  token="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(12))')"
  .venv/bin/python - "$token" <<'PY'
import sys, pathlib
p = pathlib.Path(".env")
p.write_text(p.read_text(encoding="utf-8").replace("TOKEN_REGISTRO=troque-este-valor", f"TOKEN_REGISTRO={sys.argv[1]}"), encoding="utf-8")
PY
  echo "    TOKEN_REGISTRO gerado (aleatório)"
fi
if grep -qx 'PROVEDOR=openai' .env && grep -qx 'OPENAI_API_KEY=' .env; then
  if [[ -t 0 ]]; then
    read -r -p "    Cole a sua OPENAI_API_KEY e tecle Enter (ou só Enter para preencher depois no .env): " chave
  else
    chave=""
  fi
  if [[ -n "${chave// /}" ]]; then
    .venv/bin/python - "$chave" <<'PY'
import sys, pathlib
p = pathlib.Path(".env")
linhas = ["OPENAI_API_KEY=" + sys.argv[1].strip() if l == "OPENAI_API_KEY=" else l for l in p.read_text(encoding="utf-8").splitlines()]
p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
PY
    echo "    chave gravada no .env (o .env não vai para o git)"
  fi
fi

passo "5/5 Verificando o ambiente"
set +e
.venv/bin/python verificar_ambiente.py
resultado=$?
set -e

printf '\nPara trabalhar no exercício, em cada terminal novo:\n    cd %s\n    source .venv/bin/activate\n' "$(pwd)"
exit "$resultado"
