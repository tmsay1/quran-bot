import os
import re
import io
import json
import time
import shutil
import random
import asyncio
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import yt_dlp
import aiohttp

from PIL import Image, ImageDraw, ImageFont

# Arabic shaping (يخلي العربي يطلع صحيح بالصورة)
import arabic_reshaper
from bidi.algorithm import get_display


# =========================
# ENV
# =========================
load_dotenv()

TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_TOKEN".lower()) or "").strip()
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN مفقود. حطه بمتغيرات البيئة (Railway/Render Variables).")

PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"
ENABLE_PREFIX_COMMANDS = (os.getenv("ENABLE_PREFIX_COMMANDS", "1").strip() == "1")

SYNC_GUILD_ID = (os.getenv("SYNC_GUILD_ID") or "").strip()  # اختياري للتجربة بسرعة
SUPPORT_INVITE = (os.getenv("SUPPORT_INVITE") or "https://discord.gg/SA67WYP9Mn").strip()

AUTO_JOIN_VOICE_CHANNEL_ID = (os.getenv("AUTO_JOIN_VOICE_CHANNEL_ID") or "").strip()
AUTO_JOIN_VOICE_CHANNEL_ID = int(AUTO_JOIN_VOICE_CHANNEL_ID) if AUTO_JOIN_VOICE_CHANNEL_ID.isdigit() else None

AUTO_PLAY_ON_READY = (os.getenv("AUTO_PLAY_ON_READY", "0").strip() == "1")

AYAH_INTERVAL_MINUTES = int((os.getenv("AYAH_INTERVAL_MINUTES") or "30").strip())

TEMPLATE_PATH = (os.getenv("TEMPLATE_PATH") or "quran_template_transparent.png").strip()
TEMPLATE_URL = (os.getenv("TEMPLATE_URL") or "https://i.postimg.cc/6p7DJpm6/quran-template-transparent.png").strip()

AR_FONT_PATH = (os.getenv("AR_FONT_PATH") or "").strip()  # إذا بدك تحدد خط يدوي
# =========================
# Quran URLs (قائمة تشغيل playall)
# تقدر تزودها بملف: quran_urls.txt (كل رابط بسطر)
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

AZKAR = [
    "سُبْحَانَ اللَّهِ وَبِحَمْدِهِ، سُبْحَانَ اللَّهِ الْعَظِيمِ",
    "اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّد",
    "لا إلهَ إلا اللهُ وحدَه لا شريكَ له، له المُلكُ وله الحمدُ وهو على كلِّ شيءٍ قدير",
    "أستغفرُ اللهَ العظيمَ وأتوبُ إليه",
    "حسبيَ اللهُ لا إلهَ إلا هو عليه توكّلتُ وهو ربُّ العرشِ العظيم",
]

SETTINGS_FILE = "guild_settings.json"


# =========================
# Settings per guild
# =========================
def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(data: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

SETTINGS: Dict[str, Any] = load_settings()

def get_gcfg(guild_id: int) -> Dict[str, Any]:
    gid = str(guild_id)
    if gid not in SETTINGS:
        SETTINGS[gid] = {
            "ayah_channel_id": None,
            "ayah_interval_minutes": AYAH_INTERVAL_MINUTES,
            "ayah_last_sent": 0,
        }
        save_settings(SETTINGS)
    return SETTINGS[gid]


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
# Track model
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
        self.autorefill = True
        self.last_text_channel_id: Optional[int] = None
        self.task = asyncio.create_task(self.player_loop())

    def set_last_channel(self, ch: discord.TextChannel):
        self.last_text_channel_id = ch.id

    async def refill_defaults(self, channel: discord.TextChannel):
        urls = load_urls_from_file() or list(DEFAULT_SONG_URLS)
        for u in urls:
            await self.queue.put((Track(url=u), channel))

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next_event.clear()

            # إذا الطابور فاضي وعندنا آخر روم نصي ومفعل autorefill => عبّي
            if self.queue.empty() and self.autorefill and self.last_text_channel_id:
                vc = self.guild.voice_client
                ch = self.guild.get_channel(self.last_text_channel_id)
                if vc and vc.is_connected() and isinstance(ch, discord.TextChannel):
                    await self.refill_defaults(ch)
                    try:
                        await ch.send("🔁 خلصت القائمة… عبّيتها من جديد وكملت.")
                    except Exception:
                        pass

            track, channel = await self.queue.get()
            self.set_last_channel(channel)
            self.current = track

            vc = self.guild.voice_client
            if vc is None or not vc.is_connected():
                self.current = None
                continue

            try:
                source = await self.create_source(track)
            except Exception as e:
                try:
                    await channel.send(f"⚠️ ما قدرت أشغل هذا المقطع، رح أتجاوزه.\nسبب: `{type(e).__name__}: {e}`")
                except Exception:
                    pass
                self.current = None
                continue

            def _after(err: Optional[Exception]):
                if err:
                    print(f"[AFTER ERROR] {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            vc.play(source, after=_after)
            try:
                await channel.send(f"▶️ **Now Playing:** {track.title}")
            except Exception:
                pass

            await self.next_event.wait()
            self.current = None

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

        audio = discord.FFmpegPCMAudio(
            stream_url,
            before_options=FFMPEG_BEFORE,
            options=FFMPEG_OPTS
        )
        return discord.PCMVolumeTransformer(audio, volume=self.volume)


players: Dict[int, GuildPlayer] = {}

def get_player(bot: commands.Bot, guild: discord.Guild) -> GuildPlayer:
    gp = players.get(guild.id)
    if not gp:
        gp = GuildPlayer(bot, guild)
        players[guild.id] = gp
    return gp


def load_urls_from_file() -> List[str]:
    path = "quran_urls.txt"
    if not os.path.exists(path):
        return []
    urls: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u and URL_RE.match(u):
                urls.append(u)
    return urls


# =========================
# Discord intents + bot
# =========================
intents = discord.Intents.default()
intents.voice_states = True
if ENABLE_PREFIX_COMMANDS:
    intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX if ENABLE_PREFIX_COMMANDS else commands.when_mentioned, intents=intents)


# =========================
# HTTP session
# =========================
session: Optional[aiohttp.ClientSession] = None


# =========================
# Helpers
# =========================
async def ensure_voice_member(interaction_or_ctx):
    # works for ctx OR interaction
    if isinstance(interaction_or_ctx, commands.Context):
        author = interaction_or_ctx.author
        guild = interaction_or_ctx.guild
    else:
        author = interaction_or_ctx.user
        guild = interaction_or_ctx.guild

    if not author or not getattr(author, "voice", None) or not author.voice or not author.voice.channel:
        raise RuntimeError("لازم تكون داخل روم صوت أولاً.")

    vc = guild.voice_client
    if vc and vc.is_connected():
        return vc
    return await author.voice.channel.connect()


def shape_arabic(text: str) -> str:
    # reshaping + bidi for correct Arabic rendering
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


async def ensure_template_file():
    if os.path.exists(TEMPLATE_PATH):
        return
    # download once
    global session
    if session is None:
        session = aiohttp.ClientSession()
    async with session.get(TEMPLATE_URL, timeout=aiohttp.ClientTimeout(total=30)) as r:
        r.raise_for_status()
        data = await r.read()
    with open(TEMPLATE_PATH, "wb") as f:
        f.write(data)


def find_arabic_font() -> str:
    # priority: env path
    if AR_FONT_PATH and os.path.exists(AR_FONT_PATH):
        return AR_FONT_PATH

    candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


async def build_card_image(main_text: str, footer: str = "") -> bytes:
    await ensure_template_file()

    base = Image.open(TEMPLATE_PATH).convert("RGBA")
    W, H = base.size

    # text box area (نسبة من الصورة)
    left = int(W * 0.15)
    right = int(W * 0.85)
    top = int(H * 0.37)
    bottom = int(H * 0.63)

    draw = ImageDraw.Draw(base)

    font_path = find_arabic_font()
    if not font_path:
        # fallback (بس ممكن يطلع مربعات إذا ما في خط عربي)
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    else:
        font = ImageFont.truetype(font_path, size=int(H * 0.045))
        font_small = ImageFont.truetype(font_path, size=int(H * 0.030))

    # shape Arabic
    main_text_shaped = shape_arabic(main_text)
    footer_shaped = shape_arabic(footer) if footer else ""

    # wrap
    max_w = right - left - int(W * 0.04)
    lines = wrap_text(draw, main_text_shaped, font, max_w)

    # if too many lines, reduce font size a bit
    max_lines = 4
    if len(lines) > max_lines and font_path:
        font = ImageFont.truetype(font_path, size=int(H * 0.040))
        lines = wrap_text(draw, main_text_shaped, font, max_w)

    # calculate vertical centering
    line_h = font.getbbox("A")[3] - font.getbbox("A")[1]
    total_h = line_h * len(lines) + (8 * (len(lines) - 1))
    start_y = top + ((bottom - top) - total_h) // 2

    # draw main lines centered
    y = start_y
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        x = left + ((right - left) - int(tw)) // 2
        draw.text((x, y), ln, font=font, fill=(20, 20, 20, 255))
        y += line_h + 8

    # footer at bottom inside box
    if footer_shaped:
        fw = draw.textlength(footer_shaped, font=font_small)
        fx = left + ((right - left) - int(fw)) // 2
        fy = bottom - int(H * 0.05)
        draw.text((fx, fy), footer_shaped, font=font_small, fill=(60, 60, 60, 255))

    out = io.BytesIO()
    base.save(out, format="PNG")
    return out.getvalue()


async def fetch_random_ayah_ar() -> Tuple[str, str]:
    # alquran.cloud random by number range
    # total ayahs ~ 6236
    n = random.randint(1, 6236)
    url = f"https://api.alquran.cloud/v1/ayah/{n}/ar.alafasy"
    global session
    if session is None:
        session = aiohttp.ClientSession()
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
        r.raise_for_status()
        j = await r.json()

    data = j.get("data", {})
    text = data.get("text", "").strip()
    surah = (data.get("surah", {}) or {}).get("name", "").strip()
    num_in_surah = data.get("numberInSurah", 0)
    footer = f"{surah} - آية {num_in_surah}" if surah and num_in_surah else ""
    return text, footer


# =========================
# Background task: post ayah/zekr
# =========================
@tasks.loop(minutes=1)
async def ayah_scheduler():
    await bot.wait_until_ready()

    for guild in bot.guilds:
        try:
            cfg = get_gcfg(guild.id)
            ch_id = cfg.get("ayah_channel_id")
            if not ch_id:
                continue

            interval = int(cfg.get("ayah_interval_minutes") or AYAH_INTERVAL_MINUTES)
            last = int(cfg.get("ayah_last_sent") or 0)

            now = int(time.time())
            if now - last < interval * 60:
                continue

            channel = guild.get_channel(int(ch_id))
            if not isinstance(channel, discord.TextChannel):
                continue

            # 75% ayah / 25% zikr
            if random.random() < 0.75:
                text, footer = await fetch_random_ayah_ar()
                if not text:
                    continue
            else:
                text = random.choice(AZKAR)
                footer = "ذكر"

            img = await build_card_image(text, footer)

            file = discord.File(fp=io.BytesIO(img), filename="ayah.png")  # ✅ FIXED
            await channel.send(file=file)

            cfg["ayah_last_sent"] = now
            SETTINGS[str(guild.id)] = cfg
            save_settings(SETTINGS)

        except Exception as e:
            print(f"[AYAH ERROR] {guild.name}: {e}")


# =========================
# Setup hook: sync slash commands
# =========================
@bot.event
async def setup_hook():
    # start task
    if not ayah_scheduler.is_running():
        ayah_scheduler.start()

    # sync commands
    if SYNC_GUILD_ID.isdigit():
        gobj = discord.Object(id=int(SYNC_GUILD_ID))
        bot.tree.copy_global_to(guild=gobj)
        await bot.tree.sync(guild=gobj)
        print(f"[SYNC] synced to guild {SYNC_GUILD_ID}")
    else:
        await bot.tree.sync()
        print("[SYNC] synced globally")


# =========================
# on_ready
# =========================
@bot.event
async def on_ready():
    print(f"[READY] {bot.user} is online.")
    if not pick_js_runtimes():
        print("[WARN] ما لقيت Deno/Node. (اختياري) وجودهم يساعد مع تغييرات يوتيوب.")
    # Status (يطلع بالواجهة مثل صورتك)
    try:
        await bot.change_presence(activity=discord.Game("!playall /playall"))
    except Exception:
        pass

    # Auto-join option
    if AUTO_JOIN_VOICE_CHANNEL_ID:
        for g in bot.guilds:
            ch = g.get_channel(AUTO_JOIN_VOICE_CHANNEL_ID)
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await ch.connect()
                    print(f"[AUTO] joined voice: {ch.name} in {g.name}")
                    if AUTO_PLAY_ON_READY:
                        player = get_player(bot, g)
                        # نرسل رسائل للروم النصي الافتراضي (اول روم نصي)
                        text_ch = next((c for c in g.text_channels if c.permissions_for(g.me).send_messages), None)
                        if text_ch:
                            await player.refill_defaults(text_ch)
                except Exception as e:
                    print(f"[AUTO] failed: {e}")


# =========================
# PREFIX COMMANDS (اختياري)
# =========================
if ENABLE_PREFIX_COMMANDS:
    @bot.command()
    async def join(ctx: commands.Context):
        vc = await ensure_voice_member(ctx)
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
        await ensure_voice_member(ctx)
        player = get_player(bot, ctx.guild)

        q = query.strip()
        if not URL_RE.match(q):
            q = f"ytsearch1:{q}"

        await player.queue.put((Track(url=q, requester=ctx.author), ctx.channel))
        player.set_last_channel(ctx.channel)
        await ctx.reply(f"✅ انضافت للطابور. (المتبقي: **{player.queue.qsize()}**)")

    @bot.command()
    async def playall(ctx: commands.Context):
        await ensure_voice_member(ctx)
        player = get_player(bot, ctx.guild)
        await player.refill_defaults(ctx.channel)
        player.set_last_channel(ctx.channel)
        await ctx.reply("✅ تم تحميل قائمة القرآن للطابور. رح يشتغل 24/7.")

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


# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="join", description="يدخل روم الصوت")
async def slash_join(interaction: discord.Interaction):
    try:
        vc = await ensure_voice_member(interaction)
        await interaction.response.send_message(f"✅ دخلت: **{vc.channel}**", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)

@bot.tree.command(name="leave", description="يطلع من روم الصوت")
async def slash_leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()
        await interaction.response.send_message("👋 طلعت من الروم.", ephemeral=True)
    else:
        await interaction.response.send_message("أنا أصلاً مو داخل روم.", ephemeral=True)

@bot.tree.command(name="playall", description="تشغيل القرآن 24/7 (قائمة الروابط)")
async def slash_playall(interaction: discord.Interaction):
    try:
        await ensure_voice_member(interaction)
        player = get_player(bot, interaction.guild)
        # نرسل تحديثات لروم تنفيذ الأمر
        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if not channel:
            await interaction.response.send_message("نفّذ الأمر داخل روم نصي.", ephemeral=True)
            return
        await player.refill_defaults(channel)
        player.set_last_channel(channel)
        await interaction.response.send_message("✅ تم تحميل قائمة القرآن للطابور. رح يشتغل 24/7.", ephemeral=False)
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)

@bot.tree.command(name="now", description="وش شغال الآن؟")
async def slash_now(interaction: discord.Interaction):
    player = get_player(bot, interaction.guild)
    if player.current:
        await interaction.response.send_message(f"🎶 الآن: **{player.current.title}**", ephemeral=False)
    else:
        await interaction.response.send_message("ما في شي شغال حالياً.", ephemeral=True)

@bot.tree.command(name="skip", description="تخطي المقطع الحالي")
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("⏭️ تم السكيب.", ephemeral=False)
    else:
        await interaction.response.send_message("ما في شي شغال.", ephemeral=True)


@bot.tree.command(name="setayahchannel", description="تحديد روم إرسال الآيات/الأذكار بالصورة (كل 30 دقيقة)")
@app_commands.describe(channel="اختار الروم النصي")
async def setayahchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    cfg = get_gcfg(interaction.guild.id)
    cfg["ayah_channel_id"] = channel.id
    cfg["ayah_interval_minutes"] = AYAH_INTERVAL_MINUTES
    cfg["ayah_last_sent"] = 0
    SETTINGS[str(interaction.guild.id)] = cfg
    save_settings(SETTINGS)
    await interaction.response.send_message(f"✅ تم ضبط روم الآيات: {channel.mention}\n⏱️ كل {AYAH_INTERVAL_MINUTES} دقيقة.", ephemeral=True)

@bot.tree.command(name="ayahnow", description="إرسال آية/ذكر الآن للتجربة")
async def ayahnow(interaction: discord.Interaction):
    try:
        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        if not channel:
            await interaction.response.send_message("نفّذ الأمر داخل روم نصي.", ephemeral=True)
            return

        if random.random() < 0.75:
            text, footer = await fetch_random_ayah_ar()
        else:
            text, footer = random.choice(AZKAR), "ذكر"

        img = await build_card_image(text, footer)
        file = discord.File(fp=io.BytesIO(img), filename="ayah.png")  # ✅ FIXED
        await interaction.response.send_message(file=file)
    except Exception as e:
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ صار خطأ: `{e}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ صار خطأ: `{e}`", ephemeral=True)


# =========================
# Run
# =========================
bot.run(TOKEN)
