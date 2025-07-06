import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === CONFIGURATION ===
MEMBER_ROLE_ID = 1390601556717731840
TICKET_VIEWER_ID = 1391416643003092992
TICKET_CATEGORY_ID = 1391417657273880706
CREATE_TICKET_ALLOWED_USER_ID = 1389327871486595153
LOG_CHANNEL_ID = 1391620593383475330  # Replace with your actual logging channel ID
TICKET_TIMEOUT = 60 * 30  # 30 minutes timeout

ticket_creators = {}
ticket_last_activity = {}

# === EVENTS ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    ticket_inactivity_checker.start()

@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    role = guild.get_role(MEMBER_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="Auto role on server join")
            print(f"✅ Assigned role to {member}")
        except Exception as e:
            print(f"❌ Failed to assign role to {member.name}: {e}")

@bot.event
async def on_message(message):
    if message.channel.id in ticket_last_activity:
        ticket_last_activity[message.channel.id] = message.created_at.timestamp()
    await bot.process_commands(message)

# === COMMANDS ===

# /ticket
@bot.tree.command(name="ticket", description="Create a ticket to report a user")
@app_commands.describe(report_user="User to report", report_reason="Reason", ping_user="Ping the reported user in ticket?")
async def ticket(interaction: discord.Interaction, report_user: discord.Member, report_reason: str, ping_user: bool = False):
    guild = interaction.guild
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if not category or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("⚠️ Ticket category not found.", ephemeral=True)
        return

    # Check existing ticket
    channel_name = f"ticket-{interaction.user.id}"
    existing_channel = discord.utils.get(category.channels, name=channel_name)
    if existing_channel:
        await interaction.response.send_message(f"You already have a ticket open: {existing_channel.mention}", ephemeral=True)
        return

    # Handle viewer
    viewer = guild.get_member(TICKET_VIEWER_ID) or await guild.fetch_member(TICKET_VIEWER_ID)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        viewer: discord.PermissionOverwrite(view_channel=True)
    }

    ticket_channel = await category.create_text_channel(channel_name, overwrites=overwrites, reason="New Ticket")
    ticket_creators[ticket_channel.id] = interaction.user.id
    ticket_last_activity[ticket_channel.id] = interaction.created_at.timestamp()

    embed = discord.Embed(
        title="🎫 New Ticket",
        description=f"**Reporter:** {interaction.user.mention}\n"
                    f"**Reported User:** {report_user.mention}\n"
                    f"**Reason:** {report_reason}",
        color=discord.Color.blue()
    )

    await ticket_channel.send(content=(report_user.mention if ping_user else None), embed=embed)
    await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

# /close-ticket
@bot.tree.command(name="close-ticket", description="Close the current ticket")
async def close_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.id not in ticket_creators:
        await interaction.response.send_message("⚠️ This is not a ticket channel.", ephemeral=True)
        return

    # DM user
    user_id = ticket_creators[channel.id]
    user = await bot.fetch_user(user_id)
    try:
        await user.send(f"Your ticket **{channel.name}** was closed by {interaction.user.mention}.")
    except:
        pass

    # Transcript logging
    try:
        messages = [f"{m.author}: {m.content}" async for m in channel.history(limit=100, oldest_first=True)]
        transcript = "\n".join(messages)
        log_channel = channel.guild.get_channel(LOG_CHANNEL_ID)
        await log_channel.send(f"📄 Transcript of `{channel.name}`:\n```{transcript[:1900]}```")
    except Exception as e:
        print(f"⚠️ Error logging transcript: {e}")

    await interaction.response.send_message("✅ Ticket closed. Deleting channel...", ephemeral=True)
    await asyncio.sleep(3)
    await channel.delete()
    ticket_creators.pop(channel.id, None)
    ticket_last_activity.pop(channel.id, None)

# /create-ticket (staff only)
@bot.tree.command(name="create-ticket", description="Create a staff-initiated ticket")
@app_commands.describe(user="User to mention (optional)", reason="Reason for ticket (optional)")
async def create_ticket(interaction: discord.Interaction, user: discord.Member = None, reason: str = None):
    if interaction.user.id != CREATE_TICKET_ALLOWED_USER_ID:
        await interaction.response.send_message("⚠️ You are not allowed to use this command.", ephemeral=True)
        return

    guild = interaction.guild
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if not category or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message("⚠️ Ticket category not found.", ephemeral=True)
        return

    viewer = guild.get_member(TICKET_VIEWER_ID) or await guild.fetch_member(TICKET_VIEWER_ID)

    channel_name = f"ticket-{interaction.user.id}"
    existing_channel = discord.utils.get(category.channels, name=channel_name)
    if existing_channel:
        await interaction.response.send_message(f"Ticket already exists: {existing_channel.mention}", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
        viewer: discord.PermissionOverwrite(view_channel=True)
    }

    ticket_channel = await category.create_text_channel(channel_name, overwrites=overwrites, reason="Staff Ticket")
    ticket_creators[ticket_channel.id] = interaction.user.id
    ticket_last_activity[ticket_channel.id] = interaction.created_at.timestamp()

    desc = f"**Created by:** {interaction.user.mention}\n"
    if user:
        desc += f"**Related User:** {user.mention}\n"
    if reason:
        desc += f"**Reason:** {reason}"

    embed = discord.Embed(title="🛠️ Staff Ticket", description=desc, color=discord.Color.orange())
    await ticket_channel.send(embed=embed)
    await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

# === BACKGROUND TASKS ===
@tasks.loop(minutes=5)
async def ticket_inactivity_checker():
    now = asyncio.get_event_loop().time()
    for channel_id, last_time in list(ticket_last_activity.items()):
        if now - last_time > TICKET_TIMEOUT:
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send("⏳ This ticket has been inactive for 30 minutes and will now close.")
                    await asyncio.sleep(3)
                    await channel.delete()
                except Exception as e:
                    print(f"Failed to close inactive ticket: {e}")
            ticket_creators.pop(channel_id, None)
            ticket_last_activity.pop(channel_id, None)

# === RUN ===
bot.run("MTM5MDU5OTk2NjIzNzY1NTA5Mg.GWVIil.z5tmiiaVuomE75LQWQWhHlA6twcIzAWJRVJ1xI")
