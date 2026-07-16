"""
Comando /bot-setup
Configura el prefix y el canal de logs de sanciones automáticas.
"""
import discord
from discord import app_commands
from discord.ext import commands

import database as db


class BotSetupModal(discord.ui.Modal, title="⚙️ Configurar Bot"):
    prefix = discord.ui.TextInput(
        label="Prefix del bot",
        placeholder="Ej: ! / $ / > / ?",
        default="!",
        required=True,
        max_length=5,
    )
    log_channel = discord.ui.TextInput(
        label="Canal de logs de sanciones (ID)",
        placeholder="Ej: 123456789012345678",
        required=False,
        max_length=20,
    )
    automod_flood = discord.ui.TextInput(
        label="Umbral de flood (mensajes antes de sancionar)",
        placeholder="Ej: 5  (por defecto: 5 mensajes)",
        default="5",
        required=False,
        max_length=3,
    )
    automod_interval = discord.ui.TextInput(
        label="Intervalo de flood (segundos)",
        placeholder="Ej: 5  (por defecto: 5 segundos)",
        default="5",
        required=False,
        max_length=3,
    )

    def __init__(self, existing_guild: dict | None = None, existing_automod: dict | None = None):
        super().__init__()
        if existing_guild:
            self.prefix.default = existing_guild.get("prefix") or "!"
            log_ch = existing_guild.get("log_channel_id")
            if log_ch:
                self.log_channel.default = str(log_ch)
        if existing_automod:
            self.automod_flood.default = str(existing_automod.get("flood_threshold") or 5)
            self.automod_interval.default = str(existing_automod.get("flood_interval") or 5)

    async def on_submit(self, interaction: discord.Interaction):
        prefix = self.prefix.value.strip() or "!"

        # Canal de logs
        log_channel_id = None
        log_channel_mention = "No configurado"
        log_channel_str = self.log_channel.value.strip()
        if log_channel_str:
            try:
                log_channel_id = int(log_channel_str)
                ch = interaction.guild.get_channel(log_channel_id)
                if not ch:
                    await interaction.response.send_message(
                        "❌ No encontré el canal de logs en este servidor.", ephemeral=True
                    )
                    return
                log_channel_mention = ch.mention
            except ValueError:
                await interaction.response.send_message(
                    "❌ El ID del canal de logs no es válido.", ephemeral=True
                )
                return

        # Flood settings
        try:
            flood_threshold = int(self.automod_flood.value.strip() or "5")
            flood_threshold = max(2, min(flood_threshold, 50))
        except ValueError:
            flood_threshold = 5

        try:
            flood_interval = int(self.automod_interval.value.strip() or "5")
            flood_interval = max(1, min(flood_interval, 60))
        except ValueError:
            flood_interval = 5

        # Guardar configuración
        guild_kwargs: dict = {"prefix": prefix}
        if log_channel_id:
            guild_kwargs["log_channel_id"] = log_channel_id

        await db.set_guild_settings(interaction.guild_id, **guild_kwargs)
        await db.set_automod_settings(
            interaction.guild_id,
            flood_threshold=flood_threshold,
            flood_interval=flood_interval,
            log_channel_id=log_channel_id,
            enabled=1,
            flood_enabled=1,
            links_enabled=1,
        )

        # Actualizar prefix en el caché del bot en caliente
        interaction.client._prefix_cache[interaction.guild_id] = prefix

        embed = discord.Embed(
            title="✅ Configuración del bot guardada",
            color=discord.Color.green(),
        )
        embed.add_field(name="Prefix", value=f"`{prefix}`", inline=True)
        embed.add_field(name="Canal de logs", value=log_channel_mention, inline=True)
        embed.add_field(
            name="AutoMod — Flood",
            value=f"**{flood_threshold}** mensajes en **{flood_interval}s**",
            inline=False,
        )
        embed.add_field(
            name="AutoMod — Links",
            value="✅ Activo",
            inline=True,
        )
        embed.set_footer(text="Usa /welcome-setup y /tickets-setup para configurar los demás sistemas.")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="bot-setup",
        description="Configura el prefix y el canal de logs de sanciones.",
    )
    @app_commands.default_permissions(administrator=True)
    async def configurar_bot(self, interaction: discord.Interaction):
        existing_guild = await db.get_guild_settings(interaction.guild_id)
        existing_automod = await db.get_automod_settings(interaction.guild_id)
        modal = BotSetupModal(existing_guild=existing_guild, existing_automod=existing_automod)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="advertencias",
        description="Muestra las advertencias de automod de un usuario.",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(usuario="El usuario del que quieres ver las advertencias")
    async def warnings(self, interaction: discord.Interaction, usuario: discord.Member):
        warns = await db.get_warnings(interaction.guild_id, usuario.id)
        if not warns:
            await interaction.response.send_message(
                f"✅ **{usuario}** no tiene advertencias registradas.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"⚠️ Advertencias de {usuario}",
            color=discord.Color.orange(),
        )
        for i, w in enumerate(warns[:10], 1):
            embed.add_field(
                name=f"#{i} — {w['reason']}",
                value=f"<t:{int(__import__('datetime').datetime.fromisoformat(w['timestamp']).timestamp())}:R>",
                inline=False,
            )
        embed.set_thumbnail(url=usuario.display_avatar.url)
        embed.set_footer(text=f"Total: {len(warns)} advertencias")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
