import json
import os
import requests
import signal
import sys
import secrets
import string
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# === CONFIG ===
BOT_TOKEN = '8761531653:AAHpNyeDZf9SmU7SzIu3_95M68VIA'
API_KEY = '322737378ba87558dde68aa5ec86a23ac5a'
BASE_URL = 'https://t.me/STR_LIKE_BOT?start=verified_'
GROUP_CHAT_IDS = [-1003582740952,-1003248703812]  # ✅ Multiple groups list
LIKE_API_URL = 'https://star-like-50.vercel.app/like?uid={uid}&server_name={region}'
VERIFIED_FILE = 'verified_users.json'
SHORT_LINK_FILE = 'verified_links.json'
USAGE_FILE = 'daily_usage.json'
VIP_FILE = 'vip_users.json'
TOKEN_FILE = 'verification_tokens.json'
OWNER_ID = 8278060186
MAX_LIKES = 99999

# Channel Configuration for Force Subscription
CHANNEL_LINK = "https://t.me/STAR_METHODE"

# Valid regions
VALID_REGIONS = ['ind', 'bd', 'sg', 'id', 'me', 'br', 'vn', 'eu', 'th', 'na', 'us', 'uk']

# Updated links
JOIN_CHANNEL_LINK = "https://t.me/STAR_METHODE"
HOW_TO_VERIFY_LINK = "https://t.me/STAR_METHODE"
BUY_VIP_LINK = "https://t.me/STAR_RDP"

# Free user daily limit
FREE_DAILY_LIMIT = 1

# === File Helpers ===
def load_json(path):
    """Safely load JSON data from file"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:  # If file is empty
                return []
            return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        print(f"Warning: {path} contains invalid JSON. Resetting to empty list.")
        return []

def save_json(path, data):
    """Safely save JSON data to file"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# === Force Subscription System ===
async def is_user_subscribed(bot, user_id):
    """Check if user is subscribed to the channel"""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        status = member.status
        # User is subscribed if status is 'member', 'administrator', or 'creator'
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

async def check_subscription_and_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check subscription and send notification if not subscribed"""
    user_id = update.effective_user.id
    
    # Owner bypass
    if user_id == OWNER_ID:
        return True
        
    # VIP users also need to subscribe
    is_subscribed = await is_user_subscribed(context.bot, user_id)
    
    if not is_subscribed:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)],
            [InlineKeyboardButton("✅ I'VE JOINED", callback_data="check_subscription")]
        ])
        
        text = (
            "📢 <b>Subscription Required</b>\n\n"
            "🔒 To use this bot, you must join our official channel!\n\n"
            "👇 Please join the channel below and then click <b>I'VE JOINED</b> to continue."
        )
        
        if update.message:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
        
        return False
    
    return True

# === Token System ===
def generate_verification_token(length=16):
    """Generate a secure random token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def save_verification_token(user_id, uid, region):
    """Save token with user data"""
    tokens = load_json(TOKEN_FILE)
    
    # Remove any existing token for this user
    tokens = [t for t in tokens if t["user_id"] != user_id]
    
    # Generate new token
    token = generate_verification_token()
    expiry_time = datetime.now() + timedelta(minutes=10)
    
    tokens.append({
        "user_id": user_id,
        "token": token,
        "uid": uid,
        "region": region,
        "expiry": expiry_time.isoformat(),
        "used": False
    })
    
    save_json(TOKEN_FILE, tokens)
    return token

def get_token_data(token):
    """Get token data and mark as used"""
    tokens = load_json(TOKEN_FILE)
    for t in tokens:
        if t["token"] == token and not t["used"]:
            # Check if token expired
            expiry = datetime.fromisoformat(t["expiry"])
            if datetime.now() > expiry:
                return None
            # Mark token as used
            t["used"] = True
            save_json(TOKEN_FILE, tokens)
            return t
    return None

def get_user_active_token(user_id):
    """Check if user has an active token"""
    tokens = load_json(TOKEN_FILE)
    for t in tokens:
        if t["user_id"] == user_id and not t["used"]:
            expiry = datetime.fromisoformat(t["expiry"])
            if datetime.now() <= expiry:
                return t
    return None

# === Verified User Logic ===
def load_verified_users():
    return load_json(VERIFIED_FILE)

def save_verified_user(user_id, uid=None, region=None):
    users = load_verified_users()
    now = datetime.now().isoformat()
    for u in users:
        if u["id"] == user_id:
            u["timestamp"] = now
            if uid: u["uid"] = uid
            if region: u["region"] = region
            break
    else:
        users.append({
            "id": user_id, 
            "timestamp": now,
            "uid": uid,
            "region": region
        })
    save_json(VERIFIED_FILE, users)

def is_user_verified_recently(user_id):
    users = load_verified_users()
    for u in users:
        if u["id"] == user_id:
            ts = datetime.fromisoformat(u["timestamp"])
            return datetime.now() - ts < timedelta(hours=12)
    return False

def get_user_like_request(user_id):
    users = load_verified_users()
    for u in users:
        if u["id"] == user_id:
            return u.get("uid"), u.get("region")
    return None, None

# === Short Link Logic ===
def load_short_links():
    return load_json(SHORT_LINK_FILE)

def save_short_link(user_id, uid, region):
    data = load_short_links()
    now = datetime.now().isoformat()
    for entry in data:
        if entry["id"] == user_id:
            entry["timestamp"] = now
            entry["uid"] = uid
            entry["region"] = region
            break
    else:
        data.append({
            "id": user_id, 
            "timestamp": now,
            "uid": uid,
            "region": region
        })
    save_json(SHORT_LINK_FILE, data)

def is_short_link_expired(user_id):
    data = load_short_links()
    for entry in data:
        if entry["id"] == user_id:
            ts = datetime.fromisoformat(entry["timestamp"])
            return datetime.now() - ts > timedelta(minutes=10)
    return True

# === Daily Usage ===
def load_daily_usage():
    return load_json(USAGE_FILE)

def save_daily_usage(user_id):
    usage = load_daily_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Find user's usage for today
    user_found = False
    for u in usage:
        if u["id"] == user_id and u["date"] == today:
            u["count"] = u.get("count", 0) + 1
            user_found = True
            break
    
    # If user not found for today, create new entry
    if not user_found:
        usage.append({
            "id": user_id, 
            "date": today,
            "count": 1
        })
    
    save_json(USAGE_FILE, usage)

def get_today_usage_count(user_id):
    usage = load_daily_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    for u in usage:
        if u["id"] == user_id and u["date"] == today:
            return u.get("count", 0)
    return 0

def has_reached_daily_limit(user_id):
    if is_vip_user(user_id):
        return False  # VIP users have no limit
    return get_today_usage_count(user_id) >= FREE_DAILY_LIMIT

# === VIP Logic ===
def load_vip_users():
    return load_json(VIP_FILE)

def save_vip_user(user_id, days, like_limit):
    vip_users = load_vip_users()
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    for user in vip_users:
        if user["id"] == user_id:
            user["expiry"] = expiry_date
            user["like_limit"] = like_limit
            break
    else:
        vip_users.append({
            "id": user_id, 
            "expiry": expiry_date, 
            "like_limit": like_limit
        })
    save_json(VIP_FILE, vip_users)

def remove_vip_user(user_id):
    vip_users = load_vip_users()
    vip_users = [u for u in vip_users if u["id"] != user_id]
    save_json(VIP_FILE, vip_users)

def is_vip_user(user_id):
    vip_users = load_vip_users()
    for user in vip_users:
        if user["id"] == user_id:
            expiry_date = datetime.strptime(user["expiry"], "%Y-%m-%d")
            return datetime.now() < expiry_date
    return False

def get_vip_like_limit(user_id):
    vip_users = load_vip_users()
    for user in vip_users:
        if user["id"] == user_id:
            return user.get("like_limit", 999)  # Default high limit for VIP
    return 1

# === API CALL ===
async def call_like_api(region, uid):
    try:
        url = LIKE_API_URL.format(region=region, uid=uid)
        response = requests.get(url, timeout=30)
        
        # Check if response is valid JSON
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Check if API returned an error
                if data.get("error"):
                    return {
                        "status": 0,
                        "message": f"API Error: {data.get('error')}",
                        "LikesafterCommand": 0,
                        "LikesbeforeCommand": 0,
                        "PlayerNickname": "N/A",
                        "UID": uid,
                        "LikesGivenByAPI": 0
                    }
                
                if data.get("LikesafterCommand", 0) >= MAX_LIKES:
                    return {
                        "status": 2,
                        "message": "🎉 Player already has maximum likes!",
                        "LikesafterCommand": data.get("LikesafterCommand", 0),
                        "LikesbeforeCommand": data.get("LikesbeforeCommand", 0),
                        "PlayerNickname": data.get("PlayerNickname", "N/A"),
                        "UID": uid,
                        "LikesGivenByAPI": data.get("LikesGivenByAPI", 0)
                    }
                
                # Add status if not present
                if "status" not in data:
                    data["status"] = 1
                    
                return data
                
            except json.JSONDecodeError:
                return {
                    "status": 0,
                    "message": "⚠️ Invalid response from server",
                    "LikesafterCommand": 0,
                    "LikesbeforeCommand": 0,
                    "PlayerNickname": "N/A",
                    "UID": uid,
                    "LikesGivenByAPI": 0
                }
        else:
            return {
                "status": 0,
                "message": f"⚠️ Server returned status code: {response.status_code}",
                "LikesafterCommand": 0,
                "LikesbeforeCommand": 0,
                "PlayerNickname": "N/A",
                "UID": uid,
                "LikesGivenByAPI": 0
            }
            
    except requests.exceptions.Timeout:
        return {
            "status": 0,
            "message": "⏰ Request timeout! Server is taking too long to respond.",
            "LikesafterCommand": 0,
            "LikesbeforeCommand": 0,
            "PlayerNickname": "N/A",
            "UID": uid,
            "LikesGivenByAPI": 0
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": 0,
            "message": "🔌 Connection error! Unable to reach the server.",
            "LikesafterCommand": 0,
            "LikesbeforeCommand": 0,
            "PlayerNickname": "N/A",
            "UID": uid,
            "LikesGivenByAPI": 0
        }
    except Exception as e:
        return {
            "status": 0,
            "message": f"❌ Unexpected error: {str(e)}",
            "LikesafterCommand": 0,
            "LikesbeforeCommand": 0,
            "PlayerNickname": "N/A",
            "UID": uid,
            "LikesGivenByAPI": 0
        }

# === Helper Functions ===
def reset_daily_data():
    """Reset daily usage and verification data"""
    # Reset only daily usage and verification files, keep VIP data
    for file in [VERIFIED_FILE, SHORT_LINK_FILE, USAGE_FILE, TOKEN_FILE]:
        if os.path.exists(file):
            with open(file, 'w') as f:
                json.dump([], f)
    print(f"[{datetime.now()}] ✅ Daily data reset completed!")

def format_next_available_time():
    now = datetime.now()
    next_time = now + timedelta(hours=24)
    return next_time.strftime("%Y-%m-%d %H:%M:%S")

async def send_like_success_message(update, context, api_response, region, is_vip=False):
    user = update.effective_user.first_name or "User"
    user_id = update.effective_user.id
    
    # Get remaining likes for today
    if is_vip:
        remaining = "Unlimited"
        user_type = "💎 <b>VIP User</b>"
    else:
        used = get_today_usage_count(user_id)
        remaining = max(0, FREE_DAILY_LIMIT - used)
        user_type = "👤 <b>Free User</b>"
    
    if api_response.get("status") == 2:
        # Max likes reached
        text = f"""
🎮 <b>FREE FIRE LIKE STATUS</b>
────────────────────
{user_type}
🎯 <b>Player:</b> <code>{api_response.get('PlayerNickname', 'N/A')}</code>
🆔 <b>UID:</b> <code>{api_response.get('UID', 'N/A')}</code>
🌍 <b>Region:</b> <code>{region.upper()}</code>

📊 <b>CURRENT LIKES:</b> <code>{api_response.get('LikesafterCommand', 0)}</code>
🎉 <b>Status:</b> Maximum likes reached!

📅 <b>Next Reset:</b> 04:00 AM IST
────────────────────
<b>Owner:</b> @Unknown_mod1
        """
    elif api_response.get("status") == 1:
        # Success
        text = f"""
🎮 <b>FREE FIRE LIKE SUCCESS</b>
────────────────────
{user_type}
👤 <b>User:</b> {user}
🎯 <b>Player:</b> <code>{api_response.get('PlayerNickname', 'N/A')}</code>
🆔 <b>UID:</b> <code>{api_response.get('UID', 'N/A')}</code>
🌍 <b>Region:</b> <code>{region.upper()}</code>

📊 <b>BEFORE:</b> <code>{api_response.get('LikesbeforeCommand', 0)}</code>
📈 <b>AFTER:</b> <code>{api_response.get('LikesafterCommand', 0)}</code>
🎁 <b>SENT:</b> <code>{api_response.get('LikesGivenByAPI', 0)}</code> likes

📅 <b>Next Reset:</b> 04:00 AM IST
🔄 <b>Remaining Today:</b> <code>{remaining}</code>
────────────────────
<b>Owner:</b> @STAR_GMR 
        """
    else:
        # Error case
        text = f"""
❌ <b>LIKE SENDING FAILED</b>
────────────────────
{user_type}
🎯 <b>Player:</b> <code>{api_response.get('PlayerNickname', 'N/A')}</code>
🆔 <b>UID:</b> <code>{api_response.get('UID', 'N/A')}</code>
🌍 <b>Region:</b> <code>{region.upper()}</code>

⚠️ <b>Error:</b> {api_response.get('message', 'Unknown error')}

🔄 <b>Remaining Today:</b> <code>{remaining}</code>
────────────────────
<b>Owner:</b> @STAR_GMR
        """

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("💎 BUY VIP", url=BUY_VIP_LINK)],
        [InlineKeyboardButton("📊 CHECK STATS", callback_data="stats")]
    ])
    
    # Reply to user's message
    await update.message.reply_text(
        text=text.strip(),
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    # Also send to groups if not VIP and success
    if not is_vip and api_response.get("status") == 1:
        for group_id in GROUP_CHAT_IDS:
            try:
                await context.bot.send_message(
                    chat_id=group_id,
                    text=text.strip(),
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Failed to send message to group {group_id}: {e}")

# === Subscription Check Handler ===
async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'I'VE JOINED' button click"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Check if user has subscribed
    is_subscribed = await is_user_subscribed(context.bot, user_id)
    
    if is_subscribed:
        await query.edit_message_text(
            "✅ <b>Subscription Verified!</b>\n\n"
            "Thank you for joining our channel! 🎉\n\n"
            "You can now use the bot features:\n"
            "• Use <code>/like [region] [uid]</code> to send likes\n"
            "• Check <code>/stats</code> for your usage\n"
            "• Consider <code>/vip</code> for unlimited access\n\n"
            "<b>Happy Gaming! 🎮</b>",
            parse_mode='HTML'
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)],
            [InlineKeyboardButton("✅ I'VE JOINED", callback_data="check_subscription")]
        ])
        
        await query.edit_message_text(
            "❌ <b>Not Subscribed Yet</b>\n\n"
            "I still don't see you in our channel! 😔\n\n"
            "Please make sure to:\n"
            "1. Click the JOIN CHANNEL button\n"
            "2. Actually join the channel\n"
            "3. Then click I'VE JOINED\n\n"
            "If you've already joined, wait a moment and try again.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )

# === Commands ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name or "there"
    args = context.args

    # Check subscription first (except for owner)
    if user_id != OWNER_ID:
        is_subscribed = await check_subscription_and_notify(update, context)
        if not is_subscribed:
            return

    if args and args[0].startswith("verified_"):
        token = args[0][9:]  # Remove "verified_" prefix
        
        # Get token data
        token_data = get_token_data(token)
        
        if not token_data:
            await update.message.reply_text(
                "❌ <b>Invalid or expired verification link!</b>\n\n"
                "⚠️ Link expires in 10 minutes for security.\n"
                "Please generate a new link using: <code>/like [region] [uid]</code>",
                parse_mode='HTML'
            )
            return
        
        # Check if token belongs to this user
        if token_data["user_id"] != user_id:
            await update.message.reply_text(
                "❌ <b>This verification link is not for you!</b>\n\n"
                "Please generate your own link using: <code>/like [region] [uid]</code>",
                parse_mode='HTML'
            )
            return
        
        region = token_data["region"]
        uid = token_data["uid"]
        
        # Check daily limit for free users
        if not is_vip_user(user_id) and has_reached_daily_limit(user_id):
            used = get_today_usage_count(user_id)
            await update.message.reply_text(
                f"🚫 <b>Daily Limit Reached!</b>\n\n"
                f"You have used {used}/{FREE_DAILY_LIMIT} free likes today.\n"
                f"Please try again tomorrow after 4 AM IST.\n\n"
                f"💎 <b>Want unlimited likes?</b> Buy VIP! @STAR_GMR",
                parse_mode='HTML'
            )
            return
        
        # Send verification message to user
        await update.message.reply_text(
            text="✅ <b>Verification complete!</b>\n\n⏳ <b>Processing like request...</b>",
            parse_mode='HTML'
        )
        
        loading_msg = await update.message.reply_text(
            text="🎮 <b>Sending likes to Free Fire...</b>\n\n⏳ <i>Please wait 10-20 seconds</i>",
            parse_mode='HTML'
        )
        
        # Save verification and automatically send like
        save_verified_user(user_id, uid, region)
        
        api_response = await call_like_api(region, uid)
        
        # Check if API returned error
        if api_response.get("status") == 0:
            await loading_msg.edit_text(
                f"❌ <b>Failed to send likes!</b>\n\n"
                f"<b>Error:</b> {api_response.get('message', 'Unknown error')}\n\n"
                f"⚠️ Please try again after some time.",
                parse_mode='HTML'
            )
            return
        
        save_daily_usage(user_id)
        await send_like_success_message(update, context, api_response, region, is_vip=is_vip_user(user_id))
        await loading_msg.delete()
        
    else:
        # Show remaining likes for today
        used = get_today_usage_count(user_id)
        remaining = max(0, FREE_DAILY_LIMIT - used)
        vip_status = "💎 <b>VIP User</b>" if is_vip_user(user_id) else "👤 <b>Free User</b>"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 BUY VIP", url=BUY_VIP_LINK)],
            [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)],
            [InlineKeyboardButton("📖 HOW TO USE", url=HOW_TO_VERIFY_LINK)],
            [InlineKeyboardButton("🎮 SEND LIKES", callback_data="send_likes_help")]
        ])
        
        welcome_text = f"""
🎮 <b>WELCOME TO FREE FIRE VIP LIKES BOT</b>
────────────────────
{vip_status}
📊 <b>Likes Used Today:</b> <code>{used}/{FREE_DAILY_LIMIT}</code>
🔄 <b>Remaining:</b> <code>{remaining}</code>
🕐 <b>Daily Reset:</b> 04:00 AM IST

<b>COMMANDS:</b>
🎁 <code>/like [region] [uid]</code> - Send likes
📊 <code>/stats</code> - Check your stats

<b>EXAMPLE:</b>
<code>/like ind 8431487083</code>

<b>VALID REGIONS:</b>
🇮🇳 ind, 🇧🇩 bd, 🇸🇬 sg, 🇮🇩 id, 🇲🇪 me
🇧🇷 br, 🇻🇳 vn, 🇪🇺 eu, 🇹🇭 th, 🇺🇸 us, 🇬🇧 uk

💎 <b>Buy VIP for unlimited likes!</b>
        """
        
        await update.message.reply_text(
            welcome_text.strip(),
            parse_mode='HTML',
            reply_markup=keyboard
        )

async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user.first_name or "there"
    
    # Check subscription first (except for owner)
    if user_id != OWNER_ID:
        is_subscribed = await check_subscription_and_notify(update, context)
        if not is_subscribed:
            return
    
    # Send initial message to user
    loading_msg = await update.message.reply_text(
        text="🎮 <b>Processing your like request...</b>\n\n⏳ <i>Please wait</i>",
        parse_mode='HTML'
    )

    if not context.args or len(context.args) < 2:
        await loading_msg.edit_text(
            "❌ <b>Invalid Format</b>\n\n"
            "📝 <b>Usage:</b> <code>/like [region] [uid]</code>\n\n"
            "🌍 <b>Valid regions:</b> ind, bd, sg, id, me, br, vn, eu, th, na, us, uk\n\n"
            "📌 <b>Example:</b> <code>/like ind 8431487083</code>",
            parse_mode='HTML'
        )
        return

    region = context.args[0].lower()
    uid = context.args[1]
    
    # Validate region
    if region not in VALID_REGIONS:
        await loading_msg.edit_text(
            f"❌ <b>Invalid Region</b>\n\n"
            f"<b>You entered:</b> <code>{region}</code>\n"
            f"<b>Valid regions:</b> ind, bd, sg, id, me, br, vn, eu, th, na, us, uk\n\n"
            f"📌 <b>Example:</b> <code>/like ind 8431487083</code>",
            parse_mode='HTML'
        )
        return

    # Owner bypass
    if user_id == OWNER_ID:
        await loading_msg.edit_text(
            text="🎮 <b>Sending likes to Free Fire...</b>\n\n⏳ <i>Please wait 10-20 seconds</i>",
            parse_mode='HTML'
        )
        
        api_response = await call_like_api(region, uid)
        
        if api_response.get("status") == 0:
            await loading_msg.edit_text(
                f"❌ <b>Failed to send likes!</b>\n\n"
                f"<b>Error:</b> {api_response.get('message', 'Unknown error')}",
                parse_mode='HTML'
            )
            return
        
        await send_like_success_message(update, context, api_response, region)
        await loading_msg.delete()
        return

    # VIP bypass
    if is_vip_user(user_id):
        await loading_msg.edit_text(
            text="🎮 <b>Sending likes to Free Fire...</b>\n\n⏳ <i>Please wait 10-20 seconds</i>",
            parse_mode='HTML'
        )
        
        api_response = await call_like_api(region, uid)
        
        if api_response.get("status") == 0:
            await loading_msg.edit_text(
                f"❌ <b>Failed to send likes!</b>\n\n"
                f"<b>Error:</b> {api_response.get('message', 'Unknown error')}",
                parse_mode='HTML'
            )
            return
        
        await send_like_success_message(update, context, api_response, region, is_vip=True)
        await loading_msg.delete()
        return

    # Check daily limit for free users
    if has_reached_daily_limit(user_id):
        used = get_today_usage_count(user_id)
        await loading_msg.edit_text(
            f"🚫 <b>Daily Limit Reached!</b>\n\n"
            f"You have used {used}/{FREE_DAILY_LIMIT} free likes today.\n"
            f"Please try again tomorrow after 4 AM IST.\n\n"
            f"💎 <b>Want unlimited likes?</b> Buy VIP! @STAR_GMR",
            parse_mode='HTML'
        )
        return

    # Normal user flow
    if not is_user_verified_recently(user_id):
        # Generate unique token for verification
        token = save_verification_token(user_id, uid, region)
        destination_url = f"{BASE_URL}{token}"

        try:
            short_api = f"https://vplink.in/api?api={API_KEY}&url={destination_url}"
            response = requests.get(short_api, timeout=30).json()
            if response.get("status") != "success":
                raise Exception(response.get("message", "Unknown error"))
            short_link = response["shortenedUrl"]
            save_short_link(user_id, uid, region)
        except Exception as e:
            await loading_msg.edit_text(
                f"⚠️ <b>Link generation failed!</b>\n\n"
                f"<b>Error:</b> {str(e)}\n\n"
                f"Please try again.",
                parse_mode='HTML'
            )
            return

        text = f"""
🎮 <b>LIKE REQUEST VERIFICATION</b>
────────────────────
👤 <b>Name:</b> <code>{user}</code>
🆔 <b>UID:</b> <code>{uid}</code>
🌍 <b>Region:</b> <code>{region.upper()}</code>

🔗 <b>Verification Link:</b>
{short_link}

⚠️ <b>Link expires in 10 minutes</b>
📞 <b>Any Problem DM:</b> @STAR_GMR
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ VERIFY & SEND LIKES", url=short_link)],
            [InlineKeyboardButton("❓ HOW TO VERIFY?", url=HOW_TO_VERIFY_LINK)],
            [InlineKeyboardButton("💎 BUY VIP", url=BUY_VIP_LINK)],
            [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)]
        ])
        
        await loading_msg.edit_text(text.strip(), reply_markup=keyboard, parse_mode='HTML')
        return

    # If user is verified and under daily limit, send likes
    await loading_msg.edit_text(
        text="🎮 <b>Sending likes to Free Fire...</b>\n\n⏳ <i>Please wait 10-20 seconds</i>",
        parse_mode='HTML'
    )
    
    api_response = await call_like_api(region, uid)

    if api_response.get("status") == 0:
        await loading_msg.edit_text(
            f"❌ <b>Failed to send likes!</b>\n\n"
            f"<b>Error:</b> {api_response.get('message', 'Unknown error')}\n\n"
            f"⚠️ Please try again after some time.",
            parse_mode='HTML'
        )
        return

    save_daily_usage(user_id)
    await send_like_success_message(update, context, api_response, region)
    await loading_msg.delete()

async def add_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ <b>Only the owner can use this command.</b>", parse_mode='HTML')
        return

    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ <b>Usage:</b> <code>/add user_id days like_limit</code>", parse_mode='HTML')
        return

    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        like_limit = int(context.args[2])
        save_vip_user(user_id, days, like_limit)
        await update.message.reply_text(
            f"✅ <b>User {user_id} added to VIP for {days} days with {like_limit} likes per day.</b>", 
            parse_mode='HTML'
        )
    except ValueError:
        await update.message.reply_text("❌ <b>Invalid user ID, days or like limit.</b>", parse_mode='HTML')

async def remove_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ <b>Only the owner can use this command.</b>", parse_mode='HTML')
        return

    if not context.args:
        await update.message.reply_text("❌ <b>Usage:</b> <code>/remove user_id</code>", parse_mode='HTML')
        return

    try:
        user_id = int(context.args[0])
        remove_vip_user(user_id)
        await update.message.reply_text(f"✅ <b>User {user_id} removed from VIP.</b>", parse_mode='HTML')
    except ValueError:
        await update.message.reply_text("❌ <b>Invalid user ID.</b>", parse_mode='HTML')

async def vip_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ <b>Only the owner can use this command.</b>", parse_mode='HTML')
        return
        
    vip_users = load_vip_users()
    if not vip_users:
        await update.message.reply_text("ℹ️ <b>No VIP users found.</b>", parse_mode='HTML')
        return

    text = "🌟 <b>VIP Users List:</b>\n\n"
    for user in vip_users:
        expiry_date = user['expiry']
        like_limit = user.get('like_limit', 999)
        text += f"• <b>ID:</b> <code>{user['id']}</code> - <b>Expiry:</b> <code>{expiry_date}</code> - <b>Limit:</b> <code>{like_limit}</code> likes/day\n"

    await update.message.reply_text(text, parse_mode='HTML')

async def reset_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ <b>Only the owner can use this command.</b>", parse_mode='HTML')
        return

    reset_daily_data()
    await update.message.reply_text("✅ <b>Daily data has been reset.</b>", parse_mode='HTML')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check subscription first (except for owner)
    if user_id != OWNER_ID:
        is_subscribed = await check_subscription_and_notify(update, context)
        if not is_subscribed:
            return
    
    used = get_today_usage_count(user_id)
    remaining = max(0, FREE_DAILY_LIMIT - used)
    vip_status = "💎 <b>VIP User</b>" if is_vip_user(user_id) else "👤 <b>Free User</b>"
    
    # Get next reset time
    now = datetime.now()
    if now.hour < 4:
        reset_time = datetime(now.year, now.month, now.day, 4, 0, 0)
    else:
        tomorrow = now + timedelta(days=1)
        reset_time = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 4, 0, 0)
    
    time_until_reset = reset_time - now
    hours = time_until_reset.seconds // 3600
    minutes = (time_until_reset.seconds % 3600) // 60
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 BUY VIP", url=BUY_VIP_LINK)],
        [InlineKeyboardButton("🌟 JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🎮 SEND LIKES", callback_data="send_likes_help")]
    ])
    
    stats_text = f"""
📊 <b>YOUR STATISTICS</b>
────────────────────
{vip_status}
🎁 <b>Likes Used Today:</b> <code>{used}/{FREE_DAILY_LIMIT}</code>
🔄 <b>Remaining:</b> <code>{remaining}</code>
⏰ <b>Next Reset In:</b> {hours}h {minutes}m
🕐 <b>Daily Reset:</b> 04:00 AM IST

💎 <b>VIP FEATURES:</b>
• Unlimited daily likes
• No verification required
• Priority processing
• No ads

📞 <b>Contact @STAR_GMR for VIP</b>
    """
    
    await update.message.reply_text(
        stats_text.strip(),
        parse_mode='HTML',
        reply_markup=keyboard
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send broadcast message to all users"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ <b>Only the owner can use this command.</b>", parse_mode='HTML')
        return
    
    if not context.args:
        await update.message.reply_text("❌ <b>Usage:</b> <code>/broadcast Your message here</code>", parse_mode='HTML')
        return
    
    message = " ".join(context.args)
    broadcast_text = f"""
📢 <b>ANNOUNCEMENT FROM ADMIN</b>
────────────────────
{message}
────────────────────
<b>Bot Owner:</b> @STAR_GMR
    """
    
    # Get all unique user IDs from different files
    all_users = set()
    
    # From verified users
    verified = load_verified_users()
    for user in verified:
        all_users.add(user["id"])
    
    # From daily usage
    usage = load_daily_usage()
    for user in usage:
        all_users.add(user["id"])
    
    # From VIP users
    vip_users = load_vip_users()
    for user in vip_users:
        all_users.add(user["id"])
    
    sent_count = 0
    failed_count = 0
    
    status_msg = await update.message.reply_text(f"📤 <b>Broadcasting to {len(all_users)} users...</b>", parse_mode='HTML')
    
    for user_id in all_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_text.strip(),
                parse_mode='HTML'
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
        
        # Update status every 10 users
        if sent_count % 10 == 0:
            await status_msg.edit_text(
                f"📤 <b>Broadcasting...</b>\n\n"
                f"✅ Sent: {sent_count}\n"
                f"❌ Failed: {failed_count}\n"
                f"📊 Total: {len(all_users)}",
                parse_mode='HTML'
            )
    
    await status_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"✅ Successfully sent: {sent_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"📊 Total users: {len(all_users)}",
        parse_mode='HTML'
    )

# === Cleanup Expired Tokens ===
async def cleanup_expired_tokens():
    """Clean up expired tokens periodically"""
    tokens = load_json(TOKEN_FILE)
    current_time = datetime.now()
    
    # Remove tokens older than 10 minutes
    valid_tokens = []
    expired_count = 0
    for token in tokens:
        expiry = datetime.fromisoformat(token["expiry"])
        if current_time <= expiry and not token["used"]:
            valid_tokens.append(token)
        else:
            expired_count += 1
    
    if expired_count > 0:
        print(f"[{current_time}] 🗑️ Cleared {expired_count} expired tokens")
    
    save_json(TOKEN_FILE, valid_tokens)

# === Scheduled Reset at 4 AM ===
async def scheduled_daily_reset():
    """Reset daily usage at 4 AM IST every day"""
    reset_daily_data()
    
    # Also notify owner
    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        await app.bot.send_message(
            chat_id=OWNER_ID,
            text=f"✅ <b>Daily Reset Completed!</b>\n\n"
                 f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                 f"📊 All user limits have been reset.\n"
                 f"🔄 Ready for new day!",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Failed to notify owner: {e}")

# === Initialize JSON files ===
def initialize_files():
    """Initialize JSON files if they don't exist"""
    files = [VERIFIED_FILE, SHORT_LINK_FILE, USAGE_FILE, VIP_FILE, TOKEN_FILE]
    for file in files:
        if not os.path.exists(file):
            with open(file, 'w') as f:
                json.dump([], f)
            print(f"[{datetime.now()}] Created {file}")

# === Shutdown Cleanup ===
def clear_verified_data():
    for file in [VERIFIED_FILE, SHORT_LINK_FILE, USAGE_FILE, VIP_FILE, TOKEN_FILE]:
        if os.path.exists(file):
            with open(file, 'w') as f:
                json.dump([], f)
    print(f"[{datetime.now()}] 🧹 Data cleared.")

def handle_shutdown(signum, frame):
    print(f"[{datetime.now()}] 🚫 Bot stopping...")
    clear_verified_data()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# === Main Function ===
async def main():
    """Main function to run the bot"""
    # Initialize files
    initialize_files()
    
    # Create application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("like", like_command))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_vip_command))
    app.add_handler(CommandHandler("remove", remove_vip_command))
    app.add_handler(CommandHandler("viplist", vip_list_command))
    app.add_handler(CommandHandler("resetdaily", reset_daily_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Add callback handler for subscription check
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    
    # Cleanup expired tokens on startup
    await cleanup_expired_tokens()
    
    # Setup scheduler for daily reset at 4 AM IST
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_daily_reset, CronTrigger(hour=4, minute=0, timezone='Asia/Kolkata'))
    scheduler.add_job(cleanup_expired_tokens, 'interval', minutes=30)
    scheduler.start()
    
    print(f"[{datetime.now()}] 🤖 Free Fire VIP Likes Bot is running...")
print(f"[{datetime.now()}] 📢 Channel: @STAR_METHODE")
print(f"[{datetime.now()}] ⏰ Daily reset scheduled at: 04:00 AM IST")

    # Run the bot
    await app.start()
    await app.updater.start_polling()
    
    # Keep the bot running
    await asyncio.Event().wait()

# === Start Bot ===
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{datetime.now()}] 👋 Bot stopped by user")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Error: {e}")
