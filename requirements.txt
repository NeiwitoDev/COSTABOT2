"""
Sistema de Tickets Profesional — Panel estilo profesional
Comando: /tickets-setup
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import database as db


# ─── Helpers ──────────────────────────────────────────────────────────────────

def build_tickets_panel_embed(settings: dict | None, categories: list[dict], guild: discord.Guild) -> discord.Embed:
    enabled = bool(settings and settings.get("panel_channel_id"))

    embed = discord.Embed(
        title="🎫 Sistema de Tickets",
        description="Usa los botones de abajo para configurar cada sección.",
        color=0x5865F2,
    )

    estado = "🟢 Activado" if enabled else "🔴 Desactivado"
    embed.add_field(name="● Estado", value=estado, inline=False)

    # Canal del panel
    panel_ch = "Sin configurar"
    if settings and settings.get("panel_channel_id"):
        panel_ch = f"<#{settings['panel_channel_id']}>"
    embed.add_field(name="📢 Canal del panel", value=panel_ch, inline=True)

    # Canal de logs
    log_ch = "Sin configurar"
    if settings and settings.get("log_channel_id"):
        log_ch = f"<#{settings['log_channel_id']}>"
    embed.add_field(name="📋 Canal de logs", value=log_ch, inline=True)

    # Tipo de apertura
    open_type = "Botones"
    if settings and settings.get("open_type") == "select":
        open_type = "Menú desplegable"
    embed.add_field(name="🔘 Tipo de apertura", value=open_type, inline=True)

    # Rol de soporte
    role_val = "Sin configurar"
    if settings and settings.get("support_role_id"):
        role_val = f"<@&{settings['support_role_id']}>"
    embed.add_field(name="🛡️ Rol de soporte", value=role_val, inline=True)

    # Categoría Discord
    cat_val = "Sin configurar"
    if settings and settings.get("category_id"):
        cat_val = f"<#{settings['category_id']}>"
    embed.add_field(name="📁 Categoría (canales)", value=cat_val, inline=True)

    # Mensaje del panel
    msg_val = settings.get("panel_message") if settings else None
    embed.add_field(
        name="✉️ Mensaje del panel",
        value=(msg_val or "¿Necesitas ayuda? Abre un ticket.")[:200],
        inline=False,
    )

    # Categorías de tickets
    if categories:
        cats_text = "\n".join(
            f"{c.get('emoji','🎫')} **{c['name']}** — {c.get('description') or 'Sin descripción'} `[ID: {c['id']}]`"
            for c in categories
        )
        embed.add_field(name=f"🗂️ Categorías ({len(categories)})", value=cats_text, inline=False)
    else:
        embed.add_field(name="🗂️ Categorías", value="No hay categorías. Añade una con el botón.", inline=False)

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text=f"{guild.name} · Solo visible para ti")
    return embed


# ─── Modales de configuración ─────────────────────────────────────────────────

class TicketBasicModal(discord.ui.Modal, title="⚙️ Configuración Principal"):
    panel_channel = discord.ui.TextInput(
        label="Canal donde enviar el panel (ID)",
        placeholder="Ej: 123456789012345678",
        required=True,
        max_length=20,
    )
    log_channel = discord.ui.TextInput(
        label="Canal de logs de tickets (ID)",
        placeholder="Ej: 123456789012345678",
        required=False,
        max_length=20,
    )
    support_role = discord.ui.TextInput(
        label="Rol de soporte (ID, opcional)",
        placeholder="Ej: 123456789012345678",
        required=False,
        max_length=20,
    )
    discord_category = discord.ui.TextInput(
        label="Categoría de Discord para canales (ID)",
        placeholder="Ej: 123456789012345678",
        required=False,
        max_length=20,
    )

    def __init__(self, panel: TicketsPanel):
        super().__init__()
        self.panel = panel
        s = panel.settings
        if s:
            if s.get("panel_channel_id"):
                self.panel_channel.default = str(s["panel_channel_id"])
            if s.get("log_channel_id"):
                self.log_channel.default = str(s["log_channel_id"])
            if s.get("support_role_id"):
                self.support_role.default = str(s["support_role_id"])
            if s.get("category_id"):
                self.discord_category.default = str(s["category_id"])

    async def on_submit(self, interaction: discord.Interaction):
        # Panel channel
        try:
            panel_ch_id = int(self.panel_channel.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID del canal del panel no válido.", ephemeral=True)
            return
        if not interaction.guild.get_channel(panel_ch_id):
            await interaction.response.send_message("❌ Canal del panel no encontrado.", ephemeral=True)
            return

        log_ch_id = None
        if self.log_channel.value.strip():
            try:
                log_ch_id = int(self.log_channel.value.strip())
                if not interaction.guild.get_channel(log_ch_id):
                    await interaction.response.send_message("❌ Canal de logs no encontrado.", ephemeral=True)
                    return
            except ValueError:
                await interaction.response.send_message("❌ ID del canal de logs no válido.", ephemeral=True)
                return

        support_role_id = None
        if self.support_role.value.strip():
            try:
                support_role_id = int(self.support_role.value.strip())
            except ValueError:
                pass

        cat_id = None
        if self.discord_category.value.strip():
            try:
                cat_id = int(self.discord_category.value.strip())
            except ValueError:
                pass

        await db.set_ticket_settings(
            interaction.guild_id,
            panel_channel_id=panel_ch_id,
            log_channel_id=log_ch_id,
            support_role_id=support_role_id,
            category_id=cat_id,
        )
        self.panel.settings = await db.get_ticket_settings(interaction.guild_id)
        await self._refresh_panel(interaction)
        await interaction.response.send_message("✅ Configuración guardada.", ephemeral=True, delete_after=4)

    async def _refresh_panel(self, interaction: discord.Interaction):
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.panel.settings, cats, interaction.guild)
        await self.panel.panel_message.edit(embed=embed, view=self.panel)


class TicketMensajeModal(discord.ui.Modal, title="✉️ Mensaje del Panel"):
    panel_message = discord.ui.TextInput(
        label="Mensaje que aparece en el embed del panel",
        style=discord.TextStyle.paragraph,
        default="¿Necesitas ayuda? Selecciona una categoría para abrir un ticket.",
        required=True,
        max_length=1024,
    )

    def __init__(self, panel: TicketsPanel):
        super().__init__()
        self.panel = panel
        if panel.settings and panel.settings.get("panel_message"):
            self.panel_message.default = panel.settings["panel_message"]

    async def on_submit(self, interaction: discord.Interaction):
        await db.set_ticket_settings(interaction.guild_id, panel_message=self.panel_message.value.strip())
        self.panel.settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.panel.settings, cats, interaction.guild)
        await self.panel.panel_message.edit(embed=embed, view=self.panel)
        await interaction.response.send_message("✅ Mensaje guardado.", ephemeral=True, delete_after=4)


class TicketCategoryModal(discord.ui.Modal, title="➕ Nueva Categoría"):
    name = discord.ui.TextInput(
        label="Nombre de la categoría",
        placeholder="Ej: Soporte General",
        required=True,
        max_length=50,
    )
    description = discord.ui.TextInput(
        label="Descripción breve",
        placeholder="Ej: Ayuda con problemas generales",
        required=False,
        max_length=100,
    )
    emoji = discord.ui.TextInput(
        label="Emoji",
        placeholder="Ej: 🎫  🔧  ❓",
        default="🎫",
        required=False,
        max_length=8,
    )

    def __init__(self, panel: TicketsPanel):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        cats = await db.get_ticket_categories(interaction.guild_id)
        if len(cats) >= 10:
            await interaction.response.send_message("❌ Máximo 10 categorías por servidor.", ephemeral=True)
            return
        await db.add_ticket_category(
            interaction.guild_id,
            self.name.value.strip(),
            self.description.value.strip(),
            self.emoji.value.strip() or "🎫",
        )
        self.panel.settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.panel.settings, cats, interaction.guild)
        await self.panel.panel_message.edit(embed=embed, view=self.panel)
        await interaction.response.send_message(
            f"✅ Categoría **{self.name.value.strip()}** creada.", ephemeral=True, delete_after=4
        )


# ─── Vista para eliminar categorías ───────────────────────────────────────────

class DeleteCategoryView(discord.ui.View):
    def __init__(self, categories: list[dict], panel: TicketsPanel):
        super().__init__(timeout=60)
        self.panel = panel
        options = [
            discord.SelectOption(
                label=cat["name"],
                description=cat.get("description") or "Sin descripción",
                emoji=cat.get("emoji") or "🎫",
                value=str(cat["id"]),
            )
            for cat in categories[:25]
        ]
        select = discord.ui.Select(
            placeholder="Selecciona la categoría a eliminar...",
            options=options,
        )
        select.callback = self._delete_callback
        self.add_item(select)

    async def _delete_callback(self, interaction: discord.Interaction):
        cat_id = int(interaction.data["values"][0])
        await db.delete_ticket_category(cat_id, interaction.guild_id)
        self.panel.settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.panel.settings, cats, interaction.guild)
        await self.panel.panel_message.edit(embed=embed, view=self.panel)
        await interaction.response.send_message("🗑️ Categoría eliminada.", ephemeral=True, delete_after=4)
        self.stop()


# ─── Panel principal de tickets ───────────────────────────────────────────────

class TicketsPanel(discord.ui.View):
    def __init__(self, settings: dict | None, guild: discord.Guild):
        super().__init__(timeout=300)
        self.settings = settings
        self.guild = guild
        self.panel_message: discord.Message | None = None

    # ── Fila 1 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Canales / Roles", style=discord.ButtonStyle.primary, emoji="⚙️", row=0)
    async def config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketBasicModal(self))

    @discord.ui.button(label="Mensaje", style=discord.ButtonStyle.primary, emoji="✉️", row=0)
    async def mensaje_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketMensajeModal(self))

    @discord.ui.button(label="Tipo: Botones", style=discord.ButtonStyle.secondary, emoji="🔘", row=0)
    async def type_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.set_ticket_settings(interaction.guild_id, open_type="button")
        self.settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.settings, cats, interaction.guild)
        await self.panel_message.edit(embed=embed, view=self)
        await interaction.response.send_message("✅ Tipo: **Botones**.", ephemeral=True, delete_after=4)

    @discord.ui.button(label="Tipo: Menú", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def type_select(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.set_ticket_settings(interaction.guild_id, open_type="select")
        self.settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(self.settings, cats, interaction.guild)
        await self.panel_message.edit(embed=embed, view=self)
        await interaction.response.send_message("✅ Tipo: **Menú desplegable**.", ephemeral=True, delete_after=4)

    # ── Fila 2 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Añadir categoría", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def add_cat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCategoryModal(self))

    @discord.ui.button(label="Eliminar categoría", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def del_cat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cats = await db.get_ticket_categories(interaction.guild_id)
        if not cats:
            await interaction.response.send_message("❌ No hay categorías para eliminar.", ephemeral=True)
            return
        view = DeleteCategoryView(cats, self)
        await interaction.response.send_message(
            "Selecciona la categoría a eliminar:", view=view, ephemeral=True
        )

    # ── Fila 3 ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="🚀 Publicar Panel", style=discord.ButtonStyle.success, emoji=None, row=2)
    async def publish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.settings or not self.settings.get("panel_channel_id"):
            await interaction.response.send_message("❌ Configura el canal del panel primero.", ephemeral=True)
            return
        cats = await db.get_ticket_categories(interaction.guild_id)
        if not cats:
            await interaction.response.send_message(
                "❌ Necesitas al menos una categoría antes de publicar.", ephemeral=True
            )
            return
        panel_ch = interaction.guild.get_channel(self.settings["panel_channel_id"])
        if not panel_ch:
            await interaction.response.send_message("❌ Canal del panel no encontrado.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Sistema de Tickets",
            description=self.settings.get("panel_message") or "¿Necesitas ayuda? Abre un ticket.",
            color=0x5865F2,
        )
        for cat in cats:
            embed.add_field(
                name=f"{cat.get('emoji','🎫')} {cat['name']}",
                value=cat.get("description") or "Abre un ticket de esta categoría.",
                inline=True,
            )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{interaction.guild.name} · Sistema de Tickets")

        open_type = self.settings.get("open_type") or "button"
        panel_view = TicketPanelSelectView(cats) if open_type == "select" else TicketPanelButtonView(cats)

        try:
            await panel_ch.send(embed=embed, view=panel_view)
            await interaction.response.send_message(
                f"✅ Panel publicado en {panel_ch.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Sin permisos para enviar en ese canal.", ephemeral=True
            )

    async def on_timeout(self):
        if self.panel_message:
            for item in self.children:
                item.disabled = True
            try:
                await self.panel_message.edit(view=self)
            except Exception:
                pass


# ─── Panel de tickets (usuario) ───────────────────────────────────────────────

class TicketPanelButtonView(discord.ui.View):
    def __init__(self, categories: list[dict]):
        super().__init__(timeout=None)
        for cat in categories[:5]:
            btn = discord.ui.Button(
                label=cat["name"],
                emoji=cat.get("emoji") or "🎫",
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket:open:{cat['id']}",
            )
            btn.callback = self._make_cb(cat["id"])
            self.add_item(btn)

    def _make_cb(self, cat_id: int):
        async def cb(interaction: discord.Interaction):
            await open_ticket(interaction, cat_id)
        return cb


class TicketPanelSelectView(discord.ui.View):
    def __init__(self, categories: list[dict]):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(
                label=cat["name"],
                description=cat.get("description") or "Abre un ticket",
                emoji=cat.get("emoji") or "🎫",
                value=str(cat["id"]),
            )
            for cat in categories[:25]
        ]
        sel = discord.ui.Select(
            placeholder="Selecciona el tipo de ticket...",
            options=options,
            custom_id="ticket:select",
        )
        sel.callback = self._cb
        self.add_item(sel)

    async def _cb(self, interaction: discord.Interaction):
        cat_id = int(interaction.data["values"][0])
        await open_ticket(interaction, cat_id)


# ─── Lógica de apertura de ticket ─────────────────────────────────────────────

async def open_ticket(interaction: discord.Interaction, category_id: int):
    existing = await db.get_open_ticket_by_user(interaction.guild_id, interaction.user.id)
    if existing:
        ch = interaction.guild.get_channel(existing["channel_id"])
        if ch:
            await interaction.response.send_message(
                f"❌ Ya tienes un ticket abierto: {ch.mention}", ephemeral=True
            )
            return

    settings = await db.get_ticket_settings(interaction.guild_id)
    if not settings:
        await interaction.response.send_message("❌ El sistema de tickets no está configurado.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    categories = await db.get_ticket_categories(interaction.guild_id)
    cat_info = next((c for c in categories if c["id"] == category_id), None)
    cat_name = cat_info["name"] if cat_info else "General"

    discord_category = None
    if settings.get("category_id"):
        discord_category = interaction.guild.get_channel(settings["category_id"])

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True, embed_links=True
        ),
        interaction.guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True, manage_messages=True
        ),
    }
    if settings.get("support_role_id"):
        role = interaction.guild.get_role(settings["support_role_id"])
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_messages=True
            )

    safe_name = interaction.user.display_name[:12].lower().replace(" ", "-")
    channel_name = f"ticket-{safe_name}-{interaction.user.id % 10000}"

    try:
        ticket_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=discord_category if isinstance(discord_category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user} | Categoría: {cat_name}",
            reason=f"Ticket abierto por {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.followup.send("❌ Sin permisos para crear canales.", ephemeral=True)
        return

    ticket_id = await db.create_ticket(interaction.guild_id, interaction.user.id, ticket_channel.id, category_id)

    embed = discord.Embed(
        title=f"🎫 Ticket #{ticket_id} — {cat_name}",
        description=(
            f"¡Hola {interaction.user.mention}! Gracias por contactarnos.\n\n"
            f"Por favor describe tu problema con el mayor detalle posible. "
            f"Un miembro del staff lo atenderá en breve."
        ),
        color=0x5865F2,
    )
    embed.add_field(name="Abierto por", value=interaction.user.mention, inline=True)
    embed.add_field(name="Categoría", value=cat_name, inline=True)
    embed.add_field(name="Estado", value="🟢 Abierto", inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text=f"ID #{ticket_id} · {interaction.guild.name}")

    mention = interaction.user.mention
    if settings.get("support_role_id"):
        role = interaction.guild.get_role(settings["support_role_id"])
        if role:
            mention += f" | {role.mention}"

    await ticket_channel.send(content=mention, embed=embed, view=TicketChannelView())

    # Log
    if settings.get("log_channel_id"):
        log_ch = interaction.guild.get_channel(settings["log_channel_id"])
        if log_ch:
            log_embed = discord.Embed(title="📋 Nuevo Ticket", color=discord.Color.green())
            log_embed.add_field(name="Usuario", value=f"{interaction.user.mention} (`{interaction.user}`)", inline=True)
            log_embed.add_field(name="Canal", value=ticket_channel.mention, inline=True)
            log_embed.add_field(name="Categoría", value=cat_name, inline=True)
            log_embed.timestamp = discord.utils.utcnow()
            try:
                await log_ch.send(embed=log_embed)
            except discord.Forbidden:
                pass

    await interaction.followup.send(f"✅ Ticket creado: {ticket_channel.mention}", ephemeral=True)


# ─── Vista dentro del canal de ticket ─────────────────────────────────────────

class TicketChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reclamar Ticket", style=discord.ButtonStyle.primary, emoji="🙋", custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ No se encontró información de este ticket.", ephemeral=True)
            return
        if ticket["status"] != "open":
            await interaction.response.send_message("❌ Este ticket ya fue reclamado o está cerrado.", ephemeral=True)
            return

        await db.update_ticket(interaction.channel_id, claimed_by=interaction.user.id, status="claimed")

        button.disabled = True
        button.label = f"Reclamado por {interaction.user.display_name}"
        claimed_embed = discord.Embed(
            title="🙋 Ticket Reclamado",
            description=f"Este ticket fue reclamado por {interaction.user.mention}.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=claimed_embed, view=self)

        # Log
        settings = await db.get_ticket_settings(interaction.guild_id)
        if settings and settings.get("log_channel_id"):
            log_ch = interaction.guild.get_channel(settings["log_channel_id"])
            if log_ch:
                log_embed = discord.Embed(title="📋 Ticket Reclamado", color=discord.Color.blue())
                log_embed.add_field(name="Canal", value=interaction.channel.mention, inline=True)
                log_embed.add_field(name="Staff", value=interaction.user.mention, inline=True)
                ticket_user = interaction.guild.get_member(ticket["user_id"])
                if ticket_user:
                    log_embed.add_field(name="Abierto por", value=ticket_user.mention, inline=True)
                log_embed.timestamp = discord.utils.utcnow()
                try:
                    await log_ch.send(embed=log_embed)
                except discord.Forbidden:
                    pass

        # DM al usuario
        ticket_user = interaction.guild.get_member(ticket["user_id"])
        if ticket_user:
            try:
                dm = discord.Embed(
                    title="📬 Tu ticket fue reclamado",
                    description=(
                        f"¡Hola! Tu ticket en **{interaction.guild.name}** fue reclamado por "
                        f"**{interaction.user}** y pronto recibirás atención."
                    ),
                    color=discord.Color.blue(),
                )
                dm.add_field(name="Servidor", value=interaction.guild.name, inline=True)
                dm.add_field(name="Staff asignado", value=str(interaction.user), inline=True)
                dm.add_field(name="Canal", value=f"#{interaction.channel.name}", inline=True)
                dm.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm.timestamp = discord.utils.utcnow()
                dm.set_footer(text=f"{interaction.guild.name} · Sistema de Tickets")
                await ticket_user.send(embed=dm)
            except discord.Forbidden:
                pass

    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("❌ No se encontró información de este ticket.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await interaction.response.send_message("❌ Este ticket ya está cerrado.", ephemeral=True)
            return

        confirm = ConfirmCloseView()
        await interaction.response.send_message("¿Seguro que quieres cerrar este ticket?", view=confirm, ephemeral=True)
        await confirm.wait()
        if not confirm.confirmed:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.update_ticket(interaction.channel_id, status="closed", closed_at=now_iso)

        # DM al usuario
        ticket_user = interaction.guild.get_member(ticket["user_id"])
        closer = interaction.user
        if ticket_user:
            try:
                dm = discord.Embed(
                    title="🔒 Tu ticket fue cerrado",
                    description=(
                        f"Tu ticket en **{interaction.guild.name}** fue cerrado por **{closer}**.\n"
                        f"Si necesitas más ayuda puedes abrir un nuevo ticket."
                    ),
                    color=discord.Color.red(),
                )
                dm.add_field(name="Servidor", value=interaction.guild.name, inline=True)
                dm.add_field(name="Cerrado por", value=str(closer), inline=True)
                dm.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                dm.timestamp = discord.utils.utcnow()
                dm.set_footer(text=f"{interaction.guild.name} · Sistema de Tickets")
                await ticket_user.send(embed=dm)
            except discord.Forbidden:
                pass

        # Log
        settings = await db.get_ticket_settings(interaction.guild_id)
        if settings and settings.get("log_channel_id"):
            log_ch = interaction.guild.get_channel(settings["log_channel_id"])
            if log_ch:
                log_embed = discord.Embed(title="🔒 Ticket Cerrado", color=discord.Color.red())
                log_embed.add_field(name="Canal", value=f"#{interaction.channel.name}", inline=True)
                log_embed.add_field(name="Cerrado por", value=closer.mention, inline=True)
                if ticket_user:
                    log_embed.add_field(name="Abierto por", value=ticket_user.mention, inline=True)
                log_embed.timestamp = discord.utils.utcnow()
                try:
                    await log_ch.send(embed=log_embed)
                except discord.Forbidden:
                    pass

        close_embed = discord.Embed(
            title="🔒 Ticket Cerrado",
            description=f"Cerrado por {closer.mention}. El canal se eliminará en 5 segundos.",
            color=discord.Color.red(),
        )
        try:
            await interaction.channel.send(embed=close_embed)
            await asyncio.sleep(5)
            await interaction.channel.delete(reason=f"Ticket cerrado por {closer}")
        except (discord.Forbidden, discord.NotFound):
            pass


class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.confirmed = False

    @discord.ui.button(label="Sí, cerrar", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.send_message("❌ Cancelado.", ephemeral=True, delete_after=3)
        self.stop()


# ─── Cog ──────────────────────────────────────────────────────────────────────

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketChannelView())

    @app_commands.command(
        name="tickets-setup",
        description="Abre el panel de configuración del sistema de tickets.",
    )
    @app_commands.default_permissions(administrator=True)
    async def tickets_setup(self, interaction: discord.Interaction):
        settings = await db.get_ticket_settings(interaction.guild_id)
        cats = await db.get_ticket_categories(interaction.guild_id)
        embed = build_tickets_panel_embed(settings, cats, interaction.guild)
        panel = TicketsPanel(settings, interaction.guild)
        await interaction.response.send_message(embed=embed, view=panel, ephemeral=True)
        panel.panel_message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
