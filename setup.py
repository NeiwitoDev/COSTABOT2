"""
Sistema de Auto-Moderación
- Detección de FLOOD (muchos mensajes en poco tiempo)
- Detección de SPAM / Links
"""
import re
import asyncio
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

import database as db

# Regex para detectar URLs/links
URL_REGEX = re.compile(
    r"(https?://|discord\.gg/|discord\.com/invite/|www\.)"
    r"[\w\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE,
)

# Dominios permitidos en algunos servidores (se pueden personalizar)
ALLOWED_DOMAINS: set[str] = set()


class FloodTracker:
    """Rastrea mensajes por usuario para detectar flood."""

    def __init__(self, threshold: int = 5, interval: float = 5.0):
        self.threshold = threshold
        self.interval = interval
        # guild_id -> user_id -> deque de timestamps
        self._data: dict[int, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))

    def add_message(self, guild_id: int, user_id: int) -> bool:
        """
        Registra un mensaje. Devuelve True si se detectó flood.
        """
        now = time.monotonic()
        queue = self._data[guild_id][user_id]
        queue.append(now)
        # Limpiar mensajes fuera del intervalo
        while queue and now - queue[0] > self.interval:
            queue.popleft()
        return len(queue) >= self.threshold

    def reset(self, guild_id: int, user_id: int):
        """Limpia el historial de un usuario (tras sancionarlo)."""
        self._data[guild_id][user_id].clear()


async def send_sanction_log(
    guild: discord.Guild,
    log_channel_id: int | None,
    member: discord.Member,
    reason: str,
    action: str,
    color: discord.Color,
):
    """Envía un embed de sanción al canal de log configurado."""
    if not log_channel_id:
        return
    channel = guild.get_channel(log_channel_id)
    if not channel:
        return

    embed = discord.Embed(
        title=f"🛡️ AutoMod — {action}",
        color=color,
    )
    embed.add_field(name="Usuario", value=f"{member.mention} (`{member}`)", inline=True)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(name="Razón", value=reason, inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="AutoMod · Sanción automática")

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.flood_tracker = FloodTracker()
        # Usuarios en cooldown de advertencia para no spamear warnings
        # guild_id -> user_id -> timestamp
        self._warned: dict[int, dict[int, float]] = defaultdict(dict)
        self._warn_cooldown = 8.0  # segundos entre advertencias del bot

    def _can_warn(self, guild_id: int, user_id: int) -> bool:
        now = time.monotonic()
        last = self._warned[guild_id].get(user_id, 0)
        if now - last >= self._warn_cooldown:
            self._warned[guild_id][user_id] = now
            return True
        return False

    async def _warn_user(
        self,
        message: discord.Message,
        warning_text: str,
        reason: str,
        action_label: str,
        log_channel_id: int | None,
        color: discord.Color,
    ):
        """Elimina el mensaje y avisa al usuario."""
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        if self._can_warn(message.guild.id, message.author.id):
            embed = discord.Embed(
                description=warning_text,
                color=color,
            )
            embed.set_author(
                name=str(message.author),
                icon_url=message.author.display_avatar.url,
            )
            embed.set_footer(text="AutoMod · Advertencia automática")
            try:
                warn_msg = await message.channel.send(
                    content=message.author.mention,
                    embed=embed,
                )
                await asyncio.sleep(8)
                await warn_msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

        await db.add_warning(message.guild.id, message.author.id, reason)
        await send_sanction_log(
            message.guild,
            log_channel_id,
            message.author,
            reason,
            action_label,
            color,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar DMs, bots y el propio bot
        if not message.guild or message.author.bot:
            return

        # Ignorar administradores y moderadores
        if message.author.guild_permissions.manage_messages:
            return

        settings = await db.get_automod_settings(message.guild.id)
        if not settings or not settings.get("enabled"):
            return

        log_ch = settings.get("log_channel_id")

        # ── FLOOD ─────────────────────────────────────────────────────────────
        if settings.get("flood_enabled"):
            threshold = settings.get("flood_threshold") or 5
            interval = settings.get("flood_interval") or 5
            self.flood_tracker.threshold = threshold
            self.flood_tracker.interval = float(interval)

            is_flood = self.flood_tracker.add_message(message.guild.id, message.author.id)
            if is_flood:
                self.flood_tracker.reset(message.guild.id, message.author.id)
                # Eliminar mensajes recientes en masa
                try:
                    def is_from_user(m: discord.Message):
                        return m.author.id == message.author.id

                    await message.channel.purge(limit=20, check=is_from_user, bulk=True)
                except (discord.Forbidden, discord.HTTPException):
                    try:
                        await message.delete()
                    except (discord.Forbidden, discord.NotFound):
                        pass

                if self._can_warn(message.guild.id, message.author.id):
                    embed = discord.Embed(
                        description=(
                            f"⚠️ ¡Oye! Deja de mandar muchos mensajes repetidamente **(Flood)**.\n"
                            f"Fuiste advertido/a automáticamente."
                        ),
                        color=discord.Color.orange(),
                    )
                    embed.set_author(
                        name=str(message.author),
                        icon_url=message.author.display_avatar.url,
                    )
                    embed.set_footer(text="AutoMod · Advertencia automática")
                    try:
                        warn_msg = await message.channel.send(
                            content=message.author.mention,
                            embed=embed,
                        )
                        await asyncio.sleep(8)
                        await warn_msg.delete()
                    except (discord.Forbidden, discord.NotFound):
                        pass

                await db.add_warning(message.guild.id, message.author.id, "Flood detectado")
                await send_sanction_log(
                    message.guild,
                    log_ch,
                    message.author,
                    f"Flood detectado (>{threshold} mensajes en {interval}s)",
                    "Advertencia — Flood",
                    discord.Color.orange(),
                )
                return  # No procesar más reglas en este mensaje

        # ── LINKS / SPAM ──────────────────────────────────────────────────────
        if settings.get("links_enabled"):
            if URL_REGEX.search(message.content):
                await self._warn_user(
                    message=message,
                    warning_text=(
                        "🔗 No puedes enviar **links** en este servidor.\n"
                        "Tu mensaje fue eliminado y fuiste advertido/a automáticamente."
                    ),
                    reason="Envío de links/spam detectado",
                    action_label="Advertencia — Spam/Link",
                    log_channel_id=log_ch,
                    color=discord.Color.red(),
                )
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodCog(bot))
