import os
import json
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, List

import discord
from discord import app_commands
from discord.ext import commands

# ======================
# ENV
# ======================
TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Set it in Railway Variables.")

SUPPORT_INVITE = (os.getenv("SUPPORT_INVITE") or "https://discord.gg/KVuBY5Zwzk").strip()

# إذا حطيت GUILD_ID (ايدي سيرفرك) الأوامر / تظهر فوراً عندك
GUILD_ID = int(os.getenv("GUILD_ID") or "0")

DEFAULT_RECITER = (os.getenv("RECITER_FOLDER") or "Alafasy_128kbps").strip()

FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"

CONFIG_FILE = "guild_config.json"

# ======================
# Quran data (114 surahs)
# ======================
SURAH_NAMES_AR = [
    "الفاتحة","البقرة","آل عمران","النساء","المائدة","الأنعام","الأعراف","الأنفال","التوبة","يونس",
    "هود","يوسف","الرعد","إبراهيم","الحجر","النحل","الإسراء","الكهف","مريم","طه",
    "الأنبياء","الحج","المؤمنون","النور","الفرقان","الشعراء","النمل","القصص","العنكبوت","الروم",
    "لقمان","السجدة","الأحزاب","سبأ","فاطر","يس","الصافات","ص","الزمر","غافر",
    "فصلت","الشورى","الزخرف","الدخان","الجاثية","الأحقاف","محمد","الفتح","الحجرات","ق",
    "الذاريات","الطور","النجم","القمر","الرحمن","الواقعة","الحديد","المجادلة","الحشر","الممتحنة",
    "الصف","الجمعة","المنافقون","التغابن","الطلاق","التحريم","الملك","القلم","الحاقة","المعارج",
    "نوح","الجن","المزمل","المدثر","القيامة","الإنسان","المرسلات","النبأ","النازعات","عبس",
    "التكوير","الانفطار","المطففين","الانشقاق","البروج","الطارق","الأعلى","الغاشية","الفجر","البلد",
    "الشمس","الليل","الضحى","الشرح","التين","العلق","القدر","البينة","الزلزلة","العاديات",
    "القارعة","التكاثر","العصر","الهمزة","الفيل","قريش","الماعون","الكوثر","الكافرون","النصر",
    "المسد","الإخلاص","الفلق","الناس"
]
SURAH_AYAH_COUNTS = [
    7,286,200,176,120,165,206,75,129,109,
    123,111,43,52,99,128,111,110,98,135,
    112,78,118,64,77,227,93,88,69,60,
    34,30,73,54,45,83,182,88,75,85,
    54,53,89,59,37,35,38,29,18,45,
    60,49,62,55,78,96,29,22,24,13,
    14,11,11,18,12,12,30,52,52,44,
    28,28,20,56,40,31,50,40,46,42,
    29,19,36,25,22,17,19,26,30,20,
    15,21,11,8,8,19,5,8,8,11,
    11,8,3,9,5,4,7,3,6,3,
    5,4,5,6
]

RECITERS = {
    "Alafasy (128kbps)": "Alafasy_128kbps",
    "Alafasy (64kbps)": "Alafasy_64kbps",
    "Husary (128kbps)": "Husary_128kbps",
}

def ayah_id(surah: int, ayah: int) -> str:
    return f"{surah:03d}{ayah:03d}"

def everyayah_url(surah: int, ayah: int, reciter_folder: str) -> str:
    return f"https://everyayah.com/data/{reciter_folder}/{ayah_id(surah, ayah)}.mp3"

def surah_name(surah: int) -> str:
    if 1 <= surah <= 114:
        return SURAH_NAMES_AR[surah - 1]
    return f"سورة {surah}"

# ======================
# Config store (auto-join channel per guild)
# ======================
def load_config() -> Dict[str, Dict[str, int]]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg: Dict[str, Dict[str, int]]) -> None:
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)

config = load_config()

def get_autojoin_channel_id(guild_id: int) -> int:
    entry = config.get(str(guild_id), {})
    return int(entry.get("voice_channel_id") or 0)

def set_autojoin_channel_id(guild_id: int, channel_id: int) -> None:
    config[str(guild_id)] = {"voice_channel_id": int(channel_id)}
    save_config(config)

def clear_autojoin_channel_id(guild_id: int) -> None:
    if str(guild_id) in config:
        del config[str(guild_id)]
        save_config(config)

# ======================
# Audio Queue per Guild
# ======================
@dataclass
class Track:
    title: str
    url: str

class GuildAudio:
    def __init__(self):
        self.queue: asyncio.Queue[Track] = asyncio.Queue()
        self.voice: Optional[discord.VoiceClient] = None
        self.player_task: Optional[asyncio.Task] = None
        self.current: Optional[Track] = None
        self.lock = asyncio.Lock()

    async def ensure_player(self):
        if self.player_task is None or self.player_task.done():
            self.player_task = asyncio.create_task(self._player_loop())

    async def _player_loop(self):
        while True:
            track = await self.queue.get()
            self.current = track
            if not self.voice or not self.voice.is_connected():
                self.current = None
                continue

            source = discord.FFmpegPCMAudio(
                track.url,
                before_options=FFMPEG_BEFORE,
                options=FFMPEG_OPTS,
            )

            done = asyncio.Event()

            def _after(_err):
                done.set()

            self.voice.play(source, after=_after)
            await done.wait()
            self.current = None

    async def stop(self):
        if self.voice and self.voice.is_connected():
            if self.voice.is_playing() or self.voice.is_paused():
                self.voice.stop()

    async def clear(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Exception:
                break

# ======================
# Bot
# ======================
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
audio_states: Dict[int, GuildAudio] = {}

def get_state(guild_id: int) -> GuildAudio:
    if guild_id not in audio_states:
        audio_states[guild_id] = GuildAudio()
    return audio_states[guild_id]

async def join_voice_channel(guild: discord.Guild, channel_id: int) -> Optional[discord.VoiceClient]:
    if not guild:
        return None
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        return None

    state = get_state(guild.id)
    async with state.lock:
        if state.voice and state.voice.is_connected():
            if state.voice.channel.id != channel.id:
                await state.voice.move_to(channel)
        else:
            state.voice = await channel.connect(self_deaf=True)

        await state.ensure_player()
        return state.voice

async def join_user_vc(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.guild:
        raise RuntimeError("Guild only.")
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        raise RuntimeError("Member only.")

    vc = interaction.user.voice.channel if interaction.user.voice else None
    if not vc:
        raise RuntimeError("لازم تكون داخل روم صوتي أولاً.")

    state = get_state(interaction.guild.id)
    async with state.lock:
        if state.voice and state.voice.is_connected():
            if state.voice.channel.id != vc.id:
                await state.voice.move_to(vc)
        else:
            state.voice = await vc.connect(self_deaf=True)
        await state.ensure_player()
        return state.voice

async def enqueue_track(interaction: discord.Interaction, track: Track):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    await state.queue.put(track)
    await state.ensure_player()

# ======================
# Slash Commands Sync
# ======================
@bot.event
async def setup_hook():
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
    else:
        await bot.tree.sync()

# ======================
# Auto-rejoin loop (24/7)
# ======================
async def auto_rejoin_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for g in bot.guilds:
                ch_id = get_autojoin_channel_id(g.id)
                if not ch_id:
                    continue
                state = get_state(g.id)
                # إذا مو متصل، رجّعه
                if not state.voice or not state.voice.is_connected():
                    await join_voice_channel(g, ch_id)
            await asyncio.sleep(30)
        except Exception:
            await asyncio.sleep(10)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")
    # جرّب يدخل تلقائياً للسيرفرات اللي إلها autojoin
    for g in bot.guilds:
        ch_id = get_autojoin_channel_id(g.id)
        if ch_id:
            try:
                await join_voice_channel(g, ch_id)
            except Exception:
                pass
    # شغّل مهمة المراقبة 24/7
    if not hasattr(bot, "_auto_rejoin_started"):
        bot._auto_rejoin_started = True
        bot.loop.create_task(auto_rejoin_task())

# ======================
# Commands
# ======================
@bot.tree.command(name="help", description="شرح أوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    cmds = [
        "/join - دخول الروم الصوتي اللي أنت فيه",
        "/leave - خروج من الروم",
        "/ayah - تشغيل آية",
        "/surah - تشغيل سورة كاملة",
        "/stop - إيقاف",
        "/skip - تخطي",
        "/queue - عرض الطابور",
        "/clear - مسح الطابور",
        "/set_autojoin - يخلي البوت 24/7 بهالروم",
        "/autojoin_off - يلغي 24/7",
        "/support - رابط السيرفر",
    ]
    embed = discord.Embed(title="📖 Quran Bot Commands", description="\n".join(cmds))
    embed.add_field(name="🔗 Support Server", value=SUPPORT_INVITE, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="support", description="رابط السيرفر/الدعم")
async def support_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔗 {SUPPORT_INVITE}", ephemeral=True)

@bot.tree.command(name="join", description="يدخل الروم الصوتي اللي أنت فيه")
async def join_cmd(interaction: discord.Interaction):
    try:
        await join_user_vc(interaction)
        await interaction.response.send_message("✅ دخلت الروم الصوتي.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="leave", description="يطلع من الروم الصوتي")
async def leave_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    if state.voice and state.voice.is_connected():
        await state.clear()
        await state.stop()
        await state.voice.disconnect(force=True)
        state.voice = None
        await interaction.response.send_message("👋 طلعت من الروم.", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ️ أنا أصلاً مو داخل روم.", ephemeral=True)

# ====== 24/7 SETUP ======
@bot.tree.command(name="set_autojoin", description="يثبت البوت 24/7 في روم صوتي")
@app_commands.describe(channel="اختار روم صوتي (إذا تركته فاضي بيأخذ رومك الحالي)")
async def set_autojoin_cmd(interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
    if not interaction.guild:
        return
    # صلاحية: لازم إدارة سيرفر أو إدارة قنوات (خفيفة)
    if isinstance(interaction.user, discord.Member):
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.manage_channels or perms.administrator):
            return await interaction.response.send_message("❌ لازم تكون عندك صلاحية إدارة (Manage Server/Channels).", ephemeral=True)

    if channel is None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
            return await interaction.response.send_message("❌ ادخل روم صوتي أو اختر channel.", ephemeral=True)
        channel = interaction.user.voice.channel  # type: ignore

    set_autojoin_channel_id(interaction.guild.id, channel.id)
    try:
        await join_voice_channel(interaction.guild, channel.id)
    except Exception:
        pass
    await interaction.response.send_message(f"✅ تم تثبيت 24/7 على: **{channel.name}**", ephemeral=True)

@bot.tree.command(name="autojoin_off", description="يلغي تثبيت 24/7")
async def autojoin_off_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    if isinstance(interaction.user, discord.Member):
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.manage_channels or perms.administrator):
            return await interaction.response.send_message("❌ لازم تكون عندك صلاحية إدارة (Manage Server/Channels).", ephemeral=True)

    clear_autojoin_channel_id(interaction.guild.id)
    await interaction.response.send_message("✅ تم إلغاء 24/7.", ephemeral=True)

# ====== PLAY AYAH/SURAH ======
def reciter_choices():
    return [app_commands.Choice(name=k, value=v) for k, v in list(RECITERS.items())[:20]]

@bot.tree.command(name="ayah", description="يشغل آية")
@app_commands.describe(surah="رقم السورة 1-114", ayah="رقم الآية", reciter="القارئ")
@app_commands.choices(reciter=reciter_choices())
async def ayah_cmd(interaction: discord.Interaction, surah: int, ayah: int, reciter: Optional[app_commands.Choice[str]] = None):
    if surah < 1 or surah > 114:
        return await interaction.response.send_message("❌ رقم السورة لازم بين 1 و 114", ephemeral=True)
    max_ayah = SURAH_AYAH_COUNTS[surah - 1]
    if ayah < 1 or ayah > max_ayah:
        return await interaction.response.send_message(f"❌ السورة فيها {max_ayah} آية فقط.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    await join_user_vc(interaction)

    folder = reciter.value if reciter else DEFAULT_RECITER
    url = everyayah_url(surah, ayah, folder)
    title = f"{surah_name(surah)} • آية {ayah} ({surah}:{ayah})"
    await enqueue_track(interaction, Track(title=title, url=url))
    await interaction.followup.send(f"✅ تمت الإضافة للطابور: **{title}**", ephemeral=True)

@bot.tree.command(name="surah", description="يشغل سورة كاملة")
@app_commands.describe(surah="رقم السورة 1-114", reciter="القارئ")
@app_commands.choices(reciter=reciter_choices())
async def surah_cmd(interaction: discord.Interaction, surah: int, reciter: Optional[app_commands.Choice[str]] = None):
    if surah < 1 or surah > 114:
        return await interaction.response.send_message("❌ رقم السورة لازم بين 1 و 114", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    await join_user_vc(interaction)

    folder = reciter.value if reciter else DEFAULT_RECITER
    total = SURAH_AYAH_COUNTS[surah - 1]
    sname = surah_name(surah)

    for a in range(1, total + 1):
        url = everyayah_url(surah, a, folder)
        title = f"{sname} • آية {a} ({surah}:{a})"
        await enqueue_track(interaction, Track(title=title, url=url))

    await interaction.followup.send(f"✅ تمت إضافة **سورة {sname}** كاملة للطابور ({total} آية)", ephemeral=True)

@bot.tree.command(name="queue", description="يعرض الطابور")
async def queue_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    items = list(state.queue._queue)
    now = f"🎧 الآن: **{state.current.title}**" if state.current else "🎧 الآن: لا شيء"
    if not items:
        return await interaction.response.send_message(f"{now}\n\nالطابور فارغ.", ephemeral=True)
    preview = "\n".join([f"{i+1}. {t.title}" for i, t in enumerate(items[:15])])
    more = "" if len(items) <= 15 else f"\n… و {len(items)-15} زيادة"
    await interaction.response.send_message(f"{now}\n\n📜 الطابور:\n{preview}{more}", ephemeral=True)

@bot.tree.command(name="stop", description="يوقف التشغيل الحالي")
async def stop_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    await state.stop()
    await interaction.response.send_message("⏹️ تم الإيقاف.", ephemeral=True)

@bot.tree.command(name="skip", description="يتخطى الحالي")
async def skip_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    await state.stop()
    await interaction.response.send_message("⏭️ تم التخطي.", ephemeral=True)

@bot.tree.command(name="clear", description="يمسح الطابور")
async def clear_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return
    state = get_state(interaction.guild.id)
    await state.clear()
    await interaction.response.send_message("🧹 تم مسح الطابور.", ephemeral=True)

bot.run(TOKEN)
