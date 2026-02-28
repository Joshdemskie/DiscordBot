import os
import sqlite3
import datetime
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Load .env from the same folder as this bot.py
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

TOKEN = os.getenv("DISCORD_TOKEN")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))
SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID", "0"))
ALLOWED_GUILD_ID = int(os.getenv("ALLOWED_GUILD_ID", "0"))

# Rules + roles panels
RULES_CHANNEL_ID = int(os.getenv("RULES_CHANNEL_ID", "0"))
ROLES_CHANNEL_ID = int(os.getenv("ROLES_CHANNEL_ID", "0"))
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID", "0"))

# Self-assign roles panels (up to 5 pages)
SELF_ROLES_1 = os.getenv("SELF_ROLES_1", "").strip()
SELF_ROLES_2 = os.getenv("SELF_ROLES_2", "").strip()
SELF_ROLES_3 = os.getenv("SELF_ROLES_3", "").strip()
SELF_ROLES_4 = os.getenv("SELF_ROLES_4", "").strip()
SELF_ROLES_5 = os.getenv("SELF_ROLES_5", "").strip()

# --- Karma / Warnings system ---
ENABLE_KARMA = os.getenv("ENABLE_KARMA", "false").strip().lower() == "true"
MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID", "0"))
DEBATE_ROLE_ID = int(os.getenv("DEBATE_ROLE_ID", "0"))

# Optional "failsafe" lock role (denies debate channels). 0 = off
DEBATE_LOCK_ROLE_ID = int(os.getenv("DEBATE_LOCK_ROLE_ID", "0"))

KARMA_START = int(os.getenv("KARMA_START", "100"))
KARMA_WARN = int(os.getenv("KARMA_WARN", "-25"))   # legacy default; new warn uses mapped deltas
KARMA_PRAISE = int(os.getenv("KARMA_PRAISE", "5"))
KARMA_KUDOS = int(os.getenv("KARMA_KUDOS", "1"))

KARMA_LOCK_THRESHOLD = int(os.getenv("KARMA_LOCK_THRESHOLD", "25"))
KARMA_REGAIN_THRESHOLD = int(os.getenv("KARMA_REGAIN_THRESHOLD", "40"))

KARMA_AUTO_RESTORE_DEBATE = os.getenv("KARMA_AUTO_RESTORE_DEBATE", "false").strip().lower() == "true"

# Optional profanity scanning (simple example)
ENABLE_PROFANITY_SCAN = os.getenv("ENABLE_PROFANITY_SCAN", "false").strip().lower() == "true"
PROFANITY_WORDS = [w.strip().lower() for w in os.getenv("PROFANITY_WORDS", "").split(",") if w.strip()]

# --- Warn rule catalog (specific, ordered by severity) ---
# value key, label shown in Discord, delta (negative = lose ELO)
WARN_VIOLATIONS = [
    # Minor (-5)
    ("A1_WRONG_CHANNEL", "A1 Wrong channel / off-topic (-5)", -5),
    ("A2_SPAM_LIGHT", "A2 Light spam / clutter (-5)", -5),
    ("A3_BAD_FAITH_LIGHT", "A3 Bad faith (light) (-5)", -5),

    # Medium (-10)
    ("B1_TOXIC_TACTICS", "B1 Toxic debate tactics (-10)", -10),
    ("B2_SOURCES_REPEAT", "B2 Repeated refusal to source (-10)", -10),
    ("B3_MOD_CONDUCT", "B3 Disrespecting mod calls publicly (-10)", -10),

    # High (-15)
    ("C1_INSULTS", "C1 Insults / ad hominem / harassment (-15)", -15),

    # Severe (-20 / -25)
    ("D1_SENSITIVE", "D1 Sensitive content (nudity/gore/violence) (-20)", -20),
    ("D2_HATE_SPEECH", "D2 Hate speech / racism / slurs (-25)", -25),

    # Perm-ban tier
    ("E1_DOXX", "E1 Doxxing / personal info (PERM BAN tier)", 0),
]

WARN_LABEL_BY_KEY = {k: label for (k, label, d) in WARN_VIOLATIONS}
WARN_DELTA_BY_KEY = {k: d for (k, label, d) in WARN_VIOLATIONS}

# ---- Intents ----
intents = discord.Intents.default()
intents.message_content = True  # needed if you want to scan chat content
intents.members = True          # helpful for role ops; many bots enable this

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# TICKET VIEW
# -------------------------
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, custom_id="ticket_create_button_v1")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        if guild is None:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            return await interaction.response.send_message("Ticket category not found. Check TICKET_CATEGORY_ID.", ephemeral=True)

        support_role = guild.get_role(SUPPORT_ROLE_ID)
        if support_role is None:
            return await interaction.response.send_message("Support role not found. Check SUPPORT_ROLE_ID.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True
            ),
        }

        safe_name = user.name.lower().replace(" ", "-")
        ticket_name = f"ticket-{safe_name}-{interaction.id}"

        ticket_channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket created by {user} ({user.id})"
        )

        embed = discord.Embed(
            title="Ticket Created",
            description=f"Welcome {user.mention}! Please describe your issue below.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Only you and support can see this ticket.")

        await ticket_channel.send(content=user.mention, embed=embed)
        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


async def ensure_ticket_panel():
    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        print("ERROR: Panel channel not found. Check PANEL_CHANNEL_ID.")
        return

    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if getattr(comp, "custom_id", None) == "ticket_create_button_v1":
                        print("Panel already exists. Not reposting.")
                        return

    embed = discord.Embed(
        title="Support Tickets",
        description="Click the button below to create a ticket.",
        color=discord.Color.blurple()
    )
    await channel.send(embed=embed, view=TicketView())
    print("Panel posted automatically.")


# -------------------------
# RULES VERIFY BUTTON
# -------------------------
class RulesVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="I read the rules",
        style=discord.ButtonStyle.green,
        custom_id="rules_verify_button_v1"
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        if guild is None:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        verified_role = guild.get_role(VERIFIED_ROLE_ID)
        if verified_role is None:
            return await interaction.response.send_message("Verified role not found. Check VERIFIED_ROLE_ID.", ephemeral=True)

        if verified_role in member.roles:
            return await interaction.response.send_message("You're already verified.", ephemeral=True)

        try:
            await member.add_roles(verified_role, reason="Accepted rules")
            await interaction.response.send_message("Verified. You can now access the server.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I can't assign roles. Make sure I have Manage Roles and my role is ABOVE Verified.",
                ephemeral=True
            )


async def ensure_rules_panel():
    channel = bot.get_channel(RULES_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        print("ERROR: Rules channel not found. Check RULES_CHANNEL_ID.")
        return

    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if getattr(comp, "custom_id", None) == "rules_verify_button_v1":
                        print("Rules panel already exists. Not reposting.")
                        return

    embed = discord.Embed(
        title="Rules Verification",
        description="Read the rules above, then click I read the rules to get Verified and unlock the server.",
        color=discord.Color.green()
    )
    await channel.send(embed=embed, view=RulesVerifyView())
    print("Rules panel posted automatically.")


# -------------------------
# SELF-ROLES (BUTTON TOGGLES)
# -------------------------
def parse_self_roles(raw: str):
    """
    Format: Label:ROLE_ID;Label:ROLE_ID;...
    Returns list[(label, role_id)]
    """
    out = []
    if not raw:
        return out
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    for p in parts:
        if ":" not in p:
            continue
        label, rid = p.split(":", 1)
        label = label.strip()
        rid = rid.strip()
        if not label or not rid.isdigit():
            continue
        out.append((label, int(rid)))
    return out


SELF_ROLE_PAGES = [
    parse_self_roles(SELF_ROLES_1),
    parse_self_roles(SELF_ROLES_2),
    parse_self_roles(SELF_ROLES_3),
    parse_self_roles(SELF_ROLES_4),
    parse_self_roles(SELF_ROLES_5),
]
SELF_ROLE_PAGES = [page for page in SELF_ROLE_PAGES if page]  # remove empties


# -------------------------
# KARMA DB + HELPERS
# -------------------------
def _karma_db_path() -> str:
    return os.path.join(os.path.dirname(__file__), "karma.db")


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_karma_db():
    # No global flag -> avoids SyntaxError issues forever
    if getattr(_ensure_karma_db, "_init", False):
        return

    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS karma_users (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        karma    INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS karma_cases (
        case_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        mod_id   INTEGER NOT NULL,
        action   TEXT NOT NULL,
        delta    INTEGER NOT NULL,
        reason   TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    _ensure_karma_db._init = True


def _get_or_create_karma(guild_id: int, user_id: int) -> int:
    _ensure_karma_db()
    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()

    cur.execute("SELECT karma FROM karma_users WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    row = cur.fetchone()
    if row:
        conn.close()
        return int(row[0])

    cur.execute(
        "INSERT INTO karma_users (guild_id, user_id, karma, updated_at) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, KARMA_START, _utc_now_iso())
    )
    conn.commit()
    conn.close()
    return KARMA_START


def _set_karma(guild_id: int, user_id: int, value: int):
    _ensure_karma_db()
    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO karma_users (guild_id, user_id, karma, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET karma=excluded.karma, updated_at=excluded.updated_at
    """, (guild_id, user_id, value, _utc_now_iso()))
    conn.commit()
    conn.close()


def _insert_case(guild_id: int, user_id: int, mod_id: int, action: str, delta: int, reason: str) -> int:
    _ensure_karma_db()
    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO karma_cases (guild_id, user_id, mod_id, action, delta, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (guild_id, user_id, mod_id, action, delta, reason, _utc_now_iso()))
    conn.commit()
    case_id = cur.lastrowid
    conn.close()
    return int(case_id)


def _fetch_history(guild_id: int, user_id: int, limit: int = 10):
    _ensure_karma_db()
    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()
    cur.execute("""
        SELECT case_id, action, delta, reason, mod_id, created_at
        FROM karma_cases
        WHERE guild_id=? AND user_id=?
        ORDER BY case_id DESC
        LIMIT ?
    """, (guild_id, user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def _fetch_case(guild_id: int, case_id: int):
    _ensure_karma_db()
    conn = sqlite3.connect(_karma_db_path())
    cur = conn.cursor()
    cur.execute("""
        SELECT case_id, user_id, mod_id, action, delta, reason, created_at
        FROM karma_cases
        WHERE guild_id=? AND case_id=?
    """, (guild_id, case_id))
    row = cur.fetchone()
    conn.close()
    return row


def _is_mod(member: discord.Member) -> bool:
    p = member.guild_permissions
    return any([
        p.manage_guild,
        p.manage_messages,
        p.moderate_members,
        p.kick_members,
        p.ban_members,
        p.manage_roles
    ])


async def _send_modlog(guild: discord.Guild, embed: discord.Embed):
    if not MOD_LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(embed=embed)
        except discord.Forbidden:
            pass


async def _enforce_debate_access(member: discord.Member, karma: int):
    debate_role = member.guild.get_role(DEBATE_ROLE_ID) if DEBATE_ROLE_ID else None
    lock_role = member.guild.get_role(DEBATE_LOCK_ROLE_ID) if DEBATE_LOCK_ROLE_ID else None

    try:
        if karma < KARMA_LOCK_THRESHOLD:
            if debate_role and debate_role in member.roles:
                await member.remove_roles(debate_role, reason=f"Karma below {KARMA_LOCK_THRESHOLD}")
            if lock_role and lock_role not in member.roles:
                await member.add_roles(lock_role, reason=f"Karma below {KARMA_LOCK_THRESHOLD}")
        else:
            if lock_role and lock_role in member.roles and karma >= KARMA_REGAIN_THRESHOLD:
                await member.remove_roles(lock_role, reason=f"Karma at/above {KARMA_REGAIN_THRESHOLD}")

            if KARMA_AUTO_RESTORE_DEBATE and debate_role and karma >= KARMA_REGAIN_THRESHOLD:
                if debate_role not in member.roles:
                    await member.add_roles(debate_role, reason=f"Karma at/above {KARMA_REGAIN_THRESHOLD}")
    except discord.Forbidden:
        pass


class RoleToggleButton(discord.ui.Button):
    def __init__(self, label: str, role_id: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.blurple,
            custom_id=f"selfrole_toggle_{role_id}_v1"
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        if guild is None:
            return await interaction.response.send_message("This must be used in a server.", ephemeral=True)

        verified_role = guild.get_role(VERIFIED_ROLE_ID)
        if verified_role is None:
            return await interaction.response.send_message("Verified role not found. Check VERIFIED_ROLE_ID.", ephemeral=True)

        if verified_role not in member.roles:
            return await interaction.response.send_message(
                "You must click I read the rules in the rules channel first.",
                ephemeral=True
            )

        role = guild.get_role(self.role_id)
        if role is None:
            return await interaction.response.send_message("That role no longer exists.", ephemeral=True)

        # prevent bypass for Debater role
        if ENABLE_KARMA and DEBATE_ROLE_ID and self.role_id == DEBATE_ROLE_ID:
            current_karma = _get_or_create_karma(guild.id, member.id)
            if role not in member.roles and current_karma < KARMA_REGAIN_THRESHOLD:
                return await interaction.response.send_message(
                    f"You need at least {KARMA_REGAIN_THRESHOLD} karma to get Debate access. "
                    f"You're currently at {current_karma}.",
                    ephemeral=True
                )

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(f"Removed {role.name}", ephemeral=True)
            else:
                await member.add_roles(role, reason="Self-role toggle")
                await interaction.response.send_message(f"Added {role.name}", ephemeral=True)

                if ENABLE_KARMA and DEBATE_ROLE_ID and self.role_id == DEBATE_ROLE_ID:
                    current_karma = _get_or_create_karma(guild.id, member.id)
                    await _enforce_debate_access(member, current_karma)

        except discord.Forbidden:
            await interaction.response.send_message(
                "I can't change roles. Make sure I have Manage Roles and my role is ABOVE the roles I assign.",
                ephemeral=True
            )


class SelfRolesView(discord.ui.View):
    def __init__(self, page_index: int, roles_for_page: list[tuple[str, int]]):
        super().__init__(timeout=None)
        self.page_index = page_index
        for label, rid in roles_for_page[:25]:
            self.add_item(RoleToggleButton(label, rid))


async def ensure_roles_panels():
    channel = bot.get_channel(ROLES_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        print("ERROR: Roles channel not found. Check ROLES_CHANNEL_ID.")
        return

    if not SELF_ROLE_PAGES:
        print("No SELF_ROLES_X configured; skipping role panels.")
        return

    for i, page in enumerate(SELF_ROLE_PAGES, start=1):
        sentinel_custom_id = f"selfrole_toggle_{page[0][1]}_v1"
        found = False

        async for msg in channel.history(limit=200):
            if msg.author == bot.user and msg.components:
                for row in msg.components:
                    for comp in row.children:
                        if getattr(comp, "custom_id", None) == sentinel_custom_id:
                            found = True
                            break
                    if found:
                        break
            if found:
                break

        if found:
            print(f"Roles panel page {i} already exists. Not reposting.")
            continue

        embed = discord.Embed(
            title=f"Choose Your Roles (Page {i})",
            description="Click buttons to toggle roles. (You must be Verified first.)",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed, view=SelfRolesView(i, page))
        print(f"Roles panel page {i} posted automatically.")


# -------------------------
# KARMA SLASH COMMANDS
# -------------------------
def _register_karma_commands_once():
    if getattr(bot, "_karma_commands_registered", False):
        return
    bot._karma_commands_registered = True

    @app_commands.command(name="karma", description="Check karma for yourself or another user.")
    @app_commands.describe(user="User to check (optional)")
    async def karma_cmd(interaction: discord.Interaction, user: discord.Member | None = None):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        target = user or interaction.user
        value = _get_or_create_karma(interaction.guild.id, target.id)

        embed = discord.Embed(title="Karma", color=discord.Color.blurple())
        embed.add_field(name="User", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.add_field(name="Karma", value=str(value), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sync", description="Force re-sync slash commands (admin only).")
    async def sync_cmd(interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        try:
            bot.tree.copy_global_to(guild=interaction.guild)
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.response.send_message(f"Synced {len(synced)} commands to this server.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Sync failed: {repr(e)}", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a user using the rules dropdown and log a case.")
    @app_commands.describe(
        user="User to warn",
        violation="Pick the rule item",
        description="Describe what rule was broken (be specific)"
    )
    @app_commands.choices(
        violation=[app_commands.Choice(name=label, value=key) for (key, label, _d) in WARN_VIOLATIONS]
    )
    async def warn_cmd(
        interaction: discord.Interaction,
        user: discord.Member,
        violation: app_commands.Choice[str],
        description: str
    ):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("Not for bots.", ephemeral=True)

        key = violation.value
        label = WARN_LABEL_BY_KEY.get(key, "Rule violation")

        # Perm-ban tier: doxxing/privacy & safety
        if key == "E1_DOXX":
            reason = f"[{label}] {description}"
            case_id = _insert_case(interaction.guild.id, user.id, interaction.user.id, "WARN_PERMBAN", 0, reason)

            embed = discord.Embed(
                title=f"Case #{case_id} | WARN (PERM BAN TIER)",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
            embed.add_field(name="Moderator", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
            embed.add_field(name="Violation", value=label, inline=False)
            embed.add_field(name="Description", value=description, inline=False)

            await _send_modlog(interaction.guild, embed)

            # Intentionally NOT auto-banning in code (you can choose ban/kick manually)
            return await interaction.response.send_message(
                f"Logged perm-ban tier case for {user.mention}. Case #{case_id}. (No auto-ban performed.)",
                ephemeral=True
            )

        delta = int(WARN_DELTA_BY_KEY.get(key, KARMA_WARN))  # negative
        reason = f"[{label}] {description}"

        current = _get_or_create_karma(interaction.guild.id, user.id)
        new_val = current + delta
        _set_karma(interaction.guild.id, user.id, new_val)

        case_id = _insert_case(interaction.guild.id, user.id, interaction.user.id, "WARN", delta, reason)
        await _enforce_debate_access(user, new_val)

        embed = discord.Embed(
            title=f"Case #{case_id} | WARN",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Violation", value=label, inline=False)
        embed.add_field(name="Delta", value=str(delta), inline=True)
        embed.add_field(name="New karma", value=str(new_val), inline=True)
        embed.add_field(name="Description", value=description, inline=False)

        await _send_modlog(interaction.guild, embed)

        # DM the user (best-effort)
        try:
            dm = discord.Embed(title="You received a warning", color=discord.Color.red())
            dm.add_field(name="Server", value=interaction.guild.name, inline=False)
            dm.add_field(name="Violation", value=label, inline=False)
            dm.add_field(name="Description", value=description, inline=False)
            dm.add_field(name="Karma change", value=str(delta), inline=True)
            dm.add_field(name="New karma", value=str(new_val), inline=True)
            dm.set_footer(text=f"Case #{case_id}")
            await user.send(embed=dm)
        except Exception:
            pass

        await interaction.response.send_message(
            f"OK. Warned {user.mention}. ({label}) Case #{case_id}. New karma: {new_val}.",
            ephemeral=True
        )

    @app_commands.command(name="praise", description="Praise a user (default +5) and log it.")
    @app_commands.describe(user="User to praise", reason="Reason / what they did well")
    async def praise_cmd(interaction: discord.Interaction, user: discord.Member, reason: str):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("Not for bots.", ephemeral=True)

        current = _get_or_create_karma(interaction.guild.id, user.id)
        new_val = current + KARMA_PRAISE
        _set_karma(interaction.guild.id, user.id, new_val)

        case_id = _insert_case(interaction.guild.id, user.id, interaction.user.id, "PRAISE", KARMA_PRAISE, reason)
        await _enforce_debate_access(user, new_val)

        embed = discord.Embed(
            title=f"Case #{case_id} | PRAISE",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Delta", value=f"+{KARMA_PRAISE}", inline=True)
        embed.add_field(name="New karma", value=str(new_val), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        await _send_modlog(interaction.guild, embed)
        await interaction.response.send_message(
            f"OK. Praised {user.mention}. Case #{case_id}. New karma: {new_val}.",
            ephemeral=True
        )

    @app_commands.command(name="kudos", description="Small +1 (default) and log it.")
    @app_commands.describe(user="User to kudos", reason="Quick reason")
    async def kudos_cmd(interaction: discord.Interaction, user: discord.Member, reason: str):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("Not for bots.", ephemeral=True)

        current = _get_or_create_karma(interaction.guild.id, user.id)
        new_val = current + KARMA_KUDOS
        _set_karma(interaction.guild.id, user.id, new_val)

        case_id = _insert_case(interaction.guild.id, user.id, interaction.user.id, "KUDOS", KARMA_KUDOS, reason)
        await _enforce_debate_access(user, new_val)

        embed = discord.Embed(
            title=f"Case #{case_id} | KUDOS",
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="Moderator", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Delta", value=f"+{KARMA_KUDOS}", inline=True)
        embed.add_field(name="New karma", value=str(new_val), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        await _send_modlog(interaction.guild, embed)
        await interaction.response.send_message(
            f"OK. Kudos to {user.mention}. Case #{case_id}. New karma: {new_val}.",
            ephemeral=True
        )

    @app_commands.command(name="history", description="Show last 10 karma actions (mods only).")
    @app_commands.describe(user="User to view")
    async def history_cmd(interaction: discord.Interaction, user: discord.Member):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)

        rows = _fetch_history(interaction.guild.id, user.id, limit=10)
        if not rows:
            return await interaction.response.send_message("No history for that user yet.", ephemeral=True)

        lines = []
        for case_id, action, delta, reason, mod_id, created_at in rows:
            sign = "+" if int(delta) > 0 else ""
            short_reason = (reason[:80] + "...") if len(reason) > 80 else reason
            lines.append(f"#{case_id} {action} {sign}{delta} - {short_reason} (by <@{mod_id}> - {created_at})")

        embed = discord.Embed(title=f"History: {user}", description="\n".join(lines), color=discord.Color.dark_gray())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="case", description="View a case by ID (mods only).")
    @app_commands.describe(case_id="Case number")
    async def case_cmd(interaction: discord.Interaction, case_id: int):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _is_mod(interaction.user):
            return await interaction.response.send_message("Mods only.", ephemeral=True)

        row = _fetch_case(interaction.guild.id, case_id)
        if not row:
            return await interaction.response.send_message("Case not found.", ephemeral=True)

        case_id, user_id, mod_id, action, delta, reason, created_at = row
        embed = discord.Embed(title=f"Case #{case_id}", color=discord.Color.dark_teal())
        embed.add_field(name="Action", value=str(action), inline=True)
        embed.add_field(name="Delta", value=str(delta), inline=True)
        embed.add_field(name="User", value=f"<@{user_id}> ({user_id})", inline=False)
        embed.add_field(name="Moderator", value=f"<@{mod_id}> ({mod_id})", inline=False)
        embed.add_field(name="Reason", value=str(reason), inline=False)
        embed.set_footer(text=str(created_at))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setkarma", description="Set a user's karma to an exact value (admin only).")
    @app_commands.describe(user="User to set karma for", amount="New karma value", reason="Reason for the change")
    async def setkarma_cmd(interaction: discord.Interaction, user: discord.Member, amount: int, reason: str):
        if interaction.guild is None:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Admins only.", ephemeral=True)

        if user.bot:
            return await interaction.response.send_message("Not for bots.", ephemeral=True)

        if amount < -100000 or amount > 100000:
            return await interaction.response.send_message("Amount is out of allowed range.", ephemeral=True)

        old_val = _get_or_create_karma(interaction.guild.id, user.id)
        _set_karma(interaction.guild.id, user.id, amount)

        delta = amount - old_val
        case_id = _insert_case(interaction.guild.id, user.id, interaction.user.id, "SETKARMA", delta, reason)

        await _enforce_debate_access(user, amount)

        embed = discord.Embed(
            title=f"Case #{case_id} | SETKARMA",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
        embed.add_field(name="Administrator", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Old karma", value=str(old_val), inline=True)
        embed.add_field(name="New karma", value=str(amount), inline=True)
        embed.add_field(name="Delta", value=f"{delta:+d}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        await _send_modlog(interaction.guild, embed)

        await interaction.response.send_message(
            f"OK. Set {user.mention}'s karma from {old_val} to {amount} (delta {delta:+d}). Case #{case_id}.",
            ephemeral=True
        )

    bot.tree.add_command(karma_cmd)
    bot.tree.add_command(sync_cmd)
    bot.tree.add_command(warn_cmd)
    bot.tree.add_command(praise_cmd)
    bot.tree.add_command(kudos_cmd)
    bot.tree.add_command(history_cmd)
    bot.tree.add_command(case_cmd)
    bot.tree.add_command(setkarma_cmd)


# -------------------------
# OPTIONAL PROFANITY SCAN (simple)
# -------------------------
@bot.event
async def on_message(message: discord.Message):
    # Let slash commands / interactions work normally
    await bot.process_commands(message)

    if not ENABLE_PROFANITY_SCAN:
        return
    if message.guild is None:
        return
    if message.author.bot:
        return
    if not PROFANITY_WORDS:
        return

    content = (message.content or "").lower()
    if any(w in content for w in PROFANITY_WORDS):
        embed = discord.Embed(title="Profanity detected", color=discord.Color.gold())
        embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        embed.add_field(
            name="Message",
            value=(message.content[:900] + "...") if len(message.content) > 900 else message.content,
            inline=False
        )
        await _send_modlog(message.guild, embed)


@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(RulesVerifyView())
    for idx, page in enumerate(SELF_ROLE_PAGES, start=1):
        bot.add_view(SelfRolesView(idx, page))

    print(f"Logged in as: {bot.user} (id={bot.user.id})")
    print(f"Connected guilds: {[f'{g.name}({g.id})' for g in bot.guilds]}")

    # Leave other servers if restricted
    if ALLOWED_GUILD_ID:
        for g in list(bot.guilds):
            if g.id != ALLOWED_GUILD_ID:
                print(f"Leaving unauthorized server: {g.name} ({g.id})")
                await g.leave()

    allowed_ok = (not ALLOWED_GUILD_ID) or any(g.id == ALLOWED_GUILD_ID for g in bot.guilds)
    if not allowed_ok:
        print("Not in allowed guild yet; skipping panel post and command sync.")
        return

    await ensure_ticket_panel()
    await ensure_rules_panel()
    await ensure_roles_panels()

    if ENABLE_KARMA:
        _register_karma_commands_once()

    try:
        if ALLOWED_GUILD_ID:
            guild_obj = discord.Object(id=ALLOWED_GUILD_ID)
            bot.tree.copy_global_to(guild=guild_obj)
            await bot.tree.sync(guild=guild_obj)
            print(f"Slash commands synced to guild {ALLOWED_GUILD_ID}.")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally.")
    except Exception as e:
        print(f"ERROR syncing slash commands: {repr(e)}")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Put it in /opt/ticketbot/.env")

if PANEL_CHANNEL_ID == 0 or TICKET_CATEGORY_ID == 0 or SUPPORT_ROLE_ID == 0:
    raise RuntimeError("Missing IDs in .env. Check PANEL_CHANNEL_ID / TICKET_CATEGORY_ID / SUPPORT_ROLE_ID")

if RULES_CHANNEL_ID == 0 or ROLES_CHANNEL_ID == 0 or VERIFIED_ROLE_ID == 0:
    raise RuntimeError("Missing IDs in .env. Check RULES_CHANNEL_ID / ROLES_CHANNEL_ID / VERIFIED_ROLE_ID")

if ENABLE_KARMA and (MOD_LOG_CHANNEL_ID == 0 or DEBATE_ROLE_ID == 0):
    raise RuntimeError("Karma enabled but missing MOD_LOG_CHANNEL_ID or DEBATE_ROLE_ID in .env")

bot.run(TOKEN)