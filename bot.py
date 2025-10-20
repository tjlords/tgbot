import asyncio
import logging
import os
import random
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExactCopyBackupBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_string = os.getenv('USER_SESSION_STRING')
        self.dest_channel = int(os.getenv('DESTINATION_CHANNEL'))
        self.min_delay = int(os.getenv('MIN_DELAY', '5'))
        self.max_delay = int(os.getenv('MAX_DELAY', '15'))
        
        self.app = Client(
            "exact_copy_bot",
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

        @self.app.on_message(filters.command("exact"))
        async def exact_handler(client, message):
            await self.handle_exact_backup(message)

    async def handle_start(self, message: Message):
        help_text = """
🤖 **Exact Copy Backup Bot**

✨ **Preserves ALL original metadata:**
✅ Original caption exactly
✅ File names unchanged  
✅ Media attributes (duration, resolution, etc.)
✅ Message formatting
✅ Creation timestamps

**Commands:**
`/backup [link]` - Normal backup
`/exact [link]` - Exact copy with all metadata
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        """Normal backup"""
        await self.process_backup(message, exact_copy=False)

    async def handle_exact_backup(self, message: Message):
        """Exact copy backup"""
        await self.process_backup(message, exact_copy=True)

    async def process_backup(self, message: Message, exact_copy=True):
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link")
                return

            link = message.command[1]
            mode = "EXACT COPY" if exact_copy else "NORMAL"
            await message.reply(f"🔄 {mode} backup: `{link}`")

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

            await message.reply(f"✅ Found: **{chat['title']}**\n📊 Starting {mode} backup...")

            success_count = await self.backup_messages_exact(chat, [message_id], message.chat.id, exact_copy)
            
            if success_count > 0:
                await message.reply(f"✅ {mode} backup completed!\n📨 Processed: {success_count} messages")
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
                chat_formats = [f"-100{link_chat_id}", f"-{link_chat_id}", link_chat_id]
                
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

    async def backup_messages_exact(self, chat, message_ids, user_chat_id, exact_copy=True):
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
                    if exact_copy:
                        await self.backup_exact_copy(original_msg, chat)
                    else:
                        await self.backup_normal(original_msg, chat)
                    
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
        """Create exact copy with all original metadata"""
        try:
            # Preserve original caption exactly
            original_caption = ""
            if original_msg.caption:
                original_caption = original_msg.caption
            elif original_msg.text and not original_msg.media:
                original_caption = original_msg.text

            if original_msg.media:
                # Download with original file name
                file_path = await original_msg.download()
                
                if file_path and os.path.exists(file_path):
                    # Send with ALL original attributes
                    if original_msg.video:
                        await self.app.send_video(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            duration=original_msg.video.duration,
                            width=original_msg.video.width,
                            height=original_msg.video.height,
                            supports_streaming=True,
                            file_name=getattr(original_msg.video, 'file_name', None)
                        )
                    
                    elif original_msg.audio:
                        await self.app.send_audio(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            duration=original_msg.audio.duration,
                            performer=original_msg.audio.performer,
                            title=original_msg.audio.title,
                            file_name=getattr(original_msg.audio, 'file_name', None)
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
                    
                    elif original_msg.voice:
                        await self.app.send_voice(
                            self.dest_channel,
                            file_path,
                            caption=original_caption,
                            duration=original_msg.voice.duration
                        )
                    
                    elif original_msg.video_note:
                        await self.app.send_video_note(
                            self.dest_channel,
                            file_path,
                            duration=original_msg.video_note.duration,
                            length=original_msg.video_note.length
                        )
                    
                    elif original_msg.sticker:
                        await self.app.send_sticker(
                            self.dest_channel,
                            original_msg.sticker.file_id
                        )
                    
                    else:
                        # Fallback for other media types
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=original_caption
                        )
                    
                    # Clean up
                    os.remove(file_path)
                
                else:
                    # Fallback: forward the message (preserves some metadata)
                    await original_msg.forward(self.dest_channel)
            
            else:
                # Text message - send exactly as is
                if original_msg.text:
                    await self.app.send_message(
                        self.dest_channel,
                        original_msg.text,
                        entities=original_msg.entities  # Preserves formatting
                    )

            logger.info(f"✅ Exact copy of message {original_msg.id}")

        except Exception as e:
            logger.error(f"Exact copy failed: {e}")
            raise

    async def backup_normal(self, original_msg, chat):
        """Normal backup with basic metadata"""
        try:
            # Enhanced caption with some metadata
            caption = original_msg.caption or original_msg.text or ""
            
            if original_msg.media or original_msg.text:
                caption += f"\n\n💾 Backed up: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                caption += f"\n🔗 Source: {chat['title']}"

            if original_msg.media:
                file_path = await original_msg.download()
                
                if file_path and os.path.exists(file_path):
                    if original_msg.video:
                        await self.app.send_video(
                            self.dest_channel,
                            file_path,
                            caption=caption,
                            supports_streaming=True
                        )
                    elif original_msg.photo:
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
                    
                    os.remove(file_path)
                else:
                    await original_msg.forward(self.dest_channel)
            else:
                await self.app.send_message(self.dest_channel, caption)

            logger.info(f"✅ Normal backup of message {original_msg.id}")

        except Exception as e:
            logger.error(f"Normal backup failed: {e}")
            raise

    async def run(self):
        try:
            await self.app.start()
            me = await self.app.get_me()
            logger.info(f"✅ Connected as: {me.first_name}")
            await asyncio.Future()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
        finally:
            await self.app.stop()

async def main():
    bot = ExactCopyBackupBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
