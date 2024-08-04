import asyncio
from typing import Union

from discord import Message
from discord.ext.commands import Context


async def wait_for_msg(
    ctx: Context, timeout: int, msg_to_edit: Message
) -> Union[Message, str]:
    def check(msg: Message):
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        m: Message = await ctx.bot.wait_for("message", check=check, timeout=timeout)
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
