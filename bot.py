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
    return "🤖 Backup Bot is running!"

@app.route('/health')
def health():
    return "✅ OK"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BackupBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_string = os.getenv('USER_SESSION_STRING')
        self.dest_channel = int(os.getenv('DESTINATION_CHANNEL'))
        self.min_delay = int(os.getenv('MIN_DELAY', '5'))
        self.max_delay = int(os.getenv('MAX_DELAY', '15'))
        
        self.app = Client(
            "backup_bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string
        )
        
        self.setup_handlers()

    def setup_handlers(self):
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.handle_start(message)

        @self.app.on_message(filters.command("backup"))
        async def backup_handler(client, message):
            await self.handle_backup(message)

        @self.app.on_message(filters.command("verify"))
        async def verify_handler(client, message):
            await self.handle_verify(message)

    async def handle_start(self, message: Message):
        help_text = """
🤖 **Backup Bot - ALL FORMATS**

✅ **Supports all link formats:**
• Groups with topics: `/backup https://t.me/c/3166766661/4/19`
• Normal groups: `/backup https://t.me/c/3166766661/19`  
• Channels: `/backup https://t.me/c/2973208943/3`

✅ **Output verification**
✅ **Exact copy preservation**

**Commands:**
`/backup [link]` - Backup message
`/verify` - Check where backups are sent
        """
        await message.reply(help_text)

    async def handle_verify(self, message: Message):
        """Verify where backups are sent"""
        try:
            # Get destination channel info
            dest_chat = await self.app.get_chat(self.dest_channel)
            await message.reply(
                f"🔍 **Backup Destination:**\n"
                f"📢 **Channel:** {dest_chat.title}\n"
                f"🆔 **ID:** `{dest_chat.id}`\n"
                f"🔗 **Type:** {dest_chat.type}\n\n"
                f"✅ All backups are sent to this channel"
            )
        except Exception as e:
            await message.reply(f"❌ Cannot verify destination: {e}")

    async def handle_backup(self, message: Message):
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`")

            # Extract chat ID and message ID using new method
            chat_id, message_id = self.extract_from_link(link)
            if not chat_id or not message_id:
                await message.reply("❌ Invalid link format")
                return

            await message.reply(f"🔍 Extracted - Chat: `{chat_id}`, Message: `{message_id}`")

            # Find correct chat
            chat = await self.find_correct_chat(chat_id, message.chat.id)
            if not chat:
                await message.reply("❌ Could not access the chat")
                return

            await message.reply(f"✅ Found: **{chat['title']}**\n📊 Starting backup...")

            success_count = await self.process_backup(chat, [message_id], message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Processed: {success_count} messages to backup channel")
            else:
                await message.reply("❌ No messages were backed up")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    def extract_from_link(self, link):
        """
        Extract chat ID and message ID from all formats:
        - Groups with topics: https://t.me/c/3166766661/4/19
        - Normal groups: https://t.me/c/3166766661/19  
        - Channels: https://t.me/c/2973208943/3
        """
        try:
            if 't.me/c/' in link:
                # Remove protocol and get the path after /c/
                path = link.split('/c/')[1]
                parts = path.split('/')
                
                logger.info(f"🔍 Parsing link parts: {parts}")
                
                if len(parts) >= 2:
                    chat_id_from_link = parts[0]
                    
                    # The last part is always the message ID
                    message_id = int(parts[-1])
                    
                    logger.info(f"✅ Extracted - Chat ID: {chat_id_from_link}, Message ID: {message_id}")
                    return chat_id_from_link, message_id
            
            logger.error("❌ Could not parse link format")
            return None, None
            
        except Exception as e:
            logger.error(f"Link extraction error: {e}")
            return None, None

    async def find_correct_chat(self, chat_id_from_link, user_chat_id):
        """Find the correct chat using multiple formats"""
        try:
            # Try different chat ID formats
            chat_formats = [
                f"-100{chat_id_from_link}",  # Most common for supergroups/channels
                f"-{chat_id_from_link}",     # Alternative format
                chat_id_from_link,           # Original format from link
            ]
            
            logger.info(f"🔄 Trying chat formats: {chat_formats}")
            
            for chat_id in chat_formats:
                try:
                    chat = await self.app.get_chat(chat_id)
                    logger.info(f"✅ Found chat: {chat.title} with ID: {chat_id}")
                    return {
                        'id': chat.id,
                        'title': chat.title,
                        'type': chat.type
                    }
                except Exception as e:
                    logger.info(f"❌ Failed with {chat_id}: {e}")
                    continue

            # If all formats fail, try to find in user's dialogs
            await user_chat_id.reply("🔍 Searching in your dialogs...")
            async for dialog in self.app.get_dialogs():
                chat = dialog.chat
                if chat.type in ["group", "supergroup", "channel"]:
                    # Check if this might be our target chat
                    chat_id_str = str(chat.id).replace('-100', '').replace('-', '')
                    if chat_id_from_link in chat_id_str:
                        logger.info(f"🎯 Found matching chat in dialogs: {chat.title}")
                        return {
                            'id': chat.id,
                            'title': chat.title,
                            'type': chat.type
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding chat: {e}")
            return None

    async def process_backup(self, chat, message_ids, user_chat_id):
        try:
            total = len(message_ids)
            success_count = 0

            status_msg = await self.app.send_message(user_chat_id, f"📊 Processing {total} messages...")

            for i, msg_id in enumerate(message_ids, 1):
                try:
                    # Get original message
                    original_msg = await self.app.get_messages(chat['id'], msg_id)
                    
                    if not original_msg or getattr(original_msg, "empty", False):
                        logger.warning(f"Message {msg_id} not found")
                        continue

                    # Safety delay
                    delay = random.randint(self.min_delay, self.max_delay)
                    await asyncio.sleep(delay)

                    # Backup with exact copy
                    await self.backup_exact_copy(original_msg, chat)
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

    async def backup_exact_copy(self, original_msg, chat):
        """Create exact copy with original caption and file names"""
        try:
            # Preserve original caption exactly
            original_caption = original_msg.caption or ""

            if original_msg.media:
                # Download with original file name
                file_path = await original_msg.download()
                
                if file_path and os.path.exists(file_path):
                    # Send with original attributes
                    if original_msg.video:
                        await self.app.send_video(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            duration=original_msg.video.duration,
                            width=original_msg.video.width,
                            height=original_msg.video.height,
                            supports_streaming=True
                        )
                    
                    elif original_msg.audio:
                        await self.app.send_audio(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            duration=original_msg.audio.duration,
                            performer=original_msg.audio.performer,
                            title=original_msg.audio.title
                        )
                    
                    elif original_msg.document:
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            file_name=original_msg.document.file_name
                        )
                    
                    elif original_msg.photo:
                        await self.app.send_photo(
                            self.dest_channel,
                            file_path,
                            caption=original_caption
                        )
                    
                    else:
                        # Fallback for other media
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=original_caption
                        )
                    
                    # Clean up
                    os.remove(file_path)
                
                else:
                    # Fallback: forward
                    await original_msg.forward(self.dest_channel)
            
            else:
                # Text message
                if original_msg.text:
                    await self.app.send_message(
                        self.dest_channel,
                        original_msg.text
                    )

            logger.info(f"✅ Backed up message {original_msg.id} to channel {self.dest_channel}")

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            # Fallback to simple forward
            try:
                await original_msg.forward(self.dest_channel)
            except:
                pass

    async def run_telegram_bot(self):
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"✅ Connected as: {me.first_name}")
            
            # Verify destination channel
            try:
                dest_chat = await self.app.get_chat(self.dest_channel)
                logger.info(f"✅ Backup destination: {dest_chat.title} (ID: {dest_chat.id})")
            except Exception as e:
                logger.error(f"❌ Cannot access backup channel: {e}")
            
            await asyncio.Future()  # Keep running
        except Exception as e:
            logger.error(f"Telegram bot crashed: {e}")
        finally:
            await self.app.stop()

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

async def main():
    bot = BackupBot()
    await asyncio.gather(
        bot.run_telegram_bot(),
        asyncio.to_thread(run_flask)
    )

if __name__ == '__main__':
    asyncio.run(main())
