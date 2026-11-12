
import asyncio
import time
import os
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetParticipantsRequest, EditBannedRequest
from telethon.tl.types import (
    ChannelParticipantsKicked,
    ChannelParticipantsBanned,
    ChatBannedRights
)

# ================= CONFIGURATION =================
API_ID = 20137104                  # my.telegram.org se apna API_ID dalein
API_HASH = "1209338eedc55ab701dd2e9d353c05ad"    # my.telegram.org se apna API_HASH dalein
PHONE = "+919389968516"            # Apna Admin Telegram Number (+91 ke saath)

ACTION_DELAY = 1.2                 # Har user ke baad delay (seconds) - FloodWait se bachne ke liye
# =================================================

client = TelegramClient("admin_cleaner_final", API_ID, API_HASH)
CANCEL_FLAG = {}

# Saari restrictions False = Full Unban & Full Unmute
UNBAN_UNMUTE_RIGHTS = ChatBannedRights(
    until_date=0,
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

# Raw Pagination se SAARE users fetch karne ka function (No 200 limit)
async def fetch_all_by_filter(chat, p_filter):
    all_users = []
    offset = 0
    limit = 200

    while True:
        try:
            result = await client(GetParticipantsRequest(
                channel=chat,
                filter=p_filter,
                offset=offset,
                limit=limit,
                hash=0
            ))
            if not result.users:
                break
            all_users.extend(result.users)
            offset += len(result.users)
            if len(result.users) < limit:
                break
            await asyncio.sleep(1.0)  # Fetch karte waqt bhi safe delay
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
        except Exception as err:
            print(f"Fetch error: {err}")
            break

    # Duplicate IDs hatana
    unique_users = {}
    for u in all_users:
        unique_users[u.id] = u
    return list(unique_users.values())

# Exact Banned aur Muted list alag-alag nikaalna
async def get_exact_banned_and_muted(chat):
    banned_users = await fetch_all_by_filter(chat, ChannelParticipantsKicked(q=""))
    banned_ids = {u.id for u in banned_users}

    restricted_raw = await fetch_all_by_filter(chat, ChannelParticipantsBanned(q=""))
    muted_users = [u for u in restricted_raw if u.id not in banned_ids]

    return banned_users, muted_users

# Single User par Raw EditBannedRequest lagana with Auto FloodWait Retry
async def execute_unban_or_unmute(chat, user):
    while True:
        try:
            await client(EditBannedRequest(
                channel=chat,
                participant=user.id,
                banned_rights=UNBAN_UNMUTE_RIGHTS
            ))
            return True, None
        except FloodWaitError as e:
            print(f"[FloodWait] {e.seconds}s ruk rahe hain...")
            await asyncio.sleep(e.seconds + 2)
        except Exception as err:
            return False, str(err)

# Bulk Runner
async def run_bulk_action(event, chat, users_list, label):
    chat_id = chat.id
    CANCEL_FLAG[chat_id] = False
    total = len(users_list)
    done = 0
    failed = 0
    report_lines = []
    last_edit_time = time.time()

    for idx, user in enumerate(users_list, start=1):
        if CANCEL_FLAG.get(chat_id):
            await event.edit(f"🛑 **{label} Cancelled!** `{done}/{total}` complete huye the.")
            break

        ok, err = await execute_unban_or_unmute(chat, user)
        if ok:
            done += 1
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Deleted Account"
            uname = f"@{user.username}" if user.username else "No Username"
            report_lines.append(f"{done}. {name} | {uname} | ID: {user.id}")
        else:
            failed += 1
            print(f"Failed for {user.id}: {err}")

        # Har 12 seconds mein hi message edit karega (Edit par FloodWait se bachne ke liye)
        if time.time() - last_edit_time >= 12 or idx == total:
            try:
                await event.edit(
                    f"⚙️ **{label} Chal Raha Hai...**\n"
                    f"📊 Progress: `{idx}/{total}`\n"
                    f"✅ Done: `{done}` | ❌ Failed: `{failed}`\n"
                    f"🛑 Rokne ke liye `.cancel` likhein"
                )
                last_edit_time = time.time()
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                pass

        # Har user ke baad safe await delay
        await asyncio.sleep(ACTION_DELAY)

    return done, failed, report_lines

# ==================== COMMANDS ====================

# 1. .status — Exact Count
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.status$"))
async def status_cmd(event):
    if event.is_private:
        return
    await event.edit("🔍 **Poora group scan ho raha hai (Wait karein)...**")
    chat = await event.get_chat()
    banned, muted = await get_exact_banned_and_muted(chat)

    await event.edit(
        f"📊 **EXACT GROUP STATUS**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚫 **Total Banned:** `{len(banned)}`\n"
        f"🔇 **Total Muted:** `{len(muted)}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Commands: `.unbanall` | `.unmuteall` | `.cleanall`"
    )

# 2. .cancel — Process Rokne Ke Liye
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cancel$"))
async def cancel_cmd(event):
    if event.is_private:
        return
    CANCEL_FLAG[event.chat_id] = True
    await event.edit("⏳ **Process roka ja raha hai...**")

# 3. .unbanall — Sirf Sabko Unban
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unbanall$"))
async def unbanall_cmd(event):
    if event.is_private:
        return
    chat = await event.get_chat()
    await event.edit("🔍 **Sabhi Banned users fetch ho rahe hain...**")
    banned, _ = await get_exact_banned_and_muted(chat)

    if not banned:
        await event.edit("✅ Koi bhi Banned user nahi hai!")
        return

    done, failed, lines = await run_bulk_action(event, chat, banned, "Unbanning")
    await event.edit(f"✅ **Unban Complete!**\n🔓 Total Unbanned: `{done}` | ❌ Failed: `{failed}`")
    await send_report_to_saved(chat, "Unbanned", done, failed, lines)

# 4. .unmuteall — Sirf Sabko Unmute
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.unmuteall$"))
async def unmuteall_cmd(event):
    if event.is_private:
        return
    chat = await event.get_chat()
    await event.edit("🔍 **Sabhi Muted users fetch ho rahe hain...**")
    _, muted = await get_exact_banned_and_muted(chat)

    if not muted:
        await event.edit("✅ Koi bhi Muted user nahi hai!")
        return

    done, failed, lines = await run_bulk_action(event, chat, muted, "Unmuting")
    await event.edit(f"✅ **Unmute Complete!**\n🔊 Total Unmuted: `{done}` | ❌ Failed: `{failed}`")
    await send_report_to_saved(chat, "Unmuted", done, failed, lines)

# 5. .cleanall — Pehle Sabko Unban, Phir Sabko Unmute
@client.on(events.NewMessage(outgoing=True, pattern=r"^\.cleanall$"))
async def cleanall_cmd(event):
    if event.is_private:
        return
    chat = await event.get_chat()
    await event.edit("🔍 **Step 1: Banned aur Muted lists fetch ho rahi hain...**")
    banned, muted = await get_exact_banned_and_muted(chat)

    if not banned and not muted:
        await event.edit("✅ Group pehle se bilkul clean hai! (0 Banned, 0 Muted)")
        return

    u_done, u_fail, u_lines = 0, 0, []
    m_done, m_fail, m_lines = 0, 0, []

    if banned:
        u_done, u_fail, u_lines = await run_bulk_action(event, chat, banned, "Step 1/2: Unbanning")

    if muted and not CANCEL_FLAG.get(chat.id):
        m_done, m_fail, m_lines = await run_bulk_action(event, chat, muted, "Step 2/2: Unmuting")

    await event.edit(
        f"🏆 **FULL CLEANUP COMPLETE**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔓 **Total Unbanned:** `{u_done}` (Failed: `{u_fail}`)\n"
        f"🔊 **Total Unmuted:** `{m_done}` (Failed: `{m_fail}`)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 Poori list aapke **Saved Messages** mein bhej di gayi hai."
    )

    # Combined report Saved Messages mein bhejega
    filename = f"full_cleanup_{chat.id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"GROUP: {chat.title} ({chat.id})\n")
        f.write(f"Total Unbanned: {u_done} | Failed: {u_fail}\n")
        f.write(f"Total Unmuted:  {m_done} | Failed: {m_fail}\n")
        f.write("=" * 45 + "\n\n")
        f.write(f"--- UNBANNED USERS ({u_done}) ---\n")
        f.write("\n".join(u_lines) + "\n\n" if u_lines else "None\n\n")
        f.write(f"--- UNMUTED USERS ({m_done}) ---\n")
        f.write("\n".join(m_lines) + "\n" if m_lines else "None\n")

    await client.send_file("me", filename, caption=f"📄 **{chat.title}** — Unbanned ({u_done}) & Unmuted ({m_done}) Report")
    if os.path.exists(filename):
        os.remove(filename)

async def send_report_to_saved(chat, label, done, failed, lines):
    if not lines:
        return
    filename = f"{label.lower()}_{chat.id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== {label.upper()} REPORT ({chat.title}) ===\n")
        f.write(f"Total {label}: {done} | Failed: {failed}\n\n")
        f.write("\n".join(lines))
    await client.send_file("me", filename, caption=f"📄 **{chat.title}** — {label} Users List ({done})")
    if os.path.exists(filename):
        os.remove(filename)

async def main():
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"✅ Logged in as: {me.first_name} ({me.id})")
    print("Group mein .status, .unbanall, .unmuteall ya .cleanall bhejein.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
