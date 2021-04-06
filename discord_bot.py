import asyncio
from twitchio.dataclasses import Message
from os import pipe
import shlex
import subprocess

import discord
from discord.voice_client import VoiceClient
from discord.errors import ClientException

from discord.ext import commands
from discord.player import CREATE_NO_WINDOW, FFmpegAudio
from discord.opus import Encoder as OpusEncoder

from twitchio.ext import commands as twitch_commands

from voice_actor import voice_act
from omegaconf import OmegaConf

import uuid
import os

ffmpeg_options = {
    'options': '-vn'
}

tokens = OmegaConf.load('tokens.yaml')

class FFmpegPCMAudioBytesIO(FFmpegAudio):
    """An audio source from FFmpeg (or AVConv).

    This launches a sub-process to a specific input file given.

    .. warning::

        You must have the ffmpeg or avconv executable in your path environment
        variable in order for this to work.

    Parameters
    ------------
    source: Union[:class:`str`, :class:`io.BufferedIOBase`]
        The input that ffmpeg will take and convert to PCM bytes.
        If ``pipe`` is ``True`` then this is a file-like object that is
        passed to the stdin of ffmpeg.
    executable: :class:`str`
        The executable name (and path) to use. Defaults to ``ffmpeg``.
    pipe: :class:`bool`
        If ``True``, denotes that ``source`` parameter will be passed
        to the stdin of ffmpeg. Defaults to ``False``.
    stderr: Optional[:term:`py:file object`]
        A file-like object to pass to the Popen constructor.
        Could also be an instance of ``subprocess.PIPE``.
    before_options: Optional[:class:`str`]
        Extra command line arguments to pass to ffmpeg before the ``-i`` flag.
    options: Optional[:class:`str`]
        Extra command line arguments to pass to ffmpeg after the ``-i`` flag.

    Raises
    --------
    ClientException
        The subprocess failed to be created.
    """

    def __init__(self, source, *, executable='ffmpeg', stderr=None, before_options=None, options=None):
        args = []
        self._source = source
        subprocess_kwargs = {'stderr': stderr, 'stdin': subprocess.PIPE}

        if isinstance(before_options, str):
            args.extend(shlex.split(before_options))

        args.append('-i')
        args.append('-')
        args.extend(('-f', 's16le', '-ar', '48000', '-ac', '2', '-loglevel', 'warning'))

        if isinstance(options, str):
            args.extend(shlex.split(options))

        args.append('pipe:1')

        super().__init__(source, executable=executable, args=args, **subprocess_kwargs)

    def read(self):
        ret = self._stdout.read(OpusEncoder.FRAME_SIZE)
        if len(ret) != OpusEncoder.FRAME_SIZE:
            return b''
        return ret

    def is_opus(self):
        return False

    def _spawn_process(self, args, **subprocess_kwargs):
        process = None
        try:
            process = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW, **subprocess_kwargs)
            process.stdin.write(self._source)
            process.stdin.close()
        except FileNotFoundError:
            executable = args.partition(' ')[0] if isinstance(args, str) else args[0]
            raise ClientException(executable + ' was not found.') from None
        except subprocess.SubprocessError as exc:
            raise ClientException('Popen failed: {0.__class__.__name__}: {0}'.format(exc)) from exc
        else:
            return process


class Twitch(commands.Cog):
    def __init__(self, bot: discord.Client):
        self._voice_clients = {}
        self.discord_bot = bot

        self.bot: twitch_commands.Bot = twitch_commands.Bot(
            # set up the bot
            irc_token=tokens['twitch'],
            api_tocken='test',
            nick='IAM0VERIT',
            prefix='!',
            initial_channels=[]
        )
        self.discord_bot.loop.create_task(self.bot.start())
        # self.bot.command(name="help")(self.twitch_command)
        self.bot.listen("event_message")(self.event_message)

    # Discord.py event
    @commands.Cog.listener()
    async def on_message(self, message):
        print(message.content)


    @commands.command()
    async def read(self, ctx, *, query):
        """Read text to a voice channel"""

        await ctx.send('Now reading: {}'.format(query))
        filename = uuid.uuid4().hex
        count = voice_act(query, filename)
        lock = asyncio.Lock()
        def after(e):
            lock.release()
            print('Player error: %s' % e) if e else None
        for i in range(0, count):
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(f'{filename}-{i}.wav'))
            if ctx.voice_client is not None and ctx.voice_client.is_connected():
                await lock.acquire()
                ctx.voice_client.play(source, after=after)
                await lock.acquire()
                os.remove(f'{filename}-{i}.wav')
                lock.release()
            else: 
                await ctx.send('Voice is not connected. Use !tjoin <channel> command.')

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    async def tjoin(self, ctx: commands.Context, *, channel):
        """Joins a voice channel"""
        if ctx.voice_client is None:
            if ctx.author.voice:
                voice_client = await ctx.author.voice.channel.connect()
                self._voice_clients.update({ctx.author.guild: channel})
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        print(f'Joining to a channel: {channel}')
        await self.bot.join_channels([channel])
        await ctx.send('Joined to: {}'.format(channel))
        await self.bot.get_channel(channel).send('Hi there from discord!')

    @commands.command()
    async def stop(self, ctx: commands.Context):
        """Stops and disconnects the bot from voice"""
        self._voice_clients = dict((k, v) for (k, v) in self._voice_clients.items() if not (k == ctx.author.guild))
        await ctx.voice_client.disconnect()

    # Discord command
    @commands.command()
    async def test(self, ctx):
        await ctx.send('Hai there! discord')


    # TwitchIO event
    async def event_message(self, message: Message):
        """Reads text to voice"""
        if(message.author.tags.get('msg-id')=='highlighted-message'):
            for voice_client_guild, twitch_channel in self._voice_clients.items():
                if twitch_channel == message.channel.name:
                    # audio = FFmpegPCMAudioBytesIO(voice_act(message.content))
                    # source = discord.PCMVolumeTransformer(audio)
                    filename = uuid.uuid4().hex
                    count = voice_act(message.content, filename)
                    lock = asyncio.Lock()
                    def after(e):
                        lock.release()
                        print('Player error: %s' % e) if e else None
                    for i in range(0, count):
                        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(f'{filename}-{i}.wav'))
                        voice_client: VoiceClient = voice_client_guild.voice_client
                        if voice_client is not None and voice_client.is_connected():
                            await lock.acquire()
                            voice_client.play(source, after=after)
                            await lock.acquire()
                            os.remove(f'{filename}-{i}.wav')
                            lock.release()
                        else: 
                            await message.channel.send('Voice is not connected. Use !tjoin <channel> command on discord.')

    # TwitchIO command
    # async def twitch_command(self, ctx):
    #     await ctx.send('Hai there! twitch')

    # @tjoin.before_invoke
    # async def ensure_voice(self, ctx):
    #     if ctx.voice_client is None:
    #         if ctx.author.voice:
    #             await ctx.author.voice.channel.connect()
    #         else:
    #             await ctx.send("You are not connected to a voice channel.")
    #             raise commands.CommandError("Author not connected to a voice channel.")
    #     elif ctx.voice_client.is_playing():
    #         ctx.voice_client.stop()


bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"),
                   description='voice-acting-twitch-bot')

@bot.event
async def on_ready():
    print('Logged in as {0} ({0.id})'.format(bot.user))
    print('------')
    # channel = bot.get_channel(258153826920562689)
    # await channel.connect()


if __name__ == '__main__':
    bot.add_cog(Twitch(bot))
    bot.run(tokens['discord'])