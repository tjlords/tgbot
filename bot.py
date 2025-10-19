import asyncio
import logging
import os
import random
import time
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PrivateGroupBackupBot:
    def __init__(self):
        self.config = {
            'api_id': int(os.getenv('API_ID')),
            'api_hash': os.getenv('API_HASH'),
            'user_session': os.getenv('USER_SESSION_STRING'),
            'group_invite_link': os.getenv('GROUP_INVITE_LINK'),
            'destination_channel': int(os.getenv('DESTINATION_CHANNEL')),
            'message_range': os.getenv('MESSAGE_RANGE', 'all'),
            'min_delay': int(os.getenv('MIN_DELAY', 5)),
            'max_delay': int(os.getenv('MAX_DELAY', 15)),
            'max_messages': int(os.getenv('MAX_MESSAGES_PER_RUN', 10))
        }
        self.client = None
        self.stats = {'processed': 0, 'errors': 0}
    
    async def init_client(self):
        """Initialize Telegram client with user session"""
        self.client = TelegramClient(
            StringSession(self.config['user_session']),
            self.config['api_id'],
            self.config['api_hash']
        )
        await self.client.start()
        logger.info("✅ User client initialized")
        
        me = await self.client.get_me()
        logger.info(f"👤 Logged in as: {me.first_name} ({me.phone})")
        return True
    
    async def ensure_group_access(self):
        """Ensure we have access to the private group"""
        try:
            # Extract hash from invite link
            hash_part = self.config['group_invite_link'].split('+')[1]
            
            # Join the group if not already member
            await self.client(ImportChatInviteRequest(hash_part))
            logger.info("✅ Joined private group successfully")
            
            # Get group entity
            group = await self.client.get_entity(self.config['group_invite_link'])
            logger.info(f"📝 Group: {group.title}")
            return group
            
        except Exception as e:
            logger.error(f"❌ Group access failed: {e}")
            return None
    
    async def run_backup(self):
        """Main backup routine"""
        try:
            # Initialize client
            if not await self.init_client():
                return
            
            # Ensure group access
            group = await self.ensure_group_access()
            if not group:
                return
            
            logger.info("🚀 Starting backup...")
            
            # Parse message range
            message_range = self.config['message_range']
            messages_to_backup = []
            
            if '-' in message_range:
                start_id, end_id = map(int, message_range.split('-'))
                logger.info(f"📋 Backup range: {start_id} to {end_id}")
                
                # Get messages in range
                async for message in self.client.iter_messages(
                    group, 
                    min_id=start_id-1,
                    max_id=end_id+1
                ):
                    if start_id <= message.id <= end_id:
                        messages_to_backup.append(message)
            
            logger.info(f"📨 Found {len(messages_to_backup)} messages")
            
            # Backup messages
            for message in messages_to_backup:
                if self.stats['processed'] >= self.config['max_messages']:
                    break
                    
                await self.backup_single_message(message, group)
            
            logger.info(f"🎉 Backup completed! Processed: {self.stats['processed']}")
            
        except Exception as e:
            logger.error(f"💥 Backup failed: {e}")
        finally:
            if self.client:
                await self.client.disconnect()
    
    async def backup_single_message(self, message, group):
        """Backup a single message"""
        try:
            # Random delay
            delay = random.uniform(self.config['min_delay'], self.config['max_delay'])
            logger.info(f"⏳ Waiting {delay:.2f}s for message {message.id}...")
            await asyncio.sleep(delay)
            
            # Create enhanced caption
            caption = f"{message.text or ''}\n\n" if message.text else ""
            caption += f"📁 ID: {message.id} | 📅 {message.date.strftime('%Y-%m-%d %H:%M')}"
            caption += f" | 💾 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            if message.media:
                # Download and re-upload
                file_path = await self.client.download_media(message, file=f"downloads/{message.id}")
                if file_path:
                    await self.client.send_file(
                        self.config['destination_channel'],
                        file_path,
                        caption=caption,
                        supports_streaming=True
                    )
                    # Clean up
                    if os.path.exists(file_path):
                        os.remove(file_path)
                else:
                    # Fallback: forward
                    await message.forward_to(self.config['destination_channel'])
            else:
                # Text message
                await self.client.send_message(self.config['destination_channel'], caption)
            
            self.stats['processed'] += 1
            logger.info(f"✅ Backed up message {message.id}")
            
        except Exception as e:
            logger.error(f"❌ Failed message {message.id}: {e}")
            self.stats['errors'] += 1

async def main():
    bot = PrivateGroupBackupBot()
    await bot.run_backup()

if __name__ == '__main__':
    asyncio.run(main())