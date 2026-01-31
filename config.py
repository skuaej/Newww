
import asyncio
import aiohttp
import json
import zipfile
import os
import re
import time
import logging
import random
from typing import Dict, List, Any
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyromod import listen

# --------------------------------------------------
# FIX: IMPORT UPPERCASE VARIABLES
# --------------------------------------------------
from config import API_ID, API_HASH, BOT_TOKEN, AUTH_USERS

# Map them to lowercase to keep logic consistent
api_id = API_ID
api_hash = API_HASH
bot_token = BOT_TOKEN
auth_users = AUTH_USERS

# --------------------------------------------------
# LOGGING SETUP
# --------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --------------------------------------------------
# BOT INITIALIZATION
# --------------------------------------------------
try:
    API_ID_INT = int(api_id)
except ValueError:
    logger.error("API_ID in config.py must be a number!")
    exit(1)

bot = Client(
    "pw_cp_bot",
    api_id=API_ID_INT,
    api_hash=api_hash,
    bot_token=bot_token
)

IMAGE_LIST = [
    "https://graph.org/file/8b1f4146a8d6b43e5b2bc-be490579da043504d5.jpg",
    "https://graph.org/file/b75dab2b3f7eaff612391-282aa53538fd3198d4.jpg",
    "https://graph.org/file/38de0b45dd9144e524a33-0205892dd05593774b.jpg",
    "https://graph.org/file/be39f0eebb9b66d7d6bc9-59af2f46a4a8c510b7.jpg",
    "https://graph.org/file/8b7e3d10e362a2850ba0a-f7c7c46e9f4f50b10b.jpg",
]

# --------------------------------------------------
# HELPER FUNCTIONS
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
async def start_handler(client, message: Message):
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
async def process_pwwp_subject(session, subject, batch_id, batch_name, zipf, json_data, all_subject_urls, headers):
    subject_name = subject.get("subject", "Unknown").replace("/", "-")
    subject_id = subject.get("_id")
    
    if batch_name not in json_data:
        json_data[batch_name] = {}
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
    
    for chapter in all_chapters:
        c_name = chapter.get("name", "Unknown").replace("/", "-")
        zipf.writestr(f"{subject_name}/{c_name}/", "")
        json_data[batch_name][subject_name][c_name] = {}
        
        content_types = ['videos', 'notes', 'DppNotes', 'DppVideos']
        
        for c_type in content_types:
            items = []
            pg = 1
            while True:
                p_params = {'tag': chapter["_id"], 'contentType': c_type, 'page': pg}
                p_url = f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{subject_id}/contents"
                p_data = await fetch_data(session, p_url, headers=headers, params=p_params)
                
                if p_data and p_data.get("success") and p_data.get("data"):
                    items.extend(p_data["data"])
                    pg += 1
                else:
                    break
            
            extracted_links = []
            for item in items:
                s_url = f"https://api.penpencil.co/v1/batches/{batch_id}/subject/{subject_id}/schedule/{item['_id']}/schedule-details"
                s_data = await fetch_data(session, s_url, headers=headers)
                
                if s_data and s_data.get("data"):
                    d = s_data["data"]
                    if c_type in ["videos", "DppVideos"]:
                        vd = d.get('videoDetails', {})
                        if vd:
                            v_url = vd.get('videoUrl') or vd.get('embedCode')
                            if v_url:
                                extracted_links.append(f"{d.get('topic')}:{v_url}")
                    else:
                        h_ids = d.get('homeworkIds', [])
                        for h in h_ids:
                            for att in h.get('attachmentIds', []):
                                url = att.get('baseUrl', '') + att.get('key', '')
                                if url:
                                    extracted_links.append(f"{h.get('topic')}:{url}")

            if extracted_links:
                final_text = "\n".join(extracted_links[::-1])
                zipf.writestr(f"{subject_name}/{c_name}/{c_type}.txt", final_text)
                json_data[batch_name][subject_name][c_name][c_type] = extracted_links
                
                if subject_name not in all_subject_urls:
                    all_subject_urls[subject_name] = []
                all_subject_urls[subject_name].extend(extracted_links)

async def run_pwwp_extraction(client: Client, m: Message, user_id: int):
    editable = await m.reply_text("**Enter Access Token OR Phone Number:**")
    
    try:
        input1 = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
        raw_input = input1.text
        await input1.delete()
    except Exception:
        await editable.edit("**Timeout.**")
        return

    # RESTORED FULL HEADERS TO FIX 401 ERROR
    headers = {
        'client-id': '5eb393ee95fab7468a79d189',
        'client-version': '1910',
        'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
        'client-type': 'WEB',
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; M2101K6P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
    }

    async with aiohttp.ClientSession() as session:
        if raw_input.isdigit() and len(raw_input) == 10:
            try:
                await session.post("https://api.penpencil.co/v1/users/get-otp?smsType=0", 
                                 json={"username": raw_input, "countryCode": "+91", "organizationId": "5eb393ee95fab7468a79d189"}, headers=headers)
                await editable.edit("**Enter OTP:**")
                input_otp = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
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

        # Update headers with token
        headers['Authorization'] = f"Bearer {access_token}"
        
        await editable.edit("**Enter Batch Name to Search:**")
        try:
            batch_input = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
            batch_search = batch_input.text
            await batch_input.delete()
        except:
            return

        search_url = f"https://api.penpencil.co/v3/batches/search?name={batch_search}"
        data = await fetch_data(session, search_url, headers=headers)
        
        # FIX: Check if data exists before using .get()
        if not data:
            await editable.edit("**Login Failed or API Error (401). Check your Token.**")
            return

        courses = data.get("data", [])
        
        if not courses:
            await editable.edit("**No batches found.**")
            return

        course_text = "\n".join([f"{i+1}. {c['name']}" for i, c in enumerate(courses)])
        await editable.edit(f"**Select Batch Index:**\n\n{course_text}")
        
        try:
            idx_input = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
            idx = int(idx_input.text) - 1
            await idx_input.delete()
            if idx < 0 or idx >= len(courses): raise ValueError
            selected_course = courses[idx]
        except:
            await editable.edit("**Invalid Selection.**")
            return

        batch_id = selected_course['_id']
        batch_name = selected_course['name'].replace("/", "-")
        clean_name = f"{user_id}_{batch_name}"
        
        await editable.edit(f"**Extracting {batch_name}... Please wait.**")
        
        try:
            url = f"https://api.penpencil.co/v3/batches/{batch_id}/details"
            details = await fetch_data(session, url, headers=headers)
            
            if not details: 
                await editable.edit("**Failed to get batch details.**")
                return

            subjects = details.get("data", {}).get("subjects", [])
            
            json_data = {batch_name: {}}
            all_subject_urls = {}
            
            with zipfile.ZipFile(f"{clean_name}.zip", 'w') as zipf:
                tasks = [process_pwwp_subject(session, s, batch_id, batch_name, zipf, json_data, all_subject_urls, headers) for s in subjects]
                await asyncio.gather(*tasks)
            
            await editable.delete()
            if os.path.exists(f"{clean_name}.zip"):
                await m.reply_document(document=f"{clean_name}.zip", caption=f"**{batch_name}**")
            else:
                await m.reply_text("**Extraction finished but zip file was not created (Maybe empty batch?).**")
            
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
        if content['contentType'] == 1:
            tasks.append(get_cpwp_content_recursive(session, headers, batch_token, content['id']))
        else:
            url = content.get('url') or content.get('thumbnailUrl')
            name = content.get('name', 'Unknown')
            if url:
                if "media-cdn.classplusapp.com/tencent/" in url:
                    url = url.rsplit('/', 1)[0] + "/master.m3u8"
                results.append(f"{name}:{url}")

    if tasks:
        nested_results = await asyncio.gather(*tasks)
        for nr in nested_results:
            results.extend(nr)
            
    return results

async def run_cpwp_extraction(client: Client, m: Message, user_id: int):
    editable = await m.reply_text("**Enter Org Code:**")
    try:
        inp = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=120)
        org_code = inp.text.lower()
        await inp.delete()
    except:
        await editable.edit("Timeout")
        return

    async with aiohttp.ClientSession() as session:
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with session.get(f"https://{org_code}.courses.store", headers=headers) as resp:
            text = await resp.text()
            match = re.search(r'"hash":"(.*?)"', text)
            if not match:
                await editable.edit("Invalid Org Code or Store not found.")
                return
            token = match.group(1)

        await editable.edit("**Enter Batch Name to Search:**")
        try:
            inp = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=60)
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
            inp = await client.listen(chat_id=m.chat.id, user_id=user_id, timeout=60)
            idx = int(inp.text) - 1
            if idx < 0 or idx >= len(courses): raise ValueError
            selected = courses[idx]
            await inp.delete()
        except: return

        batch_headers = {'tutorWebsiteDomain': f'https://{org_code}.courses.store', 'Api-Version': '22'}
        info_url = f"https://api.classplusapp.com/v2/course/preview/org/info?courseId={selected['id']}"
        async with session.get(info_url, headers=batch_headers) as resp:
            data = await resp.json()
            batch_hash = data['data']['hash']

        await editable.edit(f"**Extracting {selected['name']}...**")
        
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
async def callback_handler(client, query):
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in auth_users:
        await query.answer("Not Authorized!", show_alert=True)
        return

    await query.answer()
    
    if data == "pwwp":
        asyncio.create_task(run_pwwp_extraction(client, query.message, user_id))
    elif data == "cpwp":
        asyncio.create_task(run_cpwp_extraction(client, query.message, user_id))

# --------------------------------------------------
# MAIN ENTRY
# --------------------------------------------------
if __name__ == "__main__":
    print("Bot Starting...")
    bot.run()

