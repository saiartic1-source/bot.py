# main.py
import logging
import requests
import re
import sqlite3
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler,
    ContextTypes, 
    filters
)
from telegram.constants import ParseMode

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - UPDATED WITH YOUR DETAILS
BOT_TOKEN = "8996878557:AAFyZfHKd-0JxlCkimXvZTxCQMrXcuY0fXc"
CHANNEL_USERNAME = "@rajamall_com"  # Your channel username
CHANNEL_LINK = "https://t.me/rajamall_com"  # Your channel link
ADMIN_IDS = [8559547390]  # Your admin ID
REFERRAL_CREDITS = 5
SEARCH_COST = 1

# Database setup
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('tracker_bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                credits INTEGER DEFAULT 5,
                total_searches INTEGER DEFAULT 0,
                referrals_count INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT NULL,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                credits_earned INTEGER DEFAULT 5,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                mobile_number TEXT,
                name TEXT,
                address TEXT,
                search_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, last_name, referred_by=None):
        existing = self.get_user(user_id)
        if existing:
            return existing
        
        self.cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, referred_by, credits, is_verified, is_banned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, referred_by, 5, 0, 0))
        self.conn.commit()
        
        if referred_by:
            self.process_referral(referred_by, user_id)
        
        return self.get_user(user_id)
    
    def process_referral(self, referrer_id, referred_id):
        self.cursor.execute('SELECT * FROM referrals WHERE referred_id = ?', (referred_id,))
        if self.cursor.fetchone():
            return
        
        self.cursor.execute('''
            UPDATE users SET credits = credits + ?, referrals_count = referrals_count + 1
            WHERE user_id = ?
        ''', (REFERRAL_CREDITS, referrer_id))
        
        self.cursor.execute('''
            INSERT INTO referrals (referrer_id, referred_id, credits_earned)
            VALUES (?, ?, ?)
        ''', (referrer_id, referred_id, REFERRAL_CREDITS))
        
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                'user_id': row[0],
                'username': row[1],
                'first_name': row[2],
                'last_name': row[3],
                'credits': row[4] if row[4] is not None else 5,
                'total_searches': row[5] if row[5] is not None else 0,
                'referrals_count': row[6] if row[6] is not None else 0,
                'referred_by': row[7],
                'join_date': row[8],
                'is_banned': row[9] if row[9] is not None else 0,
                'is_verified': row[10] if row[10] is not None else 0
            }
        return None
    
    def verify_user(self, user_id):
        self.cursor.execute('UPDATE users SET is_verified = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def deduct_credit(self, user_id):
        self.cursor.execute('''
            UPDATE users SET credits = credits - ?, total_searches = total_searches + 1
            WHERE user_id = ? AND credits >= ?
        ''', (SEARCH_COST, user_id, SEARCH_COST))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def add_search_history(self, user_id, mobile_number, name, address):
        self.cursor.execute('''
            INSERT INTO search_history (user_id, mobile_number, name, address)
            VALUES (?, ?, ?, ?)
        ''', (user_id, mobile_number, name, address))
        self.conn.commit()
    
    def get_search_history(self, user_id, limit=10):
        self.cursor.execute('''
            SELECT mobile_number, name, address, search_time FROM search_history 
            WHERE user_id = ? ORDER BY search_time DESC LIMIT ?
        ''', (user_id, limit))
        return self.cursor.fetchall()
    
    def get_all_users(self):
        self.cursor.execute('SELECT user_id, username, first_name, credits, total_searches, is_banned FROM users')
        return self.cursor.fetchall()
    
    def get_statistics(self):
        self.cursor.execute('SELECT COUNT(*) FROM users')
        total_users = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute('SELECT SUM(total_searches) FROM users')
        total_searches = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute('SELECT SUM(credits) FROM users')
        total_credits = self.cursor.fetchone()[0] or 0
        
        return {
            'total_users': total_users,
            'total_searches': total_searches,
            'total_credits': total_credits
        }
    
    def ban_user(self, user_id):
        self.cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def unban_user(self, user_id):
        self.cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def give_credits(self, user_id, amount):
        self.cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()
    
    def cut_credits(self, user_id, amount):
        self.cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ? AND credits >= ?', 
                          (amount, user_id, amount))
        self.conn.commit()
    
    def get_leaderboard(self, limit=10):
        self.cursor.execute('''
            SELECT username, first_name, credits, total_searches FROM users 
            WHERE credits > 0 AND is_banned = 0 ORDER BY credits DESC LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def get_referrals(self, user_id):
        self.cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        return self.cursor.fetchone()[0] or 0
    
    def close(self):
        self.conn.close()

db = Database()

# API function
def fetch_data(number):
    try:
        url = f"https://exploitsindia.site/track/live.php?term={number}"
        res = requests.get(url, timeout=10).text
        
        def get(pattern):
            m = re.search(pattern, res, re.IGNORECASE)
            return m.group(1).strip() if m else "N/A"
        
        return {
            "name": get(r"Name[:\-]?\s*(.*?)(?:\n|$)"),
            "mobile": number,
            "address": get(r"Address[:\-]?\s*(.*?)(?:\n|$)")
        }
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

# Check channel membership
async def check_membership(user_id, context) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logger.error(f"Membership check error: {e}")
    return False

# Main Menu Keyboard
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔍 SEARCH NUMBER", callback_data="search"),
            InlineKeyboardButton("💰 MY BALANCE", callback_data="balance")
        ],
        [
            InlineKeyboardButton("👥 REFER & EARN", callback_data="refer"),
            InlineKeyboardButton("📊 LEADERBOARD", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("📜 HISTORY", callback_data="history"),
            InlineKeyboardButton("ℹ️ HELP", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Parse referral code
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    
    # Add or get user
    user_data = db.get_user(user_id)
    if not user_data:
        user_data = db.add_user(user_id, user.username, user.first_name, user.last_name, referred_by)
    
    # Check if banned
    if user_data and user_data.get('is_banned', 0) == 1:
        await update.message.reply_text("❌ You are banned from using this bot!")
        return
    
    # Check if verified
    if user_data and user_data.get('is_verified', 0) == 1:
        # Show main menu
        menu_text = f"""
🌟 **MAIN MENU** 🌟

━━━━━━━━━━━━━━━━━━
👤 **User:** {user_data.get('first_name', 'User')}
💰 **Credits:** {user_data.get('credits', 5)}
🔍 **Searches:** {user_data.get('total_searches', 0)}
👥 **Referrals:** {db.get_referrals(user_id)}
━━━━━━━━━━━━━━━━━━

📌 **Choose an option below:**
        """
        await update.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    
    # Not verified - show verification screen
    verify_text = """
🔐 **ACCESS RESTRICTED**

━━━━━━━━━━━━━━━━━━
⚠️ You must join our channel to use this bot!

📌 **Steps:**
1️⃣ Click the JOIN button below
2️⃣ Join the channel
3️⃣ Click VERIFY button
━━━━━━━━━━━━━━━━━━
    """
    
    verify_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ VERIFY MEMBERSHIP", callback_data="verify")]
    ])
    
    await update.message.reply_text(verify_text, parse_mode=ParseMode.MARKDOWN, reply_markup=verify_keyboard)

# Verify callback
async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if await check_membership(user_id, context):
        db.verify_user(user_id)
        user_data = db.get_user(user_id)
        
        await query.message.delete()
        
        menu_text = f"""
✅ **VERIFICATION SUCCESSFUL!**

🌟 **MAIN MENU** 🌟

━━━━━━━━━━━━━━━━━━
👤 **User:** {user_data.get('first_name', 'User')}
💰 **Credits:** {user_data.get('credits', 5)}
🔍 **Searches:** {user_data.get('total_searches', 0)}
👥 **Referrals:** {db.get_referrals(user_id)}
━━━━━━━━━━━━━━━━━━

📌 **Choose an option below:**
        """
        await query.message.reply_text(menu_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await query.message.reply_text(
            "❌ **NOT VERIFIED!**\n\nPlease join the channel first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK)],
                [InlineKeyboardButton("✅ VERIFY", callback_data="verify")]
            ])
        )

# Search callback
async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.message.reply_text("❌ Please use /start first")
        return
    
    if user_data.get('is_verified', 0) != 1:
        await query.message.reply_text("❌ Please verify first using /start")
        return
    
    if user_data.get('is_banned', 0) == 1:
        await query.message.reply_text("❌ You are banned!")
        return
    
    credits = user_data.get('credits', 0)
    if credits < SEARCH_COST:
        await query.message.reply_text(
            f"❌ **Insufficient Credits!**\n\nYou have: {credits} credits\nNeed: {SEARCH_COST} credit per search\n\n👥 Invite friends to earn more credits!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await query.message.reply_text(
        "📱 **ENTER MOBILE NUMBER**\n\nSend me a 10-digit mobile number to track.\n\nExample: `9876543210`",
        parse_mode=ParseMode.MARKDOWN
    )

# Balance callback
async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    user_data = db.get_user(user_id)
    if not user_data:
        await query.message.reply_text("❌ Please use /start first")
        return
    
    # Get bot username safely
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    
    text = f"""
💰 **MY BALANCE**

━━━━━━━━━━━━━━━━━━
👤 **Username:** @{user_data.get('username') or 'N/A'}
💎 **Credits:** {user_data.get('credits', 0)}
🔍 **Total Searches:** {user_data.get('total_searches', 0)}
👥 **Referrals:** {db.get_referrals(user_id)}
━━━━━━━━━━━━━━━━━━

🔗 **Referral Link:**
`https://t.me/{bot_username}?start={user_id}`

💡 Share link to earn {REFERRAL_CREDITS} credits per referral!
    """
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Refer callback
async def refer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # Get bot username safely
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    link = f"https://t.me/{bot_username}?start={user_id}"
    
    text = f"""
👥 **REFER & EARN**

━━━━━━━━━━━━━━━━━━
🎁 **Reward:** {REFERRAL_CREDITS} credits per referral
👥 **Your Referrals:** {db.get_referrals(user_id)}
━━━━━━━━━━━━━━━━━━

🔗 **Your Link:**
`{link}`

📤 **Share this link with friends!**

💡 When friends join using your link, you get {REFERRAL_CREDITS} credits automatically!
    """
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Leaderboard callback
async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    leaderboard = db.get_leaderboard(10)
    
    if leaderboard:
        text = "🏆 **TOP 10 USERS**\n━━━━━━━━━━━━━━━━━━\n"
        for i, (username, first_name, credits, searches) in enumerate(leaderboard, 1):
            name = f"@{username}" if username else first_name
            text += f"{i}. {name}\n   💎 {credits} credits | 🔍 {searches} searches\n"
        text += "━━━━━━━━━━━━━━━━━━"
    else:
        text = "No users found on leaderboard!"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# History callback
async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    history = db.get_search_history(user_id, 10)
    
    if history:
        text = "📜 **RECENT SEARCHES**\n━━━━━━━━━━━━━━━━━━\n"
        for mobile, name, address, search_time in history:
            time = search_time[:16] if search_time else "Unknown"
            text += f"📱 `{mobile}`\n👤 {name[:30]}\n📅 {time}\n━━━━━━━━━━━━━━━━━━\n"
    else:
        text = "No search history found!"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Help callback
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = """
ℹ️ **HELP & INFORMATION**

━━━━━━━━━━━━━━━━━━
🔍 **Search Number** - Track any mobile number (1 credit)
💰 **My Balance** - Check your credits & referral link
👥 **Refer & Earn** - Get 5 credits per referral
📊 **Leaderboard** - Top users ranking
📜 **History** - View your past searches

━━━━━━━━━━━━━━━━━━
⚙️ **Commands:**
/start - Show main menu
/admin - Admin Control Panel

━━━━━━━━━━━━━━━━━━
💎 **Credit System:**
• 5 free credits on signup
• 1 credit per search
• 5 credits per referral

━━━━━━━━━━━━━━━━━━
📞 **Support:** @kingdemovideo
    """
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# Handle mobile number input
async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    number = update.message.text.strip()
    
    # Validate number
    if not number.isdigit() or len(number) < 10:
        await update.message.reply_text("❌ Invalid number! Please send a valid 10-digit mobile number.")
        return
    
    user_data = db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ Please use /start first")
        return
    
    if user_data.get('is_verified', 0) != 1:
        await update.message.reply_text("❌ Please verify first using /start")
        return
    
    if user_data.get('is_banned', 0) == 1:
        await update.message.reply_text("❌ You are banned!")
        return
    
    credits = user_data.get('credits', 0)
    if credits < SEARCH_COST:
        await update.message.reply_text(f"❌ Insufficient credits! You have {credits} credits. Need {SEARCH_COST} credit per search.")
        return
    
    processing = await update.message.reply_text("🔍 **SEARCHING...**\n\nPlease wait...")
    
    # Deduct credit
    if not db.deduct_credit(user_id):
        await processing.edit_text("❌ Failed to deduct credit! Please try again.")
        return
    
    # Fetch data
    data = fetch_data(number)
    
    if data and data.get("name") != "N/A":
        db.add_search_history(user_id, number, data['name'], data['address'])
        user_data = db.get_user(user_id)
        
        result_text = f"""
✅ **SEARCH SUCCESSFUL!**

━━━━━━━━━━━━━━━━━━
👤 **Name:** {data['name']}
📱 **Mobile:** {data['mobile']}
📍 **Address:** {data['address']}
━━━━━━━━━━━━━━━━━━

💰 **Remaining Credits:** {user_data.get('credits', 0)}
📊 **Total Searches:** {user_data.get('total_searches', 0)}
━━━━━━━━━━━━━━━━━━

Use /start for main menu
        """
        await processing.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
    else:
        # Refund credit
        db.give_credits(user_id, SEARCH_COST)
        await processing.edit_text("❌ **NO DATA FOUND!**\n\nNo information available for this number.\nYour credit has been refunded.", parse_mode=ParseMode.MARKDOWN)

# Admin commands (old ones kept for compatibility)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    
    stats = db.get_statistics()
    await update.message.reply_text(f"""
📊 **BOT STATISTICS**
━━━━━━━━━━━━━━━━━━
👥 Total Users: {stats['total_users']}
🔍 Total Searches: {stats['total_searches']}
💎 Total Credits: {stats['total_credits']}
━━━━━━━━━━━━━━━━━━
    """)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    message = ' '.join(context.args)
    users = db.get_all_users()
    success = 0
    
    status = await update.message.reply_text("📡 Broadcasting...")
    
    for user_id, username, first_name, credits, searches, is_banned in users:
        if is_banned == 0:
            try:
                await context.bot.send_message(user_id, f"📢 **Broadcast**\n\n{message}", parse_mode=ParseMode.MARKDOWN)
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
    
    await status.edit_text(f"✅ Broadcast sent to {success} users")

async def give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /give <user_id> <amount>")
        return
    
    target_user = int(context.args[0])
    amount = int(context.args[1])
    
    db.give_credits(target_user, amount)
    await update.message.reply_text(f"✅ Added {amount} credits to user {target_user}")

async def cut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /cut <user_id> <amount>")
        return
    
    target_user = int(context.args[0])
    amount = int(context.args[1])
    
    db.cut_credits(target_user, amount)
    await update.message.reply_text(f"✅ Removed {amount} credits from user {target_user}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    
    target_user = int(context.args[0])
    db.ban_user(target_user)
    await update.message.reply_text(f"✅ User {target_user} banned")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    
    target_user = int(context.args[0])
    db.unban_user(target_user)
    await update.message.reply_text(f"✅ User {target_user} unbanned")

# ============ NEW ADMIN PANEL ============

# Admin Panel Command
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ **Access Denied!**\n\nYou are not authorized to use this panel.", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Admin Panel Keyboard
    admin_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 STATISTICS", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 BROADCAST", callback_data="admin_broadcast")],
        [InlineKeyboardButton("➕ GIVE CREDITS", callback_data="admin_give")],
        [InlineKeyboardButton("➖ CUT CREDITS", callback_data="admin_cut")],
        [InlineKeyboardButton("🔨 BAN USER", callback_data="admin_ban")],
        [InlineKeyboardButton("🔓 UNBAN USER", callback_data="admin_unban")],
        [InlineKeyboardButton("📜 USER LIST", callback_data="admin_users")],
        [InlineKeyboardButton("❌ CLOSE", callback_data="admin_close")]
    ])
    
    text = """
👑 **ADMIN PANEL**

━━━━━━━━━━━━━━━━━━
Welcome to Admin Control Panel!

Select an option below:
━━━━━━━━━━━━━━━━━━
    """
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=admin_keyboard)

# Admin Callback Handlers
async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    stats = db.get_statistics()
    await query.message.reply_text(f"""
📊 **BOT STATISTICS**
━━━━━━━━━━━━━━━━━━
👥 Total Users: {stats['total_users']}
🔍 Total Searches: {stats['total_searches']}
💎 Total Credits: {stats['total_credits']}
━━━━━━━━━━━━━━━━━━
    """)

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    context.user_data['admin_action'] = 'broadcast'
    await query.message.reply_text("📢 **Send me the message to broadcast:**\n\n(Reply to this message with your broadcast text)", parse_mode=ParseMode.MARKDOWN)

async def admin_give_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    context.user_data['admin_action'] = 'give'
    await query.message.reply_text("➕ **Give Credits**\n\nSend: `/give user_id amount`\n\nExample: `/give 123456789 10`", parse_mode=ParseMode.MARKDOWN)

async def admin_cut_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    context.user_data['admin_action'] = 'cut'
    await query.message.reply_text("➖ **Cut Credits**\n\nSend: `/cut user_id amount`\n\nExample: `/cut 123456789 5`", parse_mode=ParseMode.MARKDOWN)

async def admin_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    context.user_data['admin_action'] = 'ban'
    await query.message.reply_text("🔨 **Ban User**\n\nSend: `/ban user_id`\n\nExample: `/ban 123456789`", parse_mode=ParseMode.MARKDOWN)

async def admin_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    context.user_data['admin_action'] = 'unban'
    await query.message.reply_text("🔓 **Unban User**\n\nSend: `/unban user_id`\n\nExample: `/unban 123456789`", parse_mode=ParseMode.MARKDOWN)

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.message.reply_text("❌ Access Denied!")
        return
    
    users = db.get_all_users()
    if users:
        text = "📜 **USER LIST**\n━━━━━━━━━━━━━━━━━━\n"
        for user_id, username, first_name, credits, searches, is_banned in users[:20]:
            status = "🚫 BANNED" if is_banned else "✅ ACTIVE"
            name = f"@{username}" if username else first_name
            text += f"ID: `{user_id}`\n👤 {name}\n💎 {credits} | 🔍 {searches}\n{status}\n━━━━━━━━━━━━━━━━━━\n"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text("No users found!")

async def admin_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()

# Handle admin text input for broadcast
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    if 'admin_action' not in context.user_data:
        return
    
    action = context.user_data['admin_action']
    message_text = update.message.text.strip()
    
    if action == 'broadcast':
        users = db.get_all_users()
        success = 0
        status_msg = await update.message.reply_text("📡 Broadcasting...")
        
        for user_id, username, first_name, credits, searches, is_banned in users:
            if is_banned == 0:
                try:
                    await context.bot.send_message(user_id, f"📢 **Broadcast**\n\n{message_text}", parse_mode=ParseMode.MARKDOWN)
                    success += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
        
        await status_msg.edit_text(f"✅ Broadcast sent to {success} users")
        context.user_data.pop('admin_action', None)

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ An error occurred. Please try again later.")

# Main
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))  # NEW ADMIN PANEL COMMAND
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("give", give_command))
    app.add_handler(CommandHandler("cut", cut_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    
    # Message handler for number input and admin input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="verify"))
    app.add_handler(CallbackQueryHandler(search_callback, pattern="search"))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="balance"))
    app.add_handler(CallbackQueryHandler(refer_callback, pattern="refer"))
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="leaderboard"))
    app.add_handler(CallbackQueryHandler(history_callback, pattern="history"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="help"))
    
    # Admin panel callbacks
    app.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="admin_stats"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern="admin_broadcast"))
    app.add_handler(CallbackQueryHandler(admin_give_callback, pattern="admin_give"))
    app.add_handler(CallbackQueryHandler(admin_cut_callback, pattern="admin_cut"))
    app.add_handler(CallbackQueryHandler(admin_ban_callback, pattern="admin_ban"))
    app.add_handler(CallbackQueryHandler(admin_unban_callback, pattern="admin_unban"))
    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern="admin_users"))
    app.add_handler(CallbackQueryHandler(admin_close_callback, pattern="admin_close"))
    
    # Error handler
    app.add_error_handler(error_handler)
    
    # Initialize and start
    await app.initialize()
    await app.start()
    
    bot_info = await app.bot.get_me()
    print(f"🤖 Bot is running...")
    print(f"📍 Bot username: @{bot_info.username}")
    print(f"📢 Channel: {CHANNEL_USERNAME}")
    print(f"👑 Admin ID: {ADMIN_IDS[0]}")
    
    await app.updater.start_polling()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await app.stop()

if __name__ == '__main__':
    asyncio.run(main())