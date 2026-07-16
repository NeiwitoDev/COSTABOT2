"""
Comandos de Moderación
Prefijo: ? (configurable por servidor)

?lock [#canal] [tiempo]   — Bloquea el canal
?unlock [#canal]          — Desbloquea el canal
?kick <@user> [motivo]    — Expulsa a un usuario
?ban <@user|id> [motivo]  — Banea permanentemente
?unban <user_id> [motivo] — Desbanea por ID
?tempban <@user|id> <tiempo> [motivo] — Baneo temporal
?warn <@user> <motivo>    — Registra una advertencia
?delwarn <@user> <id>     — Elimina una advertencia por ID
?warns <@user>            — Muestra las advertencias de un usuario
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

import database as db


# ─── Utilidades ───────────────────────────────────────────────────────────────

def parse_duration(text: str) -> timedelta | None:
    """Convierte '1d2h30m' en un timedelta. Retorna None si el formato es inválido."""
    pattern = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text.strip().lower())
    if not pattern or not any(pattern.groups()):
        return None
    d, h, m, s = (int(x) if x else 0 for x in pattern.groups())
    return timedelta(days=d, hours=h, minutes=m, seconds=s)


def format_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) or "0s"


async def send_modlog(guild: discord.Guild, embed: discord.Embed):
    """Envía al canal de logs de moderación si está configurado."""
    settings = await db.get_guild_settings(guild.id)
    if settings and settings.get("log_channel_id"):
        ch = guild.get_channel(settings["log_channel_id"])
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass


def mod_embed(
    action: str,
    color: discord.Color,
    moderator: discord.Member,
    target: discord.User | discord.Member,
    reason: str | None,
    extra: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=f"🔨 {action}", color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Usuario", value=f"{target.mention} (`{target.id}`)", inline=True)
    embed.add_field(name="Moderador", value=moderator.mention, inline=True)
    embed.add_field(name="Motivo", value=reason or "Sin motivo", inline=False)
    if extra:
        embed.add_field(name="Detalles", value=extra, inline=False)
    embed.set_thumbnail(url=target.display_avatar.url)
    return embed


# ─── Cog ──────────────────────────────────────────────────────────────────────

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # canal_id → asyncio.Task de desbloqueo programado
        self._unlock_tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        """Al cargar el cog, reprogramar tempbans pendientes."""
        await self._reschedule_tempbans()

    async def _reschedule_tempbans(self):
        pending = await db.get_pending_temp_bans()
        for ban in pending:
            unban_at = datetime.fromisoformat(ban["unban_at"]).replace(tzinfo=timezone.utc)
            delay = (unban_at - datetime.now(timezone.utc)).total_seconds()
            if delay <= 0:
                delay = 0
            self.bot.loop.create_task(
                self._do_unban(ban["guild_id"], ban["user_id"], ban["id"], max(delay, 0))
            )

    async def _do_unban(self, guild_id: int, user_id: int, ban_id: int, delay: float):
        await asyncio.sleep(delay)
        await db.mark_temp_ban_done(ban_id)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        try:
            await guild.unban(discord.Object(id=user_id), reason="Tempban expirado")
        except (discord.NotFound, discord.Forbidden):
            pass
        # Notificar al canal de logs
        user = await self.bot.fetch_user(user_id)
        embed = discord.Embed(
            title="⏱️ Tempban expirado",
            description=f"{user.mention} (`{user_id}`) fue desbaneado automáticamente.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        await send_modlog(guild, embed)

    async def _do_unlock(self, channel: discord.TextChannel, delay: float):
        await asyncio.sleep(delay)
        overwrites = channel.overwrites_for(channel.guild.default_role)
        overwrites.send_messages = None  # Restablecer al default
        try:
            await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
            await channel.send("🔓 Canal desbloqueado automáticamente.")
        except discord.Forbidden:
            pass
        self._unlock_tasks.pop(channel.id, None)

    # ── Checks comunes ────────────────────────────────────────────────────────

    async def _check_hierarchy(self, ctx: commands.Context, target: discord.Member) -> bool:
        if target == ctx.author:
            await ctx.send("❌ No puedes moderarte a ti mismo.", delete_after=5)
            return False
        if target == ctx.guild.owner:
            await ctx.send("❌ No puedes moderar al dueño del servidor.", delete_after=5)
            return False
        if ctx.author != ctx.guild.owner and target.top_role >= ctx.author.top_role:
            await ctx.send("❌ No puedes moderar a alguien con el mismo rol o superior.", delete_after=5)
            return False
        if target.top_role >= ctx.guild.me.top_role:
            await ctx.send("❌ No tengo permisos para moderar a ese usuario (rol superior al mío).", delete_after=5)
            return False
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # ?lock [#canal] [tiempo]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None, *, tiempo: str = None):
        """Bloquea un canal. Opcional: especifica tiempo (ej: 30m, 1h, 2d)."""
        target = channel or ctx.channel
        everyone = target.guild.default_role
        overwrites = target.overwrites_for(everyone)
        overwrites.send_messages = False

        duration = None
        if tiempo:
            duration = parse_duration(tiempo)
            if not duration:
                await ctx.send("❌ Formato de tiempo inválido. Usa: `30m`, `1h`, `2d`, `1h30m`…", delete_after=5)
                return

        try:
            await target.set_permissions(everyone, overwrite=overwrites)
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para modificar ese canal.", delete_after=5)
            return

        # Cancelar tarea anterior si existía
        old_task = self._unlock_tasks.pop(target.id, None)
        if old_task:
            old_task.cancel()

        extra = f"Duración: {format_duration(duration)}" if duration else None
        embed = mod_embed("Canal bloqueado 🔒", discord.Color.red(), ctx.author, ctx.author, None, extra)
        embed.add_field(name="Canal", value=target.mention, inline=True)

        if duration:
            task = self.bot.loop.create_task(self._do_unlock(target, duration.total_seconds()))
            self._unlock_tasks[target.id] = task
            await target.send(
                embed=discord.Embed(
                    title="🔒 Canal bloqueado",
                    description=f"Este canal ha sido bloqueado por {format_duration(duration)}.",
                    color=discord.Color.red(),
                )
            )
        else:
            await target.send(
                embed=discord.Embed(
                    title="🔒 Canal bloqueado",
                    description="Este canal ha sido bloqueado por un moderador.",
                    color=discord.Color.red(),
                )
            )

        if target != ctx.channel:
            await ctx.send(f"🔒 Canal {target.mention} bloqueado.", delete_after=5)

        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?unlock [#canal]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Desbloquea un canal."""
        target = channel or ctx.channel
        everyone = target.guild.default_role
        overwrites = target.overwrites_for(everyone)
        overwrites.send_messages = None  # Restaurar al default

        # Cancelar unlock automático si estaba programado
        task = self._unlock_tasks.pop(target.id, None)
        if task:
            task.cancel()

        try:
            await target.set_permissions(everyone, overwrite=overwrites)
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para modificar ese canal.", delete_after=5)
            return

        await target.send(
            embed=discord.Embed(
                title="🔓 Canal desbloqueado",
                description="Este canal ha sido desbloqueado.",
                color=discord.Color.green(),
            )
        )
        if target != ctx.channel:
            await ctx.send(f"🔓 Canal {target.mention} desbloqueado.", delete_after=5)

        embed = mod_embed("Canal desbloqueado 🔓", discord.Color.green(), ctx.author, ctx.author, None)
        embed.add_field(name="Canal", value=target.mention, inline=True)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?kick <@user> [motivo]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Expulsa a un miembro del servidor."""
        if not await self._check_hierarchy(ctx, member):
            return
        try:
            await member.send(
                embed=discord.Embed(
                    title="👢 Has sido expulsado",
                    description=f"**Servidor:** {ctx.guild.name}\n**Motivo:** {reason or 'Sin motivo'}",
                    color=discord.Color.orange(),
                )
            )
        except discord.Forbidden:
            pass
        await member.kick(reason=f"{ctx.author} — {reason or 'Sin motivo'}")
        embed = mod_embed("Kick", discord.Color.orange(), ctx.author, member, reason)
        await ctx.send(embed=embed)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?ban <@user|id> [motivo]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, user: discord.User, *, reason: str = None):
        """Banea permanentemente a un usuario (acepta mención o ID)."""
        member = ctx.guild.get_member(user.id)
        if member:
            if not await self._check_hierarchy(ctx, member):
                return
            try:
                await member.send(
                    embed=discord.Embed(
                        title="🔨 Has sido baneado",
                        description=f"**Servidor:** {ctx.guild.name}\n**Motivo:** {reason or 'Sin motivo'}",
                        color=discord.Color.dark_red(),
                    )
                )
            except discord.Forbidden:
                pass
        await ctx.guild.ban(user, reason=f"{ctx.author} — {reason or 'Sin motivo'}", delete_message_days=0)
        embed = mod_embed("Ban", discord.Color.dark_red(), ctx.author, user, reason)
        await ctx.send(embed=embed)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?unban <user_id> [motivo]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = None):
        """Desbanea a un usuario por su ID."""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author} — {reason or 'Sin motivo'}")
        except discord.NotFound:
            await ctx.send("❌ Usuario no encontrado o no está baneado.", delete_after=5)
            return
        except discord.Forbidden:
            await ctx.send("❌ No tengo permisos para desbanear.", delete_after=5)
            return
        embed = mod_embed("Unban", discord.Color.green(), ctx.author, user, reason)
        await ctx.send(embed=embed)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?tempban <@user|id> <tiempo> [motivo]
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="tempban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def tempban(self, ctx: commands.Context, user: discord.User, tiempo: str, *, reason: str = None):
        """Banea temporalmente. Ej: ?tempban @user 1d Raid"""
        duration = parse_duration(tiempo)
        if not duration:
            await ctx.send("❌ Formato de tiempo inválido. Usa: `30m`, `1h`, `2d`…", delete_after=5)
            return

        member = ctx.guild.get_member(user.id)
        if member:
            if not await self._check_hierarchy(ctx, member):
                return
            try:
                await member.send(
                    embed=discord.Embed(
                        title="⏱️ Has sido baneado temporalmente",
                        description=(
                            f"**Servidor:** {ctx.guild.name}\n"
                            f"**Duración:** {format_duration(duration)}\n"
                            f"**Motivo:** {reason or 'Sin motivo'}"
                        ),
                        color=discord.Color.red(),
                    )
                )
            except discord.Forbidden:
                pass

        unban_at = datetime.now(timezone.utc) + duration
        await ctx.guild.ban(user, reason=f"[TEMPBAN {format_duration(duration)}] {ctx.author} — {reason or 'Sin motivo'}", delete_message_days=0)
        ban_id = await db.add_temp_ban(ctx.guild.id, user.id, ctx.author.id, reason, unban_at.isoformat())
        self.bot.loop.create_task(self._do_unban(ctx.guild.id, user.id, ban_id, duration.total_seconds()))

        embed = mod_embed("Tempban", discord.Color.red(), ctx.author, user, reason, f"Duración: {format_duration(duration)}")
        await ctx.send(embed=embed)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?warn <@user> <motivo>
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        """Registra una advertencia para un miembro."""
        if not await self._check_hierarchy(ctx, member):
            return
        warn_id = await db.add_mod_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        total = await db.count_mod_warnings(ctx.guild.id, member.id)
        try:
            await member.send(
                embed=discord.Embed(
                    title="⚠️ Has recibido una advertencia",
                    description=(
                        f"**Servidor:** {ctx.guild.name}\n"
                        f"**Motivo:** {reason}\n"
                        f"**Advertencia #:** {total}"
                    ),
                    color=discord.Color.yellow(),
                )
            )
        except discord.Forbidden:
            pass
        embed = mod_embed("Warn", discord.Color.yellow(), ctx.author, member, reason, f"ID de advertencia: `#{warn_id}` · Total: {total}")
        await ctx.send(embed=embed)
        await send_modlog(ctx.guild, embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ?delwarn <@user> <warn_id>
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="delwarn")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def delwarn(self, ctx: commands.Context, member: discord.Member, warn_id: int):
        """Elimina una advertencia específica por su ID."""
        deleted = await db.delete_mod_warning(warn_id, ctx.guild.id, member.id)
        if not deleted:
            await ctx.send(f"❌ No encontré la advertencia `#{warn_id}` para ese usuario.", delete_after=5)
            return
        total = await db.count_mod_warnings(ctx.guild.id, member.id)
        await ctx.send(
            embed=discord.Embed(
                description=f"✅ Advertencia `#{warn_id}` de {member.mention} eliminada. Quedan **{total}** advertencia(s).",
                color=discord.Color.green(),
            )
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ?warns <@user>
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(name="warns")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warns(self, ctx: commands.Context, member: discord.Member):
        """Muestra todas las advertencias de un miembro."""
        warnings = await db.get_mod_warnings(ctx.guild.id, member.id)
        embed = discord.Embed(
            title=f"⚠️ Advertencias de {member.display_name}",
            color=discord.Color.yellow() if warnings else discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if not warnings:
            embed.description = "✅ Este usuario no tiene advertencias."
        else:
            lines = []
            for w in warnings:
                ts = datetime.fromisoformat(w["timestamp"]).strftime("%d/%m/%Y %H:%M")
                mod = ctx.guild.get_member(w["moderator_id"])
                mod_name = mod.display_name if mod else f"ID {w['moderator_id']}"
                lines.append(f"`#{w['id']}` — {ts} · **Mod:** {mod_name}\n> {w['reason']}")
            embed.description = "\n\n".join(lines)
            embed.set_footer(text=f"Total: {len(warnings)} advertencia(s)")
        await ctx.send(embed=embed)

    # ─── Error handlers ────────────────────────────────────────────────────────

    @lock.error
    @unlock.error
    @kick.error
    @ban.error
    @unban.error
    @tempban.error
    @warn.error
    @delwarn.error
    @warns.error
    async def mod_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ No tienes permisos para usar este comando.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Usuario no encontrado. Usa una mención o ID válida.", delete_after=5)
        elif isinstance(error, commands.UserNotFound):
            await ctx.send("❌ Usuario no encontrado.", delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Argumento requerido: `{error.param.name}`.", delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Argumento inválido. Verifica el comando.", delete_after=5)
        else:
            await ctx.send(f"❌ Error inesperado: {error}", delete_after=8)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
