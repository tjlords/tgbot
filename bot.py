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
    return "🤖 Smart Backup Bot is running!"

@app.route('/health')
def health():
    return "✅ OK"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SmartDiscoverBackupBot:
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
            "smart_discover_bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string
        )
        
        self.setup_handlers()
        self.chat_cache = {}  # Cache for chat IDs

    def setup_handlers(self):
        """Setup command handlers"""
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.handle_start(message)

        @self.app.on_message(filters.command("backup"))
        async def backup_handler(client, message):
            await self.handle_backup(message)

        @self.app.on_message(filters.command("chats"))
        async def chats_handler(client, message):
            await self.handle_chats(message)

    async def handle_start(self, message: Message):
        """Handle /start command"""
        help_text = """
🤖 **Smart Backup Bot - AUTO DISCOVER**

✅ **Automatically finds correct chat IDs**
✅ **No manual configuration needed**
✅ **Works with any group you're in**

**Usage:**
1. Send: `/backup https://t.me/c/3166766661/4/18`
2. Bot will automatically find the correct group
3. Or use `/chats` to see your available groups

**Examples:**
`/backup https://t.me/c/1234567890/18` - Single message
`/backup https://t.me/c/1234567890/18-25` - Range
        """
        await message.reply(help_text)

    async def handle_chats(self, message: Message):
        """List available chats"""
        try:
            await message.reply("🔍 Scanning your chats...")
            chats = await self.get_user_chats()
            
            if not chats:
                await message.reply("❌ No groups/channels found in your dialogs")
                return
            
            response = "📋 **Your Available Chats:**\n\n"
            for chat in chats[:10]:  # Show first 10 to avoid message too long
                response += f"**{chat['title']}**\n"
                response += f"   🆔 `{chat['id']}`\n"
                response += f"   👥 {chat['type']}\n"
                if chat.get('username'):
                    response += f"   🔗 @{chat['username']}\n"
                response += "\n"
            
            if len(chats) > 10:
                response += f"... and {len(chats) - 10} more chats"
            
            await message.reply(response)
            
        except Exception as e:
            await message.reply(f"❌ Error listing chats: {str(e)}")

    async def handle_backup(self, message: Message):
        """Handle /backup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link\nExample: `/backup https://t.me/c/3166766661/4/18`")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`\n🔍 Discovering correct chat ID...")

            # Extract message ID and find correct chat
            message_id = self.extract_message_id(link)
            if not message_id:
                await message.reply("❌ Could not extract message ID from link")
                return

            # Find the correct chat ID automatically
            chat = await self.find_correct_chat(link, message.chat.id)
            if not chat:
                await message.reply("❌ Could not find the chat. Make sure you're a member and try `/chats` to see available chats.")
                return

            await message.reply(f"✅ Found: **{chat['title']}**\n📊 Starting backup...")

            success_count = await self.process_backup(chat, [message_id], message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Processed: {success_count} messages from **{chat['title']}**")
            else:
                await message.reply("❌ No messages were backed up")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    def extract_message_id(self, link):
        """Extract message ID from link"""
        try:
            if 't.me/c/' in link:
                parts = link.split('/')
                # Get the last numeric part (message ID)
                for part in reversed(parts):
                    if part.isdigit():
                        return int(part)
            return None
        except:
            return None

    async def get_user_chats(self):
        """Get all groups/channels user is member of"""
        try:
            chats = []
            async for dialog in self.app.get_dialogs():
                chat = dialog.chat
                if chat.type in ["group", "supergroup", "channel"]:
                    chats.append({
                        'id': chat.id,
                        'title': chat.title,
                        'type': chat.type,
                        'username': getattr(chat, 'username', None)
                    })
            return chats
        except Exception as e:
            logger.error(f"Error getting user chats: {e}")
            return []

    async def find_correct_chat(self, link, user_chat_id):
        """Find the correct chat by trying different methods"""
        try:
            # Method 1: Extract chat ID from link and try different formats
            link_chat_id = self.extract_chat_id_from_link(link)
            if link_chat_id:
                # Try different formats
                formats_to_try = [
                    f"-100{link_chat_id}",  # Most common format
                    f"-{link_chat_id}",     # Alternative format
                    link_chat_id,           # Original format
                ]
                
                for chat_id in formats_to_try:
                    try:
                        chat = await self.app.get_chat(chat_id)
                        if chat:
                            logger.info(f"✅ Found chat with ID {chat_id}: {chat.title}")
                            return {
                                'id': chat.id,
                                'title': chat.title,
                                'type': chat.type
                            }
                    except Exception as e:
                        logger.info(f"❌ Failed with ID {chat_id}: {e}")
                        continue

            # Method 2: Check if we have this chat in dialogs by matching message
            await user_chat_id.reply("🔍 Searching in your recent chats...")
            user_chats = await self.get_user_chats()
            
            # Try to find a message in each chat to verify access
            message_id = self.extract_message_id(link)
            for chat in user_chats:
                try:
                    # Try to get the specific message
                    message = await self.app.get_messages(chat['id'], message_id)
                    if message and not getattr(message, "empty", False):
                        logger.info(f"✅ Verified chat {chat['title']} has message {message_id}")
                        return chat
                except Exception:
                    continue

            # Method 3: Ask user to forward a message
            await self.app.send_message(
                user_chat_id,
                "❓ Could not automatically find the chat.\n"
                "Please forward any message from that chat to me, then try again."
            )
            return None

        except Exception as e:
            logger.error(f"Error finding correct chat: {e}")
            return None

    def extract_chat_id_from_link(self, link):
        """Extract chat ID from link"""
        try:
            if 't.me/c/' in link:
                parts = link.split('/c/')[1].split('/')
                if parts:
                    return parts[0]
            return None
        except:
            return None

    async def process_backup(self, chat, message_ids, user_chat_id):
        """Process backup"""
        try:
            total = len(message_ids)
            success_count = 0

            status_msg = await self.app.send_message(user_chat_id, f"📊 Processing {total} messages from **{chat['title']}**...")

            for i, msg_id in enumerate(message_ids, 1):
                try:
                    # Get message
                    message = await self.app.get_messages(chat['id'], msg_id)
                    
                    if message and not getattr(message, "empty", False):
                        # Safety delay
                        delay = random.randint(self.min_delay, self.max_delay)
                        await asyncio.sleep(delay)

                        # Backup message
                        await self.backup_single_message(message, chat)
                        success_count += 1

                        logger.info(f"✅ Backed up message {msg_id} from {chat['title']}")
                    else:
                        logger.warning(f"⚠️ Message {msg_id} not found in {chat['title']}")

                    # Progress update
                    progress = f"📊 Progress: {i}/{total} ({success_count} successful)"
                    await status_msg.edit_text(progress)

                except FloodWait as e:
                    logger.warning(f"🚫 Flood wait: {e.value}s")
                    await asyncio.sleep(e.value + 5)
                except Exception as e:
                    logger.error(f"❌ Message {msg_id} failed: {e}")

            return success_count
                
        except Exception as e:
            logger.error(f"Backup process error: {e}")
            await self.app.send_message(user_chat_id, f"❌ Backup error: {str(e)}")
            return 0

    async def backup_single_message(self, message, chat):
        """Backup a single message"""
        try:
            # Create caption with metadata
            caption = f"{message.text or ''}\n\n" if message.text else ""
            caption += f"📁 ID: {message.id} | 📅 {message.date.strftime('%Y-%m-%d %H:%M')}"
            caption += f" | 🔗 {chat['title']}"

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
                    if caption.strip():
                        await self.app.send_message(self.dest_channel, caption)
            else:
                # Text message
                await self.app.send_message(self.dest_channel, caption)

        except FloodWait as e:
            logger.warning(f"🚫 Flood wait: {e.value}s")
            await asyncio.sleep(e.value + 5)
            await self.backup_single_message(message, chat)
        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise

    async def run_telegram_bot(self):
        """Run the Telegram bot part"""
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name}")
            
            # Preload user chats
            chats = await self.get_user_chats()
            logger.info(f"📋 Found {len(chats)} chats in user dialogs")
            
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
    bot = SmartDiscoverBackupBot()
    await asyncio.gather(
        bot.run_telegram_bot(),
        asyncio.to_thread(run_flask)
    )

if __name__ == '__main__':
    asyncio.run(main())
