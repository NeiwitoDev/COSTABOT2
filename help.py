"""
Comando ?cmds — Lista todos los comandos del bot.
"""
from __future__ import annotations

import discord
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="cmds", aliases=["comandos", "help", "ayuda"])
    @commands.guild_only()
    async def cmds(self, ctx: commands.Context):
        """Muestra todos los comandos disponibles."""
        # Obtener el prefix del servidor desde el caché
        prefix = self.bot._prefix_cache.get(ctx.guild.id, "?") if hasattr(self.bot, "_prefix_cache") else "?"

        embed = discord.Embed(
            title="📋 Comandos del Bot",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        # ── Slash commands ────────────────────────────────────────────────────
        embed.add_field(
            name="⚙️ Administración — Slash `/`",
            value=(
                "`/welcome-setup` — Panel de bienvenidas\n"
                "`/tickets-setup` — Panel de tickets\n"
                "`/bot-setup` — Prefix, logs y umbrales de automod\n"
                "`/embed` — Crear y enviar embeds personalizados\n"
                "`/advertencias @user` — Ver advertencias de automod"
            ),
            inline=False,
        )

        # ── Moderación ────────────────────────────────────────────────────────
        p = prefix
        embed.add_field(
            name=f"🔨 Moderación — Prefix `{p}`",
            value=(
                f"`{p}lock [#canal] [tiempo]` — Bloquea un canal\n"
                f"`{p}unlock [#canal]` — Desbloquea un canal\n"
                f"`{p}kick @user [motivo]` — Expulsar a un usuario\n"
                f"`{p}ban @user|ID [motivo]` — Banear permanentemente\n"
                f"`{p}unban <ID> [motivo]` — Desbanear por ID\n"
                f"`{p}tempban @user|ID <tiempo> [motivo]` — Baneo temporal\n"
                f"`{p}warn @user <motivo>` — Registrar advertencia\n"
                f"`{p}delwarn @user <warn_id>` — Eliminar advertencia\n"
                f"`{p}warns @user` — Ver advertencias de un usuario\n"
                f"`{p}cmds` — Esta lista"
            ),
            inline=False,
        )

        # ── Tips ──────────────────────────────────────────────────────────────
        embed.add_field(
            name="💡 Notas",
            value=(
                "**Tiempo:** `30s` · `15m` · `2h` · `1d` · combinados: `1h30m`\n"
                "**Variables embed:** `{user}` `{user_name}` `{server}` `{member_count}`\n"
                f"**Prefix actual:** `{p}`  *(cámbialo con `/bot-setup`)*"
            ),
            inline=False,
        )

        embed.set_footer(text=f"{ctx.guild.name} · Bot desarrollado por Neiwito")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
