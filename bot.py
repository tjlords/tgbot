import asyncio
import logging
import os
import random
import re
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# Create Flask app for port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Backup Bot is running!"

@app.route('/health')
def health():
    return "✅ OK"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebServiceBackupBot:
    def __init__(self):
        # Get environment variables
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_string = os.getenv('USER_SESSION_STRING')
        self.dest_channel = int(os.getenv('DESTINATION_CHANNEL'))
        self.min_delay = int(os.getenv('MIN_DELAY', '5'))
        self.max_delay = int(os.getenv('MAX_DELAY', '15'))
        
        # Create Pyrogram client
        self.app = Client(
            "webservice_bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string
        )
        
        self.setup_handlers()

    def setup_handlers(self):
        """Setup command handlers"""
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.handle_start(message)

        @self.app.on_message(filters.command("backup"))
        async def backup_handler(client, message):
            await self.handle_backup(message)

        @self.app.on_message(filters.command("status"))
        async def status_handler(client, message):
            await self.handle_status(message)

    async def handle_start(self, message: Message):
        """Handle /start command"""
        help_text = """
🤖 **Web Service Backup Bot**

✅ **Fixed port binding**
✅ **Works with any group**

**How to use:**
1. Forward any message from your target group to me
2. Send: `/backup [message-link]`

**Examples:**
`/backup https://t.me/c/1234567890/18` - Backup message 18
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        """Handle /backup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link\nExample: `/backup https://t.me/c/1234567890/18`")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`")

            success_count = await self.process_backup_smart(link, message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Processed: {success_count} messages")
            else:
                await message.reply("❌ Could not backup. Try forwarding a message from that group first.")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    async def handle_status(self, message: Message):
        """Handle /status command"""
        try:
            me = await self.app.get_me()
            status_text = f"""
📊 **Web Service Backup Bot**

✅ Connected: Yes
👤 Account: {me.first_name}
🆔 Your ID: {me.id}
🌐 Web Service: Running
💡 Ready for commands!
            """
            await message.reply(status_text)
        except Exception as e:
            await message.reply(f"❌ Status error: {str(e)}")

    async def process_backup_smart(self, link, chat_id):
        """Smart backup processing"""
        try:
            # Extract message ID from link
            message_id = self.extract_message_id(link)
            if not message_id:
                await self.app.send_message(chat_id, "❌ Could not extract message ID from link")
                return 0

            # Get the group from recent forwarded messages
            group = await self.find_group_from_history(chat_id)
            if not group:
                await self.app.send_message(
                    chat_id,
                    "❌ Could not determine the group.\n"
                    "Please forward any message from that group to me first."
                )
                return 0

            return await self.backup_messages(group, [message_id], chat_id)
                
        except Exception as e:
            logger.error(f"Backup process error: {e}")
            await self.app.send_message(chat_id, f"❌ Backup error: {str(e)}")
            return 0

    def extract_message_id(self, link):
        """Extract message ID from link"""
        try:
            if 't.me/c/' in link:
                parts = link.split('/')
                # Get the last numeric part
                for part in reversed(parts):
                    if part.isdigit():
                        return int(part)
            return None
        except:
            return None

    async def find_group_from_history(self, chat_id):
        """Find group from message history"""
        try:
            # Get recent messages to find forwarded content
            async for message in self.app.get_chat_history(chat_id, limit=50):
                if message.forward_from_chat:
                    # Found a forwarded message from a group
                    group = message.forward_from_chat
                    logger.info(f"🎯 Found group from history: {group.title}")
                    return group
            return None
        except Exception as e:
            logger.error(f"Error finding group from history: {e}")
            return None

    async def backup_messages(self, group, message_ids, chat_id):
        """Backup multiple messages"""
        total = len(message_ids)
        success_count = 0

        status_msg = await self.app.send_message(chat_id, f"📊 Processing {total} messages from {group.title}...")

        for i, msg_id in enumerate(message_ids, 1):
            try:
                # Get message
                message = await self.app.get_messages(group.id, msg_id)
                if not message or message.empty:
                    logger.warning(f"⚠️ Message {msg_id} not found")
                    continue

                # Safety delay
                delay = random.randint(self.min_delay, self.max_delay)
                logger.info(f"⏳ Waiting {delay}s before message {msg_id}")
                await asyncio.sleep(delay)

                # Backup message
                await self.backup_single_message(message, group)
                success_count += 1

                # Progress update
                progress = f"📊 Progress: {i}/{total} ({success_count} successful)"
                await status_msg.edit_text(progress)

            except FloodWait as e:
                logger.warning(f"🚫 Flood wait: {e.value}s")
                await asyncio.sleep(e.value + 5)
            except Exception as e:
                logger.error(f"❌ Message {msg_id} failed: {e}")

        return success_count

    async def backup_single_message(self, message, group):
        """Backup a single message"""
        try:
            # Create caption
            caption = f"{message.text or ''}\n\n📁 ID: {message.id} | 📅 {message.date.strftime('%Y-%m-%d %H:%M')}"

            if message.media:
                # Download and upload media
                file_path = await message.download()
                
                if file_path and os.path.exists(file_path):
                    if message.video:
                        await self.app.send_video(
                            self.dest_channel,
                            file_path,
                            caption=caption,
                            supports_streaming=True
                        )
                    elif message.photo:
                        await self.app.send_photo(
                            self.dest_channel,
                            file_path,
                            caption=caption
                        )
                    else:
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=caption
                        )
                    
                    # Clean up
                    os.remove(file_path)
                else:
                    # Forward as fallback
                    await message.forward(self.dest_channel)
            else:
                # Text message
                await self.app.send_message(self.dest_channel, caption)

            logger.info(f"✅ Backed up message {message.id}")

        except FloodWait as e:
            logger.warning(f"🚫 Flood wait: {e.value}s")
            await asyncio.sleep(e.value + 5)
        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise

    async def run_telegram_bot(self):
        """Run the Telegram bot part"""
        try:
            logger.info("🚀 Starting Telegram Bot...")
            await self.app.start()
            
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name}")
            
            logger.info("✅ Telegram Bot is running!")
            
            # Keep the bot running
            await asyncio.Future()  # Run forever
            
        except Exception as e:
            logger.error(f"💥 Telegram bot crashed: {e}")
        finally:
            await self.app.stop()

def run_flask():
    """Run Flask web server"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

async def main():
    # Start Telegram bot in background
    telegram_bot = WebServiceBackupBot()
    
    # Run Flask and Telegram bot concurrently
    await asyncio.gather(
        telegram_bot.run_telegram_bot(),
        asyncio.to_thread(run_flask)
    )

if __name__ == '__main__':
    asyncio.run(main())
