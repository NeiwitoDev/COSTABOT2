"""
Bot de Discord Principal
Sistemas: Bienvenida, AutoMod, Bot Setup, Tickets
Inicia con: DISCORD_BOT_TOKEN en variables de entorno
"""
import os
import sys
import asyncio
import logging

import discord
from discord.ext import commands

# Cargar variables de entorno desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import database as db

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bot")

# ─── Intents ──────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True   # Necesario para automod
intents.members = True            # Necesario para on_member_join (bienvenidas)
intents.guilds = True

# ─── Bot ──────────────────────────────────────────────────────────────────────

COGS = [
    "cogs.welcome",
    "cogs.automod",
    "cogs.setup",
    "cogs.tickets",
    "cogs.embed",
    "cogs.moderation",
    "cogs.help",
]


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            description="Bot con sistemas de bienvenida, automod y tickets.",
            help_command=None,
        )
        # Cache de prefixes por guild (se carga de la BD en on_ready)
        self._prefix_cache: dict[int, str] = {}

    async def _get_prefix(self, bot: "Bot", message: discord.Message) -> list[str]:
        if message.guild:
            prefix = self._prefix_cache.get(message.guild.id, "!")
        else:
            prefix = "!"
        return commands.when_mentioned_or(prefix)(bot, message)

    async def setup_hook(self):
        # Inicializar la base de datos
        await db.init_db()
        log.info("Base de datos inicializada.")

        # Cargar cogs
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"Cog cargado: {cog}")
            except Exception as e:
                log.error(f"Error cargando cog {cog}: {e}")

        # Sincronizar slash commands globalmente
        synced = await self.tree.sync()
        log.info(f"Sincronizados {len(synced)} comando(s) de slash.")

    async def on_ready(self):
        log.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        log.info(f"Servidores: {len(self.guilds)}")

        # Precargar prefixes de la BD
        for guild in self.guilds:
            settings = await db.get_guild_settings(guild.id)
            if settings:
                self._prefix_cache[guild.id] = settings.get("prefix") or "!"

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} CostaRP - Dev: Neiwito.",
            )
        )
        log.info("Bot listo.")

    async def on_guild_join(self, guild: discord.Guild):
        log.info(f"Nuevo servidor: {guild.name} (ID: {guild.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} CostaRP - Dev: Neiwito.",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ No tienes permisos para usar este comando.", delete_after=5)
            return
        log.error(f"Error en comando: {error}", exc_info=error)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ):
        msg = "❌ Ocurrió un error al ejecutar el comando."
        if isinstance(error, discord.app_commands.MissingPermissions):
            msg = "❌ No tienes permisos para usar este comando."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass
        log.error(f"Error en slash command: {error}", exc_info=error)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        log.critical("DISCORD_BOT_TOKEN no está configurado. Configúralo como variable de entorno.")
        sys.exit(1)

    bot = Bot()

    try:
        asyncio.run(bot.start(token))
    except KeyboardInterrupt:
        log.info("Bot detenido manualmente.")
    except discord.LoginFailure:
        log.critical("Token inválido. Verifica DISCORD_BOT_TOKEN.")
        sys.exit(1)
    except Exception as e:
        log.critical(f"Error fatal: {e}", exc_info=e)
        sys.exit(1)


if __name__ == "__main__":
    main()
