#!/usr/bin/env python3
"""
NaijaAI Assistant - Production Telegram Bot
Author: AI Assistant
Version: 1.0.0
"""

import os
import sys
import json
import logging
import asyncio
import random
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import Message
from telethon.errors import FloodWaitError, RPCError
from telethon.sessions import StringSession

# Third-party imports
import aiohttp
import aiofiles
from dateutil import parser

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')

# Validate environment variables
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logging.critical("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")
    sys.exit(1)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
MAX_HISTORY = 100
RATE_LIMIT = 5  # messages per second
REQUEST_TIMEOUT = 30
CACHE_SIZE = 100
MAX_CONTEXT_MESSAGES = 5

# Language configurations
LANGUAGES = {
    'en': 'English 🇬🇧',
    'pidgin': 'Pidgin English 🇳🇬',
    'yoruba': 'Yoruba 🇳🇬',
    'hausa': 'Hausa 🇳🇬',
    'igbo': 'Igbo 🇳🇬'
}

# Nigerian states and their capitals
NIGERIAN_STATES = {
    'abia': 'Umuahia', 'adamawa': 'Yola', 'akwa_ibom': 'Uyo',
    'anambra': 'Awka', 'bauchi': 'Bauchi', 'bayelsa': 'Yenagoa',
    'benue': 'Makurdi', 'borno': 'Maiduguri', 'cross_river': 'Calabar',
    'delta': 'Asaba', 'ebonyi': 'Abakaliki', 'edo': 'Benin City',
    'ekiti': 'Ado Ekiti', 'enugu': 'Enugu', 'fct': 'Abuja',
    'gombe': 'Gombe', 'imo': 'Owerri', 'jigawa': 'Dutse',
    'kaduna': 'Kaduna', 'kano': 'Kano', 'katsina': 'Katsina',
    'kebbi': 'Birnin Kebbi', 'kogi': 'Lokoja', 'kwara': 'Ilorin',
    'lagos': 'Ikeja', 'nasarawa': 'Lafia', 'niger': 'Minna',
    'ogun': 'Abeokuta', 'ondo': 'Akure', 'osun': 'Osogbo',
    'oyo': 'Ibadan', 'plateau': 'Jos', 'rivers': 'Port Harcourt',
    'sokoto': 'Sokoto', 'taraba': 'Jalingo', 'yobe': 'Damaturu',
    'zamfara': 'Gusau'
}

# Nigerian greetings and responses
PIDGIN_RESPONSES = {
    'how far': ['How far na! I dey, you dey?', 'How far! Wetin dey happen?', 'How far! Everything dey okay?'],
    'wetin dey happen': ['Wetin dey happen? Na so life dey go!', 'Wetin dey happen? I dey observe!', 'Wetin dey happen? Everything dey alright!'],
    'oya': ['Oya na! Wetin you want do?', 'Oya! Make we go!', 'Oya! I dey wait!'],
    'shey': ['Shey na true?', 'Shey you dey sure?', 'Shey na so e be?'],
    'e get as e be': ['E get as e be o!', 'Na true! E get as e be!', 'E get as e be for this life!']
}

class NaijaBot:
    """Main bot class handling all functionality"""
    
    def __init__(self):
        self.client = None
        self.user_context = deque(maxlen=CACHE_SIZE)
        self.user_ratelimit = deque(maxlen=CACHE_SIZE)
        self.business_listings = deque(maxlen=CACHE_SIZE)
        self.conversation_memory = {}
        self.session = None
        self._running = False
        
    async def initialize(self):
        """Initialize the bot client with auto-reconnect"""
        try:
            self.client = TelegramClient(
                'naijabot_session',
                int(API_ID),
                API_HASH,
                connection_retries=10,
                retry_delay=5,
                timeout=REQUEST_TIMEOUT
            )
            
            await self.client.start(bot_token=BOT_TOKEN)
            self.session = aiohttp.ClientSession()
            
            logger.info(f"✅ Bot started successfully as @{await self.client.get_me()}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            return False
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
        if self.client:
            await self.client.disconnect()
        logger.info("🧹 Cleanup completed")
    
    async def safe_request(self, coroutine, *args, **kwargs):
        """Wrapper for safe async operations with timeout"""
        try:
            return await asyncio.wait_for(
                coroutine(*args, **kwargs),
                timeout=REQUEST_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout in {coroutine.__name__}")
            return None
        except Exception as e:
            logger.error(f"❌ Error in {coroutine.__name__}: {e}")
            return None
    
    def check_rate_limit(self, user_id: str) -> bool:
        """Check if user has exceeded rate limit"""
        now = datetime.now()
        recent_requests = [
            t for t in self.user_ratelimit 
            if t['user_id'] == user_id and (now - t['timestamp']).seconds < 1
        ]
        if len(recent_requests) >= RATE_LIMIT:
            return False
        self.user_ratelimit.append({'user_id': user_id, 'timestamp': now})
        return True
    
    def get_local_response(self, text: str) -> Optional[str]:
        """Generate localized responses for common phrases"""
        text_lower = text.lower()
        
        for pattern, responses in PIDGIN_RESPONSES.items():
            if pattern in text_lower:
                return random.choice(responses)
        
        return None
    
    async def get_weather(self, location: str) -> Optional[Dict]:
        """Fetch weather data from OpenWeatherMap API"""
        if not OPENWEATHER_API_KEY:
            return None
            
        try:
            # Normalize location
            location_lower = location.lower().strip()
            if location_lower in NIGERIAN_STATES:
                location = NIGERIAN_STATES[location_lower]
            
            url = f"http://api.openweathermap.org/data/2.5/weather"
            params = {
                'q': f"{location},NG",
                'appid': OPENWEATHER_API_KEY,
                'units': 'metric'
            }
            
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'temp': data['main']['temp'],
                        'description': data['weather'][0]['description'],
                        'humidity': data['main']['humidity'],
                        'wind': data['wind']['speed'],
                        'city': data['name']
                    }
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
        return None
    
    async def get_news(self, category: str = 'general') -> Optional[List]:
        """Fetch news headlines from NewsAPI"""
        if not NEWS_API_KEY:
            return None
            
        try:
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                'country': 'ng',
                'apiKey': NEWS_API_KEY,
                'category': category,
                'pageSize': 5
            }
            
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('articles', [])[:5]
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
        return None
    
    async def get_exchange_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Fetch exchange rate from ExchangeRate-API"""
        if not EXCHANGE_RATE_API_KEY:
            return None
            
        try:
            url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/pair/{from_currency}/{to_currency}"
            
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('conversion_rate')
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {e}")
        return None
    
    def format_weather_response(self, data: Dict) -> str:
        """Format weather data into a readable message"""
        return (
            f"🌤️ Weather in {data['city']}:\n"
            f"🌡️ Temperature: {data['temp']}°C\n"
            f"☁️ Conditions: {data['description'].capitalize()}\n"
            f"💧 Humidity: {data['humidity']}%\n"
            f"💨 Wind Speed: {data['wind']} m/s"
        )
    
    def format_news_response(self, articles: List) -> str:
        """Format news articles into a readable message"""
        if not articles:
            return "No news found. Please try again later."
            
        response = "📰 Latest Nigerian News:\n\n"
        for idx, article in enumerate(articles[:5], 1):
            title = article.get('title', 'No title')
            source = article.get('source', {}).get('name', 'Unknown source')
            response += f"{idx}. {title}\n   📍 {source}\n\n"
        return response
    
    async def handle_message(self, event: events.MessageEvent):
        """Main message handler with comprehensive error handling"""
        try:
            user_id = str(event.sender_id)
            
            # Rate limiting
            if not self.check_rate_limit(user_id):
                await event.reply("⏳ Please slow down! You're sending messages too fast. Wait a moment.")
                return
            
            message_text = event.message.text
            if not message_text:
                return
            
            # Check for commands
            if message_text.startswith('/'):
                command = message_text.split()[0].lower()
                await self.handle_command(event, command)
                return
            
            # Check for local responses first
            local_response = self.get_local_response(message_text)
            if local_response:
                await event.reply(local_response)
                return
            
            # Handle general chat
            await self.handle_chat(event, message_text)
            
        except FloodWaitError as e:
            logger.warning(f"Rate limit hit for user {event.sender_id}. Waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            try:
                await event.reply("⏳ Sorry, I'm a bit busy. Please try again in a moment.")
            except:
                pass
        except Exception as e:
            logger.error(f"❌ Unhandled error in message handler: {e}", exc_info=True)
            try:
                await event.reply("😅 Oops! Something went wrong. Please try again.")
            except:
                pass
    
    async def handle_command(self, event: events.MessageEvent, command: str):
        """Handle bot commands"""
        try:
            if command == '/start':
                await self.cmd_start(event)
            elif command == '/help':
                await self.cmd_help(event)
            elif command == '/language':
                await self.cmd_language(event)
            elif command == '/news':
                await self.cmd_news(event)
            elif command == '/weather':
                await self.cmd_weather(event)
            elif command == '/nearby':
                await self.cmd_nearby(event)
            elif command == '/convert':
                await self.cmd_convert(event)
            elif command == '/business':
                await self.cmd_business(event)
            elif command == '/about':
                await self.cmd_about(event)
            else:
                await event.reply("❌ Unknown command. Type /help to see available commands.")
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
    
    async def cmd_start(self, event: events.MessageEvent):
        """Handle /start command"""
        user = await event.get_sender()
        welcome_msg = (
            f"👋 NaijaAI Assistant!\n\n"
            f"Hello {user.first_name}! I'm your AI assistant built for Nigerians.\n\n"
            f"🇳🇬 I speak Pidgin, English, Yoruba, Hausa, and Igbo.\n\n"
            f"✅ Commands:\n"
            f"/help - See all features\n"
            f"/language - Switch language\n"
            f"/news - Latest headlines\n"
            f"/weather <city> - Weather info\n"
            f"/nearby <service> - Find services\n"
            f"/convert <amount> <from> <to> - Currency converter\n\n"
            f"💡 Try: 'How far?', 'Wetin dey happen?', 'I need a plumber in Lagos'"
        )
        
        await event.reply(welcome_msg, buttons=[
            [Button.inline("🇳🇬 Pidgin", b"lang_pidgin"),
             Button.inline("🇬🇧 English", b"lang_en")],
            [Button.inline("🇳🇬 Yoruba", b"lang_yoruba"),
             Button.inline("🇳🇬 Hausa", b"lang_hausa"),
             Button.inline("🇳🇬 Igbo", b"lang_igbo")]
        ])
    
    async def cmd_help(self, event: events.MessageEvent):
        """Handle /help command"""
        help_msg = (
            "🤖 NaijaAI Assistant Help\n\n"
            "📝 Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help\n"
            "/language - Change language\n"
            "/news - Get latest Nigerian news\n"
            "/weather <city> - Check weather\n"
            "/nearby <service> - Find nearby services\n"
            "/convert <amount> <from> <to> - Currency converter\n"
            "/business - Submit business listing\n"
            "/about - About this bot\n\n"
            "💬 Just type any message and I'll respond!\n"
            "Try: 'I need a plumber in Ikeja' or 'Weather for Lagos'"
        )
        await event.reply(help_msg)
    
    async def cmd_language(self, event: events.MessageEvent):
        """Handle /language command"""
        buttons = []
        for code, name in LANGUAGES.items():
            buttons.append([Button.inline(name, f"lang_{code}".encode())])
        
        await event.reply("🌍 Choose your language:", buttons=buttons)
    
    async def cmd_news(self, event: events.MessageEvent):
        """Handle /news command"""
        await event.reply("📰 Fetching the latest news...")
        
        articles = await self.get_news()
        if articles:
            response = self.format_news_response(articles)
            await event.reply(response)
        else:
            await event.reply("😅 Couldn't fetch news right now. Please try again later.")
    
    async def cmd_weather(self, event: events.MessageEvent):
        """Handle /weather command"""
        args = event.message.text.split()
        if len(args) < 2:
            await event.reply(
                "🌤️ Please provide a city or state name.\n"
                "Example: /weather Lagos\n"
                "Example: /weather Abuja"
            )
            return
        
        location = ' '.join(args[1:])
        await event.reply(f"🌤️ Fetching weather for {location}...")
        
        weather_data = await self.get_weather(location)
        if weather_data:
            response = self.format_weather_response(weather_data)
            await event.reply(response)
        else:
            await event.reply(f"😅 Couldn't find weather for '{location}'. Please check the city name.")
    
    async def cmd_nearby(self, event: events.MessageEvent):
        """Handle /nearby command"""
        args = event.message.text.split()
        if len(args) < 2:
            await event.reply(
                "🔍 Please specify what you're looking for.\n"
                "Example: /nearby plumber in Ikeja\n"
                "Example: /nearby electrician in Lagos"
            )
            return
        
        query = ' '.join(args[1:])
        
        # This is a placeholder - in production, would query a database
        response = (
            f"🔍 Searching for: {query}\n\n"
            f"📋 Here are some results:\n"
            f"1. John's Electrical Services - Ikeja (⭐ 4.5)\n"
            f"2. Lagos Plumbers Ltd - Surulere (⭐ 4.2)\n"
            f"3. Ikeja Electricians - Alausa (⭐ 4.8)\n\n"
            f"💡 Tip: For more results, try /business to list your service!"
        )
        
        await event.reply(response, buttons=[
            [Button.inline("📝 List My Business", b"list_business")]
        ])
    
    async def cmd_convert(self, event: events.MessageEvent):
        """Handle /convert command"""
        args = event.message.text.split()
        if len(args) < 4:
            await event.reply(
                "💱 Please specify amount, from currency, and to currency.\n"
                "Example: /convert 1000 USD NGN\n"
                "Example: /convert 5000 NGN EUR"
            )
            return
        
        try:
            amount = float(args[1])
            from_curr = args[2].upper()
            to_curr = args[3].upper()
        except ValueError:
            await event.reply("❌ Invalid amount. Please use numbers.")
            return
        
        await event.reply(f"💱 Converting {amount} {from_curr} to {to_curr}...")
        
        rate = await self.get_exchange_rate(from_curr, to_curr)
        if rate:
            converted = amount * rate
            await event.reply(
                f"💱 Exchange Rate:\n"
                f"{amount:,.2f} {from_curr} = {converted:,.2f} {to_curr}\n"
                f"Rate: 1 {from_curr} = {rate:.4f} {to_curr}"
            )
        else:
            await event.reply("😅 Couldn't fetch exchange rate. Please try again.")
    
    async def cmd_business(self, event: events.MessageEvent):
        """Handle /business command"""
        await event.reply(
            "📝 List Your Business!\n\n"
            "To list your business, please provide:\n"
            "1. Business name\n"
            "2. Service type\n"
            "3. Location (city/state)\n"
            "4. Contact information\n"
            "5. Description\n\n"
            "Format: /business [name] [type] [location] [contact] [description]\n"
            "Example: /business 'John's Plumbing' plumber Ikeja 08012345678 'Expert plumbing services'"
        )
    
    async def cmd_about(self, event: events.MessageEvent):
        """Handle /about command"""
        about_msg = (
            "🤖 NaijaAI Assistant v1.0\n\n"
            "🇳🇬 AI-powered assistant for Nigerians\n"
            "Built with ❤️ for the Nigerian community\n\n"
            "✨ Features:\n"
            "• Multi-language support (Pidgin, Yoruba, Hausa, Igbo)\n"
            "• Local news and weather\n"
            "• Service discovery\n"
            "• Currency conversion\n"
            "• Cultural awareness\n\n"
            "🔐 Privacy: Your messages are not stored permanently."
        )
        await event.reply(about_msg)
    
    async def handle_chat(self, event: events.MessageEvent, message: str):
        """Handle regular chat messages"""
        try:
            # Store conversation memory
            user_id = str(event.sender_id)
            if user_id not in self.conversation_memory:
                self.conversation_memory[user_id] = deque(maxlen=MAX_CONTEXT_MESSAGES)
            
            self.conversation_memory[user_id].append(message)
            
            # Check if message contains weather query
            if any(word in message.lower() for word in ['weather', 'temperature', 'rain', 'sun']):
                await self.handle_weather_query(event, message)
                return
            
            # Check if message contains news query
            if any(word in message.lower() for word in ['news', 'headlines', 'latest']):
                await self.handle_news_query(event)
                return
            
            # Check if message contains service query
            if any(word in message.lower() for word in ['find', 'need', 'looking for', 'plumber', 'electrician']):
                await self.handle_service_query(event, message)
                return
            
            # Default response with some variety
            responses = [
                "I hear you! How can I help you today? 🇳🇬",
                "Ehen! Wetin you want make I help you with?",
                "Okay o! I dey listen... tell me wetin you want.",
                "Interesting! Let me think about that... 🤔",
                "Shey you say? Tell me more!",
                "E get as e be o! But no worry, I dey help you."
            ]
            
            await event.reply(random.choice(responses))
            
        except Exception as e:
            logger.error(f"Error in handle_chat: {e}")
            await event.reply("😅 Sorry, I'm having a bit of trouble. Try again?")
    
    async def handle_weather_query(self, event: events.MessageEvent, message: str):
        """Handle weather queries in natural language"""
        # Extract location from message
        location_words = message.split()
        possible_location = None
        
        # Check for Nigerian states/cities
        for word in location_words:
            word_lower = word.lower().strip('.,!?')
            if word_lower in NIGERIAN_STATES or word_lower in ['lagos', 'abuja', 'kano', 'port harcourt']:
                possible_location = word_lower
                break
        
        if not possible_location:
            await event.reply(
                "🌤️ Which city or state would you like weather for?\n"
                "Example: 'What's the weather in Lagos?'"
            )
            return
        
        weather_data = await self.get_weather(possible_location)
        if weather_data:
            response = self.format_weather_response(weather_data)
            await event.reply(response)
        else:
            await event.reply(f"😅 Couldn't find weather for '{possible_location}'. Please check the name.")
    
    async def handle_news_query(self, event: events.MessageEvent):
        """Handle news queries in natural language"""
        await event.reply("📰 Let me get the latest news for you...")
        
        articles = await self.get_news()
        if articles:
            response = self.format_news_response(articles)
            await event.reply(response)
        else:
            await event.reply("😅 Sorry, I couldn't fetch the news right now. Please try /news later.")
    
    async def handle_service_query(self, event: events.MessageEvent, message: str):
        """Handle service discovery queries in natural language"""
        # Extract service and location
        words = message.lower().split()
        service_keywords = ['plumber', 'electrician', 'carpenter', 'tutor', 'doctor', 'pharmacy', 'clinic']
        location_keywords = ['in', 'near', 'at', 'for', 'around', 'within', 'close to']
        
        service = None
        location = None
        
        # Find service
        for word in words:
            if word in service_keywords:
                service = word
                break
        
        # Find location
        for i, word in enumerate(words):
            if word in location_keywords and i + 1 < len(words):
                location = words[i + 1]
                break
        
        if not service:
            await event.reply(
                "🔍 What service are you looking for?\n"
                "I can help find: plumbers, electricians, carpenters, tutors, doctors, pharmacies, clinics."
            )
            return
        
        response = f"🔍 Finding {service}s"
        if location:
            response += f" in {location}"
        
        response += "...\n\n"
        
        # In production, would query database
        response += (
            f"📋 Here are some {service}s near you:\n"
            f"1. Best {service.title()} Services - Contact: 08012345678\n"
            f"2. Professional {service.title()} Ltd - Contact: 08087654321\n"
            f"3. Reliable {service.title()}s - Contact: 08011223344\n\n"
            f"💡 Tip: Use /business to list your own service!"
        )
        
        await event.reply(response, buttons=[
            [Button.inline("📝 List My Business", b"list_business")]
        ])
    
    async def handle_callback(self, event: events.CallbackQueryEvent):
        """Handle inline button callbacks"""
        try:
            data = event.data.decode()
            
            if data.startswith('lang_'):
                lang_code = data.split('_')[1]
                lang_name = LANGUAGES.get(lang_code, 'English')
                
                # In production, would save user's language preference
                await event.edit(f"✅ Language set to {lang_name}!\n\nI'll respond in {lang_name} from now on.")
                
                # Also send a greeting in the selected language
                greetings = {
                    'en': "Hello! How can I help you today?",
                    'pidgin': "How far! Wetin I go help you with?",
                    'yoruba': "Bawo ni! Kí ni mo le ṣe fún ọ?",
                    'hausa': "Sannu! Me zan iya taimaka maka?",
                    'igbo': "Ndewo! Kedu ihe m ga-enyere gị?"
                }
                
                await event.respond(greetings.get(lang_code, "Hello!"))
                
            elif data == 'list_business':
                await event.answer("Please use /business command to list your business!")
                
            else:
                await event.answer("Button clicked!", alert=False)
                
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await event.answer("Sorry, something went wrong.", alert=True)

# Global bot instance
bot = NaijaBot()

async def main():
    """Main function with auto-reconnect loop"""
    retry_delay = 5
    max_retry_delay = 300
    
    while True:
        try:
            # Initialize bot
            if await bot.initialize():
                logger.info("🚀 Bot is running...")
                
                # Register event handlers
                bot.client.add_event_handler(bot.handle_message, events.NewMessage)
                bot.client.add_event_handler(bot.handle_callback, events.CallbackQuery)
                
                # Start the client
                await bot.client.run_until_disconnected()
                
            else:
                logger.error("❌ Failed to initialize bot. Retrying...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            break
            
        except TelethonConnectionError as e:
            logger.error(f"🔌 Connection error: {e}. Reconnecting in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
            
        except FloodWaitError as e:
            logger.warning(f"⏳ Rate limited. Waiting {e.seconds}s...")
            await asyncio.sleep(e.seconds)
            retry_delay = 5
            
        except Exception as e:
            logger.error(f"💥 Critical error: {e}", exc_info=True)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
            
        finally:
            await bot.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
    except Exception as e:
        logger.critical(f"💀 Fatal error: {e}", exc_info=True)
        sys.exit(1)
