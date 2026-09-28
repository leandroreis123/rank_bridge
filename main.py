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
