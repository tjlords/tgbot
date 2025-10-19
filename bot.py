import asyncio
import logging
import os
import random
import re
import sys
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BackupBot:
    def __init__(self):
        # Get environment variables
        try:
            self.api_id = int(os.getenv('API_ID'))
            self.api_hash = os.getenv('API_HASH')
            self.user_session = os.getenv('USER_SESSION_STRING')
            self.group_link = os.getenv('GROUP_INVITE_LINK')
            self.dest_channel = int(os.getenv('DESTINATION_CHANNEL'))
            self.min_delay = int(os.getenv('MIN_DELAY', '5'))
            self.max_delay = int(os.getenv('MAX_DELAY', '15'))
        except (ValueError, TypeError) as e:
            logger.error(f"❌ Environment configuration error: {e}")
            sys.exit(1)
        
        self.client = None
        self.group = None
        
        # Validate config
        if not all([self.api_id, self.api_hash, self.user_session, self.group_link, self.dest_channel]):
            logger.error("❌ Missing required environment variables")
            sys.exit(1)

    async def safe_file_operation(self, file_path, operation="remove"):
        """Safe file operations to avoid permission errors"""
        try:
            if operation == "remove" and os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ File operation failed for {file_path}: {e}")
            return False

    async def init_client(self):
        """Initialize Telegram client"""
        try:
            logger.info("🔐 Initializing Telegram client...")
            self.client = TelegramClient(
                StringSession(self.user_session),
                self.api_id,
                self.api_hash
            )
            
            await self.client.start()
            logger.info("✅ Telegram client initialized successfully")
            
            # Verify connection
            me = await self.client.get_me()
            logger.info(f"👤 Connected as: {me.first_name} (ID: {me.id})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize client: {e}")
            return False

    async def join_group(self):
        """Join the private group"""
        try:
            logger.info(f"🔗 Joining group: {self.group_link}")
            
            if self.group_link.startswith('https://t.me/+'):
                hash_part = self.group_link.split('+')[1]
                await self.client(ImportChatInviteRequest(hash_part))
                self.group = await self.client.get_entity(self.group_link)
                logger.info(f"✅ Joined group: {self.group.title}")
                return True
            else:
                logger.error("❌ Invalid group link format")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to join group: {e}")
            return False

    def setup_handlers(self):
        """Setup command handlers"""
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.handle_start(event)

        @self.client.on(events.NewMessage(pattern=r'/backup(\s+.*)?'))
        async def backup_handler(event):
            await self.handle_backup(event)

        @self.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            await self.handle_status(event)

    async def handle_start(self, event):
        """Handle /start command"""
        help_text = """
🤖 **Telegram Backup Bot - FIXED VERSION**

✅ **Fixed Issues:**
- Python 3.13 compatibility
- No imghdr dependency
- Better error handling

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
        await event.reply(help_text)

    async def handle_backup(self, event):
        """Handle /backup command"""
        try:
            command_text = event.message.text.strip()
            parts = command_text.split(' ', 1)
            
            if len(parts) < 2 or not parts[1].strip():
                await event.reply("❌ Please specify message range\nExample: `/backup 18-25`")
                return

            range_input = parts[1].strip()
            await event.reply(f"🔄 Starting backup for: `{range_input}`\n⏳ This may take a while...")

            success_count = await self.process_backup(range_input, event.chat_id)
            
            if success_count > 0:
                await event.reply(f"✅ Backup completed!\n📨 Successfully processed: {success_count} messages")
            else:
                await event.reply("❌ No messages were backed up. Please check the message IDs.")

        except Exception as e:
            await event.reply(f"❌ Backup failed: {str(e)}")

    async def handle_status(self, event):
        """Handle /status command"""
        try:
            me = await self.client.get_me()
            group_name = self.group.title if self.group else "Not connected"
            
            status_text = f"""
📊 **Bot Status**

✅ Connected: Yes
👤 Account: {me.first_name}
📝 Group: {group_name}
🆔 Your ID: {me.id}
💡 Ready for commands!

Use `/backup [range]` to start backup.
            """
            await event.reply(status_text)
        except Exception as e:
            await event.reply(f"❌ Status error: {str(e)}")

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

    async def process_backup(self, range_input, chat_id):
        """Process the backup request"""
        message_ids = self.parse_range(range_input)
        
        if not message_ids:
            await self.client.send_message(chat_id, "❌ Invalid range format. Use: 18, 18-25, or message URL")
            return 0

        total = len(message_ids)
        success_count = 0

        status_msg = await self.client.send_message(chat_id, f"📊 Processing {total} messages...")

        for i, msg_id in enumerate(message_ids, 1):
            try:
                # Get message
                message = await self.client.get_messages(self.group, ids=msg_id)
                if not message:
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
                    await status_msg.edit(progress)

            except Exception as e:
                logger.error(f"❌ Message {msg_id} failed: {e}")

        return success_count

    async def backup_message(self, message):
        """Backup a single message"""
        file_path = None
        try:
            # Create enhanced caption
            caption_parts = []
            if message.text:
                caption_parts.append(message.text)
            
            # Add metadata
            metadata = [
                f"📁 Message ID: {message.id}",
                f"📅 Original: {message.date.strftime('%Y-%m-%d %H:%M')}",
                f"💾 Backed up: {asyncio.get_event_loop().time()}",
                f"🔗 Source: Private Group"
            ]
            caption_parts.append("\n" + "\n".join(metadata))
            caption = "\n".join(caption_parts)

            if message.media:
                # Download media
                logger.info(f"📥 Downloading media for message {message.id}")
                file_path = await self.client.download_media(message, file=f"temp_{message.id}")
                
                if file_path and os.path.exists(file_path):
                    # Upload to destination
                    logger.info(f"📤 Uploading media for message {message.id}")
                    await self.client.send_file(
                        self.dest_channel,
                        file_path,
                        caption=caption,
                        supports_streaming=True
                    )
                else:
                    # Fallback: forward with caption
                    logger.warning(f"⚠️ Media download failed, forwarding message {message.id}")
                    await self.client.send_message(self.dest_channel, caption)
                    await message.forward_to(self.dest_channel)
            else:
                # Text message
                logger.info(f"📝 Backing up text message {message.id}")
                await self.client.send_message(self.dest_channel, caption)

            logger.info(f"✅ Successfully backed up message {message.id}")

        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise
        finally:
            # Always clean up downloaded files
            if file_path and os.path.exists(file_path):
                await self.safe_file_operation(file_path, "remove")

    async def run(self):
        """Main bot loop"""
        try:
            logger.info("🚀 Starting Telegram Backup Bot...")
            
            # Initialize client
            if not await self.init_client():
                logger.error("❌ Failed to initialize client")
                return

            # Join group
            if not await self.join_group():
                logger.error("❌ Failed to join group")
                return

            # Setup command handlers
            self.setup_handlers()

            logger.info("✅ Bot is fully operational! Send commands via Telegram.")
            logger.info("💡 Available commands: /start, /backup, /status")
            
            # Keep the bot running
            await self.client.run_until_disconnected()

        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
        finally:
            if self.client:
                await self.client.disconnect()
                logger.info("🔴 Bot disconnected")

def main():
    """Main entry point"""
    try:
        # Check Python version
        python_version = sys.version_info
        logger.info(f"🐍 Python {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # Create and run bot
        bot = BackupBot()
        
        # Run the bot
        asyncio.run(bot.run())
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")

if __name__ == '__main__':
    main()
