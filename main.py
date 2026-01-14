import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPPORT_INVITE = os.getenv("SUPPORT_INVITE", "https://discord.gg/EzE7W8TJJP")

# لو بدك تفعيل أوامر ! (اختياري)
ENABLE_PREFIX_COMMANDS = os.getenv("ENABLE_PREFIX_COMMANDS", "0") == "1"

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
if ENABLE_PREFIX_COMMANDS:
    intents.message_content = True  # لازم تفعّله من Developer Portal كمان

bot = commands.Bot(command_prefix="!", intents=intents)

# ========= Quran helpers =========
API_BASE = "https://api.alquran.cloud/v1"

# اختيار قارئ (EveryAyah dataset folder)
RECITER_FOLDER = os.getenv("RECITER_FOLDER", "Alafasy_128kbps")

# FFmpeg reconnect options (مهمة للروابط)
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"

session: aiohttp.ClientSession | None = None
surah_meta_cache = {}  # surah_number -> {"numberOfAyahs": int, "englishName": str, ...}

def ayah_id_6digits(surah: int, ayah: int) -> str:
    # 1:1 -> 001001
    return f"{surah:03d}{ayah:03d}"

def everyayah_url(surah: int, ayah: int) -> str:
    return f"https://everyayah.com/data/{RECITER_FOLDER}/{ayah_id_6digits(surah, ayah)}.mp3"

async def fetch_json(url: str):
    global session
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    async with session.get(url) as r:
        r.raise_for_status()
        return await r.json()

async def get_surah_meta(surah: int):
    if surah in surah_meta_cache:
        return surah_meta_cache[surah]
    data = await fetch_json(f"{API_BASE}/surah/{surah}")
    meta = data["data"]
    surah_meta_cache[surah] = meta
    return meta

async def get_ayah_text(surah: int, ayah: int) -> str:
    # نص عثماني
    data = await fetch_json(f"{API_BASE}/ayah/{surah}:{ayah}/quran-uthmani")
    return data["data"]["text"]

# ========= Voice queue per guild =========
class GuildPlayer:
    def __init__(self):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.now_playing: str | None = None
        self.lock = asyncio.Lock()

guild_players: dict[int, GuildPlayer] = {}

def get_player(guild_id: int) -> GuildPlayer:
    if guild_id not in guild_players:
        guild_players[guild_id] = GuildPlayer()
    return guild_players[guild_id]

async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient | None:
    if not interaction.guild:
        return None
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        return None

    member: discord.Member = interaction.user
    if not member.voice or not member.voice.channel:
        await interaction.followup.send("لازم تكون داخل روم صوتي أولاً 🎧", ephemeral=True)
        return None

    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        # لو البوت بروم ثاني، انقله
        if vc.channel != member.voice.channel:
            await vc.move_to(member.voice.channel)
        return vc

    return await member.voice.channel.connect()

async def play_loop(guild: discord.Guild):
    """
    Loop يشتغل مرة واحدة لكل سيرفر.
    """
    player = get_player(guild.id)

    async with player.lock:
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        while True:
            url = await player.queue.get()
            player.now_playing = url

            done = asyncio.Event()

            def _after(err: Exception | None):
                done.set()

            source = discord.FFmpegPCMAudio(
                url,
                before_options=FFMPEG_BEFORE,
                options=FFMPEG_OPTS
            )
            vc.play(source, after=_after)
            await done.wait()

            # إذا خلصت الطابور، اطلع من الروم
            if player.queue.empty():
                await asyncio.sleep(2)
                if guild.voice_client and guild.voice_client.is_connected():
                    try:
                        await guild.voice_client.disconnect()
                    except:
                        pass
                player.now_playing = None
                break

# ========= Slash Commands =========
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    try:
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            g = discord.Object(id=int(guild_id))
            await bot.tree.sync(guild=g)
            print("Synced commands to one guild.")
        else:
            await bot.tree.sync()
            print("Synced global commands.")
    except Exception as e:
        print("Sync error:", e)

@bot.tree.command(name="help", description="شرح أوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 أوامر بوت القرآن", description="أهم الأوامر:", color=0x2ecc71)
    embed.add_field(name="/join", value="يدخل البوت للروم الصوتي اللي انت فيه", inline=False)
    embed.add_field(name="/play_surah", value="يشغل سورة كاملة (بشكل آيات متتالية)", inline=False)
    embed.add_field(name="/play_ayah", value="يشغل آية محددة", inline=False)
    embed.add_field(name="/ayah", value="يعرض نص آية (وممكن تشغلها)", inline=False)
    embed.add_field(name="/stop", value="يوقف التشغيل ويفضي الطابور", inline=False)
    embed.add_field(name="/support", value="سيرفر الدعم", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="support", description="رابط سيرفر الدعم")
async def support_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"سيرفر الدعم: {SUPPORT_INVITE}", ephemeral=True)

@bot.tree.command(name="join", description="يدخل رومك الصوتي")
async def join_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    vc = await ensure_voice(interaction)
    if vc:
        await interaction.followup.send("تمام دخلت للروم 🎧", ephemeral=True)

@bot.tree.command(name="stop", description="إيقاف التشغيل وتفريغ الطابور")
async def stop_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("هذا الأمر داخل السيرفر فقط.", ephemeral=True)

    player = get_player(interaction.guild.id)
    while not player.queue.empty():
        try:
            player.queue.get_nowait()
        except:
            break
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.followup.send("تم الإيقاف ✅", ephemeral=True)

@bot.tree.command(name="ayah", description="يعرض نص آية")
@app_commands.describe(surah="رقم السورة 1-114", ayah="رقم الآية")
async def ayah_cmd(interaction: discord.Interaction, surah: int, ayah: int):
    await interaction.response.defer(ephemeral=False)
    if surah < 1 or surah > 114:
        return await interaction.followup.send("رقم السورة لازم بين 1 و 114.")
    meta = await get_surah_meta(surah)
    if ayah < 1 or ayah > int(meta["numberOfAyahs"]):
        return await interaction.followup.send(f"هالسورة فيها {meta['numberOfAyahs']} آية فقط.")

    text = await get_ayah_text(surah, ayah)
    await interaction.followup.send(f"**{surah}:{ayah}**\n{text}")

@bot.tree.command(name="play_ayah", description="يشغل آية محددة بالروم الصوتي")
@app_commands.describe(surah="رقم السورة 1-114", ayah="رقم الآية")
async def play_ayah_cmd(interaction: discord.Interaction, surah: int, ayah: int):
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("هذا الأمر داخل السيرفر فقط.", ephemeral=True)

    vc = await ensure_voice(interaction)
    if not vc:
        return

    meta = await get_surah_meta(surah)
    if ayah < 1 or ayah > int(meta["numberOfAyahs"]):
        return await interaction.followup.send(f"هالسورة فيها {meta['numberOfAyahs']} آية فقط.", ephemeral=True)

    player = get_player(interaction.guild.id)
    url = everyayah_url(surah, ayah)
    await player.queue.put(url)

    await interaction.followup.send(f"✅ انضافت للطابور: سورة {surah} آية {ayah}", ephemeral=True)

    # شغل loop إذا مو شغال
    if not vc.is_playing():
        bot.loop.create_task(play_loop(interaction.guild))

@bot.tree.command(name="play_surah", description="يشغل سورة كاملة (آيات متتالية) بالروم الصوتي")
@app_commands.describe(surah="رقم السورة 1-114")
async def play_surah_cmd(interaction: discord.Interaction, surah: int):
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("هذا الأمر داخل السيرفر فقط.", ephemeral=True)

    if surah < 1 or surah > 114:
        return await interaction.followup.send("رقم السورة لازم بين 1 و 114.", ephemeral=True)

    vc = await ensure_voice(interaction)
    if not vc:
        return

    meta = await get_surah_meta(surah)
    count = int(meta["numberOfAyahs"])

    player = get_player(interaction.guild.id)
    for a in range(1, count + 1):
        await player.queue.put(everyayah_url(surah, a))

    await interaction.followup.send(f"✅ تم إضافة سورة {surah} كاملة للطابور ({count} آية).", ephemeral=True)

    if not vc.is_playing():
        bot.loop.create_task(play_loop(interaction.guild))

# ========= Optional Prefix Commands =========
if ENABLE_PREFIX_COMMANDS:
    @bot.command(name="playall")
    async def playall_prefix(ctx: commands.Context, surah: int):
        # مثل /play_surah
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("ادخل روم صوتي أولاً 🎧")

        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            vc = await ctx.author.voice.channel.connect()
        elif vc.channel != ctx.author.voice.channel:
            await vc.move_to(ctx.author.voice.channel)

        meta = await get_surah_meta(surah)
        count = int(meta["numberOfAyahs"])
        player = get_player(ctx.guild.id)
        for a in range(1, count + 1):
            await player.queue.put(everyayah_url(surah, a))
        await ctx.send(f"✅ أضفت سورة {surah} كاملة ({count} آية).")
        if not vc.is_playing():
            bot.loop.create_task(play_loop(ctx.guild))

@bot.event
async def on_close():
    global session
    if session:
        await session.close()

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

bot.run(DISCORD_TOKEN)

