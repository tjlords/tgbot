import asyncio
import logging
import os
import random
import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PyrogramBackupBot:
    def __init__(self):
        # Get environment variables
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.session_string = os.getenv('USER_SESSION_STRING')
        self.group_link = os.getenv('GROUP_INVITE_LINK')
        self.dest_channel = int(os.getenv('DESTINATION_CHANNEL'))
        self.min_delay = int(os.getenv('MIN_DELAY', '5'))
        self.max_delay = int(os.getenv('MAX_DELAY', '15'))
        
        # Create Pyrogram client
        self.app = Client(
            "backup_bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string
        )
        
        self.group = None
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
🤖 **Telegram Backup Bot - PYROGRAM**

✅ **No imghdr dependency**
✅ **Python 3.13+ compatible**
✅ **Modern & Fast**

**Commands:**
/start - Show this help
/backup [range] - Backup messages  
/status - Check bot status

**Examples:**
`/backup 18` - Backup message 18
`/backup 18-25` - Backup range 18 to 25
`/backup 18,20,22` - Backup specific messages
`/backup https://t.me/c/.../18` - Backup from link
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        """Handle /backup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please specify message range\nExample: `/backup 18-25`")
                return

            range_input = message.command[1]
            await message.reply(f"🔄 Starting backup for: `{range_input}`\n⏳ This may take a while...")

            success_count = await self.process_backup(range_input, message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Successfully processed: {success_count} messages")
            else:
                await message.reply("❌ No messages were backed up. Please check the message IDs.")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    async def handle_status(self, message: Message):
        """Handle /status command"""
        try:
            me = await self.app.get_me()
            group_name = self.group.title if self.group else "Not connected"
            
            status_text = f"""
📊 **Bot Status - PYROGRAM**

✅ Connected: Yes
👤 Account: {me.first_name}
📝 Group: {group_name}
🆔 Your ID: {me.id}
💡 Ready for commands!

Use `/backup [range]` to start backup.
            """
            await message.reply(status_text)
        except Exception as e:
            await message.reply(f"❌ Status error: {str(e)}")

    def parse_range(self, input_str):
        """Parse message range from input"""
        try:
            # Extract from URL
            if 't.me/c/' in input_str:
                match = re.search(r'/(\d+)$', input_str)
                if match:
                    message_id = int(match.group(1))
                    logger.info(f"📎 Extracted message ID {message_id} from URL")
                    return [message_id]
                else:
                    logger.warning("❌ Could not extract message ID from URL")
                    return []

            # Range format (18-25)
            if '-' in input_str:
                start_str, end_str = input_str.split('-', 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
                if start > end:
                    logger.warning("⚠️ Start ID greater than end ID, swapping")
                    start, end = end, start
                message_ids = list(range(start, end + 1))
                logger.info(f"🔢 Parsed range: {start} to {end} ({len(message_ids)} messages)")
                return message_ids

            # Comma-separated (18,20,22)
            if ',' in input_str:
                message_ids = [int(x.strip()) for x in input_str.split(',') if x.strip().isdigit()]
                logger.info(f"📋 Parsed specific IDs: {message_ids}")
                return message_ids

            # Single number (18)
            message_id = int(input_str.strip())
            logger.info(f"🔍 Parsed single ID: {message_id}")
            return [message_id]

        except ValueError as e:
            logger.error(f"❌ Number format error in range: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Range parse error: {e}")
            return []

    async def join_group(self):
        """Join the private group"""
        try:
            logger.info(f"🔗 Joining group: {self.group_link}")
            
            if self.group_link.startswith('https://t.me/+'):
                # Extract hash from invite link
                hash_part = self.group_link.split('+')[1]
                
                # Join the group using the invite hash
                result = await self.app.join_chat(hash_part)
                self.group = result
                logger.info(f"✅ Joined group: {self.group.title}")
                return True
            else:
                logger.error("❌ Invalid group link format")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to join group: {e}")
            return False

    async def process_backup(self, range_input, chat_id):
        """Process the backup request"""
        message_ids = self.parse_range(range_input)
        
        if not message_ids:
            await self.app.send_message(chat_id, "❌ Invalid range format. Use: 18, 18-25, or message URL")
            return 0

        total = len(message_ids)
        success_count = 0

        status_msg = await self.app.send_message(chat_id, f"📊 Processing {total} messages...")

        for i, msg_id in enumerate(message_ids, 1):
            try:
                # Get message
                message = await self.app.get_messages(self.group.id, msg_id)
                if not message or message.empty:
                    logger.warning(f"⚠️ Message {msg_id} not found")
                    continue

                # Safety delay
                delay = random.randint(self.min_delay, self.max_delay)
                logger.info(f"⏳ Waiting {delay}s before message {msg_id}")
                await asyncio.sleep(delay)

                # Backup message
                await self.backup_message(message)
                success_count += 1

                # Progress update every 3 messages or at the end
                if i % 3 == 0 or i == total:
                    progress = f"📊 Progress: {i}/{total} ({success_count} successful)"
                    await status_msg.edit_text(progress)

            except FloodWait as e:
                logger.warning(f"🚫 Flood wait: {e.value}s")
                await asyncio.sleep(e.value + 5)
            except Exception as e:
                logger.error(f"❌ Message {msg_id} failed: {e}")

        return success_count

    async def backup_message(self, message):
        """Backup a single message"""
        try:
            # Create enhanced caption
            caption_parts = []
            if message.text:
                caption_parts.append(message.text)
            
            # Add metadata
            from datetime import datetime
            metadata = [
                f"📁 Message ID: {message.id}",
                f"📅 Original: {message.date.strftime('%Y-%m-%d %H:%M')}",
                f"💾 Backed up: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"🔗 Source: Private Group"
            ]
            caption_parts.append("\n" + "\n".join(metadata))
            caption = "\n".join(caption_parts)

            if message.media:
                # Download and forward media
                logger.info(f"📥 Downloading media for message {message.id}")
                
                # Download the media file
                file_path = await message.download()
                
                if file_path and os.path.exists(file_path):
                    # Send to destination channel
                    logger.info(f"📤 Uploading media for message {message.id}")
                    
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
                    elif message.document:
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=caption
                        )
                    elif message.audio:
                        await self.app.send_audio(
                            self.dest_channel,
                            file_path,
                            caption=caption
                        )
                    else:
                        # Fallback for other media types
                        await self.app.send_document(
                            self.dest_channel,
                            file_path,
                            caption=caption
                        )
                    
                    # Clean up downloaded file
                    os.remove(file_path)
                else:
                    # Fallback: forward the message
                    logger.warning(f"⚠️ Media download failed, forwarding message {message.id}")
                    await message.forward(self.dest_channel)
                    # Also send caption separately
                    if caption.strip():
                        await self.app.send_message(self.dest_channel, caption)
            else:
                # Text message
                logger.info(f"📝 Backing up text message {message.id}")
                await self.app.send_message(self.dest_channel, caption)

            logger.info(f"✅ Successfully backed up message {message.id}")

        except FloodWait as e:
            logger.warning(f"🚫 Flood wait during backup: {e.value}s")
            await asyncio.sleep(e.value + 5)
            await self.backup_message(message)  # Retry
        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise

    async def run(self):
        """Main bot loop"""
        try:
            logger.info("🚀 Starting Pyrogram Backup Bot...")
            
            # Start the client
            await self.app.start()
            logger.info("✅ Pyrogram client started")
            
            # Verify connection
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name} (ID: {me.id})")
            
            # Join group
            if not await self.join_group():
                logger.error("❌ Failed to join group")
                return

            logger.info("✅ Bot is fully operational! Send commands via Telegram.")
            logger.info("💡 Available commands: /start, /backup, /status")
            
            # Keep the bot running
            await self.app.idle()

        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
        finally:
            if self.app.is_connected:
                await self.app.stop()
                logger.info("🔴 Bot stopped")

async def main():
    bot = PyrogramBackupBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
