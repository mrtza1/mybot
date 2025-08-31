# -*- coding: utf-8 -*-
import logging
import json
import asyncio
import uuid
from typing import Dict, Any, Set, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ==================== الإعدادات ====================
TOKEN = "6336239139:AAHSUeTIU-S7VeAyTbkR9K_ZlMTyg2tz5M0"
ADMIN_IDS = {5261515404}              # آيديات الأدمن
ADMIN_GROUP_ID = 5261515404           # جروب مراجعة الطلبات
AUCTION_CHANNEL = "@brabb"            # قناة النشر
CHANNELS_FILE = "channels.json"       # ملف حفظ قنوات الاشتراك الإلزامي
POINTS_CHANNELS_FILE = "points_channels.json" # ملف حفظ قنوات نقاط الاشتراك
POINTS_LOG_FILE = "points_log.json" # ملف حفظ سجل نقاط الاشتراك
POINTS_FILE = "points.json"           # ملف حفظ نقاط المستخدمين
OWNER_ID = 5261515404 # آيدي المالك لاستقبال الرسائل الخاصة

# ==================== تحميل/حفظ البيانات ====================
def load_channels() -> List[str]:
    try:
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return ["@brabb"]

def save_channels():
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(CHANNELS, f, ensure_ascii=False, indent=2)

def load_points_channels() -> List[str]:
    try:
        with open(POINTS_CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_points_channels():
    with open(POINTS_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(POINTS_CHANNELS, f, ensure_ascii=False, indent=2)

def load_points_log() -> Dict[str, List[str]]:
    try:
        with open(POINTS_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_points_log():
    with open(POINTS_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(points_log, f, ensure_ascii=False, indent=2)

def load_points() -> Dict[str, int]:
    try:
        with open(POINTS_FILE, "r", encoding="utf-8") as f:
            # Load as string keys to be safe with JSON
            return {int(k): v for k, v in json.load(f).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_points():
    with open(POINTS_FILE, "w", encoding="utf-8") as f:
        # Save with string keys
        json.dump({str(k): v for k, v in points.items()}, f, ensure_ascii=False, indent=2)

CHANNELS: List[str] = load_channels()
POINTS_CHANNELS: List[str] = load_points_channels()
points_log: Dict[str, List[str]] = load_points_log()
points: Dict[int, int] = load_points()

# ==================== متغيّرات داخلية ====================
pending_requests: Dict[str, Dict[str, Any]] = {}
banned_users: Set[int] = set()
all_users: Set[int] = set()
total_requests: int = 0
admin_invite_links: Dict[str, Dict[str, Any]] = {} # قاموس لروابط الدعوة الخاصة بالأدمن

# ==================== اللوج ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== أدوات مساعدة ====================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    تحقق من اشتراك المستخدم في جميع القنوات الإلزامية.
    """
    if not CHANNELS:
        return True

    for channel_username in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel_username, user_id)
            if member.status not in ("member", "administrator", "creator"):
                # المستخدم غير مشترك في هذه القناة
                return False
        except Exception as e:
            # في حال حدوث خطأ (مثل عدم وجود البوت في القناة)، اعتبر المستخدم غير مشترك لتفادي الأخطاء.
            logger.error(f"Failed to check subscription for channel {channel_username}: {e}")
            return False
            
    # المستخدم مشترك في جميع القنوات
    return True

def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    user_points = points.get(user_id, 0)
    kb = [
        [InlineKeyboardButton("🎁 نشر هدية", callback_data="gift"),
         InlineKeyboardButton("🧾 نشر معرف", callback_data="username")],
        [InlineKeyboardButton("📢 قناة النشر", url=f"https://t.me/{AUCTION_CHANNEL.strip('@')}")],
        [InlineKeyboardButton("📜 الشروط", callback_data="rules")],
        [InlineKeyboardButton("🎁 تجميع النقاط", callback_data="collect_points"),
         InlineKeyboardButton("🔄 تحويل النقاط", callback_data="transfer_points")],
        [InlineKeyboardButton(f"عدد نقاطي: {user_points}", callback_data="my_points")]
    ]
    return InlineKeyboardMarkup(kb)

def collect_points_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🔗 عبر رابط الدعوة", callback_data="invite_link")],
        [InlineKeyboardButton("🎁 عبر الاشتراك بالقنوات", callback_data="subscribe_for_points")],
        [InlineKeyboardButton("💰 شراء نقاط مقابل نجوم", callback_data="buy_points_with_stars")],
        [InlineKeyboardButton("🔙 عودة للقائمة", callback_data="back_to_start")]
    ]
    return InlineKeyboardMarkup(kb)

# ==================== /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != "private":
        return
    user = update.effective_user
    if not user or user.id in banned_users:
        return

    # إرسال إشعار للمالك عند دخول شخص جديد
    is_new_user = user.id not in all_users
    all_users.add(user.id)
    if is_new_user and user.id != OWNER_ID:
        try:
            message_text = (
                "تم دخول شخص جديد إلى البوت الخاص بك 👾\n"
                "-----------------------\n"
                "• معلومات العضو الجديد .\n\n"
                f"• الاسم : {user.full_name}\n"
                f"• المعرّف : @{user.username if user.username else 'لا يوجد'}\n"
                f"• الآيدي : {user.id}\n"
                "-----------------------\n"
                f"• عدد الأعضاء الكلي : {len(all_users)}"
            )
            await context.bot.send_message(OWNER_ID, message_text)
        except Exception as e:
            logger.error(f"Failed to send new user notification to owner: {e}")

    # التحقق من رابط الدعوة ومنح نقطة للمستخدم الذي قام بالدعوة
    if context.args:
        # رابط دعوة عادي
        if context.args[0].isdigit():
            try:
                inviter_id = int(context.args[0])
                if inviter_id != user.id:
                    if user.id not in points: 
                        points[inviter_id] = points.get(inviter_id, 0) + 1
                        save_points()
                        await context.bot.send_message(inviter_id, f"🎉 تهانينا! لقد حصلت على نقطة جديدة لدعوتك مستخدمًا جديدًا. نقاطك الآن: {points[inviter_id]}")
                        points[user.id] = points.get(user.id, 0)
            except (ValueError, IndexError):
                pass
        
        # رابط دعوة من الأدمن
        else:
            link_id = context.args[0]
            if link_id in admin_invite_links:
                link_data = admin_invite_links[link_id]
                admin_id = link_data.get("admin_id")
                
                # التحقق الجديد: هل المستخدم استخدم الرابط من قبل؟
                if user.id in link_data.get("used_by", []):
                    await update.message.reply_text("⚠️ لقد قمت بالدخول لهذا الرابط مسبقًا وحصلت على النقاط.")
                elif link_data["uses"] > 0:
                    # إضافة آيدي المستخدم إلى قائمة المستخدمين الذين استخدموا الرابط
                    link_data.setdefault("used_by", []).append(user.id)
                    points[user.id] = points.get(user.id, 0) + link_data["points"]
                    link_data["uses"] -= 1
                    save_points()
                    
                    # إرسال إشعار للأدمن
                    if admin_id and admin_id != user.id:
                        total_users_used_link = len(link_data["used_by"])
                        message_to_admin = (
                            f"📣 قام المستخدم {user.id} بالدخول إلى رابط النقاط الخاص بك.\n"
                            f"عدد الأشخاص الكلي الذين دخلوا للرابط: {total_users_used_link}"
                        )
                        try:
                            await context.bot.send_message(admin_id, message_to_admin)
                        except Exception as e:
                            logger.error(f"Failed to send link entry notification to admin {admin_id}: {e}")

                    await update.message.reply_text(f"🎉 تهانينا! لقد حصلت على {link_data['points']} نقطة من رابط الدعوة. رصيدك الآن: {points[user.id]}")
                    if link_data["uses"] == 0:
                        del admin_invite_links[link_id]
                else:
                    await update.message.reply_text("⚠️ هذا الرابط تم استخدامه بالكامل.")
            else:
                await update.message.reply_text("⚠️ هذا الرابط غير صالح أو منتهي.")

    if not await check_subscription(user.id, context):
        kb = [[InlineKeyboardButton("📢 اشترك ثم اضغط تحقق", url=f"https://t.me/{CHANNELS[0].strip('@')}")],
              [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subs")]]
        await update.message.reply_text(
            "<b>⚠️ عذراً، يجب الاشتراك في القنوات المطلوبة لاستخدام البوت.</b>",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        f"مرحباً {user.first_name} 👋\nاختر نوع النشر:",
        reply_markup=main_menu_kb(user.id)
    )

# زر تحقق
async def quick_check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok = await check_subscription(q.from_user.id, context)
    if ok:
        await q.edit_message_text("✅ تم التحقق: أنت مشترك. أرسل /start للعودة للقائمة.")
    else:
        await q.edit_message_text("⚠️ ما زلت غير مشترك بكل القنوات.")

# ==================== أزرار المستخدم ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    user_points = points.get(user_id, 0)

    if q.data == "gift":
        if not is_admin(user_id) and user_points < 3:
            await q.edit_message_text(f"⚠️ يجب أن يكون لديك 3 نقاط على الأقل لنشر هدية. نقاطك الحالية: {user_points}")
            return
        
        context.user_data["type"] = "gift"
        await q.edit_message_text("📌 أرسل رابط هديتك مثل:\nhttp://t.me/nft/SnakeBox-506")
        return

    if q.data == "username":
        if not is_admin(user_id) and user_points < 1:
            await q.edit_message_text(f"⚠️ يجب أن يكون لديك نقطة واحدة على الأقل لنشر معرف. نقاطك الحالية: {user_points}")
            return
        
        context.user_data["type"] = "username"
        await q.edit_message_text("📌 أرسل المعرف ويبدأ بـ @ مثل: @FVPPV")
        return

    if q.data == "rules":
        rules_text = (
            "⚖️ <b>الشروط والأحكام</b> ⚖️\n\n"
            "~ نوافق على المُعرفات التي اعلى من 25$ + فقط ✓.\n\n"
            "- يكون المعرف على قناة فارغة مابيها معرف تواصل فقط معرف قناة المزاد "
            "مِثال - ( المزاد هنا @NOVAVIP2 ).\n\n"
            "- ارسل مُعرفك الى الزر الخاص به ( ملكية - NFT ).\n\n"
            "- عدم تضمين اي طريقة للتواصل في داخل قناة المعرف.\n\n"
            "- اذا يوجد مزاد ثاني في قناة المعرف ما ينشر مُعرفك.\n\n"
            "- للموافقة على انضمامك داخل مجموعة المزاد أرسل لقطة الشاشه "
            "توضح رصيد محفظتك مع معرف حساب."
        )
        await q.edit_message_text(rules_text, parse_mode="HTML")
        return
    
    # معالجة الأزرار الجديدة
    if q.data == "collect_points":
        await q.edit_message_text("🎁 اختر طريقة تجميع النقاط:", reply_markup=collect_points_kb())
        return

    if q.data == "invite_link":
        user_id = q.from_user.id
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        invite_link = f"https://t.me/{bot_username}?start={user_id}"
        await q.edit_message_text(f"🔗 رابط الدعوة الخاص بك:\n<code>{invite_link}</code>\n\nشارك الرابط وادعُ أصدقائك للحصول على نقطة.", parse_mode="HTML")
        return
    
    if q.data == "subscribe_for_points":
        user_id = q.from_user.id
        user_points_log = points_log.get(str(user_id), [])

        next_channel = None
        for ch in POINTS_CHANNELS:
            if ch not in user_points_log:
                next_channel = ch
                break
        
        message = ""
        keyboard_buttons = []

        if next_channel:
            message = f"✅ اشترك في القناة التالية واحصل على نقطة:\n\n📢 {next_channel}"
            keyboard_buttons.append([InlineKeyboardButton(f"اشترك في {next_channel}", url=f"https://t.me/{next_channel.strip('@')}")])
            keyboard_buttons.append([InlineKeyboardButton("✅ تحقق", callback_data="check_points_subs"), InlineKeyboardButton("➡️ التالي", callback_data="next_channel")])
        else:
            message = "🎉 تهانينا! لقد اشتركت في جميع القنوات المتاحة لتجميع النقاط."

        keyboard_buttons.append([InlineKeyboardButton("🔙 عودة للقائمة", callback_data="back_to_start")])

        await q.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard_buttons))
        return
    
    if q.data == "check_points_subs":
        user_id = q.from_user.id
        user_points_log = points_log.get(str(user_id), [])
        
        channel_to_check = None
        for ch in POINTS_CHANNELS:
            if ch not in user_points_log:
                channel_to_check = ch
                break

        if not channel_to_check:
            await q.edit_message_text("⚠️ لا توجد قنوات جديدة للحصول على نقاط منها.")
            return

        try:
            member = await context.bot.get_chat_member(channel_to_check, user_id)
            if member.status in ("member", "administrator", "creator"):
                points[user_id] = points.get(user_id, 0) + 1
                user_points_log.append(channel_to_check)
                points_log[str(user_id)] = user_points_log
                save_points_log()
                save_points()
                
                # Edit message to show the "Next" button only
                new_message_text = f"🎉 تهانينا! لقد حصلت على 1 نقطة. نقاطك الآن: {points[user_id]}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("➡️ التالي", callback_data="next_channel")],
                    [InlineKeyboardButton("🔙 عودة للقائمة", callback_data="back_to_start")]
                ])
                await q.edit_message_text(new_message_text, reply_markup=keyboard)

            else:
                await q.edit_message_text("⚠️ لم تحصل على نقاط جديدة. تأكد من الاشتراك في القناة ثم أعد المحاولة.")
        except Exception as e:
            await q.edit_message_text("❌ حدث خطأ أثناء التحقق من الاشتراك.")
            logger.error(f"Failed to check subscription for {channel_to_check}: {e}")
        return

    # New handler for the "Next" button
    if q.data == "next_channel":
        await q.answer() # Answer the callback query
        user_id = q.from_user.id
        user_points_log = points_log.get(str(user_id), [])

        # Find the next channel to display
        next_channel = None
        for ch in POINTS_CHANNELS:
            if ch not in user_points_log:
                next_channel = ch
                break

        message = ""
        keyboard_buttons = []
        if next_channel:
            message = f"✅ اشترك في القناة التالية واحصل على نقطة:\n\n📢 {next_channel}"
            keyboard_buttons.append([InlineKeyboardButton(f"اشترك في {next_channel}", url=f"https://t.me/{next_channel.strip('@')}")])
            keyboard_buttons.append([InlineKeyboardButton("✅ تحقق", callback_data="check_points_subs"), InlineKeyboardButton("➡️ التالي", callback_data="next_channel")])
        else:
            message = "🎉 تهانينا! لقد اشتركت في جميع القنوات المتاحة لتجميع النقاط."

        keyboard_buttons.append([InlineKeyboardButton("🔙 عودة للقائمة", callback_data="back_to_start")])
        
        await q.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard_buttons))
        return

    if q.data == "buy_points_with_stars":
        await q.edit_message_text("لشراء نقاط مقابل نجوم راسل المالك @NOVAVIP2")
        return
    
    if q.data == "transfer_points":
        user_points = points.get(user_id, 0)
        message_text = (
            f"🔄 تحويل النقاط\n\n"
            f"💎 رصيدك الحالي: {user_points} نقطة\n\n"
            "• أدخل عدد النقاط التي تريد تحويلها:"
        )
        context.user_data["awaiting_points_amount_transfer"] = True
        await q.edit_message_text(message_text, parse_mode="HTML")
        return
        
    if q.data == "back_to_start":
        await q.edit_message_text(
            f"مرحباً {q.from_user.first_name} 👋\nاختر نوع النشر:",
            reply_markup=main_menu_kb(user_id)
        )
        return
    
    if q.data == "my_points":
        user_points = points.get(user_id, 0)
        await q.answer(text=f"نقاطك الحالية: {user_points}", show_alert=True)
        return

# ==================== استقبال رسائل المستخدم ====================
async def handle_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != "private":
        return
    user = update.effective_user
    if not user or user.id in banned_users:
        return

    if not await check_subscription(user.id, context):
        await update.message.reply_text("⚠️ اشترك أولاً ثم أعد /start.")
        return

    text = (update.message.text or "").strip()
    user_id = user.id

    if context.user_data.get("awaiting_points_amount_transfer"):
        try:
            transfer_amount = int(text)
            sender_points = points.get(user_id, 0)
            if transfer_amount < 10:
                await update.message.reply_text("⚠️ الحد الأدنى للتحويل هو 10 نقاط.")
            elif sender_points < transfer_amount:
                await update.message.reply_text("⚠️ نقاطك الحالية غير كافية لإتمام عملية التحويل.")
            else:
                context.user_data["transfer_amount"] = transfer_amount
                context.user_data["awaiting_points_amount_transfer"] = False
                context.user_data["awaiting_recipient_id"] = True
                await update.message.reply_text("✅ تم. الآن، أرسل آيدي المستخدم المستلم (أرقام فقط).")
            return
        except ValueError:
            await update.message.reply_text("❌ خطأ: يرجى إدخال عدد صحيح للنقاط.")
            context.user_data["awaiting_points_amount_transfer"] = False
            return

    if context.user_data.get("awaiting_recipient_id"):
        try:
            recipient_id = int(text)
            transfer_amount = context.user_data.get("transfer_amount")
            received_amount = int(transfer_amount * 0.9)
            points[user_id] -= transfer_amount
            points[recipient_id] = points.get(recipient_id, 0) + received_amount
            save_points()

            await update.message.reply_text(
                f"✅ تم التحويل بنجاح!\n"
                f"• تم خصم {transfer_amount} نقطة من حسابك.\n"
                f"• رصيدك الحالي: {points[user_id]} نقطة."
            )
            try:
                await context.bot.send_message(
                    recipient_id,
                    f"🎉 تهانينا! لقد استلمت {received_amount} نقطة من المستخدم {user.mention_html()}.\n"
                    f"• رصيدك الحالي: {points.get(recipient_id, 0)} نقطة.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send points received message to {recipient_id}: {e}")

        except (ValueError, IndexError):
            await update.message.reply_text("❌ خطأ: يرجى التأكد من إدخال آيدي صحيح (أرقام فقط).")
        
        context.user_data.pop("awaiting_recipient_id", None)
        context.user_data.pop("transfer_amount", None)
        return
        
    req_type = context.user_data.get("type")
    global total_requests

    if is_admin(user.id) and req_type in ["gift", "username"]:
        if req_type == "gift":
            msg = f'🎁 مزاد الفراعنة - <a href="{text}">Click</a>\nرجاء حط سعرك فقط مثل (1ton/1as)'
        else:
            msg = f'معرف جديد ( {text} )\nزايد بالتدريج حط سعرك تون او دولار او اسيا ممنوع الكلام بالمحادثه \nقناه مزاد @FVPPV'

        sent = await context.bot.send_message(
            AUCTION_CHANNEL,
            msg,
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ تم نشر طلبك مباشرة (أنت أدمن).\n🔗 الرابط: https://t.me/{AUCTION_CHANNEL.strip('@')}/{sent.message_id}")
        context.user_data["type"] = None
        return

    if req_type == "gift":
        if not ("t.me/nft/" in text):
            await update.message.reply_text("⚠️ الرابط غير صحيح. يجب أن يحتوي t.me/nft/")
            return
        
        user_id = user.id
        if points.get(user_id, 0) >= 3:
            points[user_id] -= 3
            save_points()
            req_id = str(update.message.message_id)
            pending_requests[req_id] = {"user_id": user_id, "type": "gift", "content": text}
            kb = [[InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{req_id}"),
                   InlineKeyboardButton("❌ رفض", callback_data=f"reject_{req_id}")]]
            await context.bot.send_message(
                ADMIN_GROUP_ID,
                f"📥 طلب (هدية) من {user.mention_html()}:\n{text}",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
            await update.message.reply_text(f"✅ تم خصم 3 من نقاطك. تم إرسال طلبك للإدارة.")
            context.user_data["type"] = None
            total_requests += 1
            return
        else:
            await update.message.reply_text("⚠️ يجب أن يكون لديك 3 نقاط على الأقل لنشر هدية. نقاطك غير كافية.")
            return

    if req_type == "username":
        user_id = user.id
        if not text.startswith("@"):
            await update.message.reply_text("⚠️ المعرّف يجب أن يبدأ بـ @")
            return
        
        points[user_id] = points.get(user_id, 0) - 1
        save_points()

        req_id = str(update.message.message_id)
        pending_requests[req_id] = {"user_id": user.id, "type": "username", "content": text}
        kb = [[InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{req_id}"),
               InlineKeyboardButton("❌ رفض", callback_data=f"reject_{req_id}")]]
        await context.bot.send_message(
            ADMIN_GROUP_ID,
            f"📥 طلب (معرّف) من {user.mention_html()}:\n{text}",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ تم خصم نقطة واحدة من نقاطك. تم إرسال طلبك للإدارة.")
        context.user_data["type"] = None
        total_requests += 1
        return

# ==================== موافقة/رفض الطلبات ====================
async def admin_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if not (data.startswith("approve_") or data.startswith("reject_")):
        return

    req_id = data.split("_", 1)[1]
    req = pending_requests.get(req_id)
    if not req:
        await q.edit_message_text("⚠️ الطلب غير موجود.")
        return

    user_id = req["user_id"]

    if data.startswith("approve_"):
        try:
            if req["type"] == "gift":
                msg = f'🎁 مزاد الفراعنة - <a href="{req["content"]}">Click</a>\nرجاء حط سعرك فقط مثل (1ton/1as)'
            else:
                username = req["content"]
                msg = f'معرف جديد ( {username} )\nزايد بالتدريج حط سعرك تون او دولار او اسيا ممنوع الكلام بالمحادثه \nقناه مزاد @FVPPV'

            sent = await context.bot.send_message(
                AUCTION_CHANNEL,
                msg,
                parse_mode="HTML"
            )

            link = f"https://t.me/{AUCTION_CHANNEL.strip('@')}/{sent.message_id}"
            await context.bot.send_message(user_id, f"✅ تمت الموافقة على طلبك.\n🔗 الرابط: {link}")
            await q.edit_message_text("✅ تمت الموافقة على الطلب ونُشر.")
            del pending_requests[req_id]
        except Exception as e:
            await q.edit_message_text(f"⚠️ خطأ أثناء النشر: {e}")
    else:
        await context.bot.send_message(user_id, "❌ تم رفض طلبك.")
        await q.edit_message_text("❌ تم رفض الطلب.")
        del pending_requests[req_id]

# ==================== لوحة الأدمن ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_admin(update.effective_user.id):
        return
    kb = [
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="ban_user"),
         InlineKeyboardButton("✅ إلغاء حظر", callback_data="unban_user")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats"),
         InlineKeyboardButton("✉️ إذاعة", callback_data="broadcast")],
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel"),
         InlineKeyboardButton("➖ حذف قناة", callback_data="remove_channel")],
        [InlineKeyboardButton("📋 عرض القنوات", callback_data="list_channels"),
         InlineKeyboardButton("🎁 صنع رابط نقاط", callback_data="create_points_link")],
        [InlineKeyboardButton("➕ إضافة قنوات للنقاط", callback_data="add_points_channel"),
         InlineKeyboardButton("➖ حذف قناة من قنوات النقاط", callback_data="remove_points_channel")]
    ]
    await update.message.reply_text("👨‍💻 لوحة تحكم الأدمن", reply_markup=InlineKeyboardMarkup(kb))

async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    data = q.data
    if data == "stats":
        await q.edit_message_text(f"📊 الإحصائيات:\n👥 المستخدمون: {len(all_users)}\n📥 الطلبات: {total_requests}")
    elif data == "broadcast":
        context.user_data["awaiting_broadcast"] = True
        await q.edit_message_text("✉️ أرسل الرسالة للاذاعة.")
    elif data == "ban_user":
        context.user_data["awaiting_ban"] = True
        await q.edit_message_text("🚫 أرسل آيدي المستخدم لحظره.")
    elif data == "unban_user":
        context.user_data["awaiting_unban"] = True
        await q.edit_message_text("✅ أرسل آيدي المستخدم لإلغاء الحظر.")
    elif data == "add_channel":
        context.user_data["awaiting_add_channel"] = True
        await q.edit_message_text("📌 أرسل يوزر القناة مع @ مثل: @MyChannel")
    elif data == "remove_channel":
        if not CHANNELS:
            await q.edit_message_text("⚠️ لا توجد قنوات.")
            return
        kb = [[InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmch_{ch}")] for ch in CHANNELS]
        await q.edit_message_text("اختر القناة للحذف:", reply_markup=InlineKeyboardMarkup(kb))
    elif data == "list_channels":
        if not CHANNELS:
            await q.edit_message_text("⚠️ لا توجد قنوات.")
            return
        await q.edit_message_text("📋 القنوات:\n" + "\n".join(f"- {ch}" for ch in CHANNELS))
    elif data == "create_points_link":
        context.user_data["awaiting_points_amount"] = True
        await q.edit_message_text("🎁 أرسل عدد النقاط التي سيمنحها الرابط.")
    elif data == "add_points_channel":
        context.user_data["awaiting_add_points_channel"] = True
        await q.edit_message_text("📌 أرسل يوزر القناة التي سيتم منح النقاط منها.")
    elif data == "remove_points_channel":
        context.user_data["awaiting_remove_points_channel"] = True
        await q.edit_message_text("📌 أرسل يوزر القناة التي تريد إزالتها من قنوات النقاط.")


# حذف قناة
async def remove_channel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    ch = q.data.replace("rmch_", "", 1)
    try:
        CHANNELS.remove(ch)
        save_channels()
        await q.edit_message_text("✅ تم حذف القناة.")
    except ValueError:
        await q.edit_message_text("⚠️ القناة غير موجودة.")

# استقبال رسائل الأدمن
async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not is_admin(update.effective_user.id):
        return
    text = (update.message.text or "").strip()

    if context.user_data.get("awaiting_broadcast"):
        ok = fail = 0
        for uid in list(all_users):
            try:
                await context.bot.send_message(uid, text)
                ok += 1
                await asyncio.sleep(0.05)  # منع FloodWait
            except Exception:
                fail += 1
        await update.message.reply_text(f"📢 إذاعة تمت.\n✅ ناجحة: {ok}\n❌ فشلت: {fail}")
        context.user_data["awaiting_broadcast"] = False

    elif context.user_data.get("awaiting_ban"):
        try:
            uid = int(text)
            banned_users.add(uid)
            await update.message.reply_text("🚫 تم الحظر.")
        except:
            await update.message.reply_text("❌ آيدي غير صالح.")
        context.user_data["awaiting_ban"] = False

    elif context.user_data.get("awaiting_unban"):
        try:
            uid = int(text)
            banned_users.discard(uid)
            await update.message.reply_text("✅ تم إلغاء الحظر.")
        except:
            await update.message.reply_text("❌ آيدي غير صالح.")
        context.user_data["awaiting_unban"] = False

    elif context.user_data.get("awaiting_add_channel"):
        if not text.startswith("@"):
            await update.message.reply_text("⚠️ صيغة غير صحيحة. أرسل يوزر القناة مع @ مثل: @MyChannel")
            context.user_data["awaiting_add_channel"] = False
            return
        try:
            chat = await context.bot.get_chat(text)
            member = await context.bot.get_chat_member(text, (await context.bot.get_me()).id)
            if member.status not in ("administrator", "creator"):
                await update.message.reply_text("❌ لازم ترفع البوت كمدير بالقناة أولاً.")
            else:
                if text not in CHANNELS:
                    CHANNELS.append(text)
                    save_channels()
                    await update.message.reply_text(f"✅ تمت إضافة القناة: {text}")
                else:
                    await update.message.reply_text("⚠️ القناة مضافة من قبل.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")
        context.user_data["awaiting_add_channel"] = False
    
    # معالجة إنشاء رابط النقاط
    elif context.user_data.get("awaiting_points_amount"):
        try:
            points_amount = int(text)
            context.user_data["points_amount"] = points_amount
            context.user_data["awaiting_points_amount"] = False
            context.user_data["awaiting_link_limit"] = True
            await update.message.reply_text("🔗 أرسل عدد الأعضاء الذين يمكنهم استخدام الرابط.")
        except ValueError:
            await update.message.reply_text("❌ يجب إرسال عدد صحيح للنقاط.")
    
    elif context.user_data.get("awaiting_link_limit"):
        try:
            link_limit = int(text)
            points_amount = context.user_data["points_amount"]
            link_id = str(uuid.uuid4())
            admin_invite_links[link_id] = {"points": points_amount, "uses": link_limit, "used_by": [], "admin_id": update.effective_user.id}
            bot_username = (await context.bot.get_me()).username
            invite_link = f"https://t.me/{bot_username}?start={link_id}"
            await update.message.reply_text(f"✅ تم إنشاء الرابط بنجاح:\n<a href='{invite_link}'>{invite_link}</a>\n\nعدد النقاط: {points_amount}\nعدد مرات الاستخدام: {link_limit}", parse_mode="HTML", disable_web_page_preview=True)
            context.user_data.pop("awaiting_link_limit", None)
            context.user_data.pop("points_amount", None)
        except ValueError:
            await update.message.reply_text("❌ يجب إرسال عدد صحيح لعدد الأعضاء.")

    elif context.user_data.get("awaiting_add_points_channel"):
        if not text.startswith("@"):
            await update.message.reply_text("⚠️ صيغة غير صحيحة. أرسل يوزر القناة مع @ مثل: @MyChannel")
            context.user_data["awaiting_add_points_channel"] = False
            return
        
        try:
            chat = await context.bot.get_chat(text)
            member = await context.bot.get_chat_member(text, (await context.bot.get_me()).id)
            if member.status not in ("administrator", "creator"):
                await update.message.reply_text("❌ يجب أن يكون البوت مديرًا في القناة لإضافتها.")
            else:
                if text not in POINTS_CHANNELS:
                    POINTS_CHANNELS.append(text)
                    save_points_channels()
                    await update.message.reply_text(f"✅ تمت إضافة القناة بنجاح: {text}")
                else:
                    await update.message.reply_text("⚠️ القناة مضافة مسبقًا.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")

        context.user_data["awaiting_add_points_channel"] = False

    elif context.user_data.get("awaiting_remove_points_channel"):
        text = text.strip()
        if not text.startswith("@"):
            await update.message.reply_text("⚠️ صيغة غير صحيحة. يرجى إرسال يوزر القناة الصحيح مع @.")
        elif text in POINTS_CHANNELS:
            POINTS_CHANNELS.remove(text)
            save_points_channels()
            await update.message.reply_text(f"✅ تم حذف القناة {text} بنجاح من قنوات النقاط.")
        else:
            await update.message.reply_text(f"⚠️ القناة {text} ليست ضمن قنوات النقاط.")
        context.user_data["awaiting_remove_points_channel"] = False


# ==================== تشغيل البوت ====================
def run():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(quick_check_subscription, pattern="^check_subs$"))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(gift|username|rules|collect_points|invite_link|back_to_start|subscribe_for_points|check_points_subs|buy_points_with_stars|transfer_points|next_channel|my_points)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_messages), group=2)
    app.add_handler(CallbackQueryHandler(admin_review_callback, pattern="^(approve_|reject_).+"))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_admin_buttons,
                                         pattern="^(ban_user|unban_user|broadcast|stats|add_channel|remove_channel|list_channels|create_points_link|add_points_channel|remove_points_channel)$"))
    app.add_handler(CallbackQueryHandler(remove_channel_cb, pattern="^rmch_.+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_messages), group=1)

    print("🚀 البوت اشتغل ...")
    app.run_polling()

if __name__ == "__main__":
    run()
