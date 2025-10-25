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

class AutoForwarder:
    def __init__(self, app):
        self.app = app
        self.is_forwarding = False
        self.active_jobs = {}
        
    async def start_auto_forward(
        self,
        source_entity,
        dest_entity,
        batch_size: int = 100,
        limit: int = None,
        offset_id: int = 0
    ) -> dict:
        """
        Start automated forwarding from source to destination
        """
        try:
            self.is_forwarding = True
            forwarded_count = 0
            failed_count = 0
            last_message_id = offset_id
            
            logger.info(f"Starting auto-forward from {source_entity} to {dest_entity}")
            
            while self.is_forwarding:
                # Fetch messages in batches
                messages = await self._fetch_messages_batch(
                    source_entity, 
                    batch_size, 
                    last_message_id
                )
                
                if not messages:
                    logger.info("No more messages to forward")
                    break
                
                # Forward the batch
                success, failed, last_id = await self._forward_batch(
                    messages, dest_entity
                )
                
                forwarded_count += success
                failed_count += failed
                last_message_id = last_id
                
                logger.info(f"Batch completed: {success} forwarded, {failed} failed")
                
                # Check if we've reached the limit
                if limit and forwarded_count >= limit:
                    logger.info(f"Reached limit of {limit} messages")
                    break
                
                # Small delay to avoid flooding
                await asyncio.sleep(1)
            
            return {
                "status": "completed",
                "forwarded": forwarded_count,
                "failed": failed_count,
                "last_message_id": last_message_id
            }
            
        except Exception as e:
            logger.error(f"Auto-forward error: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "forwarded": forwarded_count,
                "failed": failed_count,
                "last_message_id": last_message_id
            }
        finally:
            self.is_forwarding = False
    
    async def _fetch_messages_batch(self, entity, batch_size: int, offset_id: int = 0):
        """
        Fetch a batch of messages from the entity
        """
        try:
            messages = []
            async for message in self.app.get_chat_history(
                entity,
                limit=batch_size,
                offset_id=offset_id
            ):
                messages.append(message)
            
            return messages
        except Exception as e:
            logger.error(f"Error fetching messages: {str(e)}")
            return []
    
    async def _forward_batch(self, messages, dest_entity) -> tuple:
        """
        Forward a batch of messages
        Returns: (success_count, failed_count, last_message_id)
        """
        success_count = 0
        failed_count = 0
        last_message_id = 0
        
        for message in messages:
            if not self.is_forwarding:
                break
                
            try:
                # Use Pyrogram's forward method (no download/upload)
                await message.forward(dest_entity)
                success_count += 1
                last_message_id = message.id
                
                # Small delay between messages
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Failed to forward message {message.id}: {str(e)}")
                failed_count += 1
                # Continue with next message even if one fails
        
        return success_count, failed_count, last_message_id
    
    def stop_forwarding(self):
        """Stop any active forwarding process"""
        self.is_forwarding = False
        logger.info("Forwarding stopped by user")
    
    async def get_forwarding_status(self) -> dict:
        """Get current forwarding status"""
        return {
            "is_forwarding": self.is_forwarding,
            "active_jobs": len(self.active_jobs)
        }

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
        
        # Initialize auto forwarder
        self.auto_forwarder = AutoForwarder(self.app)
        
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
        
        # Auto-forward handlers
        @self.app.on_message(filters.command("autoforward"))
        async def autoforward_handler(client, message):
            await self.handle_autoforward(message)
        
        @self.app.on_message(filters.command("forward_status"))
        async def forward_status_handler(client, message):
            await self.handle_forward_status(message)
        
        @self.app.on_message(filters.command("stop_forward"))
        async def stop_forward_handler(client, message):
            await self.handle_stop_forward(message)

    async def handle_start(self, message: Message):
        """Handle /start command"""
        help_text = """
🤖 **Smart Backup Bot - RANGES & EXACT COPY**

✅ **Backup Features:**
• Single: `/backup https://t.me/c/3166766661/4/18`
• Range: `/backup https://t.me/c/3166766661/4/10-16`
• Multiple: `/backup https://t.me/c/3166766661/4/1,4,5-10`
• Preserves original captions exactly

✅ **Auto-Forward Features:**
• `/autoforward source_channel dest_channel` - Bulk forward
• `/forward_status` - Check status  
• `/stop_forward` - Stop forwarding

**Commands:**
`/backup [link]` - Backup specific messages
`/autoforward` - Bulk forward entire channels
`/chats` - List your available groups
`/forward_status` - Check forwarding status
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

    async def handle_autoforward(self, message: Message):
        """Handle /autoforward command"""
        try:
            if len(message.command) < 3:
                await message.reply(
                    "**Usage:** `/autoforward source_channel dest_channel [limit] [batch_size]`\n\n"
                    "**Examples:**\n"
                    "• `/autoforward @source_channel @dest_channel`\n"
                    "• `/autoforward 123456789 987654321 1000 100`\n"
                    "• `/autoforward @private_channel @backup_channel 5000`\n\n"
                    "**Note:** Works only in channels/groups where forwarding is enabled"
                )
                return
            
            source_input = message.command[1]
            dest_input = message.command[2]
            limit = int(message.command[3]) if len(message.command) > 3 else None
            batch_size = int(message.command[4]) if len(message.command) > 4 else 100
            
            # Check if forwarding is already active
            if self.auto_forwarder.is_forwarding:
                await message.reply("❌ Another forwarding job is already running. Use `/stop_forward` to stop it first.")
                return
            
            await message.reply("🔄 Starting auto-forward...")
            
            # Resolve source and destination entities
            try:
                source_entity = await self.resolve_entity(source_input)
                dest_entity = await self.resolve_entity(dest_input)
            except Exception as e:
                await message.reply(f"❌ Error resolving channels: {str(e)}")
                return
            
            # Start forwarding in background
            asyncio.create_task(
                self.run_auto_forward(message, source_entity, dest_entity, limit, batch_size)
            )
            
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")

    async def resolve_entity(self, entity_input):
        """Resolve entity from username or ID"""
        try:
            if entity_input.startswith('@'):
                return await self.app.get_chat(entity_input)
            else:
                entity_id = int(entity_input)
                return await self.app.get_chat(entity_id)
        except Exception as e:
            raise Exception(f"Could not resolve {entity_input}: {str(e)}")

    async def run_auto_forward(self, message, source_entity, dest_entity, limit, batch_size):
        """Run auto-forwarding and send progress updates"""
        try:
            # Send initial status
            status_msg = await message.reply(
                f"🚀 **Auto-Forward Started**\n"
                f"**From:** {source_entity.title if hasattr(source_entity, 'title') else 'Unknown'}\n"
                f"**To:** {dest_entity.title if hasattr(dest_entity, 'title') else 'Unknown'}\n"
                f"**Batch Size:** {batch_size}\n"
                f"**Limit:** {limit or 'No limit'}\n"
                f"**Status:** Processing..."
            )
            
            # Start forwarding
            result = await self.auto_forwarder.start_auto_forward(
                source_entity=source_entity.id,
                dest_entity=dest_entity.id,
                batch_size=batch_size,
                limit=limit
            )
            
            # Send completion message
            if result["status"] == "completed":
                await status_msg.edit(
                    f"✅ **Auto-Forward Completed**\n"
                    f"**Forwarded:** {result['forwarded']} messages\n"
                    f"**Failed:** {result['failed']} messages\n"
                    f"**Last Message ID:** {result.get('last_message_id', 'N/A')}"
                )
            else:
                await status_msg.edit(
                    f"❌ **Auto-Forward Error**\n"
                    f"**Error:** {result['error']}\n"
                    f"**Partial Results:** {result['forwarded']} forwarded, {result['failed']} failed"
                )
                
        except Exception as e:
            await message.reply(f"❌ Auto-forward task error: {str(e)}")

    async def handle_forward_status(self, message: Message):
        """Check current forwarding status"""
        try:
            status = await self.auto_forwarder.get_forwarding_status()
            
            if status["is_forwarding"]:
                message_text = "🔄 **Auto-Forward Status: RUNNING**\n"
                message_text += f"Active jobs: {status['active_jobs']}\n"
                message_text += "Use `/stop_forward` to stop forwarding."
            else:
                message_text = "✅ **Auto-Forward Status: IDLE**\n"
                message_text += "No active forwarding jobs."
                
            await message.reply(message_text)
            
        except Exception as e:
            await message.reply(f"❌ Error getting status: {str(e)}")

    async def handle_stop_forward(self, message: Message):
        """Stop active forwarding process"""
        try:
            if self.auto_forwarder.is_forwarding:
                self.auto_forwarder.stop_forwarding()
                await message.reply("🛑 Auto-forwarding stopped.")
            else:
                await message.reply("ℹ️ No active forwarding job to stop.")
                
        except Exception as e:
            await message.reply(f"❌ Error stopping forward: {str(e)}")

    def extract_message_ids_all_formats(self, link):
        """
        Extract message IDs from ALL formats including ranges:
        - Single: https://t.me/c/3166766661/4/18
        - Range: https://t.me/c/3166766661/4/10-16
        - Multiple: https://t.me/c/3166766661/4/1,4,5-10
        - Mixed: https://t.me/c/3166766661/4/1,3,5-8,10
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
