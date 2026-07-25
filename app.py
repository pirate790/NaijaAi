from flask import Flask, request, jsonify
from bot import NaijaBot
import asyncio
import os
import logging
from datetime import datetime
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
naija_bot = NaijaBot()
is_running = False

@app.route('/')
def home():
    return "🇳🇬 NaijaAI Bot is running! 🤖"

@app.route('/test')
def test():
    """Test connection to Telegram"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def test_connection():
            await naija_bot.initialize()
            me = await naija_bot.client.get_me()
            await naija_bot.cleanup()
            return me.username
            
        username = loop.run_until_complete(test_connection())
        loop.close()
        return jsonify({"status": "success", "message": f"Connected as @{username}"})
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/trigger', methods=['GET', 'POST'])
def trigger_bot():
    global is_running
    
    if is_running:
        return jsonify({"status": "error", "message": "Bot already running"}), 409
    
    is_running = True
    logger.info("🔄 Bot triggered via cron-job.org")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run_bot():
            try:
                # Initialize bot
                logger.info("Initializing bot...")
                await naija_bot.initialize()
                
                # Get bot info
                me = await naija_bot.client.get_me()
                logger.info(f"✅ Bot active: @{me.username}")
                
                # Send a test message (optional - remove if you don't want this)
                # await naija_bot.client.send_message('me', 'Bot triggered at ' + str(datetime.now()))
                
                # Cleanup
                await naija_bot.cleanup()
                logger.info("✅ Bot task completed successfully")
                return True
                
            except Exception as e:
                logger.error(f"❌ Error in bot execution: {e}")
                logger.error(traceback.format_exc())
                try:
                    await naija_bot.cleanup()
                except:
                    pass
                return False
                
        result = loop.run_until_complete(run_bot())
        loop.close()
        is_running = False
        
        if result:
            return jsonify({
                "status": "success",
                "message": "Bot executed successfully!",
                "time": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Bot execution failed"
            }), 500
            
    except Exception as e:
        is_running = False
        logger.error(f"❌ Trigger error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status')
def status():
    try:
        is_connected = naija_bot.client is not None and naija_bot.client.is_connected()
        return jsonify({
            "status": "connected" if is_connected else "disconnected",
            "running": is_running,
            "time": datetime.now().isoformat()
        })
    except:
        return jsonify({
            "status": "unknown",
            "running": is_running,
            "time": datetime.now().isoformat()
        })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
