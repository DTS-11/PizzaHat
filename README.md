<h1 align="center">
    <img src="./assets/bot-logo.png" width="300" height="300"/> <br>
PizzaHat Discord Bot <h1/>
	
<h4 align="center"> Your ultimate Discord companion! <h4/>
  </a><br>
  <img src="https://img.shields.io/badge/discord.py-2.3.2-blue?style=flat" />
  <img src="https://img.shields.io/badge/Python-3.11-green?style=flat&logo=python" />
  <img src="https://github.com/DTS-11/PizzaHat/actions/workflows/codeql-analysis.yml/badge.svg" />
</h1>
	

## ℹ️ • Info

[PizzaHat](https://pizzahat.netlify.app) is a multi-purpose bot, made to satisfy your needs, as well as your server's needs too! This project is open source so that other developers could work on it and make it even better!

	
## <img src="https://cdn.discordapp.com/emojis/800797566471897088.png?size=80" height="30px"> • Features

- 📌 Over 150+ commands! </li>
- 🔼 95%+ uptime. </li>
- 🏓 Low latency. </li>
- <img src="https://cdn.discordapp.com/emojis/847248846526087239.png?size=80" height="19px"> Powerful moderation. </li>
- 🥳 Fun commands. </li>
- ⚒️ Utility commands. </li>
- 📔 Logging system. </li>
- 🗳 Poll voting system </li>
- 🏷 Tag system </li>
- 🎟 Ticket system </li>
- <img src="https://cdn.discordapp.com/emojis/809170074006192130.png?size=80" height="19px"> Updated and maintained! </li>
	
## <img src='https://cdn.discordapp.com/emojis/802615573556363284.png?size=80' height="30px"> • How to contribute?

- Fork the repo.
- Create a new branch
- Add features/changes (with proper docs for help)
- Format code with Black & organise imports by using isort (vscode extension)
- Commit and push the changes
- Submit pull request

	
## <img src="https://cdn.discordapp.com/emojis/802615572080099378.png?size=80" height="30px"> • Self hosting

I'd prefer if you don't run an instance of this bot. Just use the `invite` command to invite the bot to your server. The code here is for **_educational an developmental purposes only!_** <br>\
Anyways, if you still want to self host this, here are the steps:
<b>
- Install [Python 3.8 or higher](https://www.python.org/downloads/)

- Install [Git](https://git-scm.com/downloads)

- Clone the repo
```bash
$ git clone https://github.com/DTS-11/PizzaHat.git
```

- Install the dependencies
```bash
cd PizzaHat
pip install -r requirements.txt
```

- Configuring the bot <br>
Create a `.env` file with the following format
```
TOKEN = your_bot_token
PG_URL = postgresql_connection_url
```
Create a `config.py` file in the `utils` directory
```py
COG_EXCEPTIONS = [
    "AntiAltsConfig",
    "AutoModConfig",
    "Dev",
    "Events",
    "Help",
    "Jishaku",
]

BANNED_WORDS = [
  "list of",
  "banned words",
  "for automod",
]
```

- Running the bot
```bash
python .
```
Run this command in 'PizzaHat/PizzaHat' directory \
<br>
****
Note: 

- We do not provide support for self-hosting. If you are unable to self host PizzaHat by yourself, just use the bot itself which we put lot's of work into.

- You also CANNOT USE self-hosted version commercially (ie: public bot or using this code for money).

- You CANNOT USE PizzaHat's name, logo in your bot.

- You MUST give credits to the repository and to the contributors.
****
<br>


<!-- Please DON'T run an instance of this bot. The code here is for **educational and development purpose only!** Instead, I'd recommend inviting the bot. And the bot is not made to be configurable. 

If you decide to run your own instance, you should change the necessary things and give credits to the repo and it's contributors.We **WILL NOT** provide support on self-hosting -->

<br>
<h2 align="center"> <a href="https://dsc.gg/pizza-invite">Invite Bot</a> | <a href="https://discord.gg/WhNVDTF">Discord server</a> <h2/>
