import asyncio
import time
import os
import json
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    ChannelParticipantsKicked,
    ChannelParticipantsBanned,
    ChatBannedRights
)

# ================= CONFIGURATION =================
API_ID = 20137104                  # Apna API_ID dalein
API_HASH = "1209338eedc55ab701dd2e9d353c05ad"    # Apna API_HASH dalein
BOT_TOKEN = "9179266114:AAEv7ldjOlWMi6WlIjEDhL-_Rma_BknohPY"  # @BotFather se liya hua Bot Token

OWNER_IDS = [8244493463]           # Sirf Authorized Owners
WHITELIST_FILE = "whitelist.json"  # Permanent banned users ko bachane ke liye file
# =================================================

bot = TelegramClient("cleaner_pro_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Running tasks ko track karne ke liye (taaki /cancel kaam kare)
ACTIVE_TASKS = {}

NO_RESTRICTIONS = ChatBannedRights(
    until_date=None,
    view_messages=False,
    send_messages=False,
    send_media=False,
    send_stickers=False,
    send_gifs=False,
    send_games=False,
    send_inline=False,
    embed_links=False,
    send_polls=False,
    change_info=False,
    invite_users=False,
    pin_messages=False
)

# --- Whitelist Helper Functions ---
def load_whitelist():
    if not os.path.exists(WHITELIST_FILE):
        return {}
    try:
        with open(WHITELIST_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_whitelist(data):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_chat_whitelist(chat_id):
    data = load_whitelist()
    return set(data.get(str(chat_id), []))

# --- Security Check ---
async def is_authorized(event):
    if event.sender_id in OWNER_IDS:
        return True
    try:
        perms = await bot.get_permissions(event.chat_id, event.sender_id)
        return perms.is_admin
    except Exception:
        return False

def format_user_line(index, user):
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Deleted Account"
    username = f"@{user.username}" if user.username else "No Username"
    return f"{index}. {name} | {username} | ID: {user.id}"

# --- Target User Nikalne Ka Helper (Reply ya ID/Username se) ---
async def extract_target_user(event):
    args = event.raw_text.split(maxsplit=1)
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        return await bot.get_entity(reply_msg.sender_id)
    elif len(args) > 1:
        target = args[1].strip()
        if target.isdigit():
            return await bot.get_entity(int(target))
        return await bot.get_entity(target)
    return None

# --- Core Bulk Processor ---
async def process_users(event, mode="unban"):
    chat_id = event.chat_id
    chat = await event.get_chat()
    p_filter = ChannelParticipantsKicked if mode == "unban" else ChannelParticipantsBanned
    action_text = "Unbanning" if mode == "unban" else "Unmuting"
    whitelist = get_chat_whitelist(chat_id) if mode == "unban" else set()

    ACTIVE_TASKS[chat_id] = True
    status_msg = await event.reply(f"🔍 **{action_text} ke liye users fetch kar raha hoon...**")

    users_list = []
    skipped_whitelist = 0
    async for user in bot.iter_participants(chat, filter=p_filter):
        if user.id in whitelist:
            skipped_whitelist += 1
            continue
        users_list.append(user)

    total = len(users_list)
    if total == 0:
        msg = f"✅ Koi bhi {'banned' if mode == 'unban' else 'muted'} user nahi mila!"
        if skipped_whitelist > 0:
            msg += f"\n🛡 (Whitelisted skipped: `{skipped_whitelist}`)"
        await status_msg.edit(msg)
        ACTIVE_TASKS.pop(chat_id, None)
        return [], 0, skipped_whitelist

    await status_msg.edit(
        f"⚡ Total **{total}** users mile hain. {action_text} shuru...\n"
        f"🛑 Rokne ke liye `/cancel` bhejein."
    )

    processed_users = []
    failed = 0
    start_time = time.time()

    for index, user in enumerate(users_list, start=1):
        # Check if user sent /cancel
        if not ACTIVE_TASKS.get(chat_id, False):
            await status_msg.edit(f"🛑 **Process Cancelled!** Ab tak `{len(processed_users)}` users process huye.")
            return processed_users, failed, skipped_whitelist

        try:
            if mode == "unban":
                await bot.edit_permissions(chat, user.id, view_messages=True)
            else:
                await bot.edit_permissions(chat, user.id, **NO_RESTRICTIONS.__dict__)
            processed_users.append(user)
            await asyncio.sleep(0.35)
        except FloodWaitError as e:
            await status_msg.edit(f"⏳ **FloodWait:** {e.seconds}s ruk rahe hain... ({len(processed_users)}/{total})")
            await asyncio.sleep(e.seconds + 1)
            try:
                if mode == "unban":
                    await bot.edit_permissions(chat, user.id, view_messages=True)
                else:
                    await bot.edit_permissions(chat, user.id, **NO_RESTRICTIONS.__dict__)
                processed_users.append(user)
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if index % 15 == 0 or index == total:
            elapsed = round(time.time() - start_time, 1)
            await status_msg.edit(
                f"🚀 **{action_text} Progress...**\n"
                f"📊 Progress: `{index}/{total}`\n"
                f"✅ Done: `{len(processed_users)}` | ❌ Failed: `{failed}`\n"
                f"⏱ Time: `{elapsed}s`"
            )

    ACTIVE_TASKS.pop(chat_id, None)
    return processed_users, failed, skipped_whitelist

# --- Report Generator ---
async def send_single_report(event, users, failed, skipped, label):
    total_done = len(users)
    if total_done == 0 and failed == 0:
        return

    summary = (
        f"📊 **{label} Summary Report:**\n"
        f"✅ **Total {label}:** `{total_done}`\n"
        f"❌ **Failed:** `{failed}`\n"
    )
    if skipped > 0:
        summary += f"🛡 **Whitelist Skipped:** `{skipped}`\n"

    if total_done == 0:
        await event.reply(summary)
        return

    if total_done <= 20:
        user_links = "\n".join(
            [f"{i}. [{u.first_name or 'User'}](tg://user?id={u.id}) (`{u.id}`)" for i, u in enumerate(users, start=1)]
        )
        await event.reply(f"{summary}\n📋 **List ({total_done}):**\n{user_links}")
    else:
        filename = f"{label.lower()}_report_{event.chat_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"=== {label.upper()} REPORT (Total: {total_done} | Failed: {failed}) ===\n\n")
            f.write("\n".join([format_user_line(i, u) for i, u in enumerate(users, start=1)]))

        await event.reply(f"{summary}\n📄 Sabhi `{total_done}` users ki poori list niche file mein hai:", file=filename)
        if os.path.exists(filename):
            os.remove(filename)

# ==================== COMMAND HANDLERS ====================

# 1. /help Command
@bot.on(events.NewMessage(pattern=r"^/help$"))
async def help_handler(event):
    if not await is_authorized(event):
        return
    help_text = (
        "🤖 **Group Cleaner Pro - Commands Guide**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 `/status` — Banned aur Muted users ka count dekhein\n"
        "🔓 `/unbanall` — Sabhi banned users ko unban karein\n"
        "🔊 `/unmuteall` — Sabhi muted users ko unmute karein\n"
        "🔥 `/cleanall` — Ek saath Unban + Unmute dono karein\n"
        "🛑 `/cancel` — Chalte huye process ko beech mein rokein\n\n"
        "👤 **Single User Commands (Reply ya ID/Username):**\n"
        "• `/unban <id/@user>` — Kisi ek ko unban karein\n"
        "• `/unmute <id/@user>` — Kisi ek ko unmute karein\n\n"
        "🛡 **Whitelist (Permanent Ban Protection):**\n"
        "• `/whitelist <id>` — Is user ko `/unbanall` unban nahi karega\n"
        "• `/unwhitelist <id>` — Whitelist se hatayein\n"
        "• `/wlist` — Whitelisted IDs ki list dekhein"
    )
    await event.reply(help_text)

# 2. /status Command (With Interactive Buttons)
@bot.on(events.NewMessage(pattern=r"^/status$"))
async def status_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    msg = await event.reply("📊 Group scan kar raha hoon...")
    chat = await event.get_chat()
    banned = [u async for u in bot.iter_participants(chat, filter=ChannelParticipantsKicked)]
    muted = [u async for u in bot.iter_participants(chat, filter=ChannelParticipantsBanned)]
    w_count = len(get_chat_whitelist(event.chat_id))

    buttons = [
        [
            Button.inline("🔓 Unban All", b"act_unbanall"),
            Button.inline("🔊 Unmute All", b"act_unmuteall")
        ],
        [Button.inline("🔥 Clean All (Both)", b"act_cleanall")]
    ]

    await msg.edit(
        f"📋 **Current Group Status:**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚫 **Banned Users:** `{len(banned)}`\n"
        f"🔇 **Muted Users:** `{len(muted)}`\n"
        f"🛡 **Whitelisted (Protected):** `{w_count}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Neeche button dabakar ya command bhejkar action lein:",
        buttons=buttons
    )

# Button Click Handler for /status
@bot.on(events.CallbackQuery(pattern=b"act_(unbanall|unmuteall|cleanall)"))
async def callback_handler(event):
    if not await is_authorized(event):
        await event.answer("❌ Sirf Admins hi yeh button use kar sakte hain!", alert=True)
        return

    action = event.data.decode().split("_")[1]
    await event.answer(f"Starting {action}...")
    await event.delete()

    if action == "unbanall":
        unbanned, failed, skipped = await process_users(event, mode="unban")
        await send_single_report(event, unbanned, failed, skipped, "Unbanned")
    elif action == "unmuteall":
        unmuted, failed, skipped = await process_users(event, mode="unmute")
        await send_single_report(event, unmuted, failed, skipped, "Unmuted")
    elif action == "cleanall":
        await run_cleanall(event)

# 3. /cancel Command
@bot.on(events.NewMessage(pattern=r"^/cancel$"))
async def cancel_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    if ACTIVE_TASKS.get(event.chat_id):
        ACTIVE_TASKS[event.chat_id] = False
        await event.reply("⏳ Process ko roka ja raha hai...")
    else:
        await event.reply("ℹ️ Abhi koi process nahi chal raha hai.")

# 4. /unbanall Command
@bot.on(events.NewMessage(pattern=r"^/unbanall$"))
async def unbanall_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    unbanned, failed, skipped = await process_users(event, mode="unban")
    await send_single_report(event, unbanned, failed, skipped, "Unbanned")

# 5. /unmuteall Command
@bot.on(events.NewMessage(pattern=r"^/unmuteall$"))
async def unmuteall_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    unmuted, failed, skipped = await process_users(event, mode="unmute")
    await send_single_report(event, unmuted, failed, skipped, "Unmuted")

# 6. /cleanall Command
async def run_cleanall(event):
    await event.reply("🔥 **Full Cleanup Shuru!** Pehle Unban hoga, phir Unmute...")
    unbanned, unban_failed, skipped = await process_users(event, mode="unban")
    unmuted, unmute_failed, _ = await process_users(event, mode="unmute")

    total_all = len(unbanned) + len(unmuted)
    summary = (
        f"🏆 **FINAL CLEANUP REPORT**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔓 **Total Unbanned:** `{len(unbanned)}` (Failed: `{unban_failed}`)\n"
        f"🔊 **Total Unmuted:** `{len(unmuted)}` (Failed: `{unmute_failed}`)\n"
        f"🛡 **Whitelist Skipped:** `{skipped}`\n"
        f"📈 **Grand Total Processed:** `{total_all}`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    if total_all == 0:
        await event.reply(f"{summary}\n\n✅ Group pehle se bilkul clean hai!")
        return

    if total_all <= 20:
        text = summary
        if unbanned:
            b_list = "\n".join([f"{i}. [{u.first_name or 'User'}](tg://user?id={u.id}) (`{u.id}`)" for i, u in enumerate(unbanned, 1)])
            text += f"\n\n🔓 **Unbanned Users ({len(unbanned)}):**\n{b_list}"
        if unmuted:
            m_list = "\n".join([f"{i}. [{u.first_name or 'User'}](tg://user?id={u.id}) (`{u.id}`)" for i, u in enumerate(unmuted, 1)])
            text += f"\n\n🔊 **Unmuted Users ({len(unmuted)}):**\n{m_list}"
        await event.reply(text)
    else:
        filename = f"full_cleanup_report_{event.chat_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=== FULL CLEANUP REPORT ===\n")
            f.write(f"Total Unbanned: {len(unbanned)} (Failed: {unban_failed})\n")
            f.write(f"Total Unmuted:  {len(unmuted)} (Failed: {unmute_failed})\n")
            f.write(f"Whitelist Skipped: {skipped}\n")
            f.write("=" * 40 + "\n\n")

            f.write(f"--- UNBANNED USERS ({len(unbanned)}) ---\n")
            f.write("\n".join([format_user_line(i, u) for i, u in enumerate(unbanned, 1)]) + "\n\n" if unbanned else "None\n\n")

            f.write(f"--- UNMUTED USERS ({len(unmuted)}) ---\n")
            f.write("\n".join([format_user_line(i, u) for i, u in enumerate(unmuted, 1)]) + "\n" if unmuted else "None\n")

        await event.reply(f"{summary}\n\n📄 Dono lists (Unbanned + Unmuted) niche file mein hain:", file=filename)
        if os.path.exists(filename):
            os.remove(filename)

@bot.on(events.NewMessage(pattern=r"^/cleanall$"))
async def cleanall_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    await run_cleanall(event)

# 7. Single /unban & /unmute Commands
@bot.on(events.NewMessage(pattern=r"^/unban(?:\s+|$)"))
async def single_unban_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    try:
        user = await extract_target_user(event)
        if not user:
            await event.reply("⚠️ Kisi message par reply karein ya ID/Username dein: `/unban 123456789`")
            return
        await bot.edit_permissions(event.chat_id, user.id, view_messages=True)
        await event.reply(f"🔓 [{user.first_name}](tg://user?id={user.id}) (`{user.id}`) ko unban kar diya gaya hai.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")

@bot.on(events.NewMessage(pattern=r"^/unmute(?:\s+|$)"))
async def single_unmute_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    try:
        user = await extract_target_user(event)
        if not user:
            await event.reply("⚠️ Kisi message par reply karein ya ID/Username dein: `/unmute 123456789`")
            return
        await bot.edit_permissions(event.chat_id, user.id, **NO_RESTRICTIONS.__dict__)
        await event.reply(f"🔊 [{user.first_name}](tg://user?id={user.id}) (`{user.id}`) ko unmute kar diya gaya hai.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")

# 8. Whitelist Management Commands
@bot.on(events.NewMessage(pattern=r"^/whitelist(?:\s+|$)"))
async def add_whitelist_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    try:
        user = await extract_target_user(event)
        if not user:
            await event.reply("⚠️ User ID dein ya message par reply karein: `/whitelist 123456789`")
            return
        data = load_whitelist()
        cid = str(event.chat_id)
        w_list = set(data.get(cid, []))
        w_list.add(user.id)
        data[cid] = list(w_list)
        save_whitelist(data)
        await event.reply(f"🛡 `{user.id}` ({user.first_name}) ko **Whitelist** mein add kar diya gaya hai. `/unbanall` inhe unban nahi karega.")
    except Exception as e:
        await event.reply(f"❌ Error: `{e}`")

@bot.on(events.NewMessage(pattern=r"^/unwhitelist(?:\s+|$)"))
async def rem_whitelist_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    args = event.raw_text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await event.reply("⚠️ Numeric User ID dein: `/unwhitelist 123456789`")
        return
    uid = int(args[1].strip())
    data = load_whitelist()
    cid = str(event.chat_id)
    w_list = set(data.get(cid, []))
    if uid in w_list:
        w_list.remove(uid)
        data[cid] = list(w_list)
        save_whitelist(data)
        await event.reply(f"✅ `{uid}` ko Whitelist se hata diya gaya hai.")
    else:
        await event.reply(f"ℹ️ `{uid}` Whitelist mein nahi tha.")

@bot.on(events.NewMessage(pattern=r"^/wlist$"))
async def show_whitelist_handler(event):
    if event.is_private or not await is_authorized(event):
        return
    w_list = get_chat_whitelist(event.chat_id)
    if not w_list:
        await event.reply("🛡 Is group ki Whitelist abhi khaali hai.")
        return
    formatted = "\n".join([f"• `{uid}`" for uid in w_list])
    await event.reply(f"🛡 **Whitelisted User IDs ({len(w_list)}):**\n{formatted}")

print("Group Cleaner Pro Bot active hai...")
bot.run_until_disconnected()
