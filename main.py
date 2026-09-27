from flask import Flask, request, jsonify
import json
import os
import discord
from discord.ext import commands
from threading import Thread

# =========================
# FLASK
# =========================

app = Flask(__name__)

ARQUIVO = "carteiras.json"

if not os.path.exists(ARQUIVO):
    with open(ARQUIVO, "w", encoding="utf-8") as arquivo:
        json.dump({}, arquivo)


def carregar_dados():
    with open(ARQUIVO, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


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

    if not user_id or sonhos is None:
        return jsonify({
            "sucesso": False,
            "erro": "user_id ou sonhos não informado"
        }), 400

    try:
        sonhos = int(sonhos)

    except:
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


# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# RANKING
# =========================

class RankView(discord.ui.View):

    def __init__(self, ranking):

        super().__init__(timeout=300)

        self.ranking = ranking
        self.pagina = 1

        self.atualizar_botoes()


    def atualizar_botoes(self):

        self.anterior.disabled = self.pagina <= 1
        self.proximo.disabled = self.pagina >= 20


    async def criar_embed(self):

        inicio = (self.pagina - 1) * 5
        fim = inicio + 5

        usuarios = self.ranking[inicio:fim]

        descricao = ""

        for posicao, (user_id, sonhos) in enumerate(
            usuarios,
            start=inicio + 1
        ):

            try:
                user = bot.get_user(int(user_id))

                if user is None:
                    user = await bot.fetch_user(int(user_id))

                nome = user.display_name

            except:
                nome = f"Usuário {user_id}"


            if posicao == 1:
                medalha = "🥇"

            elif posicao == 2:
                medalha = "🥈"

            elif posicao == 3:
                medalha = "🥉"

            else:
                medalha = f"`#{posicao}`"


            descricao += (
                f"{medalha} **{nome}**\n"
                f"> 💰 `{sonhos:,}` Sonhos\n\n"
            )


        if not descricao:
            descricao = "Nenhum usuário encontrado."


        embed = discord.Embed(
            title="╭・🏆・RANKING DE RIQUEZA",
            description=descricao,
            color=0x5865F2
        )

        embed.set_footer(
            text=f"Página {self.pagina}/20 • Top 100"
        )

        return embed


    @discord.ui.button(
        label="Anterior",
        emoji="⬅️",
        style=discord.ButtonStyle.secondary
    )
    async def anterior(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.pagina > 1:
            self.pagina -= 1

        self.atualizar_botoes()

        embed = await self.criar_embed()

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )


    @discord.ui.button(
        label="Próximo",
        emoji="➡️",
        style=discord.ButtonStyle.primary
    )
    async def proximo(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.pagina < 20:
            self.pagina += 1

        self.atualizar_botoes()

        embed = await self.criar_embed()

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )


# =========================
# COMANDO !RANK
# =========================

@bot.command(name="rank")
async def rank(ctx):

    try:

        carteiras = carregar_dados()

        ranking = sorted(
            carteiras.items(),
            key=lambda x: x[1],
            reverse=True
        )[:100]


        if not ranking:

            embed = discord.Embed(
                title="╭・🏆・RANKING",
                description=(
                    "> ⚠️ **Ranking vazio!**\n\n"
                    "Ainda não existem usuários "
                    "sincronizados com o ranking."
                ),
                color=0xED4245
            )

            await ctx.send(embed=embed)

            return


        view = RankView(ranking)

        embed = await view.criar_embed()

        await ctx.send(
            embed=embed,
            view=view
        )


    except Exception as erro:

        print("Erro no !rank:", erro)

        embed = discord.Embed(
            title="╭・❌・ERRO",
            description=(
                "> Não foi possível carregar "
                "o ranking no momento."
            ),
            color=0xED4245
        )

        await ctx.send(embed=embed)


# =========================
# EVENTO READY
# =========================

@bot.event
async def on_ready():

    print(f"Bot conectado como {bot.user}")
    print(f"ID: {bot.user.id}")


# =========================
# RODAR FLASK
# =========================

def iniciar_flask():

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================
# INICIAR TUDO
# =========================

if __name__ == "__main__":

    Thread(
        target=iniciar_flask,
        daemon=True
    ).start()

    token = os.environ.get("DISCORD_TOKEN")

    if not token:
        print("ERRO: DISCORD_TOKEN não configurado.")
    else:
        bot.run(token)
