import os
import re
import io
import json
import asyncio
import shutil
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

import yt_dlp
import aiohttp

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# =========================
# ENV
# =========================
load_dotenv()

TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN/BOT_TOKEN is missing. Set it in Railway Variables.")

PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"

# تقدر تطفي أوامر البريفكس إذا ما مفعل Message Content Intent بالبوابة
ENABLE_PREFIX_COMMANDS = (os.getenv("ENABLE_PREFIX_COMMANDS", "1").strip() == "1")

# Presence حتى يبين للناس شلون يشغلون
PRESENCE_TEXT = os.getenv("PRESENCE_TEXT", "!playall /playall")

# Optional: لتسريع ظهور الـ Slash Commands بسيرفرك أثناء التطوير
SYNC_GUILD_ID = (os.getenv("SYNC_GUILD_ID") or "").strip()  # حط رقم سيرفرك إذا تريد (مو ضروري)

# =========================
# تشغيل تلقائي للروم الصوتي (اختياري)
# =========================
AUTO_REFILL_DEFAULT_LIST = True
SHUFFLE_ON_REFILL = False
AUTO_JOIN_VOICE_CHANNEL_ID = None  # مثال: 123...

# =========================
# قالب الآيات (الرابط اللي عطيتني)
# =========================
AYAH_TEMPLATE_URL = "https://i.postimg.cc/6p7DJpm6/quran-template-transparent.png"

# كل نص ساعة
POST_INTERVAL_MINUTES = int(os.getenv("POST_INTERVAL_MINUTES", "30"))

# خط عربي داخل Docker (DejaVu)
AR_FONT_PATH = os.getenv("AR_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

# حجم الخط
AYAH_FONT_SIZE = int(os.getenv("AYAH_FONT_SIZE", "34"))
REF_FONT_SIZE = int(os.getenv("REF_FONT_SIZE", "22"))

# ملف إعدادات السيرفرات (قناة إرسال الآيات)
CONFIG_FILE = "guild_settings.json"

# =========================
# روابط/بحث يوتيوب (50+)
# (مو لازم تكون كلها روابط مباشرة—ممكن تكون كلمات بحث، والبوت يسوي ytsearch)
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

    # +50 بحث (يشتغل عبر ytsearch)
    "سورة الفاتحة مشاري العفاسي",
    "سورة البقرة مشاري العفاسي",
    "سورة آل عمران مشاري العفاسي",
    "سورة النساء مشاري العفاسي",
    "سورة المائدة مشاري العفاسي",
    "سورة الأنعام مشاري العفاسي",
    "سورة الأعراف مشاري العفاسي",
    "سورة الأنفال مشاري العفاسي",
    "سورة التوبة مشاري العفاسي",
    "سورة يونس مشاري العفاسي",
    "سورة هود مشاري العفاسي",
    "سورة يوسف مشاري العفاسي",
    "سورة الرعد مشاري العفاسي",
    "سورة إبراهيم مشاري العفاسي",
    "سورة الحجر مشاري العفاسي",
    "سورة النحل مشاري العفاسي",
    "سورة الإسراء مشاري العفاسي",
    "سورة الكهف مشاري العفاسي",
    "سورة مريم مشاري العفاسي",
    "سورة طه مشاري العفاسي",
    "سورة الأنبياء مشاري العفاسي",
    "سورة الحج مشاري العفاسي",
    "سورة المؤمنون مشاري العفاسي",
    "سورة النور مشاري العفاسي",
    "سورة الفرقان مشاري العفاسي",
    "سورة الشعراء مشاري العفاسي",
    "سورة النمل مشاري العفاسي",
    "سورة القصص مشاري العفاسي",
    "سورة العنكبوت مشاري العفاسي",
    "سورة الروم مشاري العفاسي",
    "سورة لقمان مشاري العفاسي",
    "سورة السجدة مشاري العفاسي",
    "سورة الأحزاب مشاري العفاسي",
    "سورة سبأ مشاري العفاسي",
    "سورة فاطر مشاري العفاسي",
    "سورة يس مشاري العفاسي",
    "سورة الصافات مشاري العفاسي",
    "سورة ص مشاري العفاسي",
    "سورة الزمر مشاري العفاسي",
    "سورة غافر مشاري العفاسي",
    "سورة فصلت مشاري العفاسي",
    "سورة الشورى مشاري العفاسي",
    "سورة الزخرف مشاري العفاسي",
    "سورة الدخان مشاري العفاسي",
    "سورة الجاثية مشاري العفاسي",
    "سورة الأحقاف مشاري العفاسي",
    "سورة محمد مشاري العفاسي",
    "سورة الفتح مشاري العفاسي",
    "سورة الحجرات مشاري العفاسي",
    "سورة ق مشاري العفاسي",
    "سورة الرحمن مشاري العفاسي",
    "سورة الواقعة مشاري العفاسي",
    "سورة الحديد مشاري العفاسي",
    "سورة الحشر مشاري العفاسي",
    "سورة الملك مشاري العفاسي",
    "سورة الإنسان مشاري العفاسي",
    "سورة النبأ مشاري العفاسي",
    "سورة النازعات مشاري العفاسي",
    "سورة عبس مشاري العفاسي",
    "سورة التكوير مشاري العفاسي",
    "سورة الانفطار مشاري العفاسي",
    "سورة المطففين مشاري العفاسي",
    "سورة البروج مشاري العفاسي",
    "سورة الطارق مشاري العفاسي",
    "سورة الأعلى مشاري العفاسي",
    "سورة الغاشية مشاري العفاسي",
    "سورة الفجر مشاري العفاسي",
    "سورة البلد مشاري العفاسي",
    "سورة الشمس مشاري العفاسي",
    "سورة الليل مشاري العفاسي",
    "سورة الضحى مشاري العفاسي",
    "سورة الشرح مشاري العفاسي",
    "سورة التين مشاري العفاسي",
    "سورة العلق مشاري العفاسي",
    "سورة القدر مشاري العفاسي",
    "سورة البينة مشاري العفاسي",
    "سورة الزلزلة مشاري العفاسي",
    "سورة العاديات مشاري العفاسي",
    "سورة القارعة مشاري العفاسي",
    "سورة التكاثر مشاري العفاسي",
    "سورة العصر مشاري العفاسي",
    "سورة الهمزة مشاري العفاسي",
    "سورة الفيل مشاري العفاسي",
    "سورة قريش مشاري العفاسي",
    "سورة الماعون مشاري العفاسي",
    "سورة الكوثر مشاري العفاسي",
    "سورة الكافرون مشاري العفاسي",
    "سورة النصر مشاري العفاسي",
    "سورة المسد مشاري العفاسي",
    "سورة الإخلاص مشاري العفاسي",
    "سورة الفلق مشاري العفاسي",
    "سورة الناس مشاري العفاسي",
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
# Track
# =========================
@dataclass
class Track:
    url: str
    title: str = "Unknown"
    requester: Optional[discord.Member] = None

# =========================
# Player per guild
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
            q = u.strip()
            if not URL_RE.match(q):
                q = f"ytsearch1:{q}"
            await self.queue.put((Track(url=q), channel))

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

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
                await channel.send(f"⚠️ ما قدرت أشغل هالأغنية، رح أتجاوزها وأكمل.\nسبب: `{type(e).__name__}: {e}`")
                self.current = None

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

            if self.queue.empty() and self.autorefill:
                await self.refill_defaults(channel)
                await channel.send("🔁 خلصت القائمة… عبّيتها من جديد وكملت.")

    async def create_source(self, track: Track) -> discord.PCMVolumeTransformer:
        # إذا كان mp3 مباشر (بدون yt-dlp)
        if track.url.lower().endswith(".mp3"):
            audio = discord.FFmpegPCMAudio(track.url, before_options=FFMPEG_BEFORE, options=FFMPEG_OPTS)
            return discord.PCMVolumeTransformer(audio, volume=self.volume)

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

players: Dict[int, GuildPlayer] = {}

def get_player(bot: commands.Bot, guild: discord.Guild) -> GuildPlayer:
    gp = players.get(guild.id)
    if not gp:
        gp = GuildPlayer(bot, guild)
        players[guild.id] = gp
    return gp

# =========================
# Config (ayah channel)
# =========================
def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {"guilds": {}}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"guilds": {}}

def save_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[CONFIG] save failed:", e)

CONFIG = load_config()

def set_guild_setting(guild_id: int, key: str, value: Any):
    g = CONFIG.setdefault("guilds", {}).setdefault(str(guild_id), {})
    g[key] = value
    save_config(CONFIG)

def get_guild_setting(guild_id: int, key: str, default=None):
    return CONFIG.get("guilds", {}).get(str(guild_id), {}).get(key, default)

# =========================
# Discord intents
# =========================
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
if ENABLE_PREFIX_COMMANDS:
    intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# =========================
# Ayah Template cache + API
# =========================
_http: Optional[aiohttp.ClientSession] = None
_template_bytes: Optional[bytes] = None

async def get_http() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _http

async def get_template_bytes() -> bytes:
    global _template_bytes
    if _template_bytes:
        return _template_bytes
    http = await get_http()
    async with http.get(AYAH_TEMPLATE_URL) as r:
        r.raise_for_status()
        _template_bytes = await r.read()
        return _template_bytes

async def fetch_random_ayah() -> Dict[str, Any]:
    # alquran.cloud random ayah (مع تلاوة العفاسي)
    url = "https://api.alquran.cloud/v1/ayah/random/ar.alafasy"
    http = await get_http()
    async with http.get(url) as r:
        r.raise_for_status()
        data = await r.json()
        return data["data"]

def shape_arabic(s: str) -> str:
    # تشكيل + bidi عشان يطلع النص عربي مضبوط بالصور
    reshaped = arabic_reshaper.reshape(s)
    return get_display(reshaped)

def wrap_arabic(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur: List[str] = []

    for w in words:
        test = (" ".join(cur + [w])).strip()
        shaped = shape_arabic(test)
        bbox = draw.textbbox((0, 0), shaped, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]

    if cur:
        lines.append(" ".join(cur))
    return lines

async def render_ayah_image(ayah_text: str, ref_text: str) -> bytes:
    tpl = await get_template_bytes()
    img = Image.open(io.BytesIO(tpl)).convert("RGBA")

    W, H = img.size
    # صندوق النص داخل المستطيل الأبيض (نِسَب تقريبية مناسبة للقالب)
    left = int(W * 0.12)
    right = int(W * 0.88)
    top = int(H * 0.36)
    bottom = int(H * 0.62)

    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_main = ImageFont.truetype(AR_FONT_PATH, AYAH_FONT_SIZE)
        font_ref = ImageFont.truetype(AR_FONT_PATH, REF_FONT_SIZE)
    except Exception:
        font_main = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    max_width = right - left

    # لف النص على سطور
    lines = wrap_arabic(draw, ayah_text, font_main, max_width)
    # حد أقصى سطور حتى ما يطلع برا
    lines = lines[:4]

    # احسب الارتفاع الكلي
    line_heights = []
    for ln in lines:
        shaped_ln = shape_arabic(ln)
        bbox = draw.textbbox((0, 0), shaped_ln, font=font_main)
        line_heights.append(bbox[3] - bbox[1])

    total_text_h = sum(line_heights) + (len(lines) - 1) * 10

    # نقطة بداية وسط الصندوق
    y = top + max(0, ((bottom - top) - total_text_h) // 2)

    for i, ln in enumerate(lines):
        shaped_ln = shape_arabic(ln)
        bbox = draw.textbbox((0, 0), shaped_ln, font=font_main)
        w = bbox[2] - bbox[0]
        x = left + ((right - left) - w) // 2
        draw.text((x, y), shaped_ln, font=font_main, fill=(40, 40, 40, 255))
        y += line_heights[i] + 10

    # المرجع أسفل
    ref_shaped = shape_arabic(ref_text)
    bbox = draw.textbbox((0, 0), ref_shaped, font=font_ref)
    rw = bbox[2] - bbox[0]
    rx = left + ((right - left) - rw) // 2
    ry = bottom + int(H * 0.02)
    draw.text((rx, ry), ref_shaped, font=font_ref, fill=(90, 90, 90, 255))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()

# =========================
# Voice helpers
# =========================
async def ensure_voice_ctx(ctx: commands.Context) -> discord.VoiceClient:
    if not ctx.author.voice or not ctx.author.voice.channel:
        raise commands.CommandError("لازم تكون داخل روم صوت أولاً.")
    vc = ctx.guild.voice_client
    if vc and vc.is_connected():
        return vc
    return await ctx.author.voice.channel.connect()

async def ensure_voice_interaction(inter: discord.Interaction) -> discord.VoiceClient:
    if not inter.user or not isinstance(inter.user, discord.Member):
        raise app_commands.AppCommandError("لازم تكون داخل سيرفر.")
    member = inter.user
    if not member.voice or not member.voice.channel:
        raise app_commands.AppCommandError("لازم تكون داخل روم صوت أولاً.")
    vc = inter.guild.voice_client if inter.guild else None
    if vc and vc.is_connected():
        return vc
    return await member.voice.channel.connect()

# =========================
# Events
# =========================
@bot.event
async def on_ready():
    print(f"[READY] {bot.user} is online.")

    try:
        await bot.change_presence(activity=discord.Game(name=PRESENCE_TEXT))
    except Exception:
        pass

    # Sync slash commands
    try:
        if SYNC_GUILD_ID.isdigit():
            gobj = discord.Object(id=int(SYNC_GUILD_ID))
            await bot.tree.sync(guild=gobj)
            print(f"[SYNC] synced to guild {SYNC_GUILD_ID}")
        else:
            await bot.tree.sync()
            print("[SYNC] synced globally")
    except Exception as e:
        print("[SYNC] failed:", e)

    if not pick_js_runtimes():
        print("[WARN] ما لقيت Deno/Node. إذا واجهت مشاكل يوتيوب، ثبت Deno/Node.")

    # تشغيل حلقة إرسال الآيات
    if not ayah_poster.is_running():
        ayah_poster.start()

    # Auto-join (اختياري)
    if AUTO_JOIN_VOICE_CHANNEL_ID:
        for g in bot.guilds:
            ch = g.get_channel(AUTO_JOIN_VOICE_CHANNEL_ID)
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await ch.connect()
                    print(f"[AUTO] joined: {ch.name} in {g.name}")
                except Exception as e:
                    print(f"[AUTO] failed: {e}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    # أول ما ينضاف لسيرفر جديد
    print(f"[GUILD] joined: {guild.name} ({guild.id})")

# =========================
# Ayah poster loop
# =========================
@tasks.loop(minutes=POST_INTERVAL_MINUTES)
async def ayah_poster():
    # يرسل لكل سيرفر مفعل عليه
    for g in bot.guilds:
        enabled = bool(get_guild_setting(g.id, "ayah_enabled", False))
        ch_id = get_guild_setting(g.id, "ayah_channel_id", None)
        if not enabled or not ch_id:
            continue

        ch = g.get_channel(int(ch_id))
        if not isinstance(ch, discord.TextChannel):
            continue

        try:
            ayah = await fetch_random_ayah()
            text = ayah.get("text", "").strip()
            surah = ayah.get("surah", {}) or {}
            surah_name = surah.get("name", "سورة")
            num_in_surah = ayah.get("numberInSurah", "?")

            ref = f"{surah_name} — آية {num_in_surah}"
            img_bytes = await render_ayah_image(text, ref)

            file = discord.File(io.BytesIO(img_bytes), filename="ayah.png")
            await ch.send(file=file)
        except Exception as e:
            print("[AYAH] failed:", e)

@ayah_poster.before_loop
async def before_ayah_poster():
    await bot.wait_until_ready()

# =========================
# Prefix commands
# =========================
if ENABLE_PREFIX_COMMANDS:

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

        await player.queue.put((Track(url=q, requester=ctx.author), ctx.channel))
        await ctx.reply(f"✅ انضافت للطابور. (المتبقي: **{player.queue.qsize()}**)")

    @bot.command()
    async def playall(ctx: commands.Context):
        await ensure_voice_ctx(ctx)
        player = get_player(bot, ctx.guild)
        await player.refill_defaults(ctx.channel)
        await ctx.reply(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** للتشغيل. رح يكمل 24/7.")

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

    @bot.command(name="setayahchannel")
    async def setayahchannel(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        set_guild_setting(ctx.guild.id, "ayah_channel_id", channel.id)
        await ctx.reply(f"✅ تم تعيين قناة الآيات: {channel.mention}")

    @bot.command(name="ayah")
    async def ayah_cmd(ctx: commands.Context, mode: Optional[str] = None):
        if mode and mode.lower() in ("on", "enable"):
            set_guild_setting(ctx.guild.id, "ayah_enabled", True)
            set_guild_setting(ctx.guild.id, "ayah_channel_id", ctx.channel.id)
            await ctx.reply("✅ تم تفعيل إرسال الآيات كل 30 دقيقة في هذه القناة.")
            return
        if mode and mode.lower() in ("off", "disable"):
            set_guild_setting(ctx.guild.id, "ayah_enabled", False)
            await ctx.reply("🛑 تم إيقاف إرسال الآيات.")
            return

        # إرسال آية الآن
        ayah = await fetch_random_ayah()
        text = (ayah.get("text") or "").strip()
        surah = ayah.get("surah", {}) or {}
        surah_name = surah.get("name", "سورة")
        num_in_surah = ayah.get("numberInSurah", "?")
        ref = f"{surah_name} — آية {num_in_surah}"
        img_bytes = await render_ayah_image(text, ref)
        await ctx.send(file=discord.File(io.BytesIO(img_bytes), filename="ayah.png"))

# =========================
# Slash commands (تظهر بقسم Commands بالبروفايل)
# =========================
@bot.tree.command(name="join", description="يدخل روم الصوت")
async def slash_join(inter: discord.Interaction):
    await ensure_voice_interaction(inter)
    await inter.response.send_message("✅ دخلت الروم الصوتي.", ephemeral=True)

@bot.tree.command(name="leave", description="يطلع من روم الصوت")
async def slash_leave(inter: discord.Interaction):
    vc = inter.guild.voice_client if inter.guild else None
    if vc and vc.is_connected():
        await vc.disconnect()
        await inter.response.send_message("👋 طلعت من الروم.", ephemeral=True)
    else:
        await inter.response.send_message("أنا أصلاً مو داخل روم.", ephemeral=True)

@bot.tree.command(name="playall", description="تشغيل القرآن 24/7 (يعبّي قائمة التشغيل)")
async def slash_playall(inter: discord.Interaction):
    vc = await ensure_voice_interaction(inter)
    player = get_player(bot, inter.guild)

    # نرسل الرد في نفس الشات
    await inter.response.send_message(f"✅ جاهز! تقدر تكتب: `{PREFIX}playall` أو تستخدم هذا الأمر.", ephemeral=True)

    # ماكو ctx هنا، نخلي الرسائل تروح لقناة الأمر الحالي
    if isinstance(inter.channel, discord.TextChannel):
        await player.refill_defaults(inter.channel)
        await inter.channel.send(f"✅ تم تحميل **{len(DEFAULT_SONG_URLS)}** للتشغيل. رح يكمل 24/7.")

@bot.tree.command(name="setayahchannel", description="تعيين قناة إرسال الآيات/الأذكار")
@app_commands.describe(channel="اختار قناة النص")
async def slash_setayahchannel(inter: discord.Interaction, channel: discord.TextChannel):
    set_guild_setting(inter.guild.id, "ayah_channel_id", channel.id)
    await inter.response.send_message(f"✅ تم تعيين قناة الآيات: {channel.mention}", ephemeral=True)

@bot.tree.command(name="ayah", description="إرسال آية الآن / تشغيل الإرسال التلقائي")
@app_commands.describe(mode="on/off أو اتركها فارغة لإرسال آية الآن")
async def slash_ayah(inter: discord.Interaction, mode: Optional[str] = None):
    if mode and mode.lower() in ("on", "enable"):
        set_guild_setting(inter.guild.id, "ayah_enabled", True)
        if isinstance(inter.channel, discord.TextChannel):
            set_guild_setting(inter.guild.id, "ayah_channel_id", inter.channel.id)
        await inter.response.send_message("✅ تم تفعيل إرسال الآيات كل 30 دقيقة في هذه القناة.", ephemeral=True)
        return

    if mode and mode.lower() in ("off", "disable"):
        set_guild_setting(inter.guild.id, "ayah_enabled", False)
        await inter.response.send_message("🛑 تم إيقاف إرسال الآيات.", ephemeral=True)
        return

    ayah = await fetch_random_ayah()
    text = (ayah.get("text") or "").strip()
    surah = ayah.get("surah", {}) or {}
    surah_name = surah.get("name", "سورة")
    num_in_surah = ayah.get("numberInSurah", "?")
    ref = f"{surah_name} — آية {num_in_surah}"
    img_bytes = await render_ayah_image(text, ref)

    file = discord.File(io.BytesIO(img_bytes), filename="ayah.png")
    await inter.response.send_message(file=file)

# =========================
# Run
# =========================
bot.run(TOKEN)
