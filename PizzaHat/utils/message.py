import asyncio
from typing import Union

import discord
from discord.ext import commands


async def wait_for_msg(
    ctx: commands.Context, timeout: int, msg_to_edit: discord.Message
) -> Union[discord.Message, str]:
    def check(msg: discord.Message):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        m = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        try:
            await m.delete()
        except Exception:
            pass

        if m.content.lower() == "cancel":
            await msg_to_edit.edit(content="Cancelled")
            return "pain"

    except asyncio.TimeoutError:
        await msg_to_edit.edit(content="Timed out")
        return "pain"

    return m
