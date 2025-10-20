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

    async def handle_start(self, message: Message):
        help_text = """
🤖 **Backup Bot - EXACT COPY**

✅ **Preserves original captions and file names**
✅ **Same reliable web service**
✅ **No port issues**

**Usage:**
`/backup https://t.me/c/1234567890/18`

**Features:**
• Original captions preserved
• File names unchanged  
• Media attributes kept
• Safe rate limiting
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link\nExample: `/backup https://t.me/c/1234567890/18`")
                return

            link = message.command[1]
            await message.reply(f"🔄 Processing: `{link}`")

            # Extract message ID
            message_id = self.extract_message_id(link)
            if not message_id:
                await message.reply("❌ Could not extract message ID")
                return

            # Find correct chat
            chat = await self.find_correct_chat(link, message.chat.id)
            if not chat:
                await message.reply("❌ Could not find the chat")
                return

            await message.reply(f"✅ Found: **{chat['title']}**\n📊 Starting backup...")

            success_count = await self.process_backup(chat, [message_id], message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Processed: {success_count} messages")
            else:
                await message.reply("❌ No messages were backed up")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    def extract_message_id(self, link):
        try:
            if 't.me/c/' in link:
                parts = link.split('/')
                for part in reversed(parts):
                    if part.isdigit():
                        return int(part)
            return None
        except:
            return None

    async def find_correct_chat(self, link, user_chat_id):
        try:
            link_chat_id = self.extract_chat_id_from_link(link)
            if link_chat_id:
                chat_formats = [f"-100{link_chat_id}", f"-{link_chat_id}"]
                
                for chat_id in chat_formats:
                    try:
                        chat = await self.app.get_chat(chat_id)
                        return {
                            'id': chat.id,
                            'title': chat.title,
                            'type': chat.type
                        }
                    except:
                        continue
            return None
        except Exception as e:
            logger.error(f"Error finding chat: {e}")
            return None

    def extract_chat_id_from_link(self, link):
        try:
            if 't.me/c/' in link:
                parts = link.split('/c/')[1].split('/')
                if parts:
                    return parts[0]
            return None
        except:
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

            logger.info(f"✅ Backed up message {original_msg.id}")

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
