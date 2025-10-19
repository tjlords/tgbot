import asyncio
import logging
import os
import random
import re
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FinalBackupBot:
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
            "final_backup_bot",
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
🤖 **Smart Backup Bot - READY!**

✅ **No group links needed**
✅ **Works with any group you're member of**
✅ **Just send message links**

**How to use:**
1. Go to any group you're member of
2. Copy message link (right-click → Copy Link)
3. Send: `/backup [message-link]`

**Examples:**
`/backup https://t.me/c/1234567890/18` - Backup single message
`/backup https://t.me/c/1234567890/18-25` - Backup range
`/backup https://t.me/c/1234567890/18,20,22` - Backup specific

**Or use message IDs if you know the group:**
`/backup 1234567890 18-25` - Group ID + range
        """
        await message.reply(help_text)

    async def handle_backup(self, message: Message):
        """Handle /backup command"""
        try:
            if len(message.command) < 2:
                await message.reply("❌ Please provide message link or range\nExample: `/backup https://t.me/c/1234567890/18`")
                return

            args = message.command[1:]
            await message.reply(f"🔄 Processing backup request...")

            success_count = await self.process_backup(args, message.chat.id)
            
            if success_count > 0:
                await message.reply(f"✅ Backup completed!\n📨 Successfully processed: {success_count} messages")
            else:
                await message.reply("❌ No messages were backed up. Please check the input.")

        except Exception as e:
            await message.reply(f"❌ Backup failed: {str(e)}")

    async def handle_status(self, message: Message):
        """Handle /status command"""
        try:
            me = await self.app.get_me()
            status_text = f"""
📊 **Smart Backup Bot Status**

✅ Connected: Yes
👤 Account: {me.first_name}
🆔 Your ID: {me.id}
💡 Ready for backup commands!

**Usage:**
Just send `/backup` with message links from any group you're in.
            """
            await message.reply(status_text)
        except Exception as e:
            await message.reply(f"❌ Status error: {str(e)}")

    def extract_info_from_link(self, link):
        """Extract group ID and message IDs from Telegram link"""
        try:
            # Pattern for t.me/c/ links
            # https://t.me/c/1234567890/18
            # https://t.me/c/1234567890/18-25
            # https://t.me/c/1234567890/18,20,22
            
            if 't.me/c/' in link:
                # Extract the parts after /c/
                parts = link.split('/c/')[1].split('/')
                if len(parts) >= 2:
                    group_id = int(parts[0])
                    message_part = parts[1]
                    
                    # Parse message range
                    message_ids = self.parse_message_range(message_part)
                    return group_id, message_ids
            
            return None, []
            
        except Exception as e:
            logger.error(f"Link parse error: {e}")
            return None, []

    def parse_message_range(self, range_str):
        """Parse message range from string"""
        try:
            # Single message: "18"
            if '-' not in range_str and ',' not in range_str:
                return [int(range_str)]
            
            # Range: "18-25"
            if '-' in range_str:
                start, end = map(int, range_str.split('-'))
                return list(range(start, end + 1))
            
            # Comma-separated: "18,20,22"
            if ',' in range_str:
                return [int(x.strip()) for x in range_str.split(',')]
            
            return []
            
        except Exception as e:
            logger.error(f"Range parse error: {e}")
            return []

    async def get_group_entity(self, group_id):
        """Get group entity from ID"""
        try:
            # For groups, the ID is negative
            if group_id > 0:
                group_id = -group_id
            
            # Try to get the group
            group = await self.app.get_chat(group_id)
            return group
            
        except Exception as e:
            logger.error(f"Failed to get group {group_id}: {e}")
            return None

    async def process_backup(self, args, chat_id):
        """Process backup based on arguments"""
        try:
            # Check if first argument is a link
            if args[0].startswith('https://t.me/'):
                # Link-based backup
                group_id, message_ids = self.extract_info_from_link(args[0])
                if not group_id or not message_ids:
                    await self.app.send_message(chat_id, "❌ Could not extract info from link")
                    return 0
                
                group = await self.get_group_entity(group_id)
                if not group:
                    await self.app.send_message(chat_id, "❌ Could not access group. Make sure you're a member.")
                    return 0
                    
                return await self.backup_messages(group, message_ids, chat_id)
            
            # Check if first argument is a group ID
            elif args[0].isdigit() and len(args) > 1:
                # Group ID + range backup
                group_id = int(args[0])
                range_str = args[1]
                
                group = await self.get_group_entity(group_id)
                if not group:
                    await self.app.send_message(chat_id, "❌ Could not access group. Make sure you're a member.")
                    return 0
                
                message_ids = self.parse_message_range(range_str)
                return await self.backup_messages(group, message_ids, chat_id)
            
            else:
                await self.app.send_message(chat_id, "❌ Invalid format. Use message links or: /backup [group_id] [range]")
                return 0
                
        except Exception as e:
            logger.error(f"Backup process error: {e}")
            await self.app.send_message(chat_id, f"❌ Backup error: {str(e)}")
            return 0

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
                    logger.warning(f"⚠️ Message {msg_id} not found in {group.title}")
                    continue

                # Safety delay
                delay = random.randint(self.min_delay, self.max_delay)
                logger.info(f"⏳ Waiting {delay}s before message {msg_id}")
                await asyncio.sleep(delay)

                # Backup message
                await self.backup_single_message(message, group)
                success_count += 1

                # Progress update
                if i % 3 == 0 or i == total:
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
                f"🔗 Source: {group.title}"
            ]
            caption_parts.append("\n" + "\n".join(metadata))
            caption = "\n".join(caption_parts)

            if message.media:
                # Download media
                logger.info(f"📥 Downloading media for message {message.id}")
                file_path = await message.download()
                
                if file_path and os.path.exists(file_path):
                    # Send based on media type
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

            logger.info(f"✅ Backed up message {message.id} from {group.title}")

        except FloodWait as e:
            logger.warning(f"🚫 Flood wait: {e.value}s")
            await asyncio.sleep(e.value + 5)
            await self.backup_single_message(message, group)
        except Exception as e:
            logger.error(f"❌ Failed to backup message {message.id}: {e}")
            raise

    async def run(self):
        """Main bot loop"""
        try:
            logger.info("🚀 Starting Final Backup Bot...")
            
            # Start the client
            await self.app.start()
            logger.info("✅ Pyrogram client started")
            
            # Verify connection
            me = await self.app.get_me()
            logger.info(f"👤 Connected as: {me.first_name} (ID: {me.id})")
            
            logger.info("✅ Bot is fully operational!")
            logger.info("💡 Send /start to see usage instructions")
            logger.info("📝 Bot will keep running and listening for commands...")
            
            # Keep the bot running indefinitely
            while True:
                await asyncio.sleep(10)  # Keep alive
                
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
        finally:
            if hasattr(self, 'app') and self.app.is_connected:
                await self.app.stop()
                logger.info("🔴 Bot stopped")

async def main():
    bot = FinalBackupBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
