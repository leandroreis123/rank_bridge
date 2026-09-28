from flask import Flask, request, jsonify, send_file
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import urlparse
import io
import json
import os
import unicodedata

import requests
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

ARQUIVO = "carteiras.json"
ARQUIVO_PERFIS = "perfis.json"

# =========================
# ARMAZENAMENTO
# =========================
# Se as duas variáveis do Upstash existirem, os dados ficam guardados
# num banco Redis PERMANENTE (não some quando o Render reinicia).
# Se não existirem, usa arquivos locais (que o Render apaga).

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
USAR_UPSTASH = bool(UPSTASH_URL and UPSTASH_TOKEN)

if USAR_UPSTASH:
    print("Armazenamento: Upstash (permanente)", flush=True)
else:
    print(
        "ATENCAO: Upstash NAO configurado. Usando arquivos locais, "
        "que o Render apaga.",
        flush=True
    )


def redis(*comando):
    resposta = requests.post(
        UPSTASH_URL,
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
        json=list(comando),
        timeout=6
    )
    resposta.raise_for_status()

    dados = resposta.json()

    if isinstance(dados, dict) and dados.get("error"):
        raise RuntimeError(dados["error"])

    return dados.get("result")


def redis_hgetall(chave):
    resultado = redis("HGETALL", chave)

    if isinstance(resultado, dict):
        return resultado

    resultado = resultado or []

    return {
        resultado[i]: resultado[i + 1]
        for i in range(0, len(resultado) - 1, 2)
    }


def ler_arquivo(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def gravar_arquivo(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4)


def carregar_dados():

    if USAR_UPSTASH:
        try:
            bruto = redis_hgetall("carteiras")
            return {uid: int(valor) for uid, valor in bruto.items()}
        except Exception as erro:
            print(f"Erro ao ler carteiras do Upstash: {erro}", flush=True)
            return {}

    return ler_arquivo(ARQUIVO)


def salvar_carteira(user_id, sonhos):

    if USAR_UPSTASH:
        redis("HSET", "carteiras", user_id, str(sonhos))
        return

    carteiras = ler_arquivo(ARQUIVO)
    carteiras[user_id] = sonhos
    gravar_arquivo(ARQUIVO, carteiras)


def carregar_perfis():

    if USAR_UPSTASH:
        try:
            bruto = redis_hgetall("perfis")
            return {uid: json.loads(valor) for uid, valor in bruto.items()}
        except Exception as erro:
            print(f"Erro ao ler perfis do Upstash: {erro}", flush=True)
            return {}

    return ler_arquivo(ARQUIVO_PERFIS)


def salvar_perfil(user_id, perfil):

    if USAR_UPSTASH:
        redis("HSET", "perfis", user_id, json.dumps(perfil))
        return

    perfis = ler_arquivo(ARQUIVO_PERFIS)
    perfis[user_id] = perfil
    gravar_arquivo(ARQUIVO_PERFIS, perfis)


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

    # Nome e foto são opcionais: se o BDFD mandar, guardamos
    nome = dados.get("nome")
    avatar = dados.get("avatar")

    try:
        salvar_carteira(user_id, sonhos)

        if nome or avatar:
            salvar_perfil(user_id, {
                "nome": str(nome or "")[:40],
                "avatar": str(avatar or "")[:300]
            })

    except Exception as erro:
        print(f"Erro ao salvar: {erro}", flush=True)

        return jsonify({
            "sucesso": False,
            "erro": "Falha ao salvar os dados"
        }), 500

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
    Versão em texto do ranking. Uso: /rank_texto?pagina=2
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


# =========================
# RANKING EM IMAGEM
# =========================

S = 2  # desenha em dobro de tamanho e reduz no final (bordas mais lisas)

BG = (30, 31, 34)
CARD = (43, 45, 49)
BRANCO = (255, 255, 255)
CINZA = (148, 155, 164)
OURO = (255, 200, 60)
PRATA = (200, 205, 215)
BRONZE = (205, 127, 50)
AZUL = (88, 101, 242)
ESCURO = (30, 31, 34)
TEXTO_SONHOS = (255, 214, 102)

HOSTS_AVATAR = {"cdn.discordapp.com", "media.discordapp.net"}

cache_avatares = {}
cache_imagens = {}


def p(valor):
    return int(valor * S)


@lru_cache(maxsize=32)
def fonte(tamanho):
    return ImageFont.load_default(size=tamanho)


def limpar_nome(nome, user_id):
    # A fonte embutida não tem acentos nem emojis, então tiramos
    # os acentos (João vira Joao) e removemos emojis/letras estilizadas
    nome = unicodedata.normalize("NFKD", nome or "")

    nome = "".join(
        c for c in nome
        if 32 <= ord(c) < 127
    ).strip()

    return nome[:22] or f"Usuario {str(user_id)[-4:]}"


def baixar_avatar(url):

    if not url:
        return None

    if url in cache_avatares:
        return cache_avatares[url]

    try:
        partes = urlparse(url)

        # só baixa de servidores do Discord
        if partes.scheme != "https" or partes.hostname not in HOSTS_AVATAR:
            return None

        resposta = requests.get(
            url.split("?")[0] + "?size=128",
            timeout=4
        )
        resposta.raise_for_status()

        imagem = Image.open(io.BytesIO(resposta.content)).convert("RGBA")

        if len(cache_avatares) > 200:
            cache_avatares.clear()

        cache_avatares[url] = imagem

        return imagem

    except Exception as erro:
        print(f"Falha ao baixar avatar: {erro}", flush=True)
        return None


def avatar_padrao(nome, user_id, tamanho):

    paleta = [
        (88, 101, 242),
        (59, 165, 93),
        (250, 166, 26),
        (235, 69, 158),
        (237, 66, 69)
    ]

    try:
        cor = paleta[int(user_id) % len(paleta)]
    except (ValueError, TypeError):
        cor = paleta[0]

    imagem = Image.new("RGBA", (tamanho, tamanho), cor + (255,))

    ImageDraw.Draw(imagem).text(
        (tamanho / 2, tamanho / 2),
        (nome[:1] or "?").upper(),
        font=fonte(int(tamanho * 0.5)),
        fill=BRANCO,
        anchor="mm"
    )

    return imagem


def avatar_redondo(imagem, tamanho):

    grande = tamanho * 4

    mascara = Image.new("L", (grande, grande), 0)

    ImageDraw.Draw(mascara).ellipse(
        (0, 0, grande - 1, grande - 1),
        fill=255
    )

    mascara = mascara.resize(
        (tamanho, tamanho),
        Image.Resampling.LANCZOS
    )

    imagem = imagem.resize(
        (tamanho, tamanho),
        Image.Resampling.LANCZOS
    )

    saida = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    saida.paste(imagem, (0, 0), mascara)

    return saida


def gerar_imagem(itens, pagina, total_paginas):

    n = max(1, len(itens))

    largura = p(900)
    topo = p(125)
    linha = p(122)
    rodape = p(70)
    altura = topo + n * linha + rodape

    img = Image.new("RGB", (largura, altura), BG)
    d = ImageDraw.Draw(img)

    # Título
    d.text(
        (p(40), p(50)),
        "RANKING DE RIQUEZA",
        font=fonte(p(44)),
        fill=BRANCO,
        anchor="lm"
    )

    d.text(
        (p(40), p(92)),
        "Top 100  |  Sonhos",
        font=fonte(p(24)),
        fill=CINZA,
        anchor="lm"
    )

    d.rounded_rectangle(
        (p(40), p(108), p(150), p(112)),
        radius=p(2),
        fill=OURO
    )

    if not itens:
        d.text(
            (largura // 2, topo + linha // 2),
            "Ninguem foi sincronizado ainda.",
            font=fonte(p(30)),
            fill=CINZA,
            anchor="mm"
        )

    for i, (posicao, user_id, sonhos, nome, av) in enumerate(itens):

        y0 = topo + i * linha
        y1 = y0 + linha - p(14)
        x0 = p(30)
        x1 = largura - p(30)
        cy = (y0 + y1) // 2

        destaque = {1: OURO, 2: PRATA, 3: BRONZE}.get(posicao)
        cor = destaque or AZUL

        d.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=p(20),
            fill=CARD,
            outline=destaque,
            width=p(3)
        )

        # Número da posição
        cx = x0 + p(48)
        raio = p(28)

        d.ellipse(
            (cx - raio, cy - raio, cx + raio, cy + raio),
            fill=cor
        )

        d.text(
            (cx, cy),
            str(posicao),
            font=fonte(p(30)),
            fill=ESCURO if destaque else BRANCO,
            anchor="mm"
        )

        # Foto redonda
        tam = p(78)
        ax = x0 + p(96)
        ay = cy - tam // 2

        d.ellipse(
            (ax - p(4), ay - p(4), ax + tam + p(4), ay + tam + p(4)),
            outline=cor,
            width=p(3)
        )

        if av is None:
            av = avatar_padrao(nome, user_id, tam)

        redondo = avatar_redondo(av, tam)
        img.paste(redondo, (ax, ay), redondo)

        # Nome e Sonhos
        tx = ax + tam + p(26)

        d.text(
            (tx, cy - p(17)),
            nome,
            font=fonte(p(34)),
            fill=BRANCO,
            anchor="lm"
        )

        d.text(
            (tx, cy + p(22)),
            f"{sonhos:,} Sonhos",
            font=fonte(p(26)),
            fill=TEXTO_SONHOS,
            anchor="lm"
        )

    d.text(
        (largura // 2, altura - rodape // 2),
        f"Pagina {pagina}/{total_paginas}",
        font=fonte(p(26)),
        fill=CINZA,
        anchor="mm"
    )

    img = img.resize(
        (largura // S, altura // S),
        Image.Resampling.LANCZOS
    )

    saida = io.BytesIO()
    img.save(saida, "PNG", optimize=True)

    return saida.getvalue()


@app.get("/rank_imagem")
def ranking_imagem():
    """
    Ranking como imagem PNG. Uso: /rank_imagem?pagina=2
    """

    carteiras = carregar_dados()
    perfis = carregar_perfis()

    ranking = sorted(
        carteiras.items(),
        key=lambda x: x[1],
        reverse=True
    )[:100]

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
    fatia = ranking[inicio:inicio + por_pagina]

    chave = (
        pagina,
        total_paginas,
        tuple(
            (
                uid,
                sonhos,
                perfis.get(uid, {}).get("nome", ""),
                perfis.get(uid, {}).get("avatar", "")
            )
            for uid, sonhos in fatia
        )
    )

    if chave not in cache_imagens:

        urls = [
            perfis.get(uid, {}).get("avatar", "")
            for uid, _ in fatia
        ]

        # baixa as fotos ao mesmo tempo para ser mais rápido
        with ThreadPoolExecutor(max_workers=5) as executor:
            avatares = list(executor.map(baixar_avatar, urls))

        itens = []

        for indice, ((uid, sonhos), av) in enumerate(
            zip(fatia, avatares)
        ):
            nome = limpar_nome(
                perfis.get(uid, {}).get("nome"),
                uid
            )

            itens.append(
                (inicio + indice + 1, uid, sonhos, nome, av)
            )

        if len(cache_imagens) > 50:
            cache_imagens.clear()

        cache_imagens[chave] = gerar_imagem(
            itens,
            pagina,
            total_paginas
        )

    return send_file(
        io.BytesIO(cache_imagens[chave]),
        mimetype="image/png",
        max_age=0
    )


@app.get("/rank_paginas")
def rank_paginas():
    """
    Devolve só o número total de páginas (5 usuarios por página, Top 100).
    O BDFD usa isso para desligar o botão Próximo na última página.
    """

    total_usuarios = min(len(carregar_dados()), 100)

    total = max(1, (total_usuarios + 4) // 5)

    return str(total), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/")
def inicio():
    tipo = "permanente (Upstash)" if USAR_UPSTASH else "TEMPORARIO (arquivo)"
    return f"Bridge BDFD → Python funcionando! | Armazenamento: {tipo}"


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    print(f"Iniciando Flask na porta {port}...", flush=True)

    app.run(
        host="0.0.0.0",
        port=port
    )
