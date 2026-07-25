from flask import Flask, jsonify
from bot import NaijaBot
import asyncio
import os
import logging
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = None
bot_thread = None
is_running = False

def run_bot_loop():
    """Run the bot in a separate thread"""
    global bot, is_running
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_bot():
        global bot, is_running
        try:
            bot = NaijaBot()
            await bot.initialize()
            logger.info("🤖 Bot is now listening for messages...")
            is_running = True
            
            # Keep bot running and listening
            await bot.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            is_running = False
        finally:
            if bot:
                await bot.cleanup()
            is_running = False
    
    loop.run_until_complete(start_bot())

@app.route('/')
def home():
    return "🇳🇬 NaijaAI Bot is running! 🤖"

@app.route('/start')
def start_bot():
    """Start the bot if not running"""
    global bot_thread, is_running
    
    if is_running:
        return jsonify({"status": "already running"})
    
    bot_thread = threading.Thread(target=run_bot_loop, daemon=True)
    bot_thread.start()
    
    return jsonify({"status": "starting", "message": "Bot is starting..."})

@app.route('/status')
def status():
    return jsonify({
        "running": is_running,
        "time": datetime.now().isoformat()
    })

@app.route('/trigger')
def trigger():
    """Keep for cron-job.org to wake up the bot"""
    if not is_running:
        start_bot()
        return jsonify({"status": "triggered", "message": "Bot started"})
    return jsonify({"status": "already running"})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    # Start bot on launch
    threading.Thread(target=run_bot_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=port)
