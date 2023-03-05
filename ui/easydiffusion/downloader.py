from time import time
import re
import rich
import aiohttp
import asyncio
import os
from aiofile import async_open
import traceback
from fastapi import WebSocket
import json
from easydiffusion import app
from easydiffusion.utils.save_utils import filename_regex


# Sends these messages:
# - During the download:
#    {
#      "type" = "model_download_status", 
#      "state":       String, "in progress" while downloading, followed by one "completed" message
#      "downloaded":  Integer, number of bytes downloaded so far
#      "total":       Integer, total number of bytes to download (file size)
#      "filename":    String, name of the file stored to the model folder
#      "url":         String, URL of the model file
#    }
#
# - After completion of the download, the following message gets sent to channel "broadcast":
#    {
#      "type" = "refresh_models"
#    }

async def downloadFile(url, folder, connection_manager, channel, filename="", offset=0):
    afp = None
    total_size = 0
    start = time()
    last_msg = start
    downloadstatus = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=None, headers={"Range": f"bytes={str(offset)}-"}) as resp:
                # First chunk, so there's no output file opened yet. First determine the filename, than open the file
                if afp == None:
                    # If no filename was provided from the caller of this function, check for a filename in the HTTP
                    # response. If that one doesn't exist, take the last part from the URL.
                    if filename == "" and "Content-Disposition" in resp.headers:
                        rich.print(f'[yellow]Content-Disposition: {resp.headers["Content-Disposition"]}[/yellow]')
                        m = re.search(r'filename="([^"]*)"', resp.headers["Content-Disposition"])
                        if m:
                            filename = m.group(1)
                    if filename == "":
                        filename = url.split("/")[-1]
                    rich.print(f'[yellow]Filename {filename}[/yellow]')
                    mode = "wb" if offset == 0 else "ab"
                    afp = await async_open(os.path.join( folder, filename), mode)
                    if offset == 0:
                        downloadstatus = {
                            "type": "model_download_status",
                            "state": "in progress",
                            "downloaded":0,
                            "total": int(resp.headers["content-length"]),
                            "filename":filename,
                            "url":url
                        }
                while True:
                    chunk = await resp.content.read(1024*1024)
                    if not chunk:
                        break
                    await afp.write(chunk)
                    total_size += len(chunk)
                    downloadstatus["downloaded"] = offset + total_size
                    if time() - last_msg > 2:
                        await connection_manager.send_to_channel(channel, json.dumps(downloadstatus))
                        rich.print(f'[cyan]{time() - start:0.2f}s, downloaded: {total_size/1024/1024:0.0f}MB of {int(resp.headers["content-length"])/1024/1024:0.0f}MB[/cyan]')
                        last_msg = time()
    except Exception as e:
        rich.print(f"[yellow]{traceback.format_exc()}[/yellow]")
        rich.print(f"[yellow]Exception: {e}[/yellow]")
    if afp != None:
        await afp.close()
    if total_size != 0 and total_size != int(resp.headers["content-length"]):
        # Resume the request
        await asyncio.sleep(2)
        await downloadFile(url, folder, filename, total_size)
    downloadstatus["state"] = "completed"
    await connection_manager.send_to_channel(channel, json.dumps(downloadstatus))

# Message:
# {
#   'type' = 'model_download'
#   'url':        String, url of the file to download
#   'model_type': String, name of the subfolder in the "models" directory
#   'channel':    String, name of the channel to send status messages to
# }
async def modelDownloadTask(message, connection_manager):
    print(f'Start download {message["url"]}')
    path = os.path.join(app.MODELS_DIR, filename_regex.sub("_", message["model_type"]))
    await downloadFile(message["url"], path, connection_manager, message["channel"])
    await connection_manager.send_to_channel("broadcast", '{"type":"refresh_models"}')

