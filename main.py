import asyncio
import json
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CANAL_NOME = "✅┇pedir-set"
NOME_CANAL_RELATORIO = "relatorio-setados"
CARGOS_PERMITIDOS = ["👑┇00", "🥇┇01", "🥇┇02", "🥇┇03", "✍️┇EDITOR DO SERVER",
                     "🔫┇LIDER TÁTICO", "👨‍💼 ┇GERENTE GERAL"]
TEMPO_AUTOEXCLUSAO = 5 * 60  # 5 minutos
ARQUIVO_JSON = "registros.json"
EMOJI_VALIDO = "✅"

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

if not os.path.exists(ARQUIVO_JSON):
    with open(ARQUIVO_JSON, 'w', encoding='utf-8') as f:
        json.dump([], f, indent=4)


def carregar_registros():
    with open(ARQUIVO_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


def salvar_registros(dados):
    with open(ARQUIVO_JSON, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
    print(f"Registros salvos no arquivo {ARQUIVO_JSON}")


def salvar_registro(novo_registro):
    dados = carregar_registros()
    dados.append(novo_registro)
    salvar_registros(dados)
    print(f"Registro salvo: {novo_registro}")
    print(f"Total de registros: {len(dados)}")


def marcar_como_setado(mensagem_id):
    dados = carregar_registros()
    for item in dados:
        if item.get("mensagem_id") == mensagem_id:
            item["setado"] = True
            break
    salvar_registros(dados)


@bot.event
async def on_ready():
    print(f'Bot logado como {bot.user}')


@bot.event
async def on_message(message):
    print(f"Mensagem recebida: {message.content}")
    if message.author.bot:
        return

    if message.channel.name != CANAL_NOME:
        return

    linhas = message.content.strip().splitlines()
    if len(linhas) < 4:
        await bot.process_commands(message)
        return

    dados = {}
    for linha in linhas:
        partes = linha.split(":", 1)
        if len(partes) != 2:
            continue
        chave = partes[0].strip().lower()
        valor = partes[1].strip()

        try:
            dados[chave] = valor
        except ValueError:
            await bot.process_commands(message)
            return
    dados = {k.lower(): v for k, v in dados.items()}
    if not all(k in dados for k in ("id", "nome", "telefone", "rec")):
        await bot.process_commands(message)
        return

    novo_registro = {
        "usuario": message.author.display_name,
        "id": dados["id"],
        "nome": dados["nome"],
        "telefone": dados["telefone"],
        "rec": dados["rec"],
        "mensagem_id": message.id,
        "data": message.created_at.strftime("%d/%m/%Y"),
        "hora": message.created_at.strftime("%H:%M:%S"),
        "setado": False
    }

    salvar_registro(novo_registro)
    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if reaction.message.channel.name != CANAL_NOME:
        return

    if str(reaction.emoji) == EMOJI_VALIDO:
        marcar_como_setado(reaction.message.id)

        # Buscar o autor da mensagem
        autor = reaction.message.author

        # Carregar registros para buscar dados
        registros = carregar_registros()
        registro = next((r for r in registros if r["mensagem_id"] == reaction.message.id), None)

        if not registro:
            print("Registro não encontrado para alterar apelido/tag.")
            return

        # Alterar apelido
        novo_apelido = f"{registro['id']} | {registro['nome']}"
        try:
            await autor.edit(nick=novo_apelido)
            print(f"Apelido de {autor} alterado para: {novo_apelido}")
        except discord.Forbidden:
            print(f"Sem permissão para mudar apelido de {autor}.")
        except Exception as e:
            print(f"Erro ao mudar apelido: {e}")

        # Adicionar role "Olheiro"
        role = discord.utils.get(reaction.message.guild.roles, name="olheiro")
        if role:
            try:
                await autor.add_roles(role)
                print(f"Tag 'olheiro' adicionada para {autor}.")
            except discord.Forbidden:
                print(f"Sem permissão para adicionar tag em {autor}.")
            except Exception as e:
                print(f"Erro ao adicionar role: {e}")
        else:
            print("Tag 'olheiro' não encontrada no servidor.")


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return

    if reaction.message.channel.name != CANAL_NOME:
        return

    if str(reaction.emoji) == EMOJI_VALIDO:
        # Marcar como não setado no JSON
        dados = carregar_registros()
        for item in dados:
            if item.get("mensagem_id") == reaction.message.id:
                item["setado"] = False
                break
        salvar_registros(dados)
        print(f"Registro com mensagem_id {reaction.message.id} desmarcado como setado.")


def criar_embed(registros, titulo):
    embed = discord.Embed(title=titulo, color=0x2ecc71)
    if not registros:
        embed.description = "Nenhum registro encontrado."
        return embed

    for r in registros:
        setado = "✅" if r.get("setado") else "❌"
        data = r.get("data", "N/A")
        hora = r.get("hora", "N/A")
        embed.add_field(
            name=f"{r['id']} ({r['nome']})",
            value=(
                f"👤 **Usuário:** {r['usuario']}\n"
                f"🆔 **ID:** {r['id']}\n"
                f"🕒 **Data:** {data} às {hora}\n"
                f"💰 **setado:** {setado}"
            ),
            inline=False
        )
    return embed


async def obter_ou_criar_canal(guild):
    canal = discord.utils.get(guild.text_channels, name=NOME_CANAL_RELATORIO)
    if canal:
        return canal

    # Criando permissões para os cargos permitidos
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
    }

    for cargo_nome in CARGOS_PERMITIDOS:
        cargo = discord.utils.get(guild.roles, name=cargo_nome)
        if cargo:
            overwrites[cargo] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True)

    return await guild.create_text_channel(NOME_CANAL_RELATORIO, overwrites=overwrites)


async def enviar_relatorio(ctx, registros, titulo):
    canal = await obter_ou_criar_canal(ctx.guild)
    embed = criar_embed(registros, titulo)
    mensagem = await canal.send(embed=embed)
    await ctx.message.delete()
    await asyncio.sleep(TEMPO_AUTOEXCLUSAO)
    await mensagem.delete()


async def verificar_permissao(ctx):
    cargos_usuario = [cargo.name for cargo in ctx.author.roles]
    for cargo in CARGOS_PERMITIDOS:
        if cargo in cargos_usuario:
            return True
    return False


@bot.command(name='setados')
async def listar_setados(ctx):
    if not await verificar_permissao(ctx):
        return await ctx.send("Você não tem permissão para usar este comando.")

    registros = [r for r in carregar_registros() if r.get("setado")]
    await enviar_relatorio(ctx, registros, "Registros Setados")


@bot.command(name='pendentes')
async def listar_pendentes(ctx):
    if not await verificar_permissao(ctx):
        return await ctx.send("Você não tem permissão para usar este comando.")

    registros = [r for r in carregar_registros() if not r.get("setado")]
    await enviar_relatorio(ctx, registros, "Registros Pendentes")


@bot.command(name='tudo')
async def listar_tudo(ctx):
    if not await verificar_permissao(ctx):
        return await ctx.send("Você não tem permissão para usar este comando.")

    registros = carregar_registros()
    await enviar_relatorio(ctx, registros, "Todos os Registros")


# Mini servidor web pra enganar o Render
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Bot do Discord online!')


def run_web_server():
    server = HTTPServer(('0.0.0.0', 10000), PingHandler)
    server.serve_forever()


# Inicia o servidor web em uma thread separada
threading.Thread(target=run_web_server).start()
bot.run(TOKEN)