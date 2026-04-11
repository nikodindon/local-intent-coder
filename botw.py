import sys, os
# Hide console window
sys.stdout = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log"), "w")
sys.stderr = sys.stdout

import bot
bot.main()
