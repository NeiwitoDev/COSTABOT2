"""
Sistema de Embeds — /embed
Panel de configuración para crear y enviar embeds personalizados.
Incluye menú de links desplegable con respuestas efímeras.
"""
from __future__ import annotations
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

import database as db


# ─── Draft (estado en memoria del panel) ──────────────────────────────────────

@dataclass
class EmbedDraft:
    channel_id: int | None = None
    title: str | None = None
    description: str | None = None
    color: str = "#5865F2"
    image_url: str | None = None
    thumbnail_url: str | None = None
    footer_text: str | None = None
    footer_icon_url: str | None = None
    fields: list[dict] = field(default_factory=list)    # [{name, value, inline}]
    menu_items: list[dict] = field(default_factory=list) # [{label, emoji, description, response_msg}]


def _parse_color(hex_str: str) -> int:
    try:
        return int(hex_str.strip().lstrip("#"), 16)
    except Exception:
        return 0x5865F2


# ─── Embeds del panel ─────────────────────────────────────────────────────────

def build_config_embed(draft: EmbedDraft) -> discord.Embed:
    """Embed del panel de control (muestra el estado de la configuración)."""
    embed = discord.Embed(
        title="📨 Configurador de Embed",
        description="Usa los botones para configurar cada sección. Cuando termines pulsa **🚀 Enviar**.",
        color=_parse_color(draft.color),
    )
    embed.add_field(
        name="📢 Canal destino",
        value=f"<#{draft.channel_id}>" if draft.channel_id else "Sin configurar",
        inline=True,
    )
    embed.add_field(name="🎨 Color", value=f"`{draft.color}`", inline=True)
    embed.add_field(name="📝 Título", value=draft.title or "*Vacío*", inline=False)

    desc_preview = draft.description
    if desc_preview and len(desc_preview) > 100:
        desc_preview = desc_preview[:100] + "…"
    embed.add_field(name="📄 Descripción", value=desc_preview or "*Vacía*", inline=False)
    embed.add_field(
        name="🖼️ Imagen",
        value=f"[Ver]({draft.image_url})" if draft.image_url else "Ninguna",
        inline=True,
    )
    embed.add_field(
        name="🖼️ Thumbnail",
        value=f"[Ver]({draft.thumbnail_url})" if draft.thumbnail_url else "Ninguno",
        inline=True,
    )
    embed.add_field(
        name="🔻 Footer",
        value=f"`{draft.footer_text}`" if draft.footer_text else "Ninguno",
        inline=True,
    )

    # Campos
    if draft.fields:
        names = "\n".join(f"• **{f['name']}**" for f in draft.fields)
        embed.add_field(name=f"📋 Campos ({len(draft.fields)})", value=names, inline=False)
    else:
        embed.add_field(name="📋 Campos", value="Ninguno", inline=False)

    # Menú de links
    if draft.menu_items:
        menu_lines = "\n".join(
            f"{'`' + i.get('emoji','🔗') + '`' if i.get('emoji') else '🔗'} **{i['label']}**"
            for i in draft.menu_items
        )
        embed.add_field(name=f"🔗 Menú de links ({len(draft.menu_items)})", value=menu_lines, inline=False)
    else:
        embed.add_field(name="🔗 Menú de links", value="Ninguno (opcional)", inline=False)

    embed.set_footer(text="Solo visible para ti · El embed real se enviará al canal configurado")
    return embed


def build_final_embed(draft: EmbedDraft) -> discord.Embed:
    """Construye el embed final que se enviará al canal."""
    embed = discord.Embed(color=_parse_color(draft.color))
    if draft.title:
        embed.title = draft.title
    if draft.description:
        embed.description = draft.description
    if draft.image_url:
        embed.set_image(url=draft.image_url)
    if draft.thumbnail_url:
        embed.set_thumbnail(url=draft.thumbnail_url)
    if draft.footer_text:
        embed.set_footer(text=draft.footer_text, icon_url=draft.footer_icon_url)
    for f in draft.fields:
        embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
    return embed


# ─── Menú de links (vista persistente) ───────────────────────────────────────

class EmbedMenuView(discord.ui.View):
    """Vista persistente que adjunta un menú desplegable al embed enviado."""

    def __init__(self, items: list[dict]):
        super().__init__(timeout=None)
        self._item_map: dict[str, str] = {str(i["id"]): i["response_msg"] for i in items}

        options = [
            discord.SelectOption(
                label=i["label"][:100],
                value=str(i["id"]),
                description=(i.get("description") or "")[:100] or None,
                emoji=i.get("emoji") or None,
            )
            for i in items
        ]
        select = discord.ui.Select(
            custom_id="embed_link_menu",
            placeholder="Selecciona una opción…",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        selected_id = interaction.data["values"][0]
        # Primero intenta el mapa en memoria (rápido)
        response = self._item_map.get(selected_id)
        if not response:
            # Fallback a la BD (tras reinicio el mapa se reconstruye en cog_load)
            items = await db.get_embed_menu_items(interaction.message.id)
            item = next((i for i in items if str(i["id"]) == selected_id), None)
            response = item["response_msg"] if item else "❌ Opción no encontrada."
        await interaction.response.send_message(response, ephemeral=True)


# ─── Modales ──────────────────────────────────────────────────────────────────

class TituloModal(discord.ui.Modal, title="📝 Título del Embed"):
    titulo = discord.ui.TextInput(label="Título", max_length=256, required=False)

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel
        if panel.draft.title:
            self.titulo.default = panel.draft.title

    async def on_submit(self, interaction: discord.Interaction):
        self.panel.draft.title = self.titulo.value.strip() or None
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(self.panel.draft), view=self.panel)


class DescripcionModal(discord.ui.Modal, title="📄 Descripción del Embed"):
    descripcion = discord.ui.TextInput(
        label="Descripción",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False,
    )

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel
        if panel.draft.description:
            self.descripcion.default = panel.draft.description

    async def on_submit(self, interaction: discord.Interaction):
        self.panel.draft.description = self.descripcion.value.strip() or None
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(self.panel.draft), view=self.panel)


class AparienciaModal(discord.ui.Modal, title="🎨 Apariencia"):
    color = discord.ui.TextInput(label="Color HEX", default="#5865F2", max_length=9, required=False)
    image_url = discord.ui.TextInput(label="URL Imagen (parte inferior)", max_length=512, required=False)
    thumbnail_url = discord.ui.TextInput(label="URL Thumbnail (esquina superior)", max_length=512, required=False)

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel
        d = panel.draft
        self.color.default = d.color
        self.image_url.default = d.image_url or ""
        self.thumbnail_url.default = d.thumbnail_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        d = self.panel.draft
        d.color = self.color.value.strip() or "#5865F2"
        d.image_url = self.image_url.value.strip() or None
        d.thumbnail_url = self.thumbnail_url.value.strip() or None
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(d), view=self.panel)


class FooterModal(discord.ui.Modal, title="🔻 Footer"):
    texto = discord.ui.TextInput(label="Texto del footer", max_length=2048, required=False)
    icon_url = discord.ui.TextInput(label="URL del ícono (opcional)", max_length=512, required=False)

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel
        d = panel.draft
        self.texto.default = d.footer_text or ""
        self.icon_url.default = d.footer_icon_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        d = self.panel.draft
        d.footer_text = self.texto.value.strip() or None
        d.footer_icon_url = self.icon_url.value.strip() or None
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(d), view=self.panel)


class CampoModal(discord.ui.Modal, title="➕ Añadir Campo"):
    nombre = discord.ui.TextInput(label="Nombre del campo", max_length=256, required=True)
    valor = discord.ui.TextInput(
        label="Valor del campo",
        style=discord.TextStyle.paragraph,
        max_length=1024,
        required=True,
    )
    inline = discord.ui.TextInput(
        label="¿En línea? (sí / no)",
        default="no",
        max_length=3,
        required=False,
    )

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        if len(self.panel.draft.fields) >= 25:
            await interaction.response.send_message("❌ Máximo 25 campos por embed.", ephemeral=True)
            return
        inline_val = self.inline.value.strip().lower() in ("sí", "si", "yes", "s", "y")
        self.panel.draft.fields.append({
            "name": self.nombre.value.strip(),
            "value": self.valor.value.strip(),
            "inline": inline_val,
        })
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(self.panel.draft), view=self.panel)


class AddLinkModal(discord.ui.Modal, title="🔗 Añadir opción al menú"):
    label = discord.ui.TextInput(
        label="Título de la opción (visible en el menú)",
        placeholder="Ej: Página web, Reglas, Instagram…",
        max_length=100,
        required=True,
    )
    emoji = discord.ui.TextInput(
        label="Emoji (opcional)",
        placeholder="Ej: 🌐  📋  📸",
        max_length=8,
        required=False,
    )
    description = discord.ui.TextInput(
        label="Descripción breve (se ve bajo el título)",
        placeholder="Ej: Visita nuestra web oficial",
        max_length=100,
        required=False,
    )
    response_msg = discord.ui.TextInput(
        label="Mensaje que recibe el usuario (solo él lo ve)",
        placeholder="Ej: 🌐 Nuestra web: https://ejemplo.com\n📸 Instagram: @usuario",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    def __init__(self, panel: EmbedPanel):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        if len(self.panel.draft.menu_items) >= 25:
            await interaction.response.send_message("❌ Máximo 25 opciones en el menú.", ephemeral=True)
            return
        self.panel.draft.menu_items.append({
            "label": self.label.value.strip(),
            "emoji": self.emoji.value.strip() or None,
            "description": self.description.value.strip() or None,
            "response_msg": self.response_msg.value.strip(),
        })
        await interaction.response.defer()
        await self.panel.panel_message.edit(embed=build_config_embed(self.panel.draft), view=self.panel)


# ─── Vista de selección de canal ──────────────────────────────────────────────

class CanalSelectView(discord.ui.View):
    def __init__(self, panel: EmbedPanel):
        super().__init__(timeout=60)
        self.panel = panel

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecciona el canal donde enviar el embed…",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
        row=0,
    )
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.panel.draft.channel_id = select.values[0].id
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Canal configurado: {select.values[0].mention}",
            view=None,
        )
        await self.panel.panel_message.edit(embed=build_config_embed(self.panel.draft), view=self.panel)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️", row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Cancelado.", view=None)


# ─── Panel principal ──────────────────────────────────────────────────────────

class EmbedPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.draft = EmbedDraft()
        self.panel_message: discord.Message | None = None

    # ── Fila 0 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Canal", style=discord.ButtonStyle.primary, emoji="📢", row=0)
    async def canal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CanalSelectView(self)
        await interaction.response.send_message(
            "**📢 Canal destino**\nSelecciona el canal donde se enviará el embed:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Título", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def titulo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TituloModal(self))

    @discord.ui.button(label="Descripción", style=discord.ButtonStyle.primary, emoji="📄", row=0)
    async def descripcion_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescripcionModal(self))

    @discord.ui.button(label="Apariencia", style=discord.ButtonStyle.primary, emoji="🎨", row=0)
    async def apariencia_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AparienciaModal(self))

    # ── Fila 1 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, emoji="🔻", row=1)
    async def footer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FooterModal(self))

    @discord.ui.button(label="Añadir campo", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def campo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CampoModal(self))

    @discord.ui.button(label="Quitar campo", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def quitar_campo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.draft.fields:
            await interaction.response.send_message("❌ No hay campos que eliminar.", ephemeral=True)
            return
        self.draft.fields.pop()
        await interaction.response.edit_message(embed=build_config_embed(self.draft), view=self)

    @discord.ui.button(label="Vista previa", style=discord.ButtonStyle.secondary, emoji="👁️", row=1)
    async def preview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        final = build_final_embed(self.draft)
        if not final.title and not final.description and not final.fields:
            await interaction.response.send_message(
                "❌ El embed está vacío. Configura al menos el título o la descripción.",
                ephemeral=True,
            )
            return
        content = "👁️ **Vista previa** — Así se verá el embed:"
        if self.draft.menu_items:
            content += f"\n> ℹ️ El menú desplegable con **{len(self.draft.menu_items)} opciones** se adjuntará al enviarlo."
        await interaction.response.send_message(content=content, embed=final, ephemeral=True)

    # ── Fila 2 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Añadir link", style=discord.ButtonStyle.success, emoji="🔗", row=2)
    async def add_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddLinkModal(self))

    @discord.ui.button(label="Quitar link", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def quitar_link_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.draft.menu_items:
            await interaction.response.send_message("❌ No hay links en el menú.", ephemeral=True)
            return
        removed = self.draft.menu_items.pop()
        await interaction.response.edit_message(embed=build_config_embed(self.draft), view=self)

    @discord.ui.button(label="Enviar al canal", style=discord.ButtonStyle.success, emoji="🚀", row=2)
    async def enviar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.draft.channel_id:
            await interaction.response.send_message("❌ Configura primero el canal destino.", ephemeral=True)
            return

        final = build_final_embed(self.draft)
        if not final.title and not final.description and not final.fields:
            await interaction.response.send_message("❌ El embed está vacío.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.draft.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Canal no encontrado.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Enviar el embed sin view primero para obtener el message_id
            msg = await channel.send(embed=final)

            # Si hay items en el menú, guardar en BD y adjuntar view
            if self.draft.menu_items:
                saved_items = await db.save_embed_menu_items(msg.id, interaction.guild_id, self.draft.menu_items)
                menu_view = EmbedMenuView(saved_items)
                await msg.edit(view=menu_view)
                # Registrar el view para que persista ante reinicios
                interaction.client.add_view(menu_view, message_id=msg.id)

        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ No tengo permisos para enviar mensajes en {channel.mention}.", ephemeral=True
            )
            return

        # Desactivar el panel
        self.stop()
        for item in self.children:
            item.disabled = True
        config_embed = build_config_embed(self.draft)
        config_embed.set_footer(text="✅ Embed enviado correctamente")
        await self.panel_message.edit(embed=config_embed, view=self)
        await interaction.followup.send(f"✅ Embed enviado en {channel.mention}.", ephemeral=True)

    async def on_timeout(self):
        if self.panel_message:
            for item in self.children:
                item.disabled = True
            try:
                await self.panel_message.edit(view=self)
            except Exception:
                pass


# ─── Cog ──────────────────────────────────────────────────────────────────────

class EmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Re-registrar todos los menús persistentes al reiniciar."""
        all_menus = await db.get_all_embed_menus()
        for message_id, items in all_menus.items():
            if items:
                view = EmbedMenuView(items)
                self.bot.add_view(view, message_id=message_id)

    @app_commands.command(name="embed", description="Abre el panel para crear y enviar un embed personalizado.")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_cmd(self, interaction: discord.Interaction):
        panel = EmbedPanel()
        embed = build_config_embed(panel.draft)
        await interaction.response.send_message(embed=embed, view=panel, ephemeral=True)
        panel.panel_message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
