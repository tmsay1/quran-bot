import os
import re
import json
import random
import asyncio
import shutil
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# =========================
# ENV
# =========================
load_dotenv()

DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
if not DISCORD_TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is missing. Set it in Railway/Render Variables.")

PREFIX = (os.getenv("PREFIX") or "!").strip() or "!"
ENABLE_PREFIX_COMMANDS = (os.getenv("ENABLE_PREFIX_COMMANDS", "1").strip() == "1")

SUPPORT_INVITE = (os.getenv("SUPPORT_INVITE") or "https://discord.gg/SA67WYP9Mn").strip()

# إرسال صورة آية/ذكر كل كم دقيقة؟
POST_INTERVAL_MINUTES = int(os.getenv("POST_INTERVAL_MINUTES", "30"))

# رابط القالب الشفاف (اللي عطيتني)
TEMPLATE_URL = (os.getenv("TEMPLATE_URL") or "https://i.postimg.cc/6p7DJpm6/quran-template-transparent.png").strip()

# مكان القالب محليًا
ASSETS_DIR = "assets"
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "quran-template.png")

# خط عربي (إذا موجود بالنظام أو بالمجلد assets/fonts)
# (Dockerfile رح يثبت fonts-amiri غالبًا)
FALLBACK_FONT_PATHS = [
    os.path.join(ASSETS_DIR, "fonts", "Amiri-Regular.ttf"),
    "/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# صندوق النص داخل الصورة (كنِسَب من حجم الصورة)
# left, top, right, bottom
TEXT_BOX = (0.17, 0.37, 0.83, 0.63)

# =========================
# روابط القرآن (أضفت كثير + خليت روابطك)
# =========================
DEFAULT_SONG_URLS = [
    # روابطك (10)
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

    # +40 بحث يوتيوب (أضمن من الروابط أحياناً)
    "ytsearch1:سورة البقرة العفاسي كاملة",
    "ytsearch1:سورة آل عمران العفاسي كاملة",
    "ytsearch1:سورة النساء العفاسي كاملة",
    "ytsearch1:سورة المائدة العفاسي كاملة",
    "ytsearch1:سورة الأنعام العفاسي كاملة",
    "ytsearch1:سورة الأعراف العفاسي كاملة",
    "ytsearch1:سورة الأنفال العفاسي كاملة",
    "ytsearch1:سورة التوبة العفاسي كاملة",
    "ytsearch1:سورة يونس العفاسي كاملة",
    "ytsearch1:سورة هود العفاسي كاملة",
    "ytsearch1:سورة يوسف العفاسي كاملة",
    "ytsearch1:سورة الرعد العفاسي كاملة",
    "ytsearch1:سورة إبراهيم العفاسي كاملة",
    "ytsearch1:سورة الحجر العفاسي كاملة",
    "ytsearch1:سورة النحل العفاسي كاملة",
    "ytsearch1:سورة الإسراء العفاسي كاملة",
    "ytsearch1:سورة الكهف العفاسي كاملة",
    "ytsearch1:سورة مريم العفاسي كاملة",
    "ytsearch1:سورة طه العفاسي كاملة",
    "ytsearch1:سورة الأنبياء العفاسي كاملة",
    "ytsearch1:سورة الحج العفاسي كاملة",
    "ytsearch1:سورة المؤمنون العفاسي كاملة",
    "ytsearch1:سورة النور العفاسي كاملة",
    "ytsearch1:سورة الفرقان العفاسي كاملة",
    "ytsearch1:سورة الشعراء العفاسي كاملة",
    "ytsearch1:سورة النمل العفاسي كاملة",
    "ytsearch1:سورة القصص العفاسي كاملة",
    "ytsearch1:سورة العنكبوت العفاسي كاملة",
    "ytsearch1:سورة الروم العفاسي كاملة",
    "ytsearch1:سورة لقمان العفاسي كاملة",
    "ytsearch1:سورة السجدة العفاسي كاملة",
    "ytsearch1:سورة يس العفاسي كاملة",
    "ytsearch1:سورة الصافات العفاسي كاملة",
    "ytsearch1:سورة ص العفاسي كاملة",
    "ytsearch1:سورة الزمر العفاسي كاملة",
    "ytsearch1:سورة غافر العفاسي كاملة",
    "ytsearch1:سورة فصلت العفاسي كاملة",
    "ytsearch1:سورة الشورى العفاسي كاملة",
    "ytsearch1:سورة الرحمن العفاسي كاملة",
    "ytsearch1:سورة الواقعة العفاسي كاملة",
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
# تخزين إعدادات السيرفرات (روم الآيات + روم الصوت)
# =========================
DATA_DIR = "data"
CFG_PATH = os.path.join(DATA_DIR, "guild_config.json")

def ensure_dirs():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

def load_config() -> Dict[str, dict]:
    ensure_dirs()
    if not os.path.exists(CFG_PATH):
        return {}
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg: Dict[str, dict]):
    ensure_dirs()
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

CFG: Dict[str, dict] = load_config()

def get_gcfg(guild_id: int) -> dict:
    k = str(guild_id)
    if k not in CFG:
        CFG[k] = {
            "ayah_channel_id": None,
            "voice_channel_id": None,
            "autoplay_on_ready": False,
        }
        save_config(CFG)
    return CFG[k]

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
        self.queue: asyncio.Queue[Tuple[Track, discord.abc.Messageable]] = asyncio.Queue()
        self.next_event = asyncio.Event()
        self.current: Optional[Track] = None
        self.volume = 0.6
        self.autorefill = True
        self.task = asyncio.create_task(self.player_loop())

    async def refill_defaults(self, channel: discord.abc.Messageable):
        urls = list(DEFAULT_SONG_URLS)
        random.shuffle(urls)
        for u in urls:
            await self.queue.put((Track(url=u), channel))

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.next_event.clear()

            track, channel = await self.queue.get()
            self.current = track
            vc = self.guild.voice_client

            if vc is None or not vc.is_connected():
                self.current = None
                continue

            try:
                source = await self.create_source(track)
            except Exception as e:
                try:
                    await channel.send(f"⚠️ ما قدرت أشغل هالمقطع، رح أتجاوز.\nسبب: `{type(e).__name__}: {e}`")
                except Exception:
                    pass
                self.current = None
                if self.queue.empty() and self.autorefill:
                    await self.refill_defaults(channel)
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

            if self.queue.empty() and self.autorefill:
                await self.refill_defaults(channel)
                try:
                    await channel.send("🔁 خلصت القائمة… عبّيتها من جديد وكملت.")
                except Exception:
                    pass

    async def create_source(self, track: Track) -> discord.PCMVolumeTransformer:
        loop = asyncio.get_running_loop()

        def _extract():
            with make_ytdl() as ydl:
                return ydl.extract_info(track.url, download=False)

        info = await loop.run_in_executor(None, _extract)
        if not info:
            raise RuntimeError("فشل استخراج معلومات من yt-dlp.")

        # playlist/search
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

# =========================
# آيات/أذكار (نص) + صورة
# =========================
session: Optional[aiohttp.ClientSession] = None
surah_meta_cache: Optional[List[dict]] = None

AZKAR = [
    "اللهم إنك عفوٌ تحب العفو فاعفُ عني.",
    "حسبنا الله ونعم الوكيل.",
    "لا إله إلا أنت سبحانك إني كنت من الظالمين.",
    "أستغفر الله العظيم وأتوب إليه.",
    "اللهم صل وسلم على نبينا محمد.",
    "لا حول ولا قوة إلا بالله.",
    "سبحان الله وبحمده، سبحان الله العظيم.",
    "اللهم اهدني وسددني.",
    "اللهم ارزقني حسن الخاتمة.",
    "رب اشرح لي صدري ويسر لي أمري.",
]

async def get_session() -> aiohttp.ClientSession:
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
    return session

async def ensure_template():
    ensure_dirs()
    if os.path.exists(TEMPLATE_PATH):
        return
    s = await get_session()
    async with s.get(TEMPLATE_URL) as r:
        r.raise_for_status()
        data = await r.read()
    with open(TEMPLATE_PATH, "wb") as f:
        f.write(data)

def pick_font_path() -> str:
    for p in FALLBACK_FONT_PATHS:
        if os.path.exists(p):
            return p
    return ""  # will fallback to default

def shape_ar(text: str) -> str:
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def fit_text_on_box(img: Image.Image, text: str) -> Image.Image:
    base = img.convert("RGBA")
    w, h = base.size

    left = int(TEXT_BOX[0] * w)
    top = int(TEXT_BOX[1] * h)
    right = int(TEXT_BOX[2] * w)
    bottom = int(TEXT_BOX[3] * h)

    box_w = right - left
    box_h = bottom - top

    font_path = pick_font_path()
    draw = ImageDraw.Draw(base)

    # جرّب أحجام خط من كبير لصغير لين يركب
    for size in range(44, 18, -2):
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

        shaped = shape_ar(text)
        lines = wrap_lines(draw, shaped, font, box_w)
        line_h = draw.textbbox((0, 0), "Hg", font=font)[3]
        total_h = len(lines) * (line_h + 8) - 8

        if total_h <= box_h and len(lines) <= 6:
            # ارسم بالوسط
            y = top + (box_h - total_h) // 2
            for ln in lines:
                bbox = draw.textbbox((0, 0), ln, font=font)
                ln_w = bbox[2] - bbox[0]
                x = left + (box_w - ln_w) // 2
                # ظل خفيف
                draw.text((x + 2, y + 2), ln, font=font, fill=(0, 0, 0, 90))
                draw.text((x, y), ln, font=font, fill=(20, 20, 20, 255))
                y += line_h + 8
            return base

    # إذا ما ركب، اكتب مختصر
    small_font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default()
    shaped = shape_ar(text[:120] + "…")
    bbox = draw.textbbox((0, 0), shaped, font=small_font)
    x = left + (box_w - (bbox[2] - bbox[0])) // 2
    y = top + (box_h - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), shaped, font=small_font, fill=(20, 20, 20, 255))
    return base

async def fetch_surah_meta() -> List[dict]:
    global surah_meta_cache
    if surah_meta_cache is not None:
        return surah_meta_cache
    s = await get_session()
    async with s.get("https://api.alquran.cloud/v1/surah") as r:
        r.raise_for_status()
        j = await r.json()
    surah_meta_cache = j["data"]
    return surah_meta_cache

async def random_ayah_text() -> str:
    meta = await fetch_surah_meta()
    surah = random.randint(1, 114)
    ayah_count = meta[surah - 1]["numberOfAyahs"]
    ayah = random.randint(1, ayah_count)

    s = await get_session()
    url = f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/ar.alafasy"
    async with s.get(url) as r:
        r.raise_for_status()
        j = await r.json()
    text = j["data"]["text"]
    surah_name = j["data"]["surah"]["name"]
    num = j["data"]["numberInSurah"]
    return f"{text}\n({surah_name} • آية {num})"

async def build_card_image(text: str) -> bytes:
    await ensure_template()
    img = Image.open(TEMPLATE_PATH).convert("RGBA")
    out = fit_text_on_box(img, text)

    import io
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

async def post_ayah_to_guild(guild: discord.Guild):
    gcfg = get_gcfg(guild.id)
    ch_id = gcfg.get("ayah_channel_id")
    if not ch_id:
        return
    channel = guild.get_channel(int(ch_id))
    if not isinstance(channel, discord.TextChannel):
        return

    # آية أو ذكر
    if random.random() < 0.75:
        text = await random_ayah_text()
    else:
        text = random.choice(AZKAR)

    img_bytes = await build_card_image(text)

    file = discord.File(fp=discord.BytesIO(img_bytes), filename="ayah.png")
    await channel.send(file=file)

async def ayah_scheduler():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for g in bot.guilds:
                try:
                    await post_ayah_to_guild(g)
                except Exception as e:
                    print(f"[AYAH] failed in {g.id}: {e}")
        except Exception as e:
            print(f"[AYAH LOOP] {e}")

        await asyncio.sleep(POST_INTERVAL_MINUTES * 60)

# =========================
# Bot + Intents
# =========================
intents = discord.Intents.default()
intents.voice_states = True

# message_content فقط إذا بدك أوامر !
if ENABLE_PREFIX_COMMANDS:
    intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def ensure_voice_for_member(guild: discord.Guild, member: discord.Member) -> discord.VoiceClient:
    if not member.voice or not member.voice.channel:
        raise commands.CommandError("لازم تكون داخل روم صوت أولاً.")
    vc = guild.voice_client
    if vc and vc.is_connected():
        # إذا البوت في روم ثاني، انقله
        if vc.channel.id != member.voice.channel.id:
            await vc.move_to(member.voice.channel)
        return vc
    return await member.voice.channel.connect()

async def enqueue_defaults(guild: discord.Guild, reply_target: discord.abc.Messageable):
    player = get_player(bot, guild)
    player.autorefill = True
    await player.refill_defaults(reply_target)

@bot.event
async def on_ready():
    print(f"[READY] {bot.user} is online.")
    if not pick_js_runtimes():
        print("[WARN] ما لقيت Deno/Node. أحيانًا يوتيوب يحتاجهم.")

    # Presence
    try:
        await bot.change_presence(activity=discord.Game(name="/playall • /setayahchannel"))
    except Exception:
        pass

    # Sync slash commands
    sync_guild_id = (os.getenv("SYNC_GUILD_ID") or "").strip()
    try:
        if sync_guild_id.isdigit():
            guild_obj = discord.Object(id=int(sync_guild_id))
            await bot.tree.sync(guild=guild_obj)
            print(f"[SYNC] synced to guild {sync_guild_id}")
        else:
            await bot.tree.sync()
            print("[SYNC] synced globally (قد تاخذ وقت لتظهر ببعض السيرفرات)")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")

    # Auto join if configured
    for g in bot.guilds:
        gcfg = get_gcfg(g.id)
        vch = gcfg.get("voice_channel_id")
        if gcfg.get("autoplay_on_ready") and vch:
            ch = g.get_channel(int(vch))
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await ch.connect()
                    # شغل تلقائي
                    await enqueue_defaults(g, g.system_channel or (g.text_channels[0] if g.text_channels else None))
                    print(f"[AUTO] joined {ch.name} in {g.name}")
                except Exception as e:
                    print(f"[AUTO] failed in {g.name}: {e}")

    # start scheduler once
    if not hasattr(bot, "_ayah_task_started"):
        bot._ayah_task_started = True
        bot.loop.create_task(ayah_scheduler())

# =========================
# Slash Commands (تظهر بروفايل البوت)
# =========================
@bot.tree.command(name="support", description="رابط سيرفر الدعم")
async def support_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🛟 Support Server: {SUPPORT_INVITE}", ephemeral=True)

@bot.tree.command(name="join", description="يدخل روم الصوت اللي انت فيه")
async def join_slash(interaction: discord.Interaction):
    try:
        vc = await ensure_voice_for_member(interaction.guild, interaction.user)
        await interaction.response.send_message(f"✅ دخلت: **{vc.channel}**")
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="leave", description="يطلع من روم الصوت")
async def leave_slash(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()
        await interaction.response.send_message("👋 طلعت من الروم.")
    else:
        await interaction.response.send_message("أنا أصلاً مو داخل روم.", ephemeral=True)

@bot.tree.command(name="play", description="يشغل مقطع/بحث يوتيوب")
async def play_slash(interaction: discord.Interaction, query: str):
    try:
        await ensure_voice_for_member(interaction.guild, interaction.user)
        player = get_player(bot, interaction.guild)
        q = query.strip()
        if not URL_RE.match(q) and not q.lower().startswith("ytsearch"):
            q = f"ytsearch1:{q}"
        await player.queue.put((Track(url=q, requester=interaction.user), interaction.channel))
        await interaction.response.send_message("✅ انضافت للطابور.")
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="playall", description="تشغيل القرآن 24/7 (يحمل القائمة ويكرر تلقائياً)")
async def playall_slash(interaction: discord.Interaction):
    try:
        vc = await ensure_voice_for_member(interaction.guild, interaction.user)

        # خزّن روم الصوت للتشغيل التلقائي بعد الريستارت
        gcfg = get_gcfg(interaction.guild.id)
        gcfg["voice_channel_id"] = vc.channel.id
        gcfg["autoplay_on_ready"] = True
        save_config(CFG)

        await enqueue_defaults(interaction.guild, interaction.channel)
        await interaction.response.send_message(f"✅ تم تحميل قائمة القرآن. رح يشتغل 24/7 🔁")
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="skip", description="يتخطى المقطع الحالي")
async def skip_slash(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("⏭️ تم السكيب.")
    else:
        await interaction.response.send_message("ما في شي شغال.", ephemeral=True)

@bot.tree.command(name="now", description="شو شغال الآن")
async def now_slash(interaction: discord.Interaction):
    player = get_player(bot, interaction.guild)
    if player.current:
        await interaction.response.send_message(f"🎶 الآن: **{player.current.title}**")
    else:
        await interaction.response.send_message("ما في شي شغال حالياً.", ephemeral=True)

@bot.tree.command(name="setayahchannel", description="حدد روم الشات اللي ينزل فيه آيات/أذكار (كل 30 دقيقة)")
async def setayahchannel_slash(interaction: discord.Interaction, channel: discord.TextChannel):
    gcfg = get_gcfg(interaction.guild.id)
    gcfg["ayah_channel_id"] = channel.id
    save_config(CFG)
    await interaction.response.send_message(f"✅ تم ضبط روم الآيات: {channel.mention}\n(كل {POST_INTERVAL_MINUTES} دقيقة)")

    # جرّب رسالة مباشرة الآن
    try:
        await post_ayah_to_guild(interaction.guild)
    except Exception as e:
        await channel.send(f"⚠️ صار خطأ بتجربة الإرسال: `{e}`")

# =========================
# Prefix Commands (اختياري)
# =========================
if ENABLE_PREFIX_COMMANDS:
    @bot.command()
    async def join(ctx: commands.Context):
        vc = await ensure_voice_for_member(ctx.guild, ctx.author)
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
        await ensure_voice_for_member(ctx.guild, ctx.author)
        player = get_player(bot, ctx.guild)
        q = query.strip()
        if not URL_RE.match(q) and not q.lower().startswith("ytsearch"):
            q = f"ytsearch1:{q}"
        await player.queue.put((Track(url=q, requester=ctx.author), ctx.channel))
        await ctx.reply("✅ انضافت للطابور.")

    @bot.command()
    async def playall(ctx: commands.Context):
        vc = await ensure_voice_for_member(ctx.guild, ctx.author)
        gcfg = get_gcfg(ctx.guild.id)
        gcfg["voice_channel_id"] = vc.channel.id
        gcfg["autoplay_on_ready"] = True
        save_config(CFG)

        await enqueue_defaults(ctx.guild, ctx.channel)
        await ctx.reply("✅ تشغيل القرآن 24/7 🔁")

    @bot.command()
    async def setayahchannel(ctx: commands.Context, channel: discord.TextChannel):
        gcfg = get_gcfg(ctx.guild.id)
        gcfg["ayah_channel_id"] = channel.id
        save_config(CFG)
        await ctx.reply(f"✅ تم ضبط روم الآيات: {channel.mention}")
        await post_ayah_to_guild(ctx.guild)

# =========================
# Run
# =========================
bot.run(DISCORD_TOKEN)
