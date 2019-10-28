import io
import json
import math
import os
import threading
import time

import bimpy
import requests
import spotipy
import spotipy.oauth2 as oauth2

from queue import Queue
from concurrent import futures

from PIL import Image

q = Queue()
data = {}

# bimpy images for display within bimpy context
bimpy_imgdict = {}

# PIL images for making collage can potentially be higher resoultion than one used for display
imgdict = {}

# urls of album art images in a playlist in the same order as they are listed in the playlist
img_urls = []

current_playlist_id = None
playlist_downloading = False
imgs_downloading = False

imgs_downloaded = 0
percent_downloaded = 0
imgs_total = 0

credentials = oauth2.SpotifyClientCredentials(
    client_id='27714d82fb8f4c8e8f6a269330b8d613',
    client_secret='b3ff8b67e39e4704baf265c4e7fa8e7c')

def make_collage(playlist_id, images, cols=5, tile_size=(64, 64)):
    rows = math.ceil(len(images) / cols)
    bg = Image.new('RGB', (cols * tile_size[0], rows * tile_size[1]), color='#000')
    y = 0
    x = 0
    for img in images:
        #img = Image.open(path)
        img.thumbnail(tile_size)
        (width, height) = img.size

        #sometimes the thumbnails are not square. resizing them to
        #tile_size retains the aspect ratio but then the width or the
        #height falls short of the tile_size. The following is to
        #"center align" the thumbnail within its tile_sized slot.
        offset_x, offset_y = 0,0
        if width < tile_size[0]:
            offset_x = (tile_size[0]-width)//2
        if height < tile_size[1]:
            offset_y = (tile_size[1]-height)//2

        bg.paste(img,(x+offset_x,y+offset_y))

        x += tile_size[0]
        if x == cols * tile_size[0]:
            x = 0
            y += tile_size[1]

    bg.save(f"/Users/deepakg/Desktop/{playlist_id}.png", "png")
    bg.show()


def download_image(url):
    # simulate slow connection by uncommenting the lines below
    # import random
    # import time
    # time.sleep(int(random.random()*10))
    r = requests.get(url)
    if r.status_code != requests.codes.ok:
        assert False, 'Status code error: {}.'.format(r.status_code)
    raw_bytes = io.BytesIO(r.content)
    img = Image.open(raw_bytes)
    return img


def fetch_playlist(playlist_uri=''):
    global current_playlist_id
    if not playlist_uri or \
       not playlist_uri.startswith('spotify:playlist:'):
        return

    playlist_id = playlist_uri.split(':')[-1]
    current_playlist_id = playlist_id

    global data
    global playlist_downloading
    global imgs_downloading
    global refresh
    global imgs_downloaded
    global imgs_total
    global percent_downloaded
    global img_urls

    playlist_downloading = True

    token = credentials.get_access_token()
    spotify = spotipy.Spotify(auth=token)

    data = spotify.user_playlist_tracks("", playlist_id)

    playlist_downloading = False
    imgs_downloaded = 0
    percent_downloaded = 0
    imgs_downloading = True

    # trigger download of album images
    img_urls = []
    seen_img_urls = set()
    for item in data['items']:
        for image in item['track']['album']['images']:
            if image['width'] == 64 and image['url'] not in seen_img_urls:
                img_urls.append(image['url'])
                seen_img_urls.add(image['url'])

    imgs_total = len(img_urls)

    # download 8 at a time
    with futures.ThreadPoolExecutor(8) as executor:
        future_url = {executor.submit(download_image, img_url): img_url for img_url in img_urls}
        first = True
        for future in futures.as_completed(future_url):
            img_url = future_url[future]
            try:
                img = future.result()
                imgs_downloaded += 1
                percent_downloaded = imgs_downloaded/imgs_total
            except Exception as ex:
                print(f"{img_url} generated exception: {ex}")
            else:
                # print(img)
                if first:
                    # first image is ready, tell imgui to start refreshing the images
                    refresh = True
                    first = False
                imgdict[img_url] = img
                q.put((img_url,img))
    imgs_downloading = False

ctx = bimpy.Context()
ctx.init(1200,768, "Spotify Collage")

playlist_url = bimpy.String()
refresh = False
COL_COUNT = 8
saved = ""
saved_time = 0
# import os
# print(os.path.dirname(os.path.realpath(__file__)))
# exit()
while(not ctx.should_close()):
    with ctx:
        # bimpy.themes.set_light_theme()
        bimpy.set_next_window_pos(bimpy.Vec2(20, 20), bimpy.Condition.Once)
        bimpy.set_next_window_size(bimpy.Vec2(600, 600), bimpy.Condition.Once)
        bimpy.begin("Track Listing", bimpy.Bool(True), bimpy.WindowFlags.HorizontalScrollbar | bimpy.WindowFlags.NoSavedSettings)
        bimpy.input_text('Playlist URL', playlist_url, 255)
        if not playlist_downloading and not imgs_downloading:
            if bimpy.button("Fetch##Fetcher"):
                # data = fetch_playlist() # this blocks so let's use a thread
                thread = threading.Thread(target=fetch_playlist, args=(playlist_url.value.strip(),))
                thread.start()
        elif imgs_downloading:
            bimpy.button("Fetching album covers...")
        elif playlist_downloading:
            bimpy.button("Fetching...")

        if data:
            bimpy.columns(2, "tracks")
            bimpy.text("Track")
            bimpy.next_column()
            bimpy.text("Album")
            bimpy.separator()
            bimpy.next_column()
            count = 1
            for item in data['items']:
                # bimpy.text(f"{count}")
                # bimpy.next_column()
                bimpy.text(item["track"]["name"])
                bimpy.next_column()
                bimpy.text(item["track"]["album"]["name"])
                bimpy.next_column()
                count += 1
            bimpy.columns(1)

        while True:
            try:
                (url,img) = q.get(block=False)
            except:
                break
            else:
                if url is None or img is None:
                    break
                if refresh == True:
                    bimpy_imgdict = {}
                    refresh = False
                bimpy_imgdict[url] = bimpy.Image(img)
                q.task_done()

        if img_urls:
            bimpy.set_next_window_pos(bimpy.Vec2(625, 20), bimpy.Condition.Once)
            bimpy.set_next_window_size(bimpy.Vec2(532, 600), bimpy.Condition.Once)
            bimpy.begin('Collage')
            if imgs_downloading:
                bimpy.progress_bar(percent_downloaded, bimpy.Vec2(-1,0), f"Downloading Thumbnails {imgs_downloaded}/{imgs_total}")
            elif bimpy.button("Save Collage"):
                # print(data)
                make_collage(current_playlist_id, imgdict.values(), COL_COUNT)
                saved = current_playlist_id
                saved_time = time.clock()
                print("saved:", saved_time)

            if time.clock() - saved_time <= 2:
                bimpy.same_line()
                bimpy.text(f"Saved to {saved}.png")

            width,height = 64,64
            first = True
            col_count = 0
            row_count = 0
            padding = 0
            for url in img_urls:
                if first:
                    padding = bimpy.get_cursor_pos().y
                    first = False
                bimpy.set_cursor_pos(bimpy.Vec2(col_count*width, row_count*height+padding))
                col_count += 1
                if col_count == COL_COUNT:
                    row_count += 1
                    col_count = 0
                b_img = bimpy_imgdict.get(url, None)
                if b_img:
                    bimpy.image(b_img)
                bimpy.same_line()
            bimpy.end()
        bimpy.end()
