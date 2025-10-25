import os
import re
import asyncio
import logging
import time
import random
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# Minimal logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8127293382:AAHnBJGwOwlgD2Fe8R-6iimUOyhuoMxw6wU"
API_ID = 11843091
API_HASH = "be955ff462011615097f96745b3627f3"
OWNER_ID = 741668895

# Speed Modes Configuration
SPEED_MODES = {
    'safe': {
        'min_delay': 2.0,
        'max_delay': 5.0,
        'batch_size': 3,
        'batch_delay': (5, 10),
        'description': 'Ultra Safe (No flood waits)'
    },
    'balanced': {
        'min_delay': 1.0,
        'max_delay': 3.0,
        'batch_size': 5,
        'batch_delay': (3, 6),
        'description': 'Balanced (Rare flood waits)'
    },
    'fast': {
        'min_delay': 0.5,
        'max_delay': 2.0,
        'batch_size': 8,
        'batch_delay': (2, 4),
        'description': 'Fast (Occasional flood waits)'
    },
    'turbo': {
        'min_delay': 0.2,
        'max_delay': 1.0,
        'batch_size': 12,
        'batch_delay': (1, 2),
        'description': 'Turbo (Risk of flood waits)'
    }
}

# Adaptive settings
DEFAULT_MODE = 'balanced'
MAX_FLOOD_WAITS = 3
PROGRESS_UPDATE_INTERVAL = 15

# User data storage
user_sessions = {}

app = Client("smart_caption_editor", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

def is_owner(user_id):
    return user_id == OWNER_ID

def get_speed_settings(mode):
    return SPEED_MODES.get(mode, SPEED_MODES[DEFAULT_MODE])

def get_random_delay(mode):
    settings = get_speed_settings(mode)
    return random.uniform(settings['min_delay'], settings['max_delay'])

def get_batch_delay(mode):
    settings = get_speed_settings(mode)
    return random.uniform(*settings['batch_delay'])

async def smart_edit_caption(client, chat_id, message_id, new_caption, user_data):
    """Smart editing with adaptive speed control"""
    try:
        await client.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=new_caption)
        user_data['consecutive_success'] = user_data.get('consecutive_success', 0) + 1
        user_data['consecutive_errors'] = 0
        return True
    except FloodWait as e:
        wait_time = e.value
        user_data['flood_waits'] = user_data.get('flood_waits', 0) + 1
        user_data['consecutive_errors'] = user_data.get('consecutive_errors', 0) + 1
        user_data['consecutive_success'] = 0
        
        logger.warning(f"Flood wait: {wait_time}s (Total: {user_data['flood_waits']})")
        
        if user_data['flood_waits'] >= MAX_FLOOD_WAITS:
            current_mode = user_data.get('speed_mode', DEFAULT_MODE)
            if current_mode != 'safe':
                user_data['speed_mode'] = 'safe'
                logger.warning(f"Switching to SAFE mode due to frequent flood waits")
        
        actual_wait = wait_time + random.uniform(2, 5)
        await asyncio.sleep(actual_wait)
        
        await asyncio.sleep(random.uniform(2, 4))
        try:
            await client.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=new_caption)
            return True
        except Exception:
            return False
    except Exception as e:
        user_data['consecutive_errors'] = user_data.get('consecutive_errors', 0) + 1
        user_data['consecutive_success'] = 0
        return False

def apply_all_edits(text, edit_instructions):
    """Enhanced text replacement that handles @username patterns correctly"""
    if not text:
        return text
    
    current_text = text
    
    for edit in edit_instructions:
        search_text = edit['search']
        replace_text = edit['replace']
        
        if edit['type'] == 'remove':
            # Remove both @search and search
            pattern1 = re.compile(re.escape(search_text), re.IGNORECASE)
            pattern2 = re.compile(re.escape(f"@{search_text}"), re.IGNORECASE)
            
            current_text = pattern1.sub("", current_text)
            current_text = pattern2.sub("", current_text)
        else:
            # Replace @search with replace_text (without @) and search with replace_text
            pattern1 = re.compile(re.escape(search_text), re.IGNORECASE)
            pattern2 = re.compile(re.escape(f"@{search_text}"), re.IGNORECASE)
            
            # First replace @search with replace_text
            current_text = pattern2.sub(replace_text, current_text)
            # Then replace search with replace_text
            current_text = pattern1.sub(replace_text, current_text)
    
    return current_text

# FIXED: Only respond to commands in private chats
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message: Message):
    if not is_owner(message.from_user.id):
        return
        
    speed_info = "**Available Speed Modes:**\n"
    for mode, settings in SPEED_MODES.items():
        speed_info += f"• `{mode}` - {settings['description']}\n"
    
    await message.reply_text(
        f"🤖 **Smart Caption Editor**\n\n"
        f"{speed_info}\n"
        f"**Enhanced Text Replacement:**\n"
        f"• `HaRsHit2027 >> Physics Wallah`\n"
        f"• `@HaRsHit2027` → `Physics Wallah` (removes @)\n"
        f"• `HaRsHit2027` → `Physics Wallah`\n"
        f"• Case-insensitive matching\n\n"
        f"**Usage:**\n"
        f"1. Set speed: `/speed balanced`\n"
        f"2. Send message links\n"
        f"3. Send edits using `>>` separator\n"
        f"4. Type `done` then `yes`\n"
    )

# FIXED: Only respond to speed command in private chats
@app.on_message(filters.command("speed") & filters.private)
async def speed_command(client, message: Message):
    if not is_owner(message.from_user.id):
        return
        
    if len(message.command) > 1:
        new_mode = message.command[1].lower()
        if new_mode in SPEED_MODES:
            user_id = message.from_user.id
            if user_id not in user_sessions:
                user_sessions[user_id] = {}
            user_sessions[user_id]['speed_mode'] = new_mode
            
            settings = get_speed_settings(new_mode)
            await message.reply_text(
                f"⚡ **Speed Mode Changed**\n\n"
                f"**Mode:** {new_mode.upper()}\n"
                f"**Description:** {settings['description']}\n"
                f"**Delay:** {settings['min_delay']}-{settings['max_delay']}s\n"
                f"**Batch Size:** {settings['batch_size']}\n\n"
                f"Now send message links to start!"
            )
        else:
            modes_list = ", ".join([f"`{mode}`" for mode in SPEED_MODES.keys()])
            await message.reply_text(f"❌ Invalid mode. Available: {modes_list}")
    else:
        user_id = message.from_user.id
        current_mode = user_sessions.get(user_id, {}).get('speed_mode', DEFAULT_MODE)
        settings = get_speed_settings(current_mode)
        
        await message.reply_text(
            f"⚡ **Current Speed Settings**\n\n"
            f"**Mode:** {current_mode.upper()}\n"
            f"**Description:** {settings['description']}\n"
            f"**Message Delay:** {settings['min_delay']}-{settings['max_delay']}s\n"
            f"**Batch Size:** {settings['batch_size']}\n"
            f"**Batch Delay:** {settings['batch_delay'][0]}-{settings['batch_delay'][1]}s\n\n"
            f"Change with: `/speed safe|balanced|fast|turbo`"
        )

# FIXED: Only handle text messages in private chats
@app.on_message(filters.text & filters.private)
async def handle_all_messages(client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
        
    text = message.text.strip()
    
    if user_id in user_sessions:
        state = user_sessions[user_id].get('state')
        
        if state == 'collecting_edits':
            if text.lower() == 'done':
                await show_confirmation(client, message, user_id)
                return
            else:
                await collect_edit_instruction(client, message, user_id, text)
                return
                
        elif state == 'waiting_for_confirmation':
            if text.lower() in ['yes', 'y', 'start']:
                await message.reply_text("🚀 Starting optimized processing...")
                await apply_edits(client, message, user_id)
            elif text.lower() in ['no', 'n', 'cancel']:
                await message.reply_text("❌ Operation cancelled.")
                user_sessions[user_id] = {}
            return
    
    await process_message_links(client, message, user_id, text)

async def process_message_links(client, message: Message, user_id: int, text: str):
    patterns = [
        r'https://t\.me/([a-zA-Z0-9_]+)/(\d+-\d+)',
        r'https://t\.me/([a-zA-Z0-9_]+)/(\d+)',
    ]
    
    all_messages = []
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            channel_username = match[0]
            
            if '-' in match[1]:
                start_end = match[1].split('-')
                if len(start_end) == 2:
                    try:
                        start_msg = int(start_end[0])
                        end_msg = int(start_end[1])
                        if (end_msg - start_msg) <= 10000:
                            for msg_id in range(start_msg, end_msg + 1):
                                all_messages.append((channel_username, msg_id))
                    except ValueError:
                        continue
            else:
                try:
                    msg_id = int(match[1])
                    all_messages.append((channel_username, msg_id))
                except ValueError:
                    continue
    
    if not all_messages:
        await message.reply_text("❌ No valid message links found!")
        return
    
    all_messages = sorted(list(set(all_messages)))
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    user_sessions[user_id]['edit_messages'] = all_messages
    user_sessions[user_id]['edit_instructions'] = []
    user_sessions[user_id]['state'] = 'collecting_edits'
    
    if 'speed_mode' not in user_sessions[user_id]:
        user_sessions[user_id]['speed_mode'] = DEFAULT_MODE
    
    total_messages = len(all_messages)
    speed_mode = user_sessions[user_id]['speed_mode']
    settings = get_speed_settings(speed_mode)
    
    estimated_time = (total_messages * settings['min_delay']) / 60
    
    await message.reply_text(
        f"✅ **{total_messages} Messages Ready**\n\n"
        f"**Speed Mode:** {speed_mode.upper()}\n"
        f"**Batch Size:** {settings['batch_size']}\n"
        f"**Delay:** {settings['min_delay']}-{settings['max_delay']}s\n"
        f"**Est. Time:** {estimated_time:.1f} minutes\n\n"
        f"Send edit instructions using `>>` separator or type `done`"
    )

async def collect_edit_instruction(client, message: Message, user_id: int, text: str):
    user_data = user_sessions[user_id]
    
    # Support both >> and -> separators
    if '>>' in text:
        parts = text.split('>>', 1)
        separator = '>>'
    elif '->' in text:
        parts = text.split('->', 1)
        separator = '->'
    else:
        await message.reply_text(
            "❌ Use `>>` or `->` as separator:\n"
            "• `HaRsHit2027 >> Physics Wallah`\n"
            "• `remove @HaRsHit2027`"
        )
        return
    
    if len(parts) == 2:
        search_text = parts[0].strip()
        replace_text = parts[1].strip()
        instruction_type = "replace"
        
        # Show what will be replaced with CORRECT examples
        examples_before = [
            f"Extracted By: @{search_text}",
            f"Title: Document {search_text}.pdf",
            f"By {search_text}",
            search_text
        ]
        
        examples_after = []
        for example in examples_before:
            examples_after.append(apply_all_edits(example, [{'search': search_text, 'replace': replace_text, 'type': 'replace'}]))
        
        user_data['edit_instructions'].append({
            'search': search_text,
            'replace': replace_text,
            'type': instruction_type
        })
        
        current_edits = len(user_data['edit_instructions'])
        
        response = (
            f"✅ **Edit #{current_edits} Added**\n\n"
            f"**Operation:** {text}\n"
            f"**Will replace both:**\n"
            f"• `{search_text}`\n"
            f"• `@{search_text}`\n\n"
            f"**With:** `{replace_text}`\n\n"
            f"**Examples:**\n"
            f"• `{examples_before[0]}` → `{examples_after[0]}`\n"
            f"• `{examples_before[1]}` → `{examples_after[1]}`\n\n"
            f"**Total edits:** {current_edits}\n"
            f"**Messages:** {len(user_data['edit_messages'])}\n\n"
            f"Send more edits or type `done`"
        )
        
        await message.reply_text(response)
    else:
        await message.reply_text("❌ Invalid format. Use: `search >> replace`")

async def show_confirmation(client, message: Message, user_id: int):
    user_data = user_sessions[user_id]
    edit_messages = user_data.get('edit_messages', [])
    edit_instructions = user_data.get('edit_instructions', [])
    
    if not edit_instructions:
        await message.reply_text("❌ No edits provided.")
        user_sessions[user_id] = {}
        return
    
    total_messages = len(edit_messages)
    speed_mode = user_data.get('speed_mode', DEFAULT_MODE)
    settings = get_speed_settings(speed_mode)
    
    estimated_time = (total_messages * settings['min_delay']) / 60
    
    confirmation_text = (
        f"🚀 **Ready for Processing**\n\n"
        f"**Scale:** {total_messages} messages\n"
        f"**Speed:** {speed_mode.upper()} mode\n"
        f"**Est. Time:** {estimated_time:.1f} minutes\n"
        f"**Edits:** {len(edit_instructions)} operations\n\n"
        f"**Replacements:**\n"
    )
    
    for i, edit in enumerate(edit_instructions, 1):
        confirmation_text += f"{i}. `{edit['search']}` & `@{edit['search']}` → `{edit['replace']}`\n"
    
    # Show CORRECT example transformation
    example_before = f"Extracted By: @{edit_instructions[0]['search']}"
    example_after = apply_all_edits(example_before, edit_instructions)
    confirmation_text += f"\n**Example:** `{example_before}` → `{example_after}`\n\n"
    
    confirmation_text += f"**Type `yes` to start** (or `no` to cancel)"
    
    user_data['state'] = 'waiting_for_confirmation'
    await message.reply_text(confirmation_text)

async def apply_edits(client, message: Message, user_id: int):
    """Optimized editing with CORRECT text replacement"""
    user_data = user_sessions[user_id]
    all_messages = user_data.get('edit_messages', [])
    edit_instructions = user_data.get('edit_instructions', [])
    
    user_data['flood_waits'] = 0
    user_data['consecutive_success'] = 0
    user_data['consecutive_errors'] = 0
    
    total_messages = len(all_messages)
    start_time = time.time()
    last_progress_update = start_time
    
    speed_mode = user_data.get('speed_mode', DEFAULT_MODE)
    settings = get_speed_settings(speed_mode)
    
    progress_msg = await message.reply_text(
        f"⚡ **Starting {speed_mode.upper()} Mode**\n\n"
        f"• Total: {total_messages} messages\n"
        f"• Speed: {settings['description']}\n"
        f"• Replacements: {len(edit_instructions)}\n"
        f"• Started: {time.strftime('%H:%M:%S')}\n\n"
        f"Progress: 0% (0/{total_messages})"
    )
    
    processed_count = 0
    edited_count = 0
    error_count = 0
    
    for batch_num, batch_start in enumerate(range(0, total_messages, settings['batch_size']), 1):
        batch = all_messages[batch_start:batch_start + settings['batch_size']]
        
        for channel_username, message_id in batch:
            try:
                msg = await client.get_messages(channel_username, message_id)
                original_caption = msg.caption if msg.caption else ""
                
                if original_caption:
                    new_caption = apply_all_edits(original_caption, edit_instructions)
                    
                    if new_caption != original_caption:
                        success = await smart_edit_caption(client, channel_username, message_id, new_caption, user_data)
                        if success:
                            edited_count += 1
                        else:
                            error_count += 1
                
                processed_count += 1
                
                current_time = time.time()
                if current_time - last_progress_update > PROGRESS_UPDATE_INTERVAL:
                    progress = (processed_count / total_messages) * 100
                    elapsed = current_time - start_time
                    messages_per_minute = (processed_count / elapsed) * 60 if elapsed > 0 else 0
                    
                    status = "🟢 Normal"
                    if user_data.get('flood_waits', 0) > 0:
                        status = "🟡 Caution"
                    if user_data.get('flood_waits', 0) >= MAX_FLOOD_WAITS:
                        status = "🔴 Safe Mode"
                    
                    await progress_msg.edit_text(
                        f"📊 **{speed_mode.upper()} Mode - {status}**\n\n"
                        f"• Progress: {progress:.1f}%\n"
                        f"• Processed: {processed_count}/{total_messages}\n"
                        f"• Speed: {messages_per_minute:.1f}/min\n"
                        f"• Edited: {edited_count}\n"
                        f"• Flood Waits: {user_data.get('flood_waits', 0)}\n"
                        f"• Elapsed: {elapsed/60:.1f}m\n"
                    )
                    last_progress_update = current_time
                
                current_mode = user_data.get('speed_mode', speed_mode)
                await asyncio.sleep(get_random_delay(current_mode))
                
            except Exception as e:
                error_count += 1
                processed_count += 1
                await asyncio.sleep(get_random_delay(speed_mode) * 2)
                continue
        
        if batch_start + settings['batch_size'] < total_messages:
            current_mode = user_data.get('speed_mode', speed_mode)
            await asyncio.sleep(get_batch_delay(current_mode))
    
    total_time = time.time() - start_time
    messages_per_minute = (processed_count / total_time) * 60 if total_time > 0 else 0
    
    await progress_msg.edit_text(
        f"✅ **Processing Complete**\n\n"
        f"**Final Stats:**\n"
        f"• Total: {total_messages} messages\n"
        f"• Edited: {edited_count}\n"
        f"• Errors: {error_count}\n"
        f"• Flood Waits: {user_data.get('flood_waits', 0)}\n"
        f"• Total Time: {total_time/60:.1f} minutes\n"
        f"• Speed: {messages_per_minute:.1f} msg/min\n"
        f"• Final Mode: {user_data.get('speed_mode', speed_mode).upper()}\n\n"
        f"⚡ **Ready for next batch!**"
    )
    
    user_sessions[user_id] = {}

# FIXED: Only respond to utility commands in private chats
@app.on_message(filters.command(["done", "cancel", "status"]) & filters.private)
async def utility_commands(client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
        
    command = message.command[0].lower()
    
    if command == "done" and user_id in user_sessions:
        await show_confirmation(client, message, user_id)
    elif command == "cancel" and user_id in user_sessions:
        user_sessions[user_id] = {}
        await message.reply_text("✅ Operation cancelled.")
    elif command == "status":
        if user_id in user_sessions:
            user_data = user_sessions[user_id]
            speed_mode = user_data.get('speed_mode', DEFAULT_MODE)
            status = (
                f"🤖 **Current Status**\n\n"
                f"• State: {user_data.get('state', 'idle')}\n"
                f"• Messages: {len(user_data.get('edit_messages', []))}\n"
                f"• Edits: {len(user_data.get('edit_instructions', []))}\n"
                f"• Speed Mode: {speed_mode.upper()}\n"
            )
            await message.reply_text(status)
        else:
            await message.reply_text("🤖 Status: Ready - Use `/speed` to configure")

if __name__ == "__main__":
    print("🤖 Fixed Caption Editor - Private Chat Only")
    print("⚡ Only responds to commands in private chats")
    print("🎯 No more interference in group chats")
    app.run()