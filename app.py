from flask import Flask, jsonify, request
from bot import NaijaBot
import asyncio
import os
import sys
import json
import time
import signal
import logging
import threading
from datetime import datetime
from functools import wraps
from typing import Dict, Any

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('flask_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

STATE_FILE = 'bot_state.json'
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_PERIOD = 60  # seconds

# ==================== FLASK APP ====================

app = Flask(__name__)

# Global variables
bot = None
bot_thread = None
is_running = False
start_time = datetime.now()
rate_limit_store: Dict[str, tuple] = {}

# ==================== RATE LIMITING ====================

def rate_limit(limit=RATE_LIMIT_REQUESTS, per=RATE_LIMIT_PERIOD):
    """Rate limit decorator for Flask routes"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            now = time.time()
            key = f"{ip}:{f.__name__}"
            
            if key in rate_limit_store:
                requests, start = rate_limit_store[key]
                if now - start < per:
                    if requests >= limit:
                        return jsonify({
                            "error": "Rate limit exceeded",
                            "retry_after": per - (now - start)
                        }), 429
                    rate_limit_store[key] = (requests + 1, start)
                else:
                    rate_limit_store[key] = (1, now)
            else:
                rate_limit_store[key] = (1, now)
            
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ==================== REQUEST LOGGING ====================

@app.before_request
def log_request():
    """Log all incoming requests"""
    logger.info(f"📥 {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response(response):
    """Log all responses"""
    logger.info(f"📤 {response.status_code} for {request.path}")
    return response

# ==================== BOT FUNCTIONS ====================

def save_state():
    """Save bot state to file"""
    global bot, is_running
    try:
        state = {
            'is_running': is_running,
            'last_start': datetime.now().isoformat(),
            'start_time': start_time.isoformat(),
            'stats': {
                'users': len(bot.conversation_memory) if bot and hasattr(bot, 'conversation_memory') else 0,
                'businesses': len(bot.business_listings) if bot and hasattr(bot, 'business_listings') else 0
            }
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.debug("State saved")
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

def load_state() -> Dict[str, Any]:
    """Load bot state from file"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load state: {e}")
    return {}

def run_bot_loop():
    """Run the bot in a separate thread"""
    global bot, is_running
    
    async def start_bot():
        global bot, is_running
        try:
            bot = NaijaBot()
            await bot.initialize()
            logger.info("🤖 Bot is now listening for messages...")
            is_running = True
            save_state()
            
            # Keep bot running
            await bot.client.run_until_disconnected()
            
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            is_running = False
            save_state()
        finally:
            if bot:
                await bot.cleanup()
            is_running = False
            save_state()
    
    try:
        # Run with timeout protection
        asyncio.run(asyncio.wait_for(start_bot(), timeout=60))
    except asyncio.TimeoutError:
        logger.error("❌ Bot initialization timed out")
        is_running = False
    except Exception as e:
        logger.error(f"❌ Bot thread error: {e}")
        is_running = False

def run_bot_with_monitoring():
    """Run bot with auto-restart on failure"""
    global is_running
    
    while True:
        try:
            run_bot_loop()
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
            is_running = False
            logger.info("🔄 Restarting bot in 5 seconds...")
            time.sleep(5)
            continue
        break

def shutdown_bot():
    """Gracefully shutdown the bot"""
    global bot, is_running, bot_thread
    
    if not is_running:
        logger.info("Bot already stopped")
        return
    
    logger.info("🛑 Shutting down bot...")
    is_running = False
    
    if bot:
        try:
            # Create new loop for cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bot.cleanup())
            logger.info("✅ Bot cleanup complete")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
    
    save_state()
    logger.info("✅ Bot shutdown complete")

# ==================== SIGNAL HANDLERS ====================

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {sig}")
    shutdown_bot()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ==================== FLASK ROUTES ====================

@app.route('/')
@rate_limit(limit=10, per=60)
def home():
    """Home endpoint"""
    return jsonify({
        "name": "NaijaAI Bot",
        "status": "running",
        "version": "2.0.0",
        "endpoints": [
            "/ - Home",
            "/start - Start bot",
            "/status - Bot status",
            "/shutdown - Shutdown bot",
            "/test - Test endpoint",
            "/trigger - Wakeup endpoint"
        ]
    })

@app.route('/start')
@rate_limit(limit=3, per=60)
def start_bot_endpoint():
    """Start the bot if not running"""
    global bot_thread, is_running
    
    try:
        if is_running:
            return jsonify({
                "status": "already running",
                "started_at": datetime.now().isoformat()
            })
        
        logger.info("🚀 Starting bot...")
        bot_thread = threading.Thread(target=run_bot_with_monitoring, daemon=True)
        bot_thread.start()
        
        # Wait a moment for bot to start
        time.sleep(2)
        
        if is_running:
            return jsonify({
                "status": "success",
                "message": "Bot started successfully",
                "started_at": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": "starting",
                "message": "Bot is starting, check /status for updates"
            }), 202
            
    except Exception as e:
        logger.error(f"Start endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/status')
@rate_limit(limit=10, per=60)
def status():
    """Check bot status with detailed stats"""
    try:
        stats = {
            "running": is_running,
            "bot_initialized": bot is not None,
            "uptime": str(datetime.now() - start_time).split('.')[0],
            "thread_alive": bot_thread.is_alive() if bot_thread else False,
            "active_users": len(bot.conversation_memory) if bot and hasattr(bot, 'conversation_memory') else 0,
            "business_listings": len(bot.business_listings) if bot and hasattr(bot, 'business_listings') else 0,
            "rate_limit_store_size": len(rate_limit_store),
            "time": datetime.now().isoformat()
        }
        
        # Try to get bot stats
        if bot and is_running:
            try:
                stats["bot_healthy"] = True
            except:
                stats["bot_healthy"] = False
        else:
            stats["bot_healthy"] = False
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/shutdown')
@rate_limit(limit=2, per=60)
def shutdown_endpoint():
    """Shutdown bot endpoint"""
    try:
        if not is_running:
            return jsonify({"status": "already stopped"})
        
        shutdown_bot()
        return jsonify({
            "status": "success",
            "message": "Bot shutdown initiated",
            "time": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Shutdown endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/test')
@rate_limit(limit=20, per=60)
def test():
    """Test endpoint for monitoring"""
    return jsonify({
        "status": "success",
        "message": "Bot is alive",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/trigger')
@rate_limit(limit=3, per=60)
def trigger():
    """Endpoint for cron-job.org to wake up the bot"""
    try:
        if not is_running:
            logger.info("🔄 Triggering bot start...")
            start_bot_endpoint()
            return jsonify({
                "status": "triggered",
                "message": "Bot started",
                "timestamp": datetime.now().isoformat()
            })
        return jsonify({
            "status": "running",
            "message": "Bot already running",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Trigger error: {e}")
        return jsonify({"error": str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(429)
def rate_limit_error(error):
    """Handle rate limit errors"""
    return jsonify({"error": "Rate limit exceeded, please try again later"}), 429

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Load previous state
    state = load_state()
    if state.get('is_running', False):
        logger.info("🔄 Restoring previous bot state...")
    
    # Start bot on launch
    logger.info(f"🚀 Starting NaijaAI Bot on port {port}...")
    thread = threading.Thread(target=run_bot_with_monitoring, daemon=True)
    thread.start()
    
    # Wait for bot to start
    time.sleep(3)
    if is_running:
        logger.info("✅ Bot started successfully!")
    else:
        logger.warning("⚠️ Bot still starting...")
    
    # Run Flask app
    try:
        app.run(
            host='0.0.0.0',
            port=port,
            debug=debug,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
        shutdown_bot()
    except Exception as e:
        logger.error(f"💀 Flask error: {e}")
        shutdown_bot()
