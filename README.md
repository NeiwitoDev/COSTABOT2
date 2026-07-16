# 🤖 Discord Bot

Bot multipropósito para Discord desarrollado en Python con discord.py 2.x.

**Dev:** Neiwito

---

## 🚀 Sistemas incluidos

| Sistema | Comando | Descripción |
|---|---|---|
| Bienvenidas | `/welcome-setup` | Panel para configurar mensajes de bienvenida |
| AutoMod | automático | Detección de flood y spam/links |
| Bot Setup | `/bot-setup` | Prefijo, canal de logs, umbrales de flood |
| Tickets | `/tickets-setup` | Sistema de tickets con categorías |
| Embeds | `/embed` | Crear y enviar embeds personalizados |
| Moderación | `?lock/unlock/kick/ban…` | Comandos de moderación completos |

---

## ⚙️ Comandos de moderación

| Comando | Descripción |
|---|---|
| `?lock [#canal] [tiempo]` | Bloquea un canal (ej: `?lock #general 30m`) |
| `?unlock [#canal]` | Desbloquea un canal |
| `?kick @user [motivo]` | Expulsa a un usuario |
| `?ban @user\|id [motivo]` | Banea permanentemente |
| `?unban <user_id> [motivo]` | Desbanea por ID |
| `?tempban @user\|id <tiempo> [motivo]` | Baneo temporal (ej: `?tempban @user 1d Raid`) |
| `?warn @user <motivo>` | Registra una advertencia |
| `?delwarn @user <id>` | Elimina una advertencia por su ID |
| `?warns @user` | Muestra todas las advertencias de un usuario |

**Formato de tiempo:** `30s` · `15m` · `2h` · `1d` · o combinados `1h30m`

---

## 🛠️ Instalación local

### Requisitos
- Python 3.11+
- pip

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/tu-repo.git
cd tu-repo/discord-bot

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar el token
cp .env.example .env
# Editar .env y poner tu DISCORD_BOT_TOKEN

# 4. Iniciar el bot
python3 main.py
```

---

## ☁️ Deploy en Render

1. Crear un nuevo **Web Service** en [Render](https://render.com)
2. Conectar el repositorio de GitHub
3. Configurar:
   - **Root Directory:** `discord-bot`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python3 main.py`
4. En **Environment Variables**, agregar:
   - `DISCORD_BOT_TOKEN` → tu token de Discord
5. Deploy ✅

> **UptimeRobot:** Crear un monitor HTTP apuntando a la URL de Render para mantener el bot activo 24/7.

---

## 🔐 Variables de entorno

| Variable | Descripción |
|---|---|
| `DISCORD_BOT_TOKEN` | Token del bot de Discord (obligatorio) |

---

## 📦 Dependencias

```
discord.py>=2.3.2
aiosqlite>=0.19.0
python-dotenv>=1.0.0
```

---

## 📁 Estructura

```
discord-bot/
├── main.py           # Entrada principal del bot
├── database.py       # Base de datos SQLite async
├── requirements.txt  # Dependencias Python
├── .env.example      # Plantilla de variables de entorno
└── cogs/
    ├── welcome.py    # Sistema de bienvenidas
    ├── automod.py    # Moderación automática
    ├── setup.py      # Configuración del bot
    ├── tickets.py    # Sistema de tickets
    ├── embed.py      # Creador de embeds
    └── moderation.py # Comandos de moderación
```
