import io
import json
import time
import threading

import bimpy
import requests
import spotipy
import spotipy.oauth2 as oauth2

from queue import Queue
from concurrent import futures

from PIL import Image

data = {}
fetching = False
img = None
q = Queue()
credentials = oauth2.SpotifyClientCredentials(
    client_id='27714d82fb8f4c8e8f6a269330b8d613',
    client_secret='b3ff8b67e39e4704baf265c4e7fa8e7c')


def download_image(url):
    r = requests.get(url)
    if r.status_code != requests.codes.ok:
        assert False, 'Status code error: {}.'.format(r.status_code)
    raw_bytes = io.BytesIO(r.content)
    img = Image.open(raw_bytes)
    return img


def fetch_playlist(playlist_id='1FaRfqrVEykFXkOl1vXSbt'):
    global data
    global fetching
    global refresh

    fetching = True
    token = credentials.get_access_token()
    spotify = spotipy.Spotify(auth=token)

    data = spotify.user_playlist_tracks("", playlist_id)
    # r = requests.get(url)
    # data = r.json()
    fetching = False

    # trigger download of album images
    img_urls = []
    seen_img_urls = set()
    count = 0
    for item in data['items']:
        for image in item['track']['album']['images']:
            if image['width'] == 64 and image['url'] not in seen_img_urls:
                img_urls.append(image['url'])
                seen_img_urls.add(image['url'])
                count += 1

        #if count == 25:
        #    break

    # download 8 at a time
    with futures.ThreadPoolExecutor(8) as executor:
        future_url = {executor.submit(download_image, img_url): img_url for img_url in img_urls}
        first = True
        for future in futures.as_completed(future_url):
            img_url = future_url[future]
            try:
                img = future.result()
            except Exception as ex:
                print(f"{img_url} generated exception: {ex}")
            else:
                # print(img)
                if first:
                    # first image is ready, tell imgui to start refreshing the images
                    refresh = True
                    first = False
                q.put(img)


# file = './spotify.old/playlist-2.json'
# with open(file, 'r') as fp:
#     data = json.load(fp)

# if data:
#     for item in data['items']:
#         print(item["track"]["name"], end=",")
#         print(item["track"]["album"]["name"])

ctx = bimpy.Context()
ctx.init(1024,768, "Spotify Collage")

playlist_url = bimpy.String()
bimpy_images = []
refresh = False
while(not ctx.should_close()):
    with ctx:
        bimpy.themes.set_light_theme()
        bimpy.set_next_window_pos(bimpy.Vec2(20, 20), bimpy.Condition.Once)
        bimpy.set_next_window_size(bimpy.Vec2(800, 600), bimpy.Condition.Once)
        bimpy.begin("Track Listing", bimpy.Bool(True), bimpy.WindowFlags.HorizontalScrollbar | bimpy.WindowFlags.NoSavedSettings)
        bimpy.input_text('Playlist URL', playlist_url, 255)
        if not fetching:
            if bimpy.button("Fetch##Fetcher"):
                # data = fetch_playlist() # this blocks so let's use a thread
                thread = threading.Thread(target=fetch_playlist, args=(playlist_url.value.strip(),))
                thread.start()
        else:
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

        # if rimgs:
        #     bimpy.begin('Collage')
        #     width = 64
        #     count = 0
        #     col_count = 0
        #     row_count = 0
        #     for rimg in rimgs:
        #         # print(rimg)
        #         bimpy.set_cursor_pos(bimpy.Vec2(col_count*width, row_count*width+20))
        #         col_count += 1
        #         if col_count == 10:
        #             row_count += 1
        #             col_count = 0


        #         if rimg.downloaded:
        #             if not rimg.bimpy_img:
        #                 rimg.make_bimpy_img(bimpy)
        #             bimpy.image(rimg.bimpy_img)
        #     bimpy.end()

        while True:
            try:
                img = q.get(block=False)
            except:
                break
            else:
                if img is None:
                    break
                if refresh == True:
                    bimpy_images = []
                    refresh = False
                bimpy_images.append(bimpy.Image(img))
                q.task_done()

        for b_img in bimpy_images:
            bimpy.image(b_img)
            bimpy.same_line()

        bimpy.end()
