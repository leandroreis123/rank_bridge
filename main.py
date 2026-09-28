from flask import Flask, request, jsonify
import json
import os

app = Flask(__name__)

ARQUIVO = "carteiras.json"

if not os.path.exists(ARQUIVO):
    with open(ARQUIVO, "w", encoding="utf-8") as arquivo:
        json.dump({}, arquivo)


def carregar_dados():
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def salvar_dados(dados):
    with open(ARQUIVO, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4)


@app.post("/sync")
def sincronizar():

    dados = request.get_json()

    if not dados:
        return jsonify({
            "sucesso": False,
            "erro": "Nenhum dado recebido"
        }), 400

    user_id = str(dados.get("user_id"))
    sonhos = dados.get("sonhos")

    if not user_id or user_id == "None" or sonhos is None:
        return jsonify({
            "sucesso": False,
            "erro": "user_id ou sonhos não informado"
        }), 400

    try:
        sonhos = int(sonhos)
    except (ValueError, TypeError):
        return jsonify({
            "sucesso": False,
            "erro": "Quantidade de Sonhos inválida"
        }), 400

    carteiras = carregar_dados()

    carteiras[user_id] = sonhos

    salvar_dados(carteiras)

    return jsonify({
        "sucesso": True,
        "user_id": user_id,
        "sonhos": sonhos
    })


@app.get("/rank")
def ranking():

    carteiras = carregar_dados()

    ranking = sorted(
        carteiras.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return jsonify(ranking[:100])


@app.get("/rank_texto")
def ranking_texto():
    """
    Devolve o ranking já formatado em texto, pronto para o BDFD
    colocar dentro de um embed. Uso: /rank_texto?pagina=2
    """

    carteiras = carregar_dados()

    ranking = sorted(
        carteiras.items(),
        key=lambda x: x[1],
        reverse=True
    )[:100]

    cabecalho = {"Content-Type": "text/plain; charset=utf-8"}

    if not ranking:
        return (
            "⚠️ **Ranking vazio!**\nNinguém foi sincronizado ainda.",
            200,
            cabecalho
        )

    por_pagina = 5

    total_paginas = max(
        1,
        (len(ranking) + por_pagina - 1) // por_pagina
    )

    try:
        pagina = int(request.args.get("pagina", 1))
    except (ValueError, TypeError):
        pagina = 1

    pagina = max(1, min(pagina, total_paginas))

    inicio = (pagina - 1) * por_pagina
    fim = inicio + por_pagina

    linhas = []

    for posicao, (user_id, sonhos) in enumerate(
        ranking[inicio:fim],
        start=inicio + 1
    ):

        if posicao == 1:
            medalha = "🥇"
        elif posicao == 2:
            medalha = "🥈"
        elif posicao == 3:
            medalha = "🥉"
        else:
            medalha = f"`#{posicao}`"

        linhas.append(
            f"{medalha} <@{user_id}>\n"
            f"> 💰 `{sonhos:,}` Sonhos"
        )

    texto = "\n\n".join(linhas)

    texto += (
        f"\n\n*Página {pagina}/{total_paginas} • Top 100 • "
        f"use !rank 2, !rank 3...*"
    )

    return texto, 200, cabecalho


@app.get("/")
def inicio():
    return "Bridge BDFD → Python funcionando!"


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print(f"Iniciando Flask na porta {port}...", flush=True)

    app.run(
        host="0.0.0.0",
        port=port
    )
