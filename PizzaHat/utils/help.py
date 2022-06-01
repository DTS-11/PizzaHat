import discord
from core.cog import Cog
from discord.ext import commands


def bot_help_embed(ctx: commands.Context):

    em = discord.Embed(
        title=f"{ctx.bot.user.name} Help",
        timestamp=ctx.message.created_at,
        color=discord.Color.blue()
    )
    em.description = (
        """
Hello, welcome to the help page!\n\n
Use `help [command]` for more info on a command.\n
Use `help [category]` for more info on a command.\n
Use the dropdown menu to select a category.\n
        """
    )

    em.add_field(
        name="Support Server",
        value="For more help, consider joining the official server over at https://discord.gg/WhNVDTF",
        inline=False
    )
    em.add_field(name="About me", value=ctx.bot.description, inline=False)
    em.add_field(
        name="🔗 Links",
        value="**[Invite me](https://dsc.gg/pizza-invite)** • **[Vote](https://top.gg/bot/860889936914677770/vote)**",
        inline=False
    )

    em.set_thumbnail(url=ctx.bot.user.avatar.url)
    em.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)

    return em

def cog_help_embed(cog):
    desc = cog.full_description if cog.full_description else None

    title = cog.qualified_name
    em = discord.Embed(
        title=f'{title} Commands',
        description=(
            f"{desc}\n\n"
            "`<>` required | `[]` optional"),
        color=discord.Color.blue()
    )

    for x in sorted(cog.get_commands(), key=lambda c: c.name):
        cmd_help = x.short_doc if x.short_doc else x.help
        em.add_field(name=f"{x.name} {x.signature}", value=cmd_help, inline=False)

    em.set_footer(text='Use help [command] for more info')
    return em


class HelpDropdown(discord.ui.Select):
    def __init__(self, mapping: dict, ctx: commands.Context):
        self.cog_mapping = mapping
        self.ctx = ctx

        options = []
        cog_exceptions = ["AutoMod", "Dev", "Events", "Help", "Jishaku"]

        for cog, _ in mapping.items():
            if cog and cog.qualified_name not in cog_exceptions:
                options.append(discord.SelectOption(
                    label=cog.qualified_name,
                    emoji=cog.emoji if hasattr(cog, "emoji") else None
                ))

        super().__init__(
            placeholder="Choose a category...",
            min_values=1,
            max_values=1,
            options=sorted(options, key=lambda x: x.label)
        )
    
    async def callback(self, interaction: discord.Interaction):
        cog_name = self.values[0]
        cog = None
        
        for c, _ in self.cog_mapping.items():
            if c and c.qualified_name == cog_name:
                cog = c
                break

        await interaction.message.edit(embed=cog_help_embed(cog))


class HelpView(discord.ui.View):
    def __init__(self, mapping: dict, ctx: commands.Context):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.mapping = mapping
        self.message = None
        self.add_item(HelpDropdown(mapping, ctx))

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                child.disabled = True

            await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user == self.ctx.author:
            return True

        await interaction.response.send_message("Not your help command ._.", ephemeral=True)

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.blurple)
    async def go_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = bot_help_embed(self.ctx)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Delete Menu", emoji="🛑", style=discord.ButtonStyle.danger)
    async def delete_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()


class MyHelp(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs = {
                "help": "Help command for the bot",
                "cooldown": commands.CooldownMapping.from_cooldown(1, 3, commands.BucketType.user),
                "aliases": ['h']
            }
        )
    
    async def send(self, **kwargs):
        await self.get_destination().send(**kwargs)

    async def send_bot_help(self, mapping):
        ctx = self.context
        view = HelpView(mapping, ctx)
        view.message = await ctx.send(embed=bot_help_embed(ctx), view=view)

    async def send_command_help(self, command):
        signature = self.get_command_signature(command)
        embed = discord.Embed(
            title=signature,
            description=command.help or "No help found...",
            color=discord.Color.blue()
        )

        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=', '.join(['`' + str(alias) + '`' for alias in command.aliases]),
                inline=False
            )

        if cog := command.cog:
            embed.add_field(name="Category", value=cog.qualified_name, inline=False)

        if command._buckets and (cooldown := command._buckets._cooldown):
            embed.add_field(
                name="Cooldown",
                value=f"{cooldown.rate} per {cooldown.per:.0f} seconds",
                inline=False,
            )

        await self.send(embed=embed)

    async def send_help_embed(self, title, description, commands):
        embed = discord.Embed(
            title=title,
            description=description or "No help found...",
            color=discord.Color.blue()
        )

        for command in commands:
            cmd_help = command.short_doc if command.short_doc else command.help
            embed.add_field(
                name=self.get_command_signature(command),
                value=cmd_help or "No help found...",
                inline=False)

        await self.send(embed=embed)

    async def send_group_help(self, group):
        title = self.get_command_signature(group)
        await self.send_help_embed(title, group.help, group.commands)

    async def send_cog_help(self, cog):
        await self.send(embed=cog_help_embed(cog))

    async def send_error_message(self, error):
        channel = self.get_destination()
        await channel.send(error)


class Help(Cog, emoji="❓"):
    def __init__(self, bot):
        self.bot = bot
        help_command = MyHelp()
        help_command.cog = self
        bot.help_command = help_command


async def setup(bot):
    await bot.add_cog(Help(bot))
