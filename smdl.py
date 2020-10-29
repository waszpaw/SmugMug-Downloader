import os
import sys
import requests
import json
import re
import argparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from colored import fg, bg, attr
from time import sleep

parser = argparse.ArgumentParser(description="SmugMug Downloader")
parser.add_argument("-s", "--session", help="session ID (required if user is password protected); log in on a web browser and paste the SMSESS cookie")
parser.add_argument("-u", "--user", help="username (from URL, USERNAME.smugmug.com)", required=True)
parser.add_argument("-o", "--output", default="output/", help="output directory")
parser.add_argument("-a", "--albums", help='specific album names to download, split by $. Defaults to all. (e.g. --albums "Title 1$Title 2$Title 3")')
parser.add_argument("-m", "--mask", help='specific album mask (start of path) to download. e.g. --mask "/2020/09/Family", please note that "--albums" has priority')
parser.add_argument("-p", "--pages", default="no", help='enable going through pages')

args = parser.parse_args()

endpoint = "https://www.smugmug.com"

# Session ID (required if user is password protected)
# Log in on a web browser and copy the SMSESS cookie
SMSESS = args.session

cookies = {"SMSESS": SMSESS}

if args.output[-1:] != "/" and args.output[-1:] != "\\":
	output_dir = args.output + "/"
else:
	output_dir = args.output

if args.albums:
	specificAlbums = [x.strip() for x in args.albums.split('$')]
	args.mask = ""

# Gets the JSON output from an API call
def get_json(url):
	r = requests.get(endpoint + url, cookies=cookies)
	soup = BeautifulSoup(r.text, "html.parser")
	pres = soup.find_all("pre")
	return json.loads(pres[-1].text)

# Retrieve the list of albums
print("Downloading album list...", end="")
albums = get_json("/api/v2/folder/user/%s!albumlist" % args.user)
print("done.")

# Quit if no albums were found
try:
	albums["Response"]["AlbumList"]
except KeyError:
	sys.exit("No albums were found for the user %s. The user may not exist or may be password protected." % args.user)

# Removing unneeded directories from the table
temp = []
if args.albums:
	while albums["Response"]["AlbumList"]:
		album = albums["Response"]["AlbumList"].pop()
		if album["Name"].strip() in specificAlbums:
			temp.append(album)
	while temp:
		albums["Response"]["AlbumList"].append(temp.pop())

elif args.mask:
	while albums["Response"]["AlbumList"]:
		album = albums["Response"]["AlbumList"].pop()
		if args.mask == album["UrlPath"][0:len(args.mask)]:
			temp.append(album)
	while temp:
		albums["Response"]["AlbumList"].append(temp.pop())

# Create output directories
print("Creating output directories...", end="")
for album in albums["Response"]["AlbumList"]:
	directory = output_dir + album["UrlPath"][1:]
	if not os.path.exists(directory):
		os.makedirs(directory)
print("done.")

def format_label(s, width=24):
	return s[:width].ljust(width)

bar_format = '{l_bar}{bar:-2}| {n_fmt:>3}/{total_fmt:<3}'

# Loop through each album
for album in tqdm(albums["Response"]["AlbumList"], position=0, leave=True, bar_format=bar_format, desc=f"{fg('yellow')}{attr('bold')}{format_label('All Albums')}{attr('reset')}"):
	album_path = output_dir + album["UrlPath"][1:]

# Iterate through one album
	images = get_json(album["Uri"] + "!images")

	# Skip if no images are in the album
	if "AlbumImage" in images["Response"]:
		# Loop through each page of the album if parameter --page given
		if args.pages != "no":
			next_images = images
			while "NextPage" in next_images["Response"]["Pages"]:
				next_images = get_json(next_images["Response"]["Pages"]["NextPage"])
				images["Response"]["AlbumImage"].extend(next_images["Response"]["AlbumImage"])

		# Loop through each image in the album
		for image in tqdm(images["Response"]["AlbumImage"], position=1, leave=True, bar_format=bar_format, desc=f"{attr('bold')}{format_label(album['Name'])}{attr('reset')}"):
			image_path = album_path + "/" + re.sub('[^\w\-_\. ]', '_', image["FileName"])

			# Skip if image has already been saved
			if os.path.isfile(image_path):
				continue

			# Grab video URI if the file is video, otherwise, the standard image URI
			largest_media = "LargestVideo" if "LargestVideo" in image["Uris"] else "LargestImage"
			if largest_media in image["Uris"]:
				image_req = get_json(image["Uris"][largest_media]["Uri"])
				download_url = image_req["Response"][largest_media]["Url"]
			else:
				# grab archive link if there's no LargestImage URI
				download_url = image["ArchivedUri"]

			try:
				while True:
					try:
						r = requests.get(download_url)
						with open(image_path, 'wb') as f:
							for chunk in r.iter_content(chunk_size=128):
								f.write(chunk)
					except requests.exceptions.ConnectionError as ex:
						print("Connection refused" + str(ex))
						sleep(5)
						continue
					break
			except UnicodeEncodeError as ex:
				print("Unicode Error: " + str(ex))
				continue
			except urllib.error.HTTPError as ex:
				print("HTTP Error: " + str(ex))

print("Completed.")

