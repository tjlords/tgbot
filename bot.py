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
        self.bot_user_id = None  # Will be set when client starts

    def setup_handlers(self):
        """Setup command handlers"""
        # Filter to only respond when the message is sent to the bot itself
        def bot_self_filter(_, __, message: Message):
            # Only respond if the message is sent to the bot's own user account
            if message.chat.type == "private":
                # In private chat, check if it's the bot talking to itself
                return message.from_user and message.from_user.id == self.bot_user_id
            return False
        
        bot_self_filter = filters.create(bot_self_filter)

        @self.app.on_message(filters.command("start") & bot_self_filter)
        async def start_handler(client, message):
            await self.handle_start(message)

        @self.app.on_message(filters.command("backup") & bot_self_filter)
        async def backup_handler(client, message):
            await self.handle_backup(message)

        @self.app.on_message(filters.command("chats") & bot_self_filter)
        async def chats_handler(client, message):
            await self.handle_chats(message)
        
        # COMPLETELY IGNORE all other commands - no response at all
        @self.app.on_message(filters.command(["start", "backup", "chats"]))
        async def ignore_all_other_commands(client, message):
            # Simply return without doing anything - no response at all
            return

    async def handle_start(self, message: Message):
        """Handle /tgprostart command"""
        help_text = """
🤖 **Smart Backup Bot - RANGES & EXACT COPY**

✅ **Supports ALL message ranges:**
• Single: `/tgprobackup https://t.me/c/123456789/4/18`
• Range: `/tgprobackup https://t.me/c/123456789/4/10-16`
• Multiple: `/tgprobackup https://t.me/c/123456789/4/1,4,5-10`
• Mixed: `/tgprobackup https://t.me/c/123456789/4/1,3,5-8,10`

✅ **Preserves original captions exactly**
✅ **Handles all link formats**

**Commands:**
`/tgprobackup [link]` - Backup messages
`/chats` - List your available groups
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
        """Handle /tgprobackup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link\nExample: `/tgprobackup https://t.me/c/123456789/4/18`")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`\n🔍 Discovering correct chat ID...")

            # Extract message IDs and find correct chat - UPDATED FOR RANGES
            message_ids = self.extract_message_ids_all_formats(link)
            if not message_ids:
                await message.reply("❌ Could not extract message IDs from link")
                return

            # Find the correct chat ID automatically
            chat = await self.find_correct_chat(link, message.chat.id)
            if not chat:
                await message.reply("❌ Could not find the chat. Make sure you're a member and try `/chats` to see available chats.")
                return

            await message.reply(f"✅ Found: **{chat['title']}**\n📊 Starting backup of {len(message_ids)} messages...")

            success_count = await self.process_backup(chat, message_ids, message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Processed: {success_count}/{len(message_ids)} messages from **{chat['title']}**")
            else:
                await message.reply("❌ No messages were backed up")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    def extract_message_ids_all_formats(self, link):
        """
        Extract message IDs from ALL formats including ranges:
        - Single: https://t.me/c/123456789/4/18
        - Range: https://t.me/c/123456789/4/10-16
        - Multiple: https://t.me/c/123456789/4/1,4,5-10
        - Mixed: https://t.me/c/123456789/4/1,3,5-8,10
        """
        try:
            if 't.me/c/' in link:
                parts = link.split('/')
                # Get the last part which contains message ID(s)
                message_part = parts[-1]
                
                logger.info(f"🔍 Parsing message part: {message_part}")
                
                # Parse the message part for ranges and multiple IDs
                message_ids = self.parse_message_range(message_part)
                
                if message_ids:
                    logger.info(f"✅ Extracted {len(message_ids)} message IDs: {message_ids[:10]}{'...' if len(message_ids) > 10 else ''}")
                    return message_ids
            
            return None
        except Exception as e:
            logger.error(f"Error extracting message IDs: {e}")
            return None

    def parse_message_range(self, range_str):
        """Parse message range string into list of message IDs"""
        try:
            message_ids = []
            
            # Handle comma-separated values
            parts = [part.strip() for part in range_str.split(',')]
            
            for part in parts:
                if '-' in part:
                    # Handle range like "10-16"
                    start_end = part.split('-')
                    if len(start_end) == 2 and start_end[0].isdigit() and start_end[1].isdigit():
                        start = int(start_end[0])
                        end = int(start_end[1])
                        if start <= end:
                            # Add all IDs in range
                            message_ids.extend(range(start, end + 1))
                        else:
                            # Reverse range if start > end
                            message_ids.extend(range(end, start + 1))
                else:
                    # Handle single number like "18"
                    if part.isdigit():
                        message_ids.append(int(part))
            
            # Remove duplicates and sort
            message_ids = sorted(set(message_ids))
            return message_ids
            
        except Exception as e:
            logger.error(f"Error parsing range {range_str}: {e}")
            return []

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
            await self.app.send_message(user_chat_id, "🔍 Searching in your recent chats...")
            user_chats = await self.get_user_chats()
            
            # Try to find a message in each chat to verify access
            message_ids = self.extract_message_ids_all_formats(link)
            if message_ids:
                first_message_id = message_ids[0]
                for chat in user_chats:
                    try:
                        # Try to get the first message to verify access
                        message = await self.app.get_messages(chat['id'], first_message_id)
                        if message and not getattr(message, "empty", False):
                            logger.info(f"✅ Verified chat {chat['title']} has message {first_message_id}")
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

                        # Backup message WITH ORIGINAL CAPTION
                        await self.backup_single_message_exact(message, chat)
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

    async def backup_single_message_exact(self, message, chat):
        """Backup a single message with EXACT original caption"""
        try:
            # PRESERVE ORIGINAL CAPTION EXACTLY - NO ADDED METADATA
            original_caption = message.caption or ""
            
            # For text messages without media, use the text as caption
            if not message.media and message.text:
                original_caption = message.text

            if message.media:
                # Download and upload media
                file_path = await message.download()
                
                if file_path and os.path.exists(file_path):
                    if message.video:
                        await self.app.send_video(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,  # Original caption only
                            supports_streaming=True
                        )
                    elif message.photo:
                        await self.app.send_photo(
                            self.dest_channel,
                            file_path,
                            caption=original_caption  # Original caption only
                        )
                    else:
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=original_caption  # Original caption only
                        )
                    
                    # Clean up
                    os.remove(file_path)
                else:
                    # Forward as fallback (preserves original content)
                    await message.forward(self.dest_channel)
            else:
                # Text message - send original text only
                await self.app.send_message(self.dest_channel, original_caption)

            logger.info(f"✅ Backed up message {message.id} with original caption")

        except FloodWait as e:
            logger.warning(f"🚫 Flood wait: {e.value}s")
            await asyncio.sleep(e.value + 5)
            await self.backup_single_message_exact(message, chat)
        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise

    async def run_telegram_bot(self):
        """Run the Telegram bot part"""
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name}")
            
            # Store the bot's own user ID
            self.bot_user_id = me.id
            logger.info(f"🤖 Bot User ID: {self.bot_user_id}")
            
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