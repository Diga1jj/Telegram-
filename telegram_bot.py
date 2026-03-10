
import logging
import os
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import qrcode
import requests
import io
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from telegram import Update, ForceReply, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid getting too much debug information
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Bot token from user
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# OpenAI client (pre-configured)
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Dictionary to store conversation history for AI chat
conversation_history = defaultdict(list)

# Dictionary to store reminders
reminders = defaultdict(list)

# --- Helper Functions ---
async def get_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Helper to get chat member information."""
    try:
        return await context.bot.get_chat_member(update.effective_chat.id, user_id)
    except Exception as e:
        logger.error(f"Error getting chat member: {e}")
        return None

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if a user is an administrator in the chat."""
    if not update.effective_chat.type in ["group", "supergroup"]:
        return False
    admin_list = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(admin.user.id == user_id for admin in admin_list)

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    welcome_message = (
        f"Hi {user.mention_html()}! I am a multi-purpose Telegram bot.\n\n"
        "Here are the commands I support:\n\n"
        "*AI Chat*\n"
        "Just send me a text message, and I'll respond using AI.\n\n"
        "*Group Management (requires admin privileges):*\n"
        "/ban - Reply to a user's message to ban them.\n"
        "/unban - Reply to a user's message to unban them.\n"
        "/mute - Reply to a user's message to mute them.\n"
        "/unmute - Reply to a user's message to unmute them.\n"
        "/kick - Reply to a user's message to kick them.\n\n"
        "*Utility Commands:*\n"
        "/start - Show this welcome message.\n"
        "/help - List all available commands.\n"
        "/id - Show your user ID and the chat ID.\n"
        "/info - Reply to a message to get info about that user.\n\n"
        "*Fun & Tools:*\n"
        "/weather <city> - Get current weather information.\n"
        "/translate <lang> <text> - Translate text to the specified language.\n"
        "/joke - Get a random joke.\n"
        "/quote - Get a random inspirational quote.\n"
        "/calc <expression> - Evaluate a mathematical expression.\n"
        "/remind <minutes> <message> - Set a reminder.\n\n"
        "*Media Tools:*\n"
        "/qr <text> - Generate a QR code from text.\n\n"
        "*Search:*\n"
        "/google <query> - Search the web using Google.\n\n"
        "I also welcome new members automatically in groups!"
    )
    await update.message.reply_html(welcome_message, reply_markup=ForceReply(selective=True))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_message = (
        "Here are the commands I support:\n\n"
        "*AI Chat*\n"
        "Just send me a text message, and I'll respond using AI.\n\n"
        "*Group Management (requires admin privileges):*\n"
        "/ban - Reply to a user's message to ban them.\n"
        "/unban - Reply to a user's message to unban them.\n"
        "/mute - Reply to a user's message to mute them.\n"
        "/unmute - Reply to a user's message to unmute them.\n"
        "/kick - Reply to a user's message to kick them.\n\n"
        "*Utility Commands:*\n"
        "/start - Show the welcome message.\n"
        "/help - Show this help message.\n"
        "/id - Show your user ID and the chat ID.\n"
        "/info - Reply to a message to get info about that user.\n\n"
        "*Fun & Tools:*\n"
        "/weather <city> - Get current weather information.\n"
        "/translate <lang> <text> - Translate text to the specified language.\n"
        "/joke - Get a random joke.\n"
        "/quote - Get a random inspirational quote.\n"
        "/calc <expression> - Evaluate a mathematical expression.\n"
        "/remind <minutes> <message> - Set a reminder.\n\n"
        "*Media Tools:*\n"
        "/qr <text> - Generate a QR code from text.\n\n"
        "*Search:*\n"
        "/google <query> - Search the web using Google.\n\n"
        "I also welcome new members automatically in groups!"
    )
    await update.message.reply_html(help_message)

async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to user messages using OpenAI API."""
    if update.message and update.message.text:
        try:
            response = openai_client.chat.completions.create(
                model="gemini-2.5-flash",
                messages=conversation_history[update.effective_chat.id] + [{"role": "user", "content": update.message.text}],
                # Add a system prompt to guide Gemini's behavior
                system_prompt=(
                    "You are a highly capable, knowledgeable, and helpful AI assistant, similar to Gemini Pro. "
                    "Provide detailed, comprehensive, and well-structured responses. "
                    "Always respond in the same language the user writes in."
                )
            )
            ai_response = response.choices[0].message.content
            await update.message.reply_text(ai_response)
            # Store conversation history
            conversation_history[update.effective_chat.id].append({"role": "user", "content": update.message.text})
            conversation_history[update.effective_chat.id].append({"role": "assistant", "content": ai_response})
        except Exception as e:
            logger.error(f"Error in AI chat: {e}")
            await update.message.reply_text("Sorry, I couldn't process that with AI right now.")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user and chat ID."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Your User ID: `{user_id}`\nChat ID: `{chat_id}`", parse_mode='MarkdownV2')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user info of a replied message."""
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        user_info = (
            f"*User Info:*\n"
            f"ID: `{target_user.id}`\n"
            f"First Name: {target_user.first_name}\n"
            f"Last Name: {target_user.last_name or 'N/A'}\n"
            f"Username: @{target_user.username or 'N/A'}\n"
            f"Is Bot: {target_user.is_bot}"
        )
        await update.message.reply_text(user_info, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("Please reply to a user's message to get their info.")

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcomes new members to the group."""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Bot itself was added to the group
            await update.message.reply_text("Hello everyone! Thanks for adding me. Use /start to see what I can do.")
        else:
            welcome_message = f"Welcome, {member.mention_html()}! Glad to have you here. Use /start to see available commands." 
            await update.message.reply_html(welcome_message)

# --- Group Management Commands ---
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bans a user from the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the user you want to ban.")
        return

    target_user = update.message.reply_to_message.from_user
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("You need to be an admin to use this command.")
        return
    
    if await is_admin(update, context, target_user.id):
        await update.message.reply_text("Cannot ban an admin.")
        return

    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(f"User {target_user.mention_html()} has been banned.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await update.message.reply_text("Failed to ban user. Make sure I have admin privileges.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unbans a user from the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the user you want to unban.")
        return

    target_user = update.message.reply_to_message.from_user
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("You need to be an admin to use this command.")
        return

    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(f"User {target_user.mention_html()} has been unbanned.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await update.message.reply_text("Failed to unban user. Make sure I have admin privileges.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user in the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the user you want to mute.")
        return

    target_user = update.message.reply_to_message.from_user
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("You need to be an admin to use this command.")
        return
    
    if await is_admin(update, context, target_user.id):
        await update.message.reply_text("Cannot mute an admin.")
        return

    try:
        # Mute for 1 hour as an example
        until_date = datetime.now() + timedelta(hours=1)
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until_date
        )
        await update.message.reply_text(f"User {target_user.mention_html()} has been muted for 1 hour.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error muting user: {e}")
        await update.message.reply_text("Failed to mute user. Make sure I have admin privileges.")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmutes a user in the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the user you want to unmute.")
        return

    target_user = update.message.reply_to_message.from_user
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("You need to be an admin to use this command.")
        return

    try:
        # Unmute by setting permissions to allow sending messages
        await context.bot.restrict_chat_member(
            update.effective_chat.id, target_user.id, permissions=ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text(f"User {target_user.mention_html()} has been unmuted.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error unmuting user: {e}")
        await update.message.reply_text("Failed to unmute user. Make sure I have admin privileges.")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kicks a user from the group."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the user you want to kick.")
        return

    target_user = update.message.reply_to_message.from_user
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("You need to be an admin to use this command.")
        return
    
    if await is_admin(update, context, target_user.id):
        await update.message.reply_text("Cannot kick an admin.")
        return

    try:
        # Kicking is essentially banning and then unbanning immediately
        await context.bot.unban_chat_member(update.effective_chat.id, target_user.id)
        await update.message.reply_text(f"User {target_user.mention_html()} has been kicked.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error kicking user: {e}")
        await update.message.reply_text("Failed to kick user. Make sure I have admin privileges.")

# --- Fun & Tools ---
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get weather information for a city."""
    if not context.args:
        await update.message.reply_text("Please provide a city. Example: /weather London")
        return
    city = " ".join(context.args)

    geolocator = Nominatim(user_agent="telegram-bot-weather-app")
    try:
        location = geolocator.geocode(city, timeout=5)
        if not location:
            await update.message.reply_text(f"Could not find coordinates for {city}. Please try a different city or a more specific name.")
            return

        latitude = location.latitude
        longitude = location.longitude

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true&timezone=auto"
        response = requests.get(weather_url)
        response.raise_for_status()
        weather_data = response.json()

        if "current_weather" in weather_data:
            current_weather = weather_data["current_weather"]
            temperature = current_weather["temperature"]
            windspeed = current_weather["windspeed"]
            weathercode = current_weather["weathercode"]

            # Basic interpretation of weather codes (can be expanded)
            weather_description = "Unknown"
            if weathercode == 0: weather_description = "Clear sky"
            elif 1 <= weathercode <= 3: weather_description = "Mainly clear, partly cloudy, and overcast"
            elif 45 <= weathercode <= 48: weather_description = "Fog and depositing rime fog"
            elif 51 <= weathercode <= 57: weather_description = "Drizzle: Light, moderate, and dense intensity"
            elif 61 <= weathercode <= 67: weather_description = "Rain: Slight, moderate and heavy intensity"
            elif 71 <= weathercode <= 77: weather_description = "Snow fall: Slight, moderate, and heavy intensity"
            elif 80 <= weathercode <= 82: weather_description = "Rain showers: Slight, moderate, and violent"
            elif 85 <= weathercode <= 86: weather_description = "Snow showers: Slight and heavy"
            elif 95 <= weathercode <= 99: weather_description = "Thunderstorm: Slight or moderate, and thunderstorm with slight and heavy hail"

            await update.message.reply_text(
                f"Weather in {city} ({latitude:.2f}, {longitude:.2f}):\n"
                f"Temperature: {temperature}°C\n"
                f"Wind Speed: {windspeed} m/s\n"
                f"Conditions: {weather_description}"
            )
        else:
            await update.message.reply_text(f"Could not retrieve current weather for {city}.")

    except GeocoderTimedOut:
        await update.message.reply_text("Geocoding service timed out. Please try again.")
    except GeocoderServiceError as e:
        logger.error(f"Geocoding service error: {e}")
        await update.message.reply_text("Geocoding service error. Please try again later.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather data: {e}")
        await update.message.reply_text("Sorry, I couldn't fetch weather information right now. Please try again later.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in weather command: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching weather. Please try again.")

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translate text using AI."""
    if len(context.args) < 2:
        await update.message.reply_text("Please provide a target language and text. Example: /translate es Hello world")
        return
    
    target_lang = context.args[0]
    text_to_translate = " ".join(context.args[1:])

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": f"Translate the following text to {target_lang}."},
                {"role": "user", "content": text_to_translate},
            ],
        )
        translated_text = response.choices[0].message.content
        await update.message.reply_text(f"Translated to {target_lang}: {translated_text}")
    except Exception as e:
        logger.error(f"Error in translation: {e}")
        await update.message.reply_text("Sorry, I couldn't translate that right now.")

async def joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell a random joke."""
    try:
        response = requests.get("https://v2.jokeapi.dev/joke/Any?blacklistFlags=racist,sexist,explicit&type=single")
        response.raise_for_status() # Raise an exception for HTTP errors
        joke_data = response.json()
        if joke_data["error"] == False:
            await update.message.reply_text(joke_data["joke"])
        else:
            await update.message.reply_text("Couldn't fetch a joke right now. Try again later.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching joke: {e}")
        await update.message.reply_text("Sorry, I couldn't fetch a joke right now. Please try again later.")

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get a random inspirational quote."""
    try:
        response = requests.get("https://api.quotable.io/random")
        response.raise_for_status() # Raise an exception for HTTP errors
        quote_data = response.json()
        quote = f"\" {quote_data['content']} \" - {quote_data['author']}"
        await update.message.reply_text(quote)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching quote: {e}")
        await update.message.reply_text("Sorry, I couldn't fetch a quote right now. Please try again later.")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Evaluate a mathematical expression."""
    if not context.args:
        await update.message.reply_text("Please provide an expression to calculate. Example: /calc 2+2*3")
        return
    expression = " ".join(context.args)
    try:
        # Using eval is generally unsafe, but for a simple calculator bot, it might be acceptable
        # For production, a safer math expression parser should be used.
        result = eval(expression)
        await update.message.reply_text(f"Result: `{result}`", parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error in calculation: {e}")
        await update.message.reply_text("Invalid expression. Please provide a valid mathematical expression.")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set a reminder."""
    if len(context.args) < 2:
        await update.message.reply_text("Please provide minutes and a message. Example: /remind 5 Buy milk")
        return
    
    try:
        minutes = int(context.args[0])
        message = " ".join(context.args[1:])
        
        if minutes <= 0:
            await update.message.reply_text("Minutes must be a positive number.")
            return

        # Schedule the reminder
        due = datetime.now() + timedelta(minutes=minutes)
        job_context = {'chat_id': update.effective_chat.id, 'user_id': update.effective_user.id, 'message': message}
        context.job_queue.run_once(send_reminder, minutes * 60, data=job_context, name=f"reminder_{update.effective_user.id}_{due}")
        
        await update.message.reply_text(f"Reminder set for {minutes} minutes from now: '{message}'")
    except ValueError:
        await update.message.reply_text("Invalid minutes. Please provide a number.")
    except Exception as e:
        logger.error(f"Error setting reminder: {e}")
        await update.message.reply_text("Failed to set reminder.")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the reminder message."""
    job_context = context.job.data
    chat_id = job_context['chat_id']
    user_id = job_context['user_id']
    message = job_context['message']
    # Fetch the user's mention_html again to ensure it's up-to-date
    # In a job_queue context, `update` is not available directly. We need to fetch the chat member via chat_id and user_id.
    # For now, we'll just use a generic mention if we can't fetch the user directly.
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        user_mention = member.user.mention_html()
    except Exception as e:
        logger.warning(f"Could not fetch chat member for reminder: {e}. Using generic mention.")
        user_mention = f"User {user_id}"
    await context.bot.send_message(chat_id, f"🔔 Reminder for {user_mention}: {message}", parse_mode='HTML')

# --- Media Tools ---
async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate QR code."""
    if not context.args:
        await update.message.reply_text("Please provide text to generate a QR code. Example: /qr Hello World")
        return
    text = " ".join(context.args)
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save image to a BytesIO object
        bio = io.BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)

        await update.message.reply_photo(photo=bio, caption=f"QR Code for: `{text}`", parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error generating QR code: {e}")
        await update.message.reply_text("Sorry, I couldn't generate the QR code right now.")

# --- Search ---
async def google_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search the web using Google."""
    if not context.args:
        await update.message.reply_text("Please provide a search query. Example: /google latest news")
        return
    query = " ".join(context.args)
    # Integrating with a real Google Search API (like Custom Search API) requires an API key and setup.
    # For this example, we'll provide a link to a Google search.
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    await update.message.reply_text(f"Here's a Google search for '{query}': {search_url}")


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # On different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("info", info_command))

    # Group Management
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # Fun & Tools
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("joke", joke_command))
    application.add_handler(CommandHandler("quote", quote_command))
    application.add_handler(CommandHandler("calc", calc_command))
    application.add_handler(CommandHandler("remind", remind_command))

    # Media Tools
    application.add_handler(CommandHandler("qr", qr_command))

    # Search
    application.add_handler(CommandHandler("google", google_command))

    # On non-command messages - respond with AI chat
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
