
API_ID = 12345678        # Your API ID (Integer, no quotes)
API_HASH = "your_hash"   # Your API Hash (String)
BOT_TOKEN = "your_token" # Your Bot Token (String)
AUTH_USERS = [7890781002, 6373737837] # Authorized User IDs

Step 2: The Main Script (bot.py)
Copy this exact code into your main file.
import asyncio
import aiohttp
import json
import zipfile
import os
import re
import time
import logging
import random
from typing import Dict, List, Any, Tuple
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyromod import listen
from pyromod.exceptions.listener_timeout import ListenerTimeout

# Import credentials
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_USERS

# --------------------------------------------------
# LOGGING SETUP
# --------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --------------------------------------------------
# BOT INITIALIZATION
# --------------------------------------------------
bot = Client(
    "pw_cp_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

IMAGE_LIST = [
    "https://graph.org/file/8b1f4146a8d6b43e5b2bc-be490579da043504d5.jpg",
    "https://graph.org/file/b75dab2b3f7eaff612391-282aa53538fd3198d4.jpg",
    "https://graph.org/file/38de0b45dd9144e524a33-0205892dd05593774b.jpg",
    "https://graph.org/file/be39f0eebb9b66d7d6bc9-59af2f46a4a8c510b7.jpg",
    "https://graph.org/file/8b7e3d10e362a2850ba0a-f7c7c46e9f4f50b10b.jpg",
]

# --------------------------------------------------
# HELPER FUNCTIONS (NETWORK)
# --------------------------------------------------
async def fetch_data(session: aiohttp.ClientSession, url: str, headers: Dict = None, params: Dict = None, data: Dict = None, method: str = 'GET') -> Any:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.request(method, url, headers=headers, params=params, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            else:
                logger.error(f"Failed to fetch {url}: {e}")
                return None

# --------------------------------------------------
# START HANDLER
# --------------------------------------------------
@bot.on_message(filters.command(["start"]))
async def start_handler(bot: Client, message: Message):
    keyboard = [
        [InlineKeyboardButton("🚀 Physics Wallah 🚀", callback_data="pwwp")],
        [InlineKeyboardButton("📘 Classplus 📘", callback_data="cpwp")]
    ]
    await message.reply_photo(
        photo=random.choice(IMAGE_LIST),
        caption="**Select an option below to start extraction:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --------------------------------------------------
# PHYSICS WALLAH (PW) LOGIC
# --------------------------------------------------
async def process_pwwp_chapter_content(session, chapter_id, batch_id, subject_id, schedule_id, content_type, headers):
    url = f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_data(session, url, headers=headers)
    content = []

    if data and data.get("success") and data.get("data"):
        data_item = data["data"]
        if content_type in ("videos", "DppVideos"):
            video_details = data_item.get('videoDetails', {})
            if video_details:
                name = data_item.get('topic', 'Unknown')
                videoUrl = video_details.get('videoUrl') or video_details.get('embedCode')
                if videoUrl:
                    content.append(f"{name}:{videoUrl}")
        
        elif content_type in ("notes", "DppNotes"):
            homework_ids = data_item.get('homeworkIds', [])
            for homework in homework_ids:
                name = homework.get('topic', 'Unknown')
                for attachment in homework.get('attachmentIds', []):
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url:
                        content.append(f"{name}:{url}")
    
    return {content_type: content} if content else {}

async def fetch_pwwp_all_schedule(session, chapter_id, batch_id, subject_id, content_type, headers):
    all_schedule = []
    page = 1
    while True:
        params = {'tag': chapter_id, 'contentType': content_type, 'page': page}
        url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents"
        data = await fetch_data(session, url, headers=headers, params=params)
        
        if data and data.get("success") and data.get("data"):
            for item in data["data"]:
                item['content_type'] = content_type
                all_schedule.append(item)
            page += 1
        else:
            break
    return all_schedule

async def process_pwwp_chapters(session, chapter_id, batch_id, subject_id, headers):
    content_types = ['videos', 'notes', 'DppNotes', 'DppVideos']
    tasks = [fetch_pwwp_all_schedule(session, chapter_id, batch_id, subject_id, ct, headers) for ct in content_types]
    results = await asyncio.gather(*tasks)
    
    all_schedule = []
    for res in results:
        all_schedule.extend(res)

    content_tasks = [
        process_pwwp_chapter_content(session, chapter_id, batch_id, subject_id, item["_id"], item['content_type'], headers)
        for item in all_schedule
    ]
    content_results = await asyncio.gather(*content_tasks)
    
    combined = {}
    for result in content_results:
        if result:
            for c_type, c_list in result.items():
                if c_type not in combined: combined[c_type] = []
                combined[c_type].extend(c_list)
    return combined

async def process_pwwp_subject(session, subject, batch_id, batch_name, zipf, json_data, all_subject_urls, headers):
    subject_name = subject.get("subject", "Unknown").replace("/", "-")
    subject_id = subject.get("_id")
    json_data[batch_name][subject_name] = {}
    zipf.writestr(f"{subject_name}/", "")

    # Get Chapters
    all_chapters = []
    page = 1
    while True:
        url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}"
        data = await fetch_data(session, url, headers=headers)
        if data and data.get("data"):
            all_chapters.extend(data["data"])
            page += 1
        else:
            break
    
    chapter_tasks = []
    for chapter in all_chapters:
        c_name = chapter.get("name", "Unknown").replace("/", "-")
        zipf.writestr(f"{subject_name}/{c_name}/", "")
        json_data[batch_name][subject_name][c_name] = {}
        chapter_tasks.append(process_pwwp_chapters(session, chapter["_id"], batch_id, subject_id, headers))
    
    chapter_contents = await asyncio.gather(*chapter_tasks)
    
    subject_urls = []
    for chapter, content in zip(all_chapters, chapter_contents):
        c_name = chapter.get("name", "Unknown").replace("/", "-")
        for c_type in ['videos', 'notes', 'DppNotes', 'DppVideos']:
            if content.get(c_type):
                items = content[c_type][::-1] # Reverse
                zipf.writestr(f"{subject_name}/{c_name}/{c_type}.txt", "\n".join(items))
                json_data[batch_name][subject_name][c_name][c_type] = items
                subject_urls.extend(items)
    
    all_subject_urls[subject_name] = subject_urls

async def run_pwwp_extraction(bot: Client, m: Message, user_id: int):
    editable = await m.reply_text("**Enter Access Token OR Phone Number:**")
    
    try:
        input1 = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
        raw_input = input1.text
        await input1.delete()
    except Exception:
        await editable.edit("**Timeout.**")
        return

    headers = {
        'client-id': '5eb393ee95fab7468a79d189',
        'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
        'client-type': 'WEB',
        'content-type': 'application/json',
    }

    async with aiohttp.ClientSession() as session:
        # Authentication Logic
        if raw_input.isdigit() and len(raw_input) == 10:
            # OTP FLOW
            try:
                await session.post("https://api.penpencil.co/v1/users/get-otp?smsType=0", 
                                 json={"username": raw_input, "countryCode": "+91", "organizationId": "5eb393ee95fab7468a79d189"}, headers=headers)
                await editable.edit("**Enter OTP:**")
                input_otp = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
                otp = input_otp.text
                await input_otp.delete()
                
                auth_payload = {
                    "username": raw_input, "otp": otp, "client_id": "system-admin", 
                    "client_secret": "KjPXuAVfC5xbmgreETNMaL7z", "grant_type": "password",
                    "organizationId": "5eb393ee95fab7468a79d189"
                }
                resp = await session.post("https://api.penpencil.co/v3/oauth/token", json=auth_payload, headers=headers)
                resp_json = await resp.json()
                access_token = resp_json["data"]["access_token"]
                await m.reply_text(f"**Login Successful.**\nToken: `{access_token}`")
            except Exception as e:
                await editable.edit(f"**Login Failed:** {e}")
                return
        else:
            access_token = raw_input

        headers['authorization'] = f"Bearer {access_token}"
        
        # Batch Selection
        await editable.edit("**Enter Batch Name to Search:**")
        try:
            batch_input = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
            batch_search = batch_input.text
            await batch_input.delete()
        except:
            return

        search_url = f"https://api.penpencil.co/v3/batches/search?name={batch_search}"
        data = await fetch_data(session, search_url, headers=headers)
        courses = data.get("data", [])
        
        if not courses:
            await editable.edit("**No batches found.**")
            return

        course_text = "\n".join([f"{i+1}. {c['name']}" for i, c in enumerate(courses)])
        await editable.edit(f"**Select Batch Index:**\n\n{course_text}")
        
        try:
            idx_input = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
            idx = int(idx_input.text) - 1
            await idx_input.delete()
            selected_course = courses[idx]
        except:
            await editable.edit("**Invalid Selection.**")
            return

        batch_id = selected_course['_id']
        batch_name = selected_course['name'].replace("/", "-")
        clean_name = f"{user_id}_{batch_name}"
        
        await editable.edit(f"**Extracting {batch_name}... Please wait.**")
        
        # Extraction
        try:
            url = f"https://api.penpencil.co/v3/batches/{batch_id}/details"
            details = await fetch_data(session, url, headers=headers)
            subjects = details.get("data", {}).get("subjects", [])
            
            json_data = {batch_name: {}}
            all_subject_urls = {}
            
            with zipfile.ZipFile(f"{clean_name}.zip", 'w') as zipf:
                tasks = [process_pwwp_subject(session, s, batch_id, batch_name, zipf, json_data, all_subject_urls, headers) for s in subjects]
                await asyncio.gather(*tasks)
            
            # Send Files
            await editable.delete()
            await m.reply_document(document=f"{clean_name}.zip", caption=f"**{batch_name}**")
            
        except Exception as e:
            logger.error(e)
            await m.reply_text(f"Extraction Error: {e}")
        finally:
            if os.path.exists(f"{clean_name}.zip"): os.remove(f"{clean_name}.zip")

# --------------------------------------------------
# CLASSPLUS (CP) LOGIC
# --------------------------------------------------
async def get_cpwp_content_recursive(session, headers, batch_token, folder_id=0):
    url = f'https://api.classplusapp.com/v2/course/preview/content/list/{batch_token}'
    params = {'folderId': folder_id, 'limit': 1000}
    
    try:
        async with session.get(url, params=params, headers=headers) as resp:
            data = await resp.json()
            contents = data.get('data', [])
    except:
        return []

    results = []
    tasks = []

    for content in contents:
        # If Folder, Recurse
        if content['contentType'] == 1:
            tasks.append(get_cpwp_content_recursive(session, headers, batch_token, content['id']))
        else:
            # Extract URL
            url = content.get('url') or content.get('thumbnailUrl')
            name = content.get('name', 'Unknown')
            if url:
                # Basic URL cleanup/formatting
                if "media-cdn.classplusapp.com/tencent/" in url:
                    url = url.rsplit('/', 1)[0] + "/master.m3u8"
                elif "jw-signed-url" in url:
                    # Logic to fetch signed URL would go here (simplified for brevity)
                    pass 
                
                results.append(f"{name}:{url}")

    if tasks:
        nested_results = await asyncio.gather(*tasks)
        for nr in nested_results:
            results.extend(nr)
            
    return results

async def run_cpwp_extraction(bot: Client, m: Message, user_id: int):
    editable = await m.reply_text("**Enter Org Code:**")
    try:
        inp = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
        org_code = inp.text.lower()
        await inp.delete()
    except:
        await editable.edit("Timeout")
        return

    async with aiohttp.ClientSession() as session:
        # Get Token from Org Store
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with session.get(f"https://{org_code}.courses.store", headers=headers) as resp:
            text = await resp.text()
            match = re.search(r'"hash":"(.*?)"', text)
            if not match:
                await editable.edit("Invalid Org Code or Store not found.")
                return
            token = match.group(1)

        # Search Courses
        await editable.edit("**Enter Batch Name to Search:**")
        try:
            inp = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=60)
            search_term = inp.text
            await inp.delete()
        except: return

        api_headers = {
            'api-version': '35',
            'device-id': 'c28d3cb16bbdac01',
            'host': 'api.classplusapp.com',
        }
        
        search_url = f"https://api.classplusapp.com/v2/course/preview/similar/{token}?search={search_term}"
        async with session.get(search_url, headers=api_headers) as resp:
            data = await resp.json()
            courses = data.get("data", {}).get("coursesData", [])

        if not courses:
            await editable.edit("No courses found.")
            return

        c_text = "\n".join([f"{i+1}. {c['name']} (₹{c['finalPrice']})" for i, c in enumerate(courses)])
        await editable.edit(f"**Select Course:**\n\n{c_text}")

        try:
            inp = await bot.listen(chat_id=m.chat.id, user_id=user_id, timeout=60)
            idx = int(inp.text) - 1
            selected = courses[idx]
            await inp.delete()
        except: return

        # Get Batch Token
        batch_headers = {'tutorWebsiteDomain': f'https://{org_code}.courses.store', 'Api-Version': '22'}
        info_url = f"https://api.classplusapp.com/v2/course/preview/org/info?courseId={selected['id']}"
        async with session.get(info_url, headers=batch_headers) as resp:
            data = await resp.json()
            batch_hash = data['data']['hash']

        await editable.edit(f"**Extracting {selected['name']}...**")
        
        # Extract Content
        links = await get_cpwp_content_recursive(session, api_headers, batch_hash)
        
        if links:
            fname = f"{user_id}_cp.txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(links))
            await editable.delete()
            await m.reply_document(fname, caption=f"**{selected['name']}**")
            os.remove(fname)
        else:
            await editable.edit("No content found or extraction failed.")

# --------------------------------------------------
# CALLBACK QUERY HANDLER
# --------------------------------------------------
@bot.on_callback_query()
async def callback_handler(bot: Client, query):
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in AUTH_USERS:
        await query.answer("Not Authorized!", show_alert=True)
        return

    await query.answer()
    
    if data == "pwwp":
        # CRITICAL FIX: Use create_task, NOT ThreadPool
        asyncio.create_task(run_pwwp_extraction(bot, query.message, user_id))
    elif data == "cpwp":
        asyncio.create_task(run_cpwp_extraction(bot, query.message, user_id))

# --------------------------------------------------
# MAIN ENTRY
# --------------------------------------------------
if __name__ == "__main__":
    print("Bot Started...")
    bot.run()

