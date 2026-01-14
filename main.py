import os
import re
import json
import asyncio
import shutil
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp

# =========================
# إعدادات عامة (ENV)
# =========================
load_dotenv()

DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not DISCORD_TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is missing. Set it in Railway Variables.")

PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"
ENABLE_PREFIX_COMMANDS = (os.getenv("ENABLE_PREFIX_COMMANDS") or "1").strip() == "1"

# رابط سيرفرك (اختياري يظهر بالأوامر)
SUPPORT_INVITE = (os.getenv("SUPPORT_INVITE") or "https://discord.gg/KVuBY5Zwzk").strip()

# لو تحط رقم سيرفر للتجربة السريعة للـ slash commands (اختياري)
DEV_GUILD_ID = (os.getenv("DEV_GUILD_ID") or "").strip()  # مثال: 123456789012345678

# =========================
# إعدادات التشغيل التلقائي
# =========================
AUTO_REFILL_DEFAULT_LIST = True   # إذا خلصت الروابط يعبيها من جديد ويكمل
SHUFFLE_ON_REFILL = False         # إذا True يشغل عشوائي

# =========================
# روابط القرآن (اللي بعثتها)
# =========================
DEFAULT_SONG_URLS = [
    "https://youtu.be/9k1U0aGQRNA?si=QEuagBJ4xXZc11G6",
    "https://youtu.be/nmCuMB2GQHQ?si=loMcI-MYmSxVQN2D",
    "https://youtu.be/KN8iHcilfdY?si=5ihc6sPyou3Fjb7L",
    "https://youtu.be/TCE5P-AhEck?si=q-l1a1bzhE2l6XEO",
    "https://youtu.be/HzXDdrKhvjg?si=xkSfk1Cg4NwDhML9",
    "https://youtu.be/8poX5OD2BR0?si=Vmo-5OXYYnpCrQq9",
    "https://youtu.be/JglxgL9juOA?si=kbyopoeajy8HgGt4",
    "https://www.youtube.com/live/F_BVjvBksOw?si=27A7n2W9wVWuD4bE",
    "https://youtu.be/p35TFiz_PDQ?si=OWTCmZ8Ps97tlCpV",
    "https://youtu.be/fRkVxypqpHA?si=c4E6XVbHPV0PRwk1",
]

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# =========================
# حفظ إعدادات لكل سيرفر (روم صوت/كتابة + auto)
# =========================
SETTINGS_FILE = "guild_settings.json"
_settings_lock = asyncio.Lock()

def _load_settings_sync() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

async def load_settings() -> Dict[str, Any]:
    async with _settings_lock:
        return _load_settings_sync()

async def save_settings(data: Dict[str, Any]) -> None:
    async with _settings_lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def guild_key(guild_id: int) -> str:
    return str(guild_id)

# =========================
# yt-dlp + ffmpeg
# =========================
def has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def pick_js_runtimes() -> List[str]:
    r = []
    if has_cmd("deno"):
        r.append("deno")
    if has_cmd("node"):
        r.append("node")
    return r

BASE_YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "default_search": "ytsearch",
    "noplaylist": False,
    "source_address": "0.0.0.0",
    "retries": 5,
    "fragment_retries": 5,
    "extractor_retries": 5,
    "socket_timeout": 15,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}

FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"

def make_ytdl() -> yt_dlp.YoutubeDL:
    opts = dict(BASE_YTDL_OPTS)
    runtimes = pick_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    try:
        return yt_dlp.YoutubeDL(opts)
    except Exception:
        opts.pop("js_runtimes", None)
        return yt_dlp.YoutubeDL(opts)

# =========================
# موديل التراك
# =========================
@dataclass
class Track:
    url: str
    title: str = "Unknown"
    requester_name: str = "Unknown"

# =========================
# مشغل لكل سيرفر
# =========================
class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: asyncio.Queue[Tuple[Track, int]] = asyncio.Queue()  # (track, text_channel_id)
        self.next_event = asyncio.Event()
        self.current: Optional[Track] = None
        self.volume = 0.6
        self.autorefill = AUTO_REFILL_DEFAULT_LIST
        self.last_text_channel_id: Optional[int] = None
        self.task = asyncio.create_task(self.player_loop())

    async def refill_defaults(self, text_channel_id: int):
        urls = list(DEFAULT_SONG_URLS)
        if SHUFFLE_ON_REFILL:
            random.shuffle(urls)
        for u in urls:
            await self.queue.put((Track(url=u, requester_name="auto"), text_channel_id))

    async def send(self, text_channel_id: int, msg: str):
        ch = self.guild.get_channel(text_channel_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(msg)
            except Exception:
                pass

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

            # إذا الطابور فاضي + autorefill شغال وعندنا روم كتابة معروف
            if self.queue.empty() and self.autorefill and self.last_text_channel_id:
                await self.refill_defaults(self.last_text_channel_id)
                await self.send(self.last_text_channel_id, "🔁 خلصت القائمة… عبّيتها من جديد وكملت.")

            track, text_ch_id = await self.queue.get()
            self.last_text_channel_id = text_ch_id
            self.current = track

            vc = self.guild.voice_client
            if vc is None or not vc.is_connected():
                # إذا مو داخل روم، نوقف التراك وننتظر أوامر
                self.current = None
                continue

            try:
                source = await self.create_source(track)
            except Exception as e:
                await self.send(text_ch_id, f"⚠️ ما قدرت أشغل هذا الرابط، رح أتجاوزه.\nسبب: `{type(e).__name__}: {e}`")
                self.current = None
                continue

            def _after(err: Optional[Exception]):
                if err:
                    print(f"[AFTER ERROR] {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            vc.play(source, after=_after)
            await self.send(text_ch_id, f"▶️ **Now Playing:** {track.title}")
            await self.next_event.wait()
            self.current = None

    async def create_source(self, track: Track) -> discord.PCMVolumeTransformer:
        loop = asyncio.get_running_loop()

        def _extract():
            with make_ytdl() as ydl:
                return ydl.extract_info(track.url, download=False)

        info = await loop.run_in_executor(None, _extract)
        if not info:
            raise RuntimeError("yt-dlp failed to extract info.")

        # playlist/search result
        if "entries" in info and info["entries"]:
            entry = next((e for e in info["entries"] if e), None)
            if not entry:
                raise RuntimeError("No valid entry found.")
            vid_url = entry.get("webpage_url") or entry.get("url")
            if not vid_url:
                vid = entry.get("id")
                if not vid:
                    raise RuntimeError("Entry missing URL/ID.")
                vid_url = f"https://www.youtube.com/watch?v={vid}"
            track.url = vid_url
            track.title = entry.get("title") or track.title
            return await self.create_source(track)

        track.title = info.get("title") or track.title
        stream_url = info.get("url")
        if not stream_url and info.get("requested_formats"):
            stream_url = info["requested_formats"][0].get("url")
        if not stream_url:
            raise RuntimeError("No stream URL found.")

        audio = discord.FFmpegPCMAudio(
            stream_url,
            before_options=FFMPEG_BEFORE,
            options=FFMPEG_OPTS
        )
        return discord.PCMVolumeTransformer(audio, volume=self.volume)

players: dict[int, GuildPlayer] = {}

def get_player(bot: commands.Bot, guild: discord.Guild) -> GuildPlayer:
    gp = players.get(guild.id)
    if not gp:
        gp = GuildPlayer(bot, guild)
        players[guild.id] = gp
    return gp

# =========================
# البوت + Intents
# =========================
intents = discord.Intents.default()
intents.voice_states = True
# Prefix commands تحتاج Message Content Intent
intents.message_content = ENABLE_PREFIX_COMMANDS

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

HELP_TEXT = (
    "📌 **أوامر البوت (Quran Bot):**\n"
    f"✅ `{PREFIX}playall` = تشغيل قائمة الروابط كاملة (ويكمل تلقائي)\n"
    f"✅ `{PREFIX}play <link/word>` = تشغيل رابط/بحث وإضافته للطابور\n"
    f"✅ `{PREFIX}join` / `{PREFIX}leave`\n"
    f"✅ `{PREFIX}skip` / `{PREFIX}now`\n"
    f"✅ `{PREFIX}auto on|off` = تشغيل/إيقاف إعادة التعبئة التلقائية\n"
    f"✅ `{PREFIX}setvoice` = يحفظ روم الصوت + روم الكتابة (حتى يرجع يدخل ويكمل)\n"
    "\n"
    "🎛️ **Slash Commands:** `/playall` `/play` `/join` `/leave` `/help`\n"
    f"🔗 سيرفر الدعم: {SUPPORT_INVITE}"
)

async def ensure_voice_for_member(guild: discord.Guild, member: discord.Member) -> discord.VoiceClient:
    if not member.voice or not member.voice.channel:
        raise commands.CommandError("لازم تكون داخل روم صوت أولاً.")
    vc = guild.voice_client
    if vc and vc.is_connected():
        return vc
    return await member.voice.channel.connect()

async def ensure_voice_ctx(ctx: commands.Context) -> discord.VoiceClient:
    return await ensure_voice_for_member(ctx.guild, ctx.author)

async def ensure_voice_interaction(inter: discord.Interaction) -> discord.VoiceClient:
    assert inter.guild is not None
    assert isinstance(inter.user, discord.Member)
    return await ensure_voice_for_member(inter.guild, inter.user)

# =========================
# أحداث
# =========================
@bot.event
async def on_ready():
    print(f"[READY] {bot.user} is online.")
    if not has_cmd("ffmpeg"):
        print("[WARN] ffmpeg not found (but you already installed it in Dockerfile).")
    if not pick_js_runtimes():
        print("[WARN] No Node/Deno found. (Optional)")

    # مزامنة Slash Commands
    try:
        if DEV_GUILD_ID.isdigit():
            gid = int(DEV_GUILD_ID)
            guild_obj = discord.Object(id=gid)
            synced = await bot.tree.sync(guild=guild_obj)
            print(f"[SYNC] Guild slash commands synced: {len(synced)}")
        else:
            synced = await bot.tree.sync()
            print(f"[SYNC] Global slash commands synced: {len(synced)}")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")

    # Auto connect إن كان مخزّن روم صوت لكل سيرفر
    data = await load_settings()
    for g in bot.guilds:
        gdata = data.get(guild_key(g.id), {})
        voice_id = gdata.get("voice_channel_id")
        text_id = gdata.get("text_channel_id")
        auto_on = bool(gdata.get("autorefill", AUTO_REFILL_DEFAULT_LIST))

        if voice_id and text_id:
            ch = g.get_channel(int(voice_id))
            if isinstance(ch, discord.VoiceChannel):
                try:
                    if not g.voice_client or not g.voice_client.is_connected():
                        await ch.connect()
                    player = get_player(bot, g)
                    player.autorefill = auto_on
                    player.last_text_channel_id = int(text_id)
                    # إذا بدك يبلّش تلقائي فوراً:
                    if player.queue.empty() and player.autorefill:
                        await player.refill_defaults(int(text_id))
                except Exception as e:
                    print(f"[AUTO JOIN] failed in {g.name}: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    # رسالة تعريف بسيطة بأول روم متاح
    ch = guild.system_channel
    if not isinstance(ch, discord.TextChannel):
        ch = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    if ch:
        try:
            await ch.send("👋 هلا! اكتب `/help` أو `!help` حتى تعرف الأوامر.\n" + HELP_TEXT)
        except Exception:
            pass

# =========================
# Prefix Commands (!)
# =========================
if ENABLE_PREFIX_COMMANDS:
    bot.remove_command("help")

    @bot.command(name="help")
    async def help_cmd(ctx: commands.Context):
        await ctx.reply(HELP_TEXT)

    @bot.command()
    async def join(ctx: commands.Context):
        vc = await ensure_voice_ctx(ctx)
        await ctx.reply(f"✅ دخلت: **{vc.channel}**")

    @bot.command()
    async def leave(ctx: commands.Context):
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            await ctx.reply("👋 طلعت من الروم.")
        else:
            await ctx.reply("أنا أصلاً مو داخل روم.")

    @bot.command()
    async def play(ctx: commands.Context, *, query: str):
        await ensure_voice_ctx(ctx)
        player = get_player(bot, ctx.guild)

        q = query.strip()
        if not URL_RE.match(q):
            q = f"ytsearch1:{q}"

        await player.queue.put((Track(url=q, requester_name=str(ctx.author)), ctx.channel.id))
        player.last_text_channel_id = ctx.channel.id
        await ctx.reply(f"✅ انضافت للطابور. (المتبقي: **{player.queue.qsize()}**)")

    @bot.command()
    async def playall(ctx: commands.Context):
        await ensure_voice_ctx(ctx)
        player = get_player(bot, ctx.guild)
        player.last_text_channel_id = ctx.channel.id

        await player.refill_defaults(ctx.channel.id)
        await ctx.reply(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** رابط للطابور. رح يبدّل تلقائيًا.")

    @bot.command()
    async def skip(ctx: commands.Context):
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await ctx.reply("⏭️ تم السكيب.")
        else:
            await ctx.reply("ما في شي شغال.")

    @bot.command()
    async def now(ctx: commands.Context):
        player = get_player(bot, ctx.guild)
        if player.current:
            await ctx.reply(f"🎶 الآن: **{player.current.title}**")
        else:
            await ctx.reply("ما في شي شغال حالياً.")

    @bot.command()
    async def auto(ctx: commands.Context, mode: str):
        player = get_player(bot, ctx.guild)
        mode = mode.lower().strip()
        if mode in ("on", "1", "true", "yes"):
            player.autorefill = True
            await ctx.reply("✅ Auto refill: ON")
        elif mode in ("off", "0", "false", "no"):
            player.autorefill = False
            await ctx.reply("✅ Auto refill: OFF")
        else:
            await ctx.reply(f"استخدم: `{PREFIX}auto on` أو `{PREFIX}auto off`")

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def setvoice(ctx: commands.Context):
        """يحفظ روم الصوت اللي انت داخله + روم الكتابة الحالي"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("لازم تكون داخل روم صوت أولاً.")
            return

        voice_ch = ctx.author.voice.channel
        text_ch = ctx.channel

        # اتصال الآن
        try:
            vc = ctx.guild.voice_client
            if not vc or not vc.is_connected():
                await voice_ch.connect()
        except Exception as e:
            await ctx.reply(f"ما قدرت أدخل الروم الصوتي: {e}")
            return

        data = await load_settings()
        data[guild_key(ctx.guild.id)] = {
            "voice_channel_id": voice_ch.id,
            "text_channel_id": text_ch.id,
            "autorefill": True,
        }
        await save_settings(data)

        player = get_player(bot, ctx.guild)
        player.last_text_channel_id = text_ch.id
        player.autorefill = True

        # بلّش مباشرة
        if player.queue.empty():
            await player.refill_defaults(text_ch.id)

        await ctx.reply(f"✅ تم الحفظ.\n🎙️ Voice: **{voice_ch.name}**\n💬 Text: **{text_ch.name}**\nوتم تشغيل القائمة تلقائياً.")

# =========================
# Slash Commands (/)
# =========================
@bot.tree.command(name="help", description="يعرض أوامر البوت")
async def slash_help(inter: discord.Interaction):
    await inter.response.send_message(HELP_TEXT, ephemeral=True)

@bot.tree.command(name="join", description="يدخل روم الصوت اللي انت داخله")
async def slash_join(inter: discord.Interaction):
    try:
        vc = await ensure_voice_interaction(inter)
        await inter.response.send_message(f"✅ دخلت: **{vc.channel}**", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"⚠️ {e}", ephemeral=True)

@bot.tree.command(name="leave", description="يطلع من روم الصوت")
async def slash_leave(inter: discord.Interaction):
    if not inter.guild:
        return
    vc = inter.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()
        await inter.response.send_message("👋 طلعت من الروم.", ephemeral=True)
    else:
        await inter.response.send_message("أنا أصلاً مو داخل روم.", ephemeral=True)

@bot.tree.command(name="playall", description="يشغل قائمة الروابط كاملة ويكمل تلقائياً")
async def slash_playall(inter: discord.Interaction):
    if not inter.guild or not isinstance(inter.user, discord.Member):
        return
    try:
        await ensure_voice_interaction(inter)
        player = get_player(bot, inter.guild)

        # اختار روم كتابة لإرسال Now Playing
        text_ch_id = inter.channel.id if inter.channel else None
        if not text_ch_id:
            await inter.response.send_message("ما لقيت روم كتابة مناسب.", ephemeral=True)
            return

        player.last_text_channel_id = text_ch_id
        await player.refill_defaults(text_ch_id)
        await inter.response.send_message(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** رابط للطابور.", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"⚠️ {e}", ephemeral=True)

@bot.tree.command(name="play", description="يشغل رابط أو يبحث بالكلمات (ويضيفه للطابور)")
@app_commands.describe(query="رابط يوتيوب أو كلمات بحث")
async def slash_play(inter: discord.Interaction, query: str):
    if not inter.guild or not isinstance(inter.user, discord.Member):
        return
    try:
        await ensure_voice_interaction(inter)
        player = get_player(bot, inter.guild)

        q = query.strip()
        if not URL_RE.match(q):
            q = f"ytsearch1:{q}"

        text_ch_id = inter.channel.id if inter.channel else None
        if not text_ch_id:
            await inter.response.send_message("ما لقيت روم كتابة مناسب.", ephemeral=True)
            return

        await player.queue.put((Track(url=q, requester_name=str(inter.user)), text_ch_id))
        player.last_text_channel_id = text_ch_id

        await inter.response.send_message("✅ انضاف للطابور.", ephemeral=True)
    except Exception as e:
        await inter.response.send_message(f"⚠️ {e}", ephemeral=True)

@bot.tree.command(name="setvoice", description="يحفظ روم الصوت + روم الكتابة لهذا السيرفر (Admin)")
async def slash_setvoice(inter: discord.Interaction):
    if not inter.guild or not isinstance(inter.user, discord.Member):
        return
    if not inter.user.guild_permissions.administrator:
        await inter.response.send_message("لازم صلاحية Administrator.", ephemeral=True)
        return
    if not inter.user.voice or not inter.user.voice.channel:
        await inter.response.send_message("لازم تكون داخل روم صوت أولاً.", ephemeral=True)
        return

    voice_ch = inter.user.voice.channel
    text_ch_id = inter.channel.id if inter.channel else None
    if not text_ch_id:
        await inter.response.send_message("ما لقيت روم كتابة مناسب.", ephemeral=True)
        return

    # اتصال الآن
    try:
        vc = inter.guild.voice_client
        if not vc or not vc.is_connected():
            await voice_ch.connect()
    except Exception as e:
        await inter.response.send_message(f"ما قدرت أدخل الروم الصوتي: {e}", ephemeral=True)
        return

    data = await load_settings()
    data[guild_key(inter.guild.id)] = {
        "voice_channel_id": voice_ch.id,
        "text_channel_id": text_ch_id,
        "autorefill": True,
    }
    await save_settings(data)

    player = get_player(bot, inter.guild)
    player.last_text_channel_id = text_ch_id
    player.autorefill = True
    if player.queue.empty():
        await player.refill_defaults(text_ch_id)

    await inter.response.send_message("✅ تم الحفظ وتم تشغيل القائمة.", ephemeral=True)

# =========================
# تشغيل
# =========================
bot.run(DISCORD_TOKEN)
