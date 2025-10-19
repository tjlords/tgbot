import asyncio
import logging
import os
import random
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FixedBackupBot:
    def __init__(self):
        self.config = {
            'api_id': int(os.getenv('API_ID')),
            'api_hash': os.getenv('API_HASH'),
            'user_session': os.getenv('USER_SESSION_STRING'),
            'group_invite_link': os.getenv('GROUP_INVITE_LINK'),
            'destination_channel': int(os.getenv('DESTINATION_CHANNEL')),
            'min_delay': int(os.getenv('MIN_DELAY', 5)),
            'max_delay': int(os.getenv('MAX_DELAY', 15))
        }
        self.client = None
        self.group = None
    
    async def safe_start(self):
        """Safely initialize the client with error handling"""
        try:
            self.client = TelegramClient(
                StringSession(self.config['user_session']),
                self.config['api_id'],
                self.config['api_hash']
            )
            
            # Add command handlers
            self.setup_handlers()
            
            await self.client.start()
            logger.info("✅ Client started successfully")
            
            # Test connection
            me = await self.client.get_me()
            logger.info(f"👤 Connected as: {me.first_name}")
            
            # Join group
            success = await self.join_private_group()
            if not success:
                logger.error("❌ Failed to join group")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Startup failed: {e}")
            return False
    
    def setup_handlers(self):
        """Setup command handlers"""
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.handle_start_command(event)
        
        @self.client.on(events.NewMessage(pattern='/backup'))
        async def backup_handler(event):
            await self.handle_backup_command(event)
        
        @self.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            await self.handle_status_command(event)
    
    async def join_private_group(self):
        """Join private group with error handling"""
        try:
            if self.config['group_invite_link'].startswith('https://t.me/+'):
                hash_part = self.config['group_invite_link'].split('+')[1]
                await self.client(ImportChatInviteRequest(hash_part))
                self.group = await self.client.get_entity(self.config['group_invite_link'])
                logger.info(f"✅ Joined group: {self.group.title}")
                return True
            else:
                logger.error("❌ Invalid group invite link format")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to join group: {e}")
            return False
    
    async def handle_start_command(self, event):
        """Handle /start command"""
        help_text = """
🤖 **Telegram Backup Bot - FIXED VERSION**

✅ **Fixed Issues:**
- Python 3.11+ compatibility
- imghdr module dependency
- Better error handling

**Commands:**
/backup [range] - Backup messages
/status - Check bot status

**Examples:**
`/backup 18` - Backup message 18
`/backup 18-25` - Backup range
`/backup 18,20,22` - Backup specific
`/backup https://t.me/c/3166766661/4/18` - Backup from link
        """
        await event.reply(help_text)
    
    async def handle_backup_command(self, event):
        """Handle /backup command"""
        try:
            command_text = event.message.text.strip()
            args = command_text.split(' ', 1)
            
            if len(args) < 2:
                await event.reply("❌ Please specify message range\nExample: `/backup 18-25`")
                return
            
            range_input = args[1].strip()
            await event.reply(f"🔄 Starting backup for: `{range_input}`")
            
            success_count = await self.process_backup(range_input, event.chat_id)
            
            await event.reply(f"✅ Backup completed!\n📨 Success: {success_count} messages")
            
        except Exception as e:
            await event.reply(f"❌ Backup error: {str(e)}")
    
    async def handle_status_command(self, event):
        """Handle /status command"""
        try:
            me = await self.client.get_me()
            status_text = f"""
📊 **Bot Status - FIXED**

✅ Connected: Yes
👤 Account: {me.first_name}
📝 Group: {self.group.title if self.group else 'Unknown'}
🎯 Ready for commands

💡 Use `/backup [range]` to start
            """
            await event.reply(status_text)
        except Exception as e:
            await event.reply(f"❌ Status error: {str(e)}")
    
    def parse_range_input(self, range_input):
        """Parse range input safely"""
        try:
            # Extract from URL
            if 't.me/c/' in range_input:
                match = re.search(r'/(\d+)$', range_input)
                if match:
                    return [int(match.group(1))]
            
            # Range format
            if '-' in range_input:
                start, end = map(int, range_input.split('-'))
                return list(range(start, end + 1))
            
            # Comma-separated
            if ',' in range_input:
                return [int(x.strip()) for x in range_input.split(',')]
            
            # Single number
            return [int(range_input)]
            
        except Exception as e:
            logger.error(f"Range parse error: {e}")
            return []
    
    async def process_backup(self, range_input, chat_id):
        """Process backup with progress updates"""
        message_ids = self.parse_range_input(range_input)
        
        if not message_ids:
            await self.client.send_message(chat_id, "❌ Invalid range format")
            return 0
        
        success_count = 0
        total = len(message_ids)
        
        await self.client.send_message(chat_id, f"📊 Starting backup of {total} messages...")
        
        for i, msg_id in enumerate(message_ids, 1):
            try:
                # Get message
                message = await self.client.get_messages(self.group, ids=msg_id)
                
                if not message:
                    logger.warning(f"Message {msg_id} not found")
                    continue
                
                # Safety delay
                delay = random.randint(self.config['min_delay'], self.config['max_delay'])
                await asyncio.sleep(delay)
                
                # Backup message
                await self.backup_single_message(message)
                success_count += 1
                
                # Progress update
                if i % 5 == 0 or i == total:
                    progress = f"📊 Progress: {i}/{total} ({success_count} successful)"
                    await self.client.send_message(chat_id, progress)
                
            except Exception as e:
                logger.error(f"Message {msg_id} failed: {e}")
        
        return success_count
    
    async def backup_single_message(self, message):
        """Backup a single message safely"""
        try:
            caption = f"{message.text or ''}\n\n" if message.text else ""
            caption += f"📁 ID: {message.id} | 📅 {message.date.strftime('%Y-%m-%d %H:%M')}"
            
            if message.media:
                # Download media
                file_path = await self.client.download_media(message)
                if file_path and os.path.exists(file_path):
                    # Upload to destination
                    await self.client.send_file(
                        self.config['destination_channel'],
                        file_path,
                        caption=caption,
                        supports_streaming=True
                    )
                    # Cleanup
                    os.remove(file_path)
                else:
                    # Fallback: forward
                    await message.forward_to(self.config['destination_channel'])
            else:
                # Text message
                await self.client.send_message(self.config['destination_channel'], caption)
            
            logger.info(f"✅ Backed up message {message.id}")
            
        except Exception as e:
            logger.error(f"❌ Backup failed for {message.id}: {e}")
            raise
    
    async def run(self):
        """Main bot loop"""
        try:
            success = await self.safe_start()
            if not success:
                logger.error("❌ Failed to start bot")
                return
            
            logger.info("🚀 Bot is running! Send commands via Telegram.")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
        finally:
            if self.client:
                await self.client.disconnect()

async def main():
    bot = FixedBackupBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
