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
import queue

from concurrent import futures

from PIL import Image

program_start_dir = os.path.dirname(os.path.realpath(__file__))

q = queue.Queue()
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

def get_credentials():
    import configparser
    keyfile = os.path.expanduser('~/') + '.api_keys'
    if not os.path.isfile(keyfile):
        print(f"Could not open {keyfile}. Please make sure it exists and has the following entries")
        print("[spotify]")
        print("client_id=<your client id>")
        print("client_secret=<your client secret>")
        exit()

    config = configparser.ConfigParser()
    config.read(keyfile)
    return (config['spotify']['client_id'], config['spotify']['client_secret'])

get_credentials()
def save_collage(playlist_id, img_urls, imgdict, save_dir, cols=5, tile_size=(100, 100)):
    rows = math.ceil(len(img_urls) / cols)
    bg = Image.new('RGB', (cols * tile_size[0], rows * tile_size[1]), color='#000')
    y = 0
    x = 0
    for url in img_urls:
        #img = Image.open(path)
        img = imgdict[url]
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

    save_path = f"{save_dir}/{playlist_id}.png"
    bg.save(save_path, "png")
    return save_path

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
            if image['width'] == 300 and image['url'] not in seen_img_urls:
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
b_col_count = bimpy.Int(0)
refresh = False
COL_COUNT = 8
saved = ""
saved_time = 0
credentials = oauth2.SpotifyClientCredentials(*get_credentials())
while(not ctx.should_close()):
    with ctx:
        # bimpy.themes.set_light_theme()
        bimpy.set_next_window_pos(bimpy.Vec2(20, 20), bimpy.Condition.Once)
        bimpy.set_next_window_size(bimpy.Vec2(600, 600), bimpy.Condition.Once)
        bimpy.begin("Track Listing", bimpy.Bool(True), bimpy.WindowFlags.HorizontalScrollbar | bimpy.WindowFlags.NoSavedSettings)
        bimpy.text('Spotify Playlist URI')
        bimpy.same_line()
        bimpy.input_text('', playlist_url, 255)
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

        try:
            (url,img) = q.get(block=False)
        except queue.Empty:
            pass
        else:
            if url is None or img is None:
                pass
            if refresh == True:
                bimpy_imgdict = {}
                if len(img_urls) < COL_COUNT:
                    b_col_count.value = len(img_urls)
                else:
                    b_col_count.value = COL_COUNT
                refresh = False
            bimpy_imgdict[url] = bimpy.Image(img.resize((64,64), Image.ANTIALIAS))
            q.task_done()

        if img_urls:
            bimpy.set_next_window_pos(bimpy.Vec2(625, 20), bimpy.Condition.Once)
            bimpy.set_next_window_size(bimpy.Vec2(532, 600), bimpy.Condition.Once)
            bimpy.begin('Collage', bimpy.Bool(True), bimpy.WindowFlags.HorizontalScrollbar)
            if imgs_downloading:
                bimpy.text("Downloading thumbnails")
                bimpy.progress_bar(percent_downloaded, bimpy.Vec2(-1,0), f"{imgs_downloaded}/{imgs_total}")
            else:
                bimpy.text("Collage columns")
                bimpy.same_line()
                bimpy.slider_int("", b_col_count, 1, len(img_urls))

            if not imgs_downloading and bimpy.button("Save Collage"):
                # print(data)
                saved = save_collage(current_playlist_id, img_urls, imgdict, program_start_dir, b_col_count.value)
                saved_time = time.clock()
                print("saved:", saved)

            if time.clock() - saved_time <= 2:
                bimpy.same_line()
                bimpy.text(f"Saved to {saved}.png")

            width,height = 64,64
            first = True
            col_count = 0
            row_count = 0
            padding = 0
            disp_count = 0
            for url in img_urls:
                if first:
                    padding = bimpy.get_cursor_pos().y
                    first = False
                bimpy.set_cursor_pos(bimpy.Vec2(col_count*width, row_count*height+padding))
                col_count += 1
                if col_count == b_col_count.value:
                    row_count += 1
                    col_count = 0
                b_img = bimpy_imgdict.get(url, None)
                if b_img:
                    bimpy.image(b_img)
                    disp_count += 1
                bimpy.same_line()
            bimpy.end()
        bimpy.end()
