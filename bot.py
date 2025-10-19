import asyncio
import logging
import os
import random
import re
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# Create Flask app for port binding
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Working Backup Bot is running!"

@app.route('/health')
def health():
    return "✅ OK"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebWorkingBackupBot:
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
            "web_working_bot",
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

    async def handle_start(self, message: Message):
        """Handle /start command"""
        help_text = """
🤖 **Working Backup Bot - WEB**

✅ **Proven link parsing**
✅ **Port binding fixed**
✅ **Ready to use**

**Usage:**
`/backup https://t.me/c/3166766661/4/18`
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        """Handle /backup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`")

            # Extract using proven method
            chat_id, message_ids, link_type = self.extract_link_info(link)
            
            if not chat_id or not message_ids:
                await message.reply("❌ Invalid link format")
                return

            success_count = await self.process_backup(chat_id, message_ids, link_type, message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed! Processed: {success_count} messages")
            else:
                await message.reply("❌ No messages backed up")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    def extract_link_info(self, link):
        """Extract chat ID and message IDs from link"""
        try:
            if 't.me/c/' in link:
                parts = link.split('/c/')[1].split('/')
                
                if len(parts) >= 2:
                    chat_id_from_link = parts[0]
                    message_part = parts[-1]
                    
                    if chat_id_from_link.isdigit():
                        # Convert to -100 format (most common)
                        chat_id_100 = f"-100{chat_id_from_link}"
                        
                        # Parse message range
                        message_ids = self.parse_message_range(message_part)
                        
                        return chat_id_100, message_ids, "private"
            
            return None, [], None
            
        except Exception as e:
            logger.error(f"Link parse error: {e}")
            return None, [], None

    def parse_message_range(self, range_str):
        """Parse message range from string"""
        try:
            if '-' not in range_str and ',' not in range_str:
                return [int(range_str)]
            
            if '-' in range_str:
                start, end = map(int, range_str.split('-'))
                return list(range(start, end + 1))
            
            if ',' in range_str:
                return [int(x.strip()) for x in range_str.split(',')]
            
            return []
            
        except Exception as e:
            logger.error(f"Range parse error: {e}")
            return []

    async def process_backup(self, chat_id, message_ids, link_type, user_chat_id):
        """Process backup"""
        try:
            total = len(message_ids)
            success_count = 0

            status_msg = await self.app.send_message(user_chat_id, f"📊 Processing {total} messages...")

            for i, msg_id in enumerate(message_ids, 1):
                try:
                    # Try to get message
                    message = await self.app.get_messages(chat_id, msg_id)
                    
                    if message and not getattr(message, "empty", False):
                        # Safety delay
                        delay = random.randint(self.min_delay, self.max_delay)
                        await asyncio.sleep(delay)

                        # Backup message
                        await self.backup_single_message(message)
                        success_count += 1

                    # Progress update
                    progress = f"📊 Progress: {i}/{total} ({success_count} successful)"
                    await status_msg.edit_text(progress)

                except FloodWait as e:
                    await asyncio.sleep(e.value + 5)
                except Exception as e:
                    logger.error(f"Message {msg_id} failed: {e}")

            return success_count
                
        except Exception as e:
            logger.error(f"Backup process error: {e}")
            return 0

    async def backup_single_message(self, message):
        """Backup a single message"""
        try:
            caption = f"{message.text or ''}\n\n📁 ID: {message.id}"

            if message.media:
                file_path = await message.download()
                
                if file_path and os.path.exists(file_path):
                    if message.video:
                        await self.app.send_video(self.dest_channel, file_path, caption=caption, supports_streaming=True)
                    elif message.photo:
                        await self.app.send_photo(self.dest_channel, file_path, caption=caption)
                    else:
                        await self.app.send_document(self.dest_channel, file_path, caption=caption)
                    
                    os.remove(file_path)
                else:
                    await message.forward(self.dest_channel)
            else:
                await self.app.send_message(self.dest_channel, caption)

            logger.info(f"✅ Backed up message {message.id}")

        except Exception as e:
            logger.error(f"Failed to backup message {message.id}: {e}")
            raise

    async def run_telegram_bot(self):
        """Run the Telegram bot part"""
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name}")
            await asyncio.Future()  # Run forever
        except Exception as e:
            logger.error(f"Telegram bot crashed: {e}")
        finally:
            await self.app.stop()

def run_flask():
    """Run Flask web server"""
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

async def main():
    bot = WebWorkingBackupBot()
    await asyncio.gather(
        bot.run_telegram_bot(),
        asyncio.to_thread(run_flask)
    )

if __name__ == '__main__':
    asyncio.run(main())
