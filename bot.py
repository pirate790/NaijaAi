#!/usr/bin/env python3
"""
NaijaAI Assistant - Production Telegram Bot
Author: AI Assistant
Version: 2.0.0 - Complete Working Version
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

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')

# Validate environment variables
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logging.critical("❌ Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")
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

# ==================== CONSTANTS ====================

MAX_HISTORY = 100
RATE_LIMIT = 5  # messages per second
REQUEST_TIMEOUT = 30
CACHE_SIZE = 100
MAX_CONTEXT_MESSAGES = 5
SESSION_FILE = 'naijabot_session.session'

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
    'e get as e be': ['E get as e be o!', 'Na true! E get as e be!', 'E get as e be for this life!'],
    'good morning': ['Good morning! How you dey?', 'Morning o! Hope you sleep well?', 'Good morning! God bless you!'],
    'good afternoon': ['Good afternoon! How body?', 'Afternoon o! Wetin dey happen?', 'Good afternoon! You don chop?'],
    'good evening': ['Good evening! How was your day?', 'Evening o! How far?', 'Good evening! Hope you dey alright?'],
    'thank you': ['You welcome! 👍', 'No wahala! 😊', 'Thank you too! 🙏'],
    'bye': ['Bye bye! Take care! 👋', 'Later! Safe journey! 🚀', 'Catch you later! 👋'],
    'hi': ['Hello! How dey? 👋', 'Hi! Wetin I fit help you do? 😊', 'Hey! How far?']
}

# Nigerian responses for random chat
NIGERIAN_CHAT_RESPONSES = [
    "Na true! Wetin else? 🤔",
    "E get as e be o! 💪",
    "I hear you! Wetin I fit help you do? 😊",
    "Oya, tell me more! 👀",
    "Shey na so? Interesting! 🤗",
    "Na wa o! That one strong! 💪",
    "Haba! Na so? 😂",
    "Chai! This life! 😅",
    "God dey! 🙏",
    "We go manage! ✌️",
    "Naija no dey carry last! 🇳🇬"
]

# ==================== MAIN BOT CLASS ====================

class NaijaBot:
    """Main bot class handling all functionality"""

    def __init__(self):
        self.client = None
        self.user_context = deque(maxlen=CACHE_SIZE)
        self.user_ratelimit = deque(maxlen=CACHE_SIZE)
        self.business_listings = deque(maxlen=CACHE_SIZE)
        self.conversation_memory = {}
        self.user_language = {}
        self.session = None
        self.uptime = datetime.now()
        self._running = False
        self.business_file = 'business_listings.json'
        self._load_business_listings()

    def _load_business_listings(self):
        """Load businesses from file"""
        try:
            if os.path.exists(self.business_file):
                with open(self.business_file, 'r') as f:
                    data = json.load(f)
                    if data:
                        self.business_listings = deque(data, maxlen=CACHE_SIZE)
                        logger.info(f"Loaded {len(self.business_listings)} businesses")
        except Exception as e:
            logger.error(f"Error loading businesses: {e}")
            self.business_listings = deque(maxlen=CACHE_SIZE)

    def _save_business_listings(self):
        """Save businesses to file"""
        try:
            with open(self.business_file, 'w') as f:
                json.dump(list(self.business_listings), f)
        except Exception as e:
            logger.error(f"Error saving businesses: {e}")

    async def initialize(self):
        """Initialize the bot client with auto-reconnect and session recovery"""
        try:
            # Handle session corruption
            if os.path.exists(SESSION_FILE):
                try:
                    self.client = TelegramClient(
                        SESSION_FILE,
                        int(API_ID),
                        API_HASH,
                        connection_retries=10,
                        retry_delay=5,
                        timeout=REQUEST_TIMEOUT
                    )
                    await self.client.start(bot_token=BOT_TOKEN)
                except Exception as e:
                    if "corrupt" in str(e).lower() or "invalid" in str(e).lower():
                        logger.warning("⚠️ Session corrupted, deleting...")
                        os.remove(SESSION_FILE)
                        # Retry with fresh session
                        self.client = TelegramClient(
                            SESSION_FILE,
                            int(API_ID),
                            API_HASH,
                            connection_retries=10,
                            retry_delay=5,
                            timeout=REQUEST_TIMEOUT
                        )
                        await self.client.start(bot_token=BOT_TOKEN)
                    else:
                        raise
            else:
                self.client = TelegramClient(
                    SESSION_FILE,
                    int(API_ID),
                    API_HASH,
                    connection_retries=10,
                    retry_delay=5,
                    timeout=REQUEST_TIMEOUT
                )
                await self.client.start(bot_token=BOT_TOKEN)

            self.session = aiohttp.ClientSession()

            me = await self.client.get_me()
            logger.info(f"✅ Bot started successfully as @{me.username or me.first_name}")
            
            # Clear old handlers and register new ones
            self.client.remove_event_handler(self.handle_message)
            self.client.remove_event_handler(self.handle_callback)
            
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.handle_message(event)
            
            @self.client.on(events.CallbackQuery)
            async def handle_callback(event):
                await self.handle_callback(event)
            
            return True

        except FloodWaitError as e:
            logger.warning(f"⏳ Rate limited during init, waiting {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
            return await self.initialize()
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            return False

    async def cleanup(self):
        """Clean up resources"""
        self._running = False
        if self.session:
            await self.session.close()
        if self.client:
            await self.client.disconnect()
        self._save_business_listings()
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
            if t.get('user_id') == user_id and (now - t.get('timestamp', now)).seconds < 1
        ]
        if len(recent_requests) >= RATE_LIMIT:
            return False
        self.user_ratelimit.append({'user_id': user_id, 'timestamp': now})
        return True

    def get_local_response(self, text: str) -> Optional[str]:
        """Generate localized responses for common phrases"""
        text_lower = text.lower().strip()
        
        for pattern, responses in PIDGIN_RESPONSES.items():
            if pattern in text_lower:
                return random.choice(responses)
        
        return None

    async def get_weather(self, location: str) -> Optional[Dict]:
        """Fetch weather data from OpenWeatherMap API"""
        if not OPENWEATHER_API_KEY:
            return None

        try:
            location_lower = location.lower().strip()
            if location_lower in NIGERIAN_STATES:
                location = NIGERIAN_STATES[location_lower]

            url = "https://api.openweathermap.org/data/2.5/weather"
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
                        'feels_like': data['main']['feels_like'],
                        'description': data['weather'][0]['description'],
                        'humidity': data['main']['humidity'],
                        'wind': data['wind']['speed'],
                        'city': data['name'],
                        'country': data['sys']['country']
                    }
                elif response.status == 404:
                    return {'error': 'City not found'}
                else:
                    return None
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
                return None
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
                return None
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {e}")
            return None

    async def get_joke(self) -> Optional[str]:
        """Fetch a random joke"""
        try:
            url = "https://official-joke-api.appspot.com/random_joke"
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return f"😂 {data.get('setup', '')}\n\n{data.get('punchline', '')}"
                return None
        except Exception as e:
            logger.error(f"Error fetching joke: {e}")
            return None

    def format_weather_response(self, data: Dict) -> str:
        """Format weather data into a readable message"""
        if 'error' in data:
            return f"😅 {data['error']}. Please check the city name."
        
        emoji = "🌤️" if "clear" in data['description'] else "☁️" if "cloud" in data['description'] else "🌧️" if "rain" in data['description'] else "🌤️"
        
        return (
            f"{emoji} Weather in {data['city']}, {data['country']}:\n"
            f"🌡️ Temperature: {data['temp']}°C (feels like {data['feels_like']}°C)\n"
            f"☁️ Conditions: {data['description'].capitalize()}\n"
            f"💧 Humidity: {data['humidity']}%\n"
            f"💨 Wind Speed: {data['wind']} m/s"
        )

    def format_news_response(self, articles: List) -> str:
        """Format news articles into a readable message"""
        if not articles:
            return "📰 No news found. Please try again later."

        response = "📰 Latest Nigerian News:\n\n"
        for idx, article in enumerate(articles[:5], 1):
            title = article.get('title', 'No title')
            source = article.get('source', {}).get('name', 'Unknown')
            url = article.get('url', '')
            response += f"{idx}. {title}\n   📍 {source}\n"
            if url:
                response += f"   🔗 {url}\n"
            response += "\n"
        return response

    # ==================== MESSAGE HANDLERS ====================

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

            logger.info(f"📩 New message from {user_id}: {message_text[:50]}...")

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

            # Check for weather query in natural language
            if any(word in message_text.lower() for word in ['weather', 'rain', 'temperature', 'weather for']):
                await self.handle_weather_query(event, message_text)
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

    async def handle_weather_query(self, event: events.MessageEvent, text: str):
        """Extract location from natural language weather query"""
        try:
            # Try to extract location
            words = text.split()
            location = None
            for word in words:
                if word.lower() in NIGERIAN_STATES:
                    location = word
                    break
                # Check if word is a city
                city_check = await self.get_weather(word)
                if city_check and 'error' not in city_check:
                    location = word
                    break
            
            if location:
                await event.reply(f"🌤️ Fetching weather for {location}...")
                weather_data = await self.get_weather(location)
                if weather_data:
                    response = self.format_weather_response(weather_data)
                    await event.reply(response)
                else:
                    await event.reply(f"😅 Couldn't find weather for '{location}'. Please try again.")
            else:
                await event.reply("🌤️ Please mention a city or state.\nExample: 'Weather for Lagos' or 'Temperature in Abuja'")
        except Exception as e:
            logger.error(f"Error in weather query: {e}")
            await event.reply("😅 Couldn't process weather request. Try /weather Lagos")

    async def handle_chat(self, event: events.MessageEvent, text: str):
        """Handle natural language chat with context"""
        user_id = str(event.sender_id)
        
        # Store conversation context
        if user_id not in self.conversation_memory:
            self.conversation_memory[user_id] = []
        
        context = self.conversation_memory[user_id]
        context.append(text)
        if len(context) > MAX_CONTEXT_MESSAGES:
            context.pop(0)
        
        # Get user's preferred language
        lang = self.user_language.get(user_id, 'en')
        
        # Generate appropriate response
        response = random.choice(NIGERIAN_CHAT_RESPONSES)
        
        # Add context-aware responses
        if any(word in text.lower() for word in ['help', 'assist', 'support']):
            response = "I dey here to help! Type /help to see all my commands. 😊"
        elif any(word in text.lower() for word in ['thanks', 'thank you', 'danke']):
            response = "You welcome o! 🙏 Anything for my Naija people!"
        elif any(word in text.lower() for word in ['joke', 'funny', 'laugh']):
            joke = await self.get_joke()
            if joke:
                response = joke
        elif any(word in text.lower() for word in ['who you be', 'who are you', 'your name']):
            response = "I be NaijaAI Assistant! Your personal Nigerian AI bot. 🇳🇬"
        
        await event.reply(response)

    async def handle_callback(self, event: events.CallbackQuery):
        """Handle callback queries from inline buttons"""
        try:
            data = event.data.decode('utf-8')
            user_id = str(event.sender_id)
            
            if data.startswith('lang_'):
                lang_code = data.split('_')[1]
                self.user_language[user_id] = lang_code
                await event.answer(f"✅ Language set to {LANGUAGES.get(lang_code, 'English')}")
                await event.edit(f"✅ Language switched to {LANGUAGES.get(lang_code, 'English')}")
                
            elif data == 'list_business':
                await event.answer("📝 Type /business to list your business")
                
            elif data.startswith('business_'):
                # Show business details
                biz_id = data.split('_')[1]
                for biz in self.business_listings:
                    if biz.get('id') == biz_id:
                        details = (
                            f"📋 Business Details:\n"
                            f"Name: {biz.get('name')}\n"
                            f"Type: {biz.get('type')}\n"
                            f"Location: {biz.get('location')}\n"
                            f"Contact: {biz.get('contact')}\n"
                            f"Description: {biz.get('description')}"
                        )
                        await event.answer(details, alert=True)
                        return
                await event.answer("Business not found")
                
            else:
                await event.answer("Unknown option")
                
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await event.answer("❌ Something went wrong")

    # ==================== COMMAND HANDLERS ====================

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
            elif command == '/status':
                await self.cmd_status(event)
            elif command == '/joke':
                await self.cmd_joke(event)
            else:
                # Try to handle as natural language
                await self.handle_chat(event, command)
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            await event.reply("😅 Error processing command. Please try again.")

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
            f"/convert <amount> <from> <to> - Currency converter\n"
            f"/business - List your business\n"
            f"/joke - Get a funny joke\n"
            f"/about - About this bot\n\n"
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
            "/joke - Get a random joke\n"
            "/status - Check bot health\n"
            "/about - About this bot\n\n"
            "💬 Just type any message and I'll respond!\n"
            "Try: 'I need a plumber in Ikeja' or 'Weather for Lagos'\n\n"
            "🇳🇬 I understand Pidgin and Nigerian English!"
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
                "Example: /weather Abuja\n\n"
                "Supported states:\n" + ", ".join(list(NIGERIAN_STATES.keys())[:10]) + "..."
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
                "Example: /nearby electrician in Lagos\n"
                "Example: /nearby restaurant in Abuja"
            )
            return

        query = ' '.join(args[1:])
        
        # Search in business listings
        results = []
        for biz in self.business_listings:
            if any(word.lower() in json.dumps(biz).lower() for word in query.split()):
                results.append(biz)
        
        if results:
            response = f"🔍 Found {len(results)} results for '{query}':\n\n"
            for idx, biz in enumerate(results[:5], 1):
                response += f"{idx}. {biz.get('name', 'Unknown')}\n"
                response += f"   📍 {biz.get('type', 'N/A')} - {biz.get('location', 'N/A')}\n"
                response += f"   📞 {biz.get('contact', 'N/A')}\n\n"
            await event.reply(response)
        else:
            response = (
                f"🔍 Searching for: {query}\n\n"
                f"📋 No results found in listings.\n\n"
                f"💡 Try /business to list your service!\n"
                f"💡 Or try searching for: plumber, electrician, restaurant, etc."
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
                "Example: /convert 5000 NGN EUR\n"
                "Example: /convert 100 GBP NGN"
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
                f"Rate: 1 {from_curr} = {rate:.4f} {to_curr}\n\n"
                f"💡 For Nigerian Naira, use NGN"
            )
        else:
            await event.reply(
                "😅 Couldn't fetch exchange rate. Please check the currency codes.\n"
                "Supported: USD, EUR, GBP, NGN, etc."
            )

    async def cmd_business(self, event: events.MessageEvent):
        """Handle /business command"""
        args = event.message.text.split()
        if len(args) < 6:
            await event.reply(
                "📝 List Your Business!\n\n"
                "To list your business, provide all details:\n"
                "1. Business name\n"
                "2. Service type\n"
                "3. Location (city/state)\n"
                "4. Contact phone number\n"
                "5. Description\n\n"
                "Format: /business [name] [type] [location] [contact] [description]\n"
                "Example: /business 'John\'s Plumbing' Plumber Ikeja 08012345678 'Expert plumbing services in Lagos'"
            )
            return

        try:
            # Parse the command (handle quoted names)
            business_data = {
                'id': str(random.randint(1000, 9999)),
                'name': args[1].strip("'\""),
                'type': args[2],
                'location': args[3],
                'contact': args[4],
                'description': ' '.join(args[5:]),
                'submitted_by': str(event.sender_id),
                'submitted_at': datetime.now().isoformat()
            }
            
            self.business_listings.append(business_data)
            self._save_business_listings()
            
            await event.reply(
                f"✅ Business listed successfully!\n\n"
                f"📋 {business_data['name']}\n"
                f"📍 {business_data['type']} - {business_data['location']}\n"
                f"📞 {business_data['contact']}\n"
                f"📝 {business_data['description']}\n\n"
                f"🆔 Your business ID: {business_data['id']}\n"
                f"📊 Total listings: {len(self.business_listings)}"
            )
        except Exception as e:
            logger.error(f"Error listing business: {e}")
            await event.reply("😅 Error listing business. Please try again with correct format.")

    async def cmd_about(self, event: events.MessageEvent):
        """Handle /about command"""
        about_msg = (
            "🤖 NaijaAI Assistant v2.0\n\n"
            "🇳🇬 AI-powered assistant for Nigerians\n"
            "Built with ❤️ for the Nigerian community\n\n"
            "✨ Features:\n"
            "• Multi-language support (English, Pidgin, Yoruba, Hausa, Igbo)\n"
            "• Weather forecasts for Nigerian cities\n"
            "• Latest Nigerian news headlines\n"
            "• Currency exchange rates\n"
            "• Business listings for services\n"
            "• Nearby service finder\n"
            "• Natural language understanding\n"
            "• Nigerian Pidgin support\n"
            "• Random jokes\n\n"
            "📊 Stats:\n"
            f"• Uptime: {str(datetime.now() - self.uptime).split('.')[0]}\n"
            f"• Active users: {len(self.conversation_memory)}\n"
            f"• Business listings: {len(self.business_listings)}\n\n"
            "💡 Type /help for all commands\n"
            "🇳🇬 Naija no dey carry last!"
        )
        await event.reply(about_msg)

    async def cmd_status(self, event: events.MessageEvent):
        """Handle /status command - health check"""
        status_msg = (
            "🟢 Bot Status: Online\n\n"
            f"⏱️ Uptime: {str(datetime.now() - self.uptime).split('.')[0]}\n"
            f"👥 Active users: {len(self.conversation_memory)}\n"
            f"📋 Business listings: {len(self.business_listings)}\n"
            f"⚡ Rate limit queue: {len(self.user_ratelimit)}\n"
            f"🔐 Session: {'Active' if self.client else 'Inactive'}\n"
            f"🌐 Connection: {'Connected' if self.session else 'Disconnected'}\n\n"
            f"✅ Bot is healthy and running smoothly!"
        )
        await event.reply(status_msg)

    async def cmd_joke(self, event: events.MessageEvent):
        """Handle /joke command"""
        await event.reply("😂 Fetching a joke for you...")
        joke = await self.get_joke()
        if joke:
            await event.reply(joke)
        else:
            # Fallback jokes
            fallback_jokes = [
                "Why did the Nigerian cross the road? 🇳🇬\n\nTo get to the other side!",
                "What do you call a Nigerian who sings? 🎤\n\nA Naija-rian!",
                "Why don't Nigerians play hide and seek? 🙈\n\nBecause good luck hiding when you're this famous!"
            ]
            await event.reply(random.choice(fallback_jokes))

    # ==================== MAIN RUNNER ====================

    async def run(self):
        """Main bot runner with auto-reconnect"""
        self._running = True
        
        while self._running:
            try:
                if not await self.initialize():
                    logger.error("❌ Failed to initialize, retrying in 10s...")
                    await asyncio.sleep(10)
                    continue
                
                logger.info("🤖 NaijaAI Assistant is LIVE!")
                await self.client.run_until_disconnected()
                
            except (ConnectionError, OSError, TimeoutError) as e:
                logger.warning(f"⚠️ Connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
                continue
                
            except FloodWaitError as e:
                logger.warning(f"⏳ Rate limited, waiting {e.seconds}s...")
                await asyncio.sleep(e.seconds + 1)
                continue
                
            except KeyboardInterrupt:
                logger.info("👋 Bot stopped by user")
                break
                
            except Exception as e:
                logger.error(f"💥 Unexpected error: {e}", exc_info=True)
                await asyncio.sleep(10)
                continue

# ==================== ENTRY POINT ====================

async def main():
    """Main entry point with signal handling"""
    bot = NaijaBot()
    
    try:
        # Handle graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(bot)))
            except NotImplementedError:
                # Windows doesn't support signal handlers in asyncio
                pass
        
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💀 Fatal error: {e}", exc_info=True)
    finally:
        await bot.cleanup()
        logger.info("🧹 Cleanup complete")

async def shutdown(bot):
    """Graceful shutdown handler"""
    logger.info("🛑 Shutting down...")
    bot._running = False
    await bot.cleanup()
    sys.exit(0)

if __name__ == "__main__":
    import signal
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"💀 Fatal error: {e}")
        sys.exit(1)
