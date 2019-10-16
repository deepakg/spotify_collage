import requests
import io
from PIL import Image
from time import sleep

class RemoteImage:
    url = ""
    downloaded = False
    img = None
    bimpy_img = None

    def __init__(self, url):
        self.url = url

    def __str__(self):
        return 'url: ' + self.url + ', img: ' +  f"{self.img}"

    def download(self, sleepy_time=1):
        # uncomment the next two lines to simulate random slow response
        # import random
        # sleep(int(random.random()*10))

        r = requests.get(self.url)
        if r.status_code != requests.codes.ok:
            assert False, 'Status code error: {}.'.format(r.status_code)
        raw_bytes = io.BytesIO(r.content)
        self.img = Image.open(raw_bytes)
        self.downloaded = True

    def make_bimpy_img(self, bimpy):
        self.bimpy_img = bimpy.Image(self.img)

    def get_image(self):
        if not self.downloaded:
            self.download()

        return self.img

def print_array(ris):
    while True:
        download_count = 0
        for ri in ris:
            print(ri)
            if ri.downloaded:
                download_count += 1

        if download_count == len(ris):
            break

        sleep(0.5)

if __name__ == "__main__":
    import threading
    from concurrent import futures
    from operator import methodcaller
    image_urls = [
        'https://i.scdn.co/image/fc8b1e48a242f4c23ce1263e2ac93d32231fe1d5',
        'https://i.scdn.co/image/a725005634ef5b58fc1a798361169049dae97b16',
        'https://i.scdn.co/image/321c7ea7463b2b1c5f38a2fb565fcc63c6294e2b',
        'https://i.scdn.co/image/1adf2503ed712f0d47654ae10312eaa15e6620ce',
    ]

    ris = list(map(RemoteImage, image_urls))

    thread = threading.Thread(target=print_array, args=(ris,))
    thread.start()
    try:
        with futures.ThreadPoolExecutor(4) as executor:
            for ri in ris:
                executor.submit(ri.download)
    except:
        print("Oops")
    else:
        for ri in ris:
            print(ri)
