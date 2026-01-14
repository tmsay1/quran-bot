import os
import re
import asyncio
import shutil
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp

# =========================
# التوكن (لا تحطه بالكود نهائياً)
# Railway Variables: DISCORD_TOKEN
# =========================
load_dotenv()
TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Set it in Railway Variables.")

PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"
SYNC_GUILD_ID = (os.getenv("SYNC_GUILD_ID") or "").strip()  # اختياري لتظهر السلاش بسرعة داخل سيرفرك

# =========================
# إعدادات التشغيل التلقائي
# =========================
AUTO_REFILL_DEFAULT_LIST = True
SHUFFLE_ON_REFILL = False
AUTO_JOIN_VOICE_CHANNEL_ID = os.getenv("AUTO_JOIN_VOICE_CHANNEL_ID")  # رقم روم الصوت (اختياري)
AUTO_PLAY_ON_READY = (os.getenv("AUTO_PLAY_ON_READY") or "0").strip() == "1"

# =========================
# روابط/بحث يوتيوب (موسّعة 60+)
# ملاحظة: استخدمت ytsearch1: حتى دائماً يجيب من يوتيوب بدون ما نمسك IDs ممكن تتغير
# =========================
DEFAULT_SONG_URLS = [
    # روابطك الأصلية
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

    # +50 بحث يوتيوب (سور + أجزاء)
    "ytsearch1:جزء عم كامل مشاري العفاسي",
    "ytsearch1:جزء تبارك كامل مشاري العفاسي",
    "ytsearch1:سورة الفاتحة مشاري العفاسي",
    "ytsearch1:سورة البقرة مشاري العفاسي كاملة",
    "ytsearch1:سورة آل عمران مشاري العفاسي كاملة",
    "ytsearch1:سورة النساء مشاري العفاسي كاملة",
    "ytsearch1:سورة المائدة مشاري العفاسي كاملة",
    "ytsearch1:سورة الأنعام مشاري العفاسي كاملة",
    "ytsearch1:سورة الأعراف مشاري العفاسي كاملة",
    "ytsearch1:سورة يونس مشاري العفاسي كاملة",
    "ytsearch1:سورة هود مشاري العفاسي كاملة",
    "ytsearch1:سورة يوسف مشاري العفاسي كاملة",
    "ytsearch1:سورة الإسراء مشاري العفاسي كاملة",
    "ytsearch1:سورة الكهف مشاري العفاسي كاملة",
    "ytsearch1:سورة مريم مشاري العفاسي كاملة",
    "ytsearch1:سورة طه مشاري العفاسي كاملة",
    "ytsearch1:سورة الأنبياء مشاري العفاسي كاملة",
    "ytsearch1:سورة المؤمنون مشاري العفاسي كاملة",
    "ytsearch1:سورة النور مشاري العفاسي كاملة",
    "ytsearch1:سورة الفرقان مشاري العفاسي كاملة",
    "ytsearch1:سورة يس مشاري العفاسي",
    "ytsearch1:سورة الصافات مشاري العفاسي",
    "ytsearch1:سورة الزمر مشاري العفاسي",
    "ytsearch1:سورة غافر مشاري العفاسي",
    "ytsearch1:سورة فصلت مشاري العفاسي",
    "ytsearch1:سورة الدخان مشاري العفاسي",
    "ytsearch1:سورة الفتح مشاري العفاسي",
    "ytsearch1:سورة قاف مشاري العفاسي",
    "ytsearch1:سورة الذاريات مشاري العفاسي",
    "ytsearch1:سورة الطور مشاري العفاسي",
    "ytsearch1:سورة النجم مشاري العفاسي",
    "ytsearch1:سورة القمر مشاري العفاسي",
    "ytsearch1:سورة الرحمن مشاري العفاسي",
    "ytsearch1:سورة الواقعة مشاري العفاسي",
    "ytsearch1:سورة الحديد مشاري العفاسي",
    "ytsearch1:سورة الحشر مشاري العفاسي",
    "ytsearch1:سورة الجمعة مشاري العفاسي",
    "ytsearch1:سورة المنافقون مشاري العفاسي",
    "ytsearch1:سورة التغابن مشاري العفاسي",
    "ytsearch1:سورة الطلاق مشاري العفاسي",
    "ytsearch1:سورة التحريم مشاري العفاسي",
    "ytsearch1:سورة الملك مشاري العفاسي",
    "ytsearch1:سورة القلم مشاري العفاسي",
    "ytsearch1:سورة الحاقة مشاري العفاسي",
    "ytsearch1:سورة المعارج مشاري العفاسي",
    "ytsearch1:سورة نوح مشاري العفاسي",
    "ytsearch1:سورة الجن مشاري العفاسي",
    "ytsearch1:سورة المزمل مشاري العفاسي",
    "ytsearch1:سورة المدثر مشاري العفاسي",
    "ytsearch1:سورة القيامة مشاري العفاسي",
    "ytsearch1:سورة الإنسان مشاري العفاسي",
    "ytsearch1:سورة المرسلات مشاري العفاسي",
    "ytsearch1:سورة النبأ مشاري العفاسي",
    "ytsearch1:سورة النازعات مشاري العفاسي",
    "ytsearch1:سورة عبس مشاري العفاسي",
    "ytsearch1:سورة التكوير مشاري العفاسي",
    "ytsearch1:سورة الانفطار مشاري العفاسي",
    "ytsearch1:سورة المطففين مشاري العفاسي",
    "ytsearch1:سورة الانشقاق مشاري العفاسي",
    "ytsearch1:سورة البروج مشاري العفاسي",
    "ytsearch1:سورة الطارق مشاري العفاسي",
    "ytsearch1:سورة الأعلى مشاري العفاسي",
    "ytsearch1:سورة الغاشية مشاري العفاسي",
    "ytsearch1:سورة الفجر مشاري العفاسي",
    "ytsearch1:سورة البلد مشاري العفاسي",
    "ytsearch1:سورة الشمس مشاري العفاسي",
    "ytsearch1:سورة الليل مشاري العفاسي",
    "ytsearch1:سورة الضحى مشاري العفاسي",
    "ytsearch1:سورة الشرح مشاري العفاسي",
    "ytsearch1:سورة التين مشاري العفاسي",
    "ytsearch1:سورة العلق مشاري العفاسي",
    "ytsearch1:سورة القدر مشاري العفاسي",
    "ytsearch1:سورة البينة مشاري العفاسي",
    "ytsearch1:سورة الزلزلة مشاري العفاسي",
    "ytsearch1:سورة العاديات مشاري العفاسي",
    "ytsearch1:سورة القارعة مشاري العفاسي",
    "ytsearch1:سورة التكاثر مشاري العفاسي",
    "ytsearch1:سورة العصر مشاري العفاسي",
    "ytsearch1:سورة الهمزة مشاري العفاسي",
    "ytsearch1:سورة الفيل مشاري العفاسي",
    "ytsearch1:سورة قريش مشاري العفاسي",
    "ytsearch1:سورة الماعون مشاري العفاسي",
    "ytsearch1:سورة الكوثر مشاري العفاسي",
    "ytsearch1:سورة الكافرون مشاري العفاسي",
    "ytsearch1:سورة النصر مشاري العفاسي",
    "ytsearch1:سورة المسد مشاري العفاسي",
    "ytsearch1:سورة الإخلاص مشاري العفاسي",
    "ytsearch1:سورة الفلق مشاري العفاسي",
    "ytsearch1:سورة الناس مشاري العفاسي",
]

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

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
    requester: Optional[discord.Member] = None

# =========================
# مشغل لكل سيرفر
# =========================
class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue: asyncio.Queue[Tuple[Track, discord.TextChannel]] = asyncio.Queue()
        self.next_event = asyncio.Event()
        self.current: Optional[Track] = None
        self.volume = 0.6
        self.autorefill = AUTO_REFILL_DEFAULT_LIST
        self.task = asyncio.create_task(self.player_loop())

    async def refill_defaults(self, channel: discord.TextChannel):
        urls = list(DEFAULT_SONG_URLS)
        if SHUFFLE_ON_REFILL:
            random.shuffle(urls)
        for u in urls:
            await self.queue.put((Track(url=u), channel))

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

            if self.queue.empty() and self.autorefill:
                await asyncio.sleep(0.5)

            try:
                track, channel = await self.queue.get()
            except Exception:
                continue

            self.current = track
            vc = self.guild.voice_client

            if vc is None or not vc.is_connected():
                self.current = None
                continue

            try:
                source = await self.create_source(track)
            except Exception as e:
                await channel.send(f"⚠️ ما قدرت أشغل، رح أتجاوز.\nسبب: `{type(e).__name__}: {e}`")
                self.current = None
                if self.queue.empty() and self.autorefill:
                    await self.refill_defaults(channel)
                    await channel.send("🔁 خلصت/صار خطأ… عبّيت القائمة من جديد وكملت.")
                continue

            def _after(err: Optional[Exception]):
                if err:
                    print(f"[AFTER ERROR] {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            vc.play(source, after=_after)
            await channel.send(f"▶️ **Now Playing:** {track.title}")
            await self.next_event.wait()
            self.current = None

            if self.queue.empty() and self.autorefill:
                await self.refill_defaults(channel)
                await channel.send("🔁 خلصت القائمة… عبّيتها من جديد وكملت.")

    async def create_source(self, track: Track) -> discord.PCMVolumeTransformer:
        loop = asyncio.get_running_loop()

        def _extract():
            with make_ytdl() as ydl:
                return ydl.extract_info(track.url, download=False)

        info = await loop.run_in_executor(None, _extract)
        if not info:
            raise RuntimeError("فشل استخراج معلومات من yt-dlp.")

        if "entries" in info and info["entries"]:
            entry = next((e for e in info["entries"] if e), None)
            if not entry:
                raise RuntimeError("ما لقيت نتيجة صالحة.")
            vid_url = entry.get("webpage_url") or entry.get("url")
            if not vid_url:
                vid = entry.get("id")
                if not vid:
                    raise RuntimeError("نتيجة بدون رابط.")
                vid_url = f"https://www.youtube.com/watch?v={vid}"
            track.url = vid_url
            track.title = entry.get("title") or track.title
            return await self.create_source(track)

        track.title = info.get("title") or track.title
        stream_url = info.get("url")
        if not stream_url and info.get("requested_formats"):
            stream_url = info["requested_formats"][0].get("url")
        if not stream_url:
            raise RuntimeError("ما حصلت رابط ستريم صالح.")

        audio = discord.FFmpegPCMAudio(stream_url, before_options=FFMPEG_BEFORE, options=FFMPEG_OPTS)
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
intents.message_content = True  # لحتى !playall يشتغل لازم تفعّل Message Content Intent بالـ Developer Portal

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
_synced = False

async def ensure_voice_ctx(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("لازم تكون داخل روم صوت أولاً.")
    vc = ctx.guild.voice_client
    if vc and vc.is_connected():
        return vc
    return await ctx.author.voice.channel.connect()

async def ensure_voice_interaction(inter: discord.Interaction) -> discord.VoiceClient:
    user = inter.user
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        raise app_commands.AppCommandError("لازم تكون داخل روم صوت أولاً.")
    vc = inter.guild.voice_client if inter.guild else None
    if vc and vc.is_connected():
        return vc
    return await user.voice.channel.connect()

@bot.event
async def on_ready():
    global _synced
    print(f"[READY] {bot.user} is online.")

    # حالة البوت حتى الناس تعرف
    try:
        await bot.change_presence(activity=discord.Game(name="!playall أو /playall"))
    except Exception:
        pass

    if not _synced:
        try:
            if SYNC_GUILD_ID.isdigit():
                g = discord.Object(id=int(SYNC_GUILD_ID))
                await bot.tree.sync(guild=g)
                print(f"[SYNC] Slash commands synced to guild {SYNC_GUILD_ID} (سريع).")
            else:
                await bot.tree.sync()
                print("[SYNC] Slash commands synced globally (قد تأخذ وقت بالظهور).")
        except Exception as e:
            print(f"[SYNC ERROR] {e}")
        _synced = True

    # Auto join/play (اختياري)
    if AUTO_JOIN_VOICE_CHANNEL_ID and AUTO_JOIN_VOICE_CHANNEL_ID.isdigit():
        vc_id = int(AUTO_JOIN_VOICE_CHANNEL_ID)
        for g in bot.guilds:
            ch = g.get_channel(vc_id)
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await ch.connect()
                    print(f"[AUTO] joined voice channel: {ch.name} in {g.name}")
                    if AUTO_PLAY_ON_READY:
                        # بدنا روم نصي للإشعارات، خليه أول روم متاح
                        txt = next((c for c in g.text_channels if c.permissions_for(g.me).send_messages), None)
                        if txt:
                            player = get_player(bot, g)
                            await player.refill_defaults(txt)
                            await txt.send("✅ Auto: شغّلت القائمة تلقائياً. اكتب /playall أو !playall لإعادة التحميل.")
                except Exception as e:
                    print(f"[AUTO] failed to join/play: {e}")

# =========================
# Prefix Commands ( ! )
# =========================
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
    if not URL_RE.match(q) and not q.lower().startswith("ytsearch"):
        q = f"ytsearch1:{q}"

    await player.queue.put((Track(url=q, requester=ctx.author), ctx.channel))
    await ctx.reply(f"✅ انضافت للطابور. (المتبقي: **{player.queue.qsize()}**)")

@bot.command()
async def playall(ctx: commands.Context):
    await ensure_voice_ctx(ctx)
    player = get_player(bot, ctx.guild)

    await player.refill_defaults(ctx.channel)
    await ctx.reply(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** عنصر للطابور. رح يكمل تلقائيًا 🔁")

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
        await ctx.reply("استخدم: `!auto on` أو `!auto off`")

# =========================
# Slash Commands ( / ) <-- هي اللي بتظهر بواجهة البوت كأزرار
# =========================
@bot.tree.command(name="playall", description="تحميل قائمة القرآن الافتراضية وتشغيلها تلقائياً")
async def slash_playall(interaction: discord.Interaction):
    await ensure_voice_interaction(interaction)
    player = get_player(bot, interaction.guild)

    # نحتاج قناة نصية للرسائل
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ استعمل الأمر داخل روم نصي.", ephemeral=True)
        return

    await player.refill_defaults(channel)
    await interaction.response.send_message(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** عنصر للطابور. 🔁")

@bot.tree.command(name="join", description="يدخل البوت لرومك الصوتي")
async def slash_join(interaction: discord.Interaction):
    vc = await ensure_voice_interaction(interaction)
    await interaction.response.send_message(f"✅ دخلت: **{vc.channel}**")

@bot.tree.command(name="leave", description="يطلع البوت من الروم الصوتي")
async def slash_leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.is_connected():
        await vc.disconnect()
        await interaction.response.send_message("👋 طلعت من الروم.")
    else:
        await interaction.response.send_message("أنا أصلاً مو داخل روم.")

@bot.tree.command(name="now", description="يعرض ايش شغال الآن")
async def slash_now(interaction: discord.Interaction):
    player = get_player(bot, interaction.guild)
    if player.current:
        await interaction.response.send_message(f"🎶 الآن: **{player.current.title}**")
    else:
        await interaction.response.send_message("ما في شي شغال حالياً.")

@bot.tree.command(name="help", description="شرح سريع للأوامر")
async def slash_help(interaction: discord.Interaction):
    msg = (
        "**أوامر التشغيل:**\n"
        f"- `{PREFIX}playall` أو `/playall` لتشغيل قائمة القرآن 24/7\n"
        f"- `{PREFIX}join` أو `/join` دخول الروم\n"
        f"- `{PREFIX}leave` أو `/leave` خروج\n"
        f"- `{PREFIX}skip` لتخطي\n"
        f"- `{PREFIX}now` أو `/now` الآن\n"
    )
    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# تشغيل
# =========================
bot.run(TOKEN)

