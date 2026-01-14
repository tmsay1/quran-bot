import os
import re
import asyncio
import shutil
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple

import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

# =========================
# ضع التوكن هنا (لا تنشره)
# =========================
BOT_TOKEN = "" 

# (اختياري وأفضل): تقدر تحط التوكن بملف .env بدل الكود
# DISCORD_TOKEN=xxxxx
load_dotenv()
TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Set it in environment variables.")


PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"

# =========================
# إعدادات التشغيل التلقائي
# =========================
AUTO_REFILL_DEFAULT_LIST = True   # إذا خلصت الأغاني يعبيها من جديد ويكمل
SHUFFLE_ON_REFILL = False         # إذا True بيشغلهم عشوائي
# لتشغيل تلقائي عند الإقلاع (اختياري): حط رقم روم الصوت
AUTO_JOIN_VOICE_CHANNEL_ID = None  # مثال: 123456789012345678

# =========================
# روابط الأغاني داخل الكود
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
    # يساعد مع تغييرات يوتيوب
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
        # لو نسخة yt-dlp ما تدعم js_runtimes
        opts.pop("js_runtimes", None)
        return yt_dlp.YoutubeDL(opts)

# =========================
# موديل الأغاني
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

            # إذا الطابور فضي + autorefill مفعّل => عبّي تلقائي
            if self.queue.empty() and self.autorefill:
                # حاول نلاقي آخر روم نصي للبث: إذا ما في، ما نعرف وين نرسل رسائل
                # فبنطر لين يجي أمر.
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
                # ما نوقف! نسكّب ونكمّل
                await channel.send(f"⚠️ ما قدرت أشغل هالأغنية، رح أتجاوزها وأكمل.\nسبب: `{type(e).__name__}: {e}`")
                self.current = None

                # إذا صار الطابور فاضي بعد السكيب و autorefill شغال
                if self.queue.empty() and self.autorefill:
                    await self.refill_defaults(channel)
                    await channel.send("🔁 خلصت القائمة/صار خطأ… عبّيت القائمة من جديد وكملت.")
                continue

            def _after(err: Optional[Exception]):
                if err:
                    print(f"[AFTER ERROR] {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            vc.play(source, after=_after)
            await channel.send(f"▶️ **Now Playing:** {track.title}")
            await self.next_event.wait()
            self.current = None

            # إذا خلصت الأغاني: عبّي تلقائي
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

        # لو رجع playlist/بحث
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
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("لازم تكون داخل روم صوت أولاً.")
    vc = ctx.guild.voice_client
    if vc and vc.is_connected():
        return vc
    return await ctx.author.voice.channel.connect()

@bot.event
async def on_ready():
    print(f"[READY] {bot.user} is online.")
    if not pick_js_runtimes():
        print("[WARN] ما لقيت Deno/Node. ثبت Deno لتفادي مشاكل يوتيوب الحديثة.")
    # Auto-join option (اختياري)
    if AUTO_JOIN_VOICE_CHANNEL_ID:
        for g in bot.guilds:
            ch = g.get_channel(AUTO_JOIN_VOICE_CHANNEL_ID)
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await ch.connect()
                    print(f"[AUTO] joined voice channel: {ch.name} in {g.name}")
                except Exception as e:
                    print(f"[AUTO] failed to join: {e}")

# =========================
# أوامر
# =========================
@bot.command()
async def join(ctx: commands.Context):
    vc = await ensure_voice(ctx)
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
    await ensure_voice(ctx)
    player = get_player(bot, ctx.guild)

    q = query.strip()
    if not URL_RE.match(q):
        q = f"ytsearch1:{q}"

    await player.queue.put((Track(url=q, requester=ctx.author), ctx.channel))
    await ctx.reply(f"✅ انضافت للطابور. (المتبقي: **{player.queue.qsize()}**)")

@bot.command()
async def playall(ctx: commands.Context):
    """يشغل روابطك (ويكمل تلقائي + يعيد تعبئة القائمة عند الانتهاء)."""
    await ensure_voice(ctx)
    player = get_player(bot, ctx.guild)

    await player.refill_defaults(ctx.channel)
    await ctx.reply(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** أغنية للطابور. رح يبدّل تلقائيًا.")

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
    """auto on/off لتشغيل/إيقاف إعادة التعبئة التلقائية."""
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
# تشغيل
# =========================
if TOKEN == "PUT_YOUR_TOKEN_HERE" or not TOKEN:
    raise SystemExit("❌ حط توكن البوت في BOT_TOKEN أو في ملف .env (DISCORD_TOKEN).")

bot.run(TOKEN)
