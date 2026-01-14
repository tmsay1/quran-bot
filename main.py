import os
import asyncio
import aiohttp
import discord
from discord import app_commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN is missing. Set it in Railway Variables.")

# حط رابط سيرفرك هون (اختياري)
SUPPORT_INVITE = os.getenv("SUPPORT_INVITE", "https://discord.gg/KVuBY5Zwzk").strip()

# إذا بدك 24/7 تلقائي بعد كل Restart: حط ID روم صوتي
AUTOJOIN_VOICE_CHANNEL_ID = int(os.getenv("AUTOJOIN_VOICE_CHANNEL_ID", "0") or "0")

# عشان أوامر / تظهر فورًا بسيرفرك (مهم جدا للتجربة)
GUILD_ID = int(os.getenv("GUILD_ID", "0") or "0")

# Reciter (Edition) افتراضي
DEFAULT_EDITION = os.getenv("QURAN_EDITION", "ar.alafasy").strip()

FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = "-vn"


class GuildPlayer:
    def __init__(self):
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.now_playing: str | None = None

    async def ensure_task(self, vc: discord.VoiceClient):
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self._loop(vc))

    async def _loop(self, vc: discord.VoiceClient):
        while True:
            url, title = await self.queue.get()
            self.now_playing = title

            loop = asyncio.get_running_loop()
            done = loop.create_future()

            def _after(err: Exception | None):
                if err:
                    print("Voice error:", err)
                if not done.done():
                    loop.call_soon_threadsafe(done.set_result, True)

            source = discord.FFmpegPCMAudio(
                url,
                before_options=FFMPEG_BEFORE,
                options=FFMPEG_OPTS,
            )
            vc.play(source, after=_after)
            await done
            self.queue.task_done()


class QuranBot(discord.Client):
    def __init__(self):
        intents = discord.Intents(guilds=True, voice_states=True)
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None
        self.players: dict[int, GuildPlayer] = {}
        self.autojoin_channel: dict[int, int] = {}  # guild_id -> voice_channel_id

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))

        # Sync commands
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
            else:
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} global commands (may take time to appear)")
        except Exception as e:
            print("Sync failed:", e)

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")

        # Auto-join 24/7 if env set
        if AUTOJOIN_VOICE_CHANNEL_ID:
            await self._try_autojoin_by_channel_id(AUTOJOIN_VOICE_CHANNEL_ID)

    async def on_voice_state_update(self, member, before, after):
        # لو انقطع البوت عن الروم، يرجع يدخل
        if not self.user or member.id != self.user.id:
            return
        if before.channel and after.channel is None:
            guild_id = member.guild.id
            ch_id = self.autojoin_channel.get(guild_id) or AUTOJOIN_VOICE_CHANNEL_ID
            if ch_id:
                await asyncio.sleep(3)
                await self._try_autojoin_by_channel_id(ch_id)

    async def _try_autojoin_by_channel_id(self, channel_id: int):
        try:
            ch = self.get_channel(channel_id)
            if ch is None:
                ch = await self.fetch_channel(channel_id)
            if isinstance(ch, discord.VoiceChannel):
                if ch.guild.voice_client and ch.guild.voice_client.is_connected():
                    return
                await ch.connect(timeout=20, reconnect=True)
                self.autojoin_channel[ch.guild.id] = ch.id
                print(f"Auto-joined: {ch.guild.name} ({ch.id})")
        except Exception as e:
            print("Auto-join failed:", e)

    async def ensure_vc(self, interaction: discord.Interaction, channel: discord.VoiceChannel | None = None):
        if not interaction.guild:
            raise RuntimeError("Guild only command.")
        guild = interaction.guild

        if guild.voice_client and guild.voice_client.is_connected():
            return guild.voice_client

        if channel is None:
            if not interaction.user or not isinstance(interaction.user, discord.Member):
                raise RuntimeError("No member.")
            if not interaction.user.voice or not interaction.user.voice.channel:
                raise RuntimeError("You must be in a voice channel.")
            channel = interaction.user.voice.channel

        return await channel.connect(timeout=20, reconnect=True)

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    async def fetch_surah(self, surah: int, edition: str):
        assert self.session is not None
        url = f"https://api.alquran.cloud/v1/surah/{surah}/{edition}"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
        return data["data"]

    async def fetch_ayah(self, surah: int, ayah: int, edition: str):
        assert self.session is not None
        url = f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/{edition}"
        async with self.session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
        return data["data"]


bot = QuranBot()


@bot.tree.command(name="help", description="شرح أوامر البوت")
async def help_cmd(interaction: discord.Interaction):
    txt = (
        "**أوامر البوت:**\n"
        "• `/join` دخول رومك الصوتي\n"
        "• `/play_surah surah:1` تشغيل سورة كاملة\n"
        "• `/play_ayah surah:1 ayah:1` تشغيل آية\n"
        "• `/random` تشغيل آية عشوائية\n"
        "• `/stop` إيقاف\n"
        "• `/now` الآن يتم تشغيل\n"
        "• `/set_autojoin` يخلي البوت يرجع يدخل 24/7 بعد أي Restart\n"
        f"• `/support` سيرفرك\n"
    )
    await interaction.response.send_message(txt, ephemeral=True)


@bot.tree.command(name="support", description="رابط السيرفر (Support)")
async def support_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Support server: {SUPPORT_INVITE}", ephemeral=True)


@bot.tree.command(name="join", description="البوت يدخل الروم الصوتي تبعك")
async def join_cmd(interaction: discord.Interaction):
    try:
        vc = await bot.ensure_vc(interaction)
        await interaction.response.send_message(f"✅ دخلت: **{vc.channel}**", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)


@bot.tree.command(name="set_autojoin", description="خلي البوت يرجع يدخل 24/7 لنفس الروم بعد أي Restart")
async def set_autojoin_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Guild فقط.", ephemeral=True)
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        return await interaction.response.send_message("Member فقط.", ephemeral=True)
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message("ادخل روم صوتي أولاً.", ephemeral=True)

    ch = interaction.user.voice.channel
    bot.autojoin_channel[interaction.guild.id] = ch.id
    await interaction.response.send_message(
        f"✅ Auto-Join صار على: **{ch.name}**\n"
        f"ملاحظة: إذا بدك يضل ثابت حتى بعد Deploy جديد، حط بمتغيرات Railway:\n"
        f"`AUTOJOIN_VOICE_CHANNEL_ID = {ch.id}`",
        ephemeral=True
    )


@bot.tree.command(name="stop", description="إيقاف التشغيل ومسح الطابور")
async def stop_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Guild فقط.", ephemeral=True)

    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        vc.stop()

    player = bot.players.get(interaction.guild.id)
    if player:
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
                player.queue.task_done()
            except Exception:
                break
        player.now_playing = None

    await interaction.response.send_message("⏹️ تم الإيقاف.", ephemeral=True)


@bot.tree.command(name="now", description="شو عم يشتغل هسا")
async def now_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message("Guild فقط.", ephemeral=True)
    player = bot.players.get(interaction.guild.id)
    if not player or not player.now_playing:
        return await interaction.response.send_message("مافي شي شغال.", ephemeral=True)
    await interaction.response.send_message(f"🎧 Now: **{player.now_playing}**", ephemeral=True)


@bot.tree.command(name="play_surah", description="تشغيل سورة كاملة (114 سورة)")
@app_commands.describe(surah="رقم السورة 1-114", edition="قارئ (مثال: ar.alafasy)")
async def play_surah_cmd(interaction: discord.Interaction, surah: int, edition: str = DEFAULT_EDITION):
    if surah < 1 or surah > 114:
        return await interaction.response.send_message("السورة لازم بين 1 و 114.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    try:
        vc = await bot.ensure_vc(interaction)
        data = await bot.fetch_surah(surah, edition)
        ayahs = data["ayahs"]
        surah_name = data.get("englishName", f"Surah {surah}")

        player = bot.get_player(interaction.guild.id)
        for a in ayahs:
            audio = a.get("audio")
            num = a.get("numberInSurah")
            if audio:
                await player.queue.put((audio, f"{surah_name} - Ayah {num}"))

        await player.ensure_task(vc)
        await interaction.followup.send(f"✅ تم إضافة **{len(ayahs)}** آية لطابور سورة **{surah_name}**.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)


@bot.tree.command(name="play_ayah", description="تشغيل آية محددة")
@app_commands.describe(surah="رقم السورة 1-114", ayah="رقم الآية", edition="قارئ (مثال: ar.alafasy)")
async def play_ayah_cmd(interaction: discord.Interaction, surah: int, ayah: int, edition: str = DEFAULT_EDITION):
    if surah < 1 or surah > 114:
        return await interaction.response.send_message("السورة لازم بين 1 و 114.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    try:
        vc = await bot.ensure_vc(interaction)
        data = await bot.fetch_ayah(surah, ayah, edition)
        audio = data.get("audio")
        if not audio:
            return await interaction.followup.send("ما لقيت Audio لهاي الآية.", ephemeral=True)

        player = bot.get_player(interaction.guild.id)
        await player.queue.put((audio, f"Surah {surah} - Ayah {ayah}"))
        await player.ensure_task(vc)

        await interaction.followup.send(f"✅ تم إضافة: سورة **{surah}** آية **{ayah}**", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)


@bot.tree.command(name="random", description="تشغيل آية عشوائية")
@app_commands.describe(edition="قارئ (مثال: ar.alafasy)")
async def random_cmd(interaction: discord.Interaction, edition: str = DEFAULT_EDITION):
    import random
    surah = random.randint(1, 114)
    await interaction.response.defer(ephemeral=True)
    try:
        # نجيب السورة لنحدد عدد الآيات ثم نختار عشوائي
        data = await bot.fetch_surah(surah, edition)
        ayahs = data["ayahs"]
        ayah = random.randint(1, len(ayahs))

        vc = await bot.ensure_vc(interaction)
        a = ayahs[ayah - 1]
        audio = a.get("audio")
        if not audio:
            return await interaction.followup.send("ما لقيت Audio.", ephemeral=True)

        player = bot.get_player(interaction.guild.id)
        await player.queue.put((audio, f"Surah {surah} - Ayah {ayah}"))
        await player.ensure_task(vc)

        await interaction.followup.send(f"✅ Random: سورة **{surah}** آية **{ayah}**", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)


bot.run(DISCORD_TOKEN)



