"""
Sistema de Bienvenida — Panel estilo profesional
Comando: /welcome-setup
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import database as db


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_color(hex_str: str) -> int:
    try:
        return int(hex_str.strip().lstrip("#"), 16)
    except Exception:
        return 0x5865F2


def build_panel_embed(settings: dict | None, guild: discord.Guild) -> discord.Embed:
    """Construye el embed del panel de configuración."""
    enabled = bool(settings and settings.get("channel_id"))

    embed = discord.Embed(
        title="🎉 Sistema de Bienvenidas",
        description=(
            "Usa los botones de abajo para configurar cada sección.\n\n"
            "**Variables disponibles:**\n"
            "`{user}` — mención · `{user_name}` — nombre\n"
            "`{server}` — servidor · `{member_count}` — miembros"
        ),
        color=parse_color((settings.get("embed_color") if settings else None) or "#5865F2"),
    )

    # Estado
    embed.add_field(name="● Estado", value="🟢 Activado" if enabled else "🔴 Desactivado", inline=False)

    # Canal
    canal_val = f"<#{settings['channel_id']}>" if (settings and settings.get("channel_id")) else "Sin configurar"
    embed.add_field(name="🔊 Canal", value=canal_val, inline=True)

    # Color
    color_val = (settings.get("embed_color") if settings else None) or "#5865F2"
    embed.add_field(name="🎨 Color", value=f"`{color_val}`", inline=True)

    # Imagen banner
    img_val = (
        f"[Ver imagen]({settings['image_url']})"
        if (settings and settings.get("image_url"))
        else "Sin imagen"
    )
    embed.add_field(name="🖼️ Imagen banner", value=img_val, inline=True)

    # Mensaje
    msg_val = (settings.get("message") if settings else None) or "¡Bienvenido/a {user} a **{server}**! Ya somos {member_count} miembros."
    embed.add_field(name="✉️ Mensaje", value=msg_val, inline=False)

    # Canales recomendados
    rec_val = "Ninguno"
    if settings and settings.get("recommended_channels"):
        ids = [r.strip() for r in settings["recommended_channels"].split(",") if r.strip()]
        mentions = [f"<#{i}>" for i in ids if i.isdigit()]
        rec_val = " ".join(mentions) if mentions else "Ninguno"
    embed.add_field(name="📌 Canales recomendados", value=rec_val, inline=True)

    # DM al entrar
    dm_val = "✅ Configurado" if (settings and settings.get("dm_message")) else "Ninguno"
    embed.add_field(name="📬 DM al entrar", value=dm_val, inline=True)

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text=f"{guild.name} · Solo visible para ti")
    return embed


def build_welcome_embed(settings: dict, member: discord.Member) -> discord.Embed:
    """Construye el embed de bienvenida real que se envía al unirse."""
    message = settings.get("message") or "¡Bienvenido/a {user} a **{server}**!"
    message = (
        message
        .replace("{user}", member.mention)
        .replace("{user_name}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{member_count}", str(member.guild.member_count))
    )
    color = parse_color(settings.get("embed_color") or "#5865F2")
    embed = discord.Embed(title="👋 ¡Bienvenido/a!", description=message, color=color)
    embed.set_thumbnail(url=member.display_avatar.url)
    if settings.get("image_url"):
        embed.set_image(url=settings["image_url"])
    embed.set_footer(
        text=f"Miembro #{member.guild.member_count}",
        icon_url=member.guild.icon.url if member.guild.icon else None,
    )
    return embed


# ─── Vistas de selección de canales ───────────────────────────────────────────

class CanalSelectView(discord.ui.View):
    """Vista efímera con un ChannelSelect para elegir el canal de bienvenidas."""

    def __init__(self, panel: WelcomePanel):
        super().__init__(timeout=60)
        self.panel = panel
        self.selected: discord.TextChannel | None = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecciona el canal de bienvenidas…",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
        row=0,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        self.selected = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message("❌ Selecciona un canal primero.", ephemeral=True)
            return
        await db.set_welcome_settings(interaction.guild_id, channel_id=self.selected.id)
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        self.panel._update_disable_button(bool(self.panel.settings and self.panel.settings.get("channel_id")))
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Canal de bienvenidas guardado: {self.selected.mention}",
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)

    async def on_timeout(self):
        pass  # El mensaje efímero desaparece solo


class RecomendadosSelectView(discord.ui.View):
    """Vista efímera con ChannelSelect múltiple para elegir canales recomendados."""

    def __init__(self, panel: WelcomePanel):
        super().__init__(timeout=60)
        self.panel = panel
        self.selected: list[discord.TextChannel] = []

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecciona hasta 10 canales recomendados…",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=10,
        row=0,
    )
    async def channel_select(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):
        self.selected = list(select.values)
        await interaction.response.defer()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        value = ",".join(str(c.id) for c in self.selected) if self.selected else None
        await db.set_welcome_settings(interaction.guild_id, recommended_channels=value)
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        self.stop()
        if self.selected:
            lista = ", ".join(c.mention for c in self.selected)
            msg = f"✅ Canales recomendados guardados: {lista}"
        else:
            msg = "✅ Canales recomendados eliminados."
        await interaction.response.edit_message(content=msg, view=None)

    @discord.ui.button(label="Limpiar selección", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.set_welcome_settings(interaction.guild_id, recommended_channels=None)
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        self.stop()
        await interaction.response.edit_message(content="✅ Canales recomendados eliminados.", view=None)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


# ─── Modales de texto ─────────────────────────────────────────────────────────

class MensajeModal(discord.ui.Modal, title="✉️ Configurar Mensaje"):
    message = discord.ui.TextInput(
        label="Mensaje del embed",
        placeholder="Usa: {user} {user_name} {server} {member_count}",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1024,
    )

    def __init__(self, panel: WelcomePanel):
        super().__init__()
        self.panel = panel
        if panel.settings and panel.settings.get("message"):
            self.message.default = panel.settings["message"]

    async def on_submit(self, interaction: discord.Interaction):
        await db.set_welcome_settings(interaction.guild_id, message=self.message.value.strip())
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        await interaction.response.send_message("✅ Mensaje guardado.", ephemeral=True, delete_after=4)


class AparienciaModal(discord.ui.Modal, title="🎨 Apariencia del Embed"):
    color = discord.ui.TextInput(
        label="Color (HEX)",
        placeholder="#5865F2",
        default="#5865F2",
        required=True,
        max_length=9,
    )
    image_url = discord.ui.TextInput(
        label="URL de imagen banner (opcional)",
        placeholder="https://ejemplo.com/banner.png",
        required=False,
        max_length=512,
    )

    def __init__(self, panel: WelcomePanel):
        super().__init__()
        self.panel = panel
        if panel.settings:
            self.color.default = panel.settings.get("embed_color") or "#5865F2"
            self.image_url.default = panel.settings.get("image_url") or ""

    async def on_submit(self, interaction: discord.Interaction):
        await db.set_welcome_settings(
            interaction.guild_id,
            embed_color=self.color.value.strip() or "#5865F2",
            image_url=self.image_url.value.strip() or None,
        )
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        await interaction.response.send_message("✅ Apariencia guardada.", ephemeral=True, delete_after=4)


class DmModal(discord.ui.Modal, title="📬 Mensaje por DM al entrar"):
    dm_message = discord.ui.TextInput(
        label="Mensaje DM (vacío = desactivar DM)",
        placeholder="¡Bienvenido/a {user_name}! Lee las reglas en {server}…",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )

    def __init__(self, panel: WelcomePanel):
        super().__init__()
        self.panel = panel
        if panel.settings and panel.settings.get("dm_message"):
            self.dm_message.default = panel.settings["dm_message"]

    async def on_submit(self, interaction: discord.Interaction):
        value = self.dm_message.value.strip() or None
        await db.set_welcome_settings(interaction.guild_id, dm_message=value)
        self.panel.settings = await db.get_welcome_settings(interaction.guild_id)
        new_embed = build_panel_embed(self.panel.settings, interaction.guild)
        await self.panel.panel_message.edit(embed=new_embed, view=self.panel)
        msg = "✅ DM configurado." if value else "✅ DM desactivado."
        await interaction.response.send_message(msg, ephemeral=True, delete_after=4)


# ─── Panel principal ──────────────────────────────────────────────────────────

class WelcomePanel(discord.ui.View):
    def __init__(self, settings: dict | None, guild: discord.Guild):
        super().__init__(timeout=300)
        self.settings = settings
        self.guild = guild
        self.panel_message: discord.Message | None = None

        enabled = bool(settings and settings.get("channel_id"))
        self._update_disable_button(enabled)

    def _update_disable_button(self, enabled: bool):
        btn = discord.utils.get(self.children, custom_id="welcome:toggle")
        if btn:
            if enabled:
                btn.label = "Desactivar"
                btn.style = discord.ButtonStyle.danger
                btn.emoji = "🔴"
            else:
                btn.label = "Activar"
                btn.style = discord.ButtonStyle.success
                btn.emoji = "🟢"

    # ── Fila 0 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Canal", style=discord.ButtonStyle.primary, emoji="🔊", row=0)
    async def canal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CanalSelectView(self)
        await interaction.response.send_message(
            "**🔊 Canal de bienvenidas**\nSelecciona el canal donde se enviarán los mensajes de bienvenida:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Mensaje", style=discord.ButtonStyle.primary, emoji="✉️", row=0)
    async def mensaje_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MensajeModal(self))

    @discord.ui.button(label="Apariencia", style=discord.ButtonStyle.primary, emoji="🎨", row=0)
    async def apariencia_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AparienciaModal(self))

    @discord.ui.button(label="Recomendados", style=discord.ButtonStyle.primary, emoji="📌", row=0)
    async def recomendados_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RecomendadosSelectView(self)
        await interaction.response.send_message(
            "**📌 Canales recomendados**\nSelecciona los canales que quieres mostrar al nuevo miembro (puedes elegir hasta 10):",
            view=view,
            ephemeral=True,
        )

    # ── Fila 1 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="DM", style=discord.ButtonStyle.primary, emoji="📬", row=1)
    async def dm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DmModal(self))

    @discord.ui.button(label="Vista previa", style=discord.ButtonStyle.secondary, emoji="👁️", row=1)
    async def preview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.settings or not self.settings.get("channel_id"):
            await interaction.response.send_message(
                "❌ Primero configura el canal de bienvenidas.", ephemeral=True
            )
            return
        preview = build_welcome_embed(self.settings, interaction.user)
        preview.title = "👁️ Vista previa — Bienvenida"

        rec = self.settings.get("recommended_channels")
        if rec:
            ids = [r.strip() for r in rec.split(",") if r.strip()]
            mentions = [f"• <#{i}>" for i in ids if i.isdigit()]
            if mentions:
                preview.add_field(
                    name="📌 Canales recomendados",
                    value="\n".join(mentions),
                    inline=False,
                )
        await interaction.response.send_message(embed=preview, ephemeral=True)

    @discord.ui.button(
        label="Desactivar",
        style=discord.ButtonStyle.danger,
        emoji="🔴",
        row=1,
        custom_id="welcome:toggle",
    )
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        enabled = bool(self.settings and self.settings.get("channel_id"))
        if enabled:
            await db.set_welcome_settings(interaction.guild_id, channel_id=None)
            msg = "🔴 Sistema de bienvenidas **desactivado**."
        else:
            msg = "⚠️ Configura primero un canal para activar el sistema."
        self.settings = await db.get_welcome_settings(interaction.guild_id)
        self._update_disable_button(bool(self.settings and self.settings.get("channel_id")))
        new_embed = build_panel_embed(self.settings, interaction.guild)
        await self.panel_message.edit(embed=new_embed, view=self)
        await interaction.response.send_message(msg, ephemeral=True, delete_after=5)

    async def on_timeout(self):
        if self.panel_message:
            for item in self.children:
                item.disabled = True
            try:
                await self.panel_message.edit(view=self)
            except Exception:
                pass


# ─── Cog ──────────────────────────────────────────────────────────────────────

class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="welcome-setup",
        description="Abre el panel de configuración del sistema de bienvenidas.",
    )
    @app_commands.default_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction):
        settings = await db.get_welcome_settings(interaction.guild_id)
        embed = build_panel_embed(settings, interaction.guild)
        panel = WelcomePanel(settings, interaction.guild)
        await interaction.response.send_message(embed=embed, view=panel, ephemeral=True)
        panel.panel_message = await interaction.original_response()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await db.get_welcome_settings(member.guild.id)
        if not settings or not settings.get("channel_id"):
            return

        channel = member.guild.get_channel(settings["channel_id"])
        if not channel:
            return

        embed = build_welcome_embed(settings, member)

        rec = settings.get("recommended_channels")
        if rec:
            ids = [r.strip() for r in rec.split(",") if r.strip()]
            mentions = [f"• <#{i}>" for i in ids if i.isdigit()]
            if mentions:
                embed.add_field(
                    name="📌 Canales que te recomendamos",
                    value="\n".join(mentions),
                    inline=False,
                )

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        # DM opcional
        dm_msg = settings.get("dm_message")
        if dm_msg:
            dm_text = (
                dm_msg
                .replace("{user}", member.mention)
                .replace("{user_name}", str(member))
                .replace("{server}", member.guild.name)
                .replace("{member_count}", str(member.guild.member_count))
            )
            try:
                dm_embed = discord.Embed(
                    description=dm_text,
                    color=parse_color(settings.get("embed_color") or "#5865F2"),
                )
                dm_embed.set_footer(
                    text=member.guild.name,
                    icon_url=member.guild.icon.url if member.guild.icon else None,
                )
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
