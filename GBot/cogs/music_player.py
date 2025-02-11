# -*- coding: utf-8 -*-
import asyncio

from GBot.core import GeneralBotCore
from GBot.data.voice import VoiceState
import discord
from discord import ui
from discord.ext import commands
from discord.ext.commands import Context
import youtube_dl
import datetime
import random
import os
from apiclient.discovery import build
from typing import List

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {'options': '-vn'}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data
        print(self.data)
        self.title: str = data.get('title')
        self.thumbnail: str = data.get('thumbnail')
        self.duration: int = data.get('duration')
        self.channel: str = data.get('channel')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        print(url)
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(
            discord.FFmpegPCMAudio(
                filename,
                **ffmpeg_options
            ),
            data=data
        )


class Music_View(ui.View):
    def __init__(self, item):
        super().__init__()
        for i in item:
            self.add_item(i)


class Music_Select(ui.Select):
    def __init__(self, args):
        select_list: List[str] = []
        for item in args:
            select_list.append(
                discord.SelectOption(
                    label=item,
                    description=''
                )
            )

        super().__init__(
            placeholder='',
            min_values=1,
            max_values=1,
            options=select_list
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f'{self.values[0]}を選択しました'
        )


class Music_Player(commands.Cog):
    def __init__(self, bot: GeneralBotCore):
        self.bot = bot
        self.youtube = build(
            'youtube',
            'v3',
            developerKey=os.environ["YOUTUBE_API_KEY"]
        )
        self.queue = {}

    @commands.group(name="music", aliases=["m"], invoke_without_command=True)
    async def music(self, ctx):
        """Music commands"""
        if ctx.invoked_subcommand is None:
            return

    def get_h_m_s(self, td):
        m, s = divmod(td.seconds, 60)
        h, m = divmod(m, 60)
        return h, m, s

    def get_video_info(self, part, keyword, order, type):
        video_list: List[dict] = []
        video_infos: List[str] = []
        search_response = self.youtube.search().list(
            part=part,
            q=keyword,
            order=order,
            type=type
        )
        output = self.youtube.search().list(
            part=part,
            q=keyword,
            order=order,
            type=type
        ).execute()
        for _ in range(2):
            video_list.append(output["items"])
            search_response = self.youtube.search().list_next(
                search_response,
                output
            )
            output = search_response.execute()
        for video in video_list:
            video_infos.append(video["snippet"]["title"])
        return video_infos

    async def create_embed(self, source: YTDLSource):
        embed = discord.Embed(title="キューに追加...", color=0x00ff00)
        embed.add_field(name="曲名", value=source.title)
        td = datetime.timedelta(seconds=source.duration)
        h, m, s = self.get_h_m_s(td)
        embed.add_field(name="再生時間", value=f"{h}時間{m}分{s}秒")
        embed.add_field(name="チャンネル名 ", value=source.channel)
        embed.set_image(url=source.thumbnail)
        return embed

    async def register_queue(self, ctx: Context, url):
        if not url in "https":
            search_result = self.get_video_info(
                part="snippet",
                keyword=url,
                order="relevance",
                type="video"
            )
            await 
        else:
            await self.create_music(ctx, url)

    async def create_music(self, ctx, url):
        source = await YTDLSource.from_url(
            url,
            loop=self.bot.loop,
            stream=True
        )
        if ctx.guild.id not in self.queue:
            self.queue[ctx.guild.id] = []
        self.queue[ctx.guild.id].append(source)
        return self.queue[ctx.guild.id]

    async def play_only(self, ctx: Context):
        """Play only"""
        if len(self.queue[ctx.guild.id]) == 0:
            await ctx.send("キューが空になりました。")
        async with ctx.typing():
            source = self.queue[ctx.guild.id][-1]
            await ctx.send(embed=await self.create_embed(source))
            if ctx.voice_client.is_playing():
                return
            ctx.guild.voice_client.play(
                source,
                after=lambda _: self.bot.loop.create_task(self.play_end(ctx)))

    async def play_end(self, ctx):
        """play_end"""
        self.queue[ctx.guild.id].pop(-1)
        if len(self.queue[ctx.guild.id]) == 0:
            await ctx.send("キューが空になりました。")
            return
        await self.play_only(ctx)

    @music.command(name="play", aliases=["p"], help="指定したURLを再生します。")
    async def play(self, ctx, url):
        if ctx.author.voice is None:
            await ctx.reply("あなたはボイスチャンネルに接続していません。")
            return
        if ctx.guild.voice_client is None:
            if not self.bot.voice[ctx.guild.id] == VoiceState.NOT_PLAYED:
                await ctx.reply("使用中です。")
                return
            self.bot.voice[ctx.guild.id] = VoiceState.MUSIC
            await ctx.author.voice.channel.connect()
            await ctx.reply("接続しました。")
        await self.register_queue(ctx, url)
        await self.play_only(ctx)

    @music.command(name="stop", aliases=["s"], help="再生を停止します。")
    async def stop(self, ctx):
        if self.bot.voice[ctx.guild.id] == VoiceState.NOT_PLAYED:
            await ctx.reply("接続していません。")
        self.bot.voice[ctx.guild.id] = VoiceState.NOT_PLAYED
        ctx.voice_client.stop()
        await ctx.reply("停止しました。")

    @music.command(name="pause", help="再生を一時停止します。")
    async def pause(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.reply("一時停止しました。")
        await ctx.reply("再生中ではありません。")

    @music.command(name="resume", aliases=["r"], help="再生を再開します。")
    async def resume(self, ctx):
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.reply("再開しました。")
        await ctx.reply("再生中です。")

    @music.command(name="skip", aliases=["next"], help="次の曲を再生します。")
    async def skip(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.reply("スキップしました。")
        await ctx.reply("再生中ではありません。")

    @music.command(name="queue", aliases=["q"], help="再生リストを表示します。")
    async def queue(self, ctx):
        if ctx.guild.id not in self.queue:
            await ctx.reply("キューが空です。")
            return
        embed = discord.Embed(title="キュー", color=0x00ff00)
        for i, source in enumerate(self.queue[ctx.guild.id]):
            td = datetime.timedelta(seconds=source.duration)
            h, m, s = self.get_h_m_s(td)
            embed.add_field(name=f"{i + 1}",
                            value=f"{source.title} [{h}時間{m}分{s}秒]",
                            inline=False)
        await ctx.send(embed=embed)

    @music.command(name="clear", aliases=["c"], help="キューを空にします。")
    async def clear(self, ctx):
        if ctx.guild.id not in self.queue:
            await ctx.reply("キューが空です。")
            return
        self.queue[ctx.guild.id] = []
        await ctx.reply("キューを空にしました。")

    @music.command(name="volume", aliases=["v"], help="音量を変更します。")
    async def volume(self, ctx, volume: int):
        if volume < 0 or volume > 100:
            await ctx.reply("0から100の間で指定してください。")
            return
        ctx.voice_client.source.volume = volume / 100
        await ctx.reply(f"音量を{volume}%にしました。")

    @music.command(name="now", aliases=["n"], help="再生中の曲を表示します。")
    async def now(self, ctx):
        if ctx.guild.id not in self.queue:
            await ctx.reply("キューが空です。")
            return
        source = self.queue[ctx.guild.id][-1]
        await ctx.send(embed=await self.create_embed(source))

    @music.command(name="shuffle", aliases=["random"], help="再生リストをシャッフルします。")
    async def shuffle(self, ctx):
        if ctx.guild.id not in self.queue:
            await ctx.reply("キューが空です。")
            return
        random.shuffle(self.queue[ctx.guild.id])
        await ctx.reply("シャッフルしました。")

    @music.command(name="repeat", aliases=["rp"], help="再生リストを繰り返し再生します。")
    async def repeat(self, ctx):
        if ctx.guild.id not in self.queue:
            await ctx.reply("キューが空です。")
            return
        self.queue[ctx.guild.id].append(self.queue[ctx.guild.id][-1])
        await ctx.reply("リピートしました。")

    @music.command(name="leave", aliases=["l"], help="ボイスチャンネルから退出します。")
    async def leave(self, ctx):
        if ctx.guild.voice_client is None:
            await ctx.reply("ボイスチャンネルに接続していません。")
            return
        await ctx.voice_client.disconnect()
        await ctx.reply("切断しました。")

    @music.command(name="help", aliases=["h"], help="ヘルプを表示します。")
    async def help(self, ctx):
        embed = discord.Embed(title="ヘルプ", color=0x00ff00)
        embed.add_field(name="play", value="指定したURLを再生します。", inline=False)
        embed.add_field(name="stop", value="再生を停止します。", inline=False)
        embed.add_field(name="pause", value="再生を一時停止します。", inline=False)
        embed.add_field(name="resume", value="再生を再開します。", inline=False)
        embed.add_field(name="skip", value="再生をスキップします。", inline=False)
        embed.add_field(name="queue", value="再生リストを表示します。", inline=False)
        embed.add_field(name="clear", value="再生リストを空にします。", inline=False)
        embed.add_field(name="shuffle", value="再生リストをシャッフルします。", inline=False)
        embed.add_field(name="repeat", value="再生リストをリピートします。", inline=False)
        embed.add_field(name="leave", value="ボイスチャンネルから切断します。", inline=False)
        embed.add_field(name="volume", value="音量を変更します。", inline=False)
        embed.add_field(name="now", value="再生中の曲を表示します。", inline=False)
        embed.add_field(
            name="help",
            value="ヘルプを表示します。",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.guild.id not in self.queue:
            return
        if before.channel is None and after.channel is not None:
            source = self.queue[member.guild.id][-1]
            await self.play(member.guild, source)


def setup(bot):
    bot.add_cog(Music_Player(bot))
