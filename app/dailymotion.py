"""Public video search via the Dailymotion legacy catalog API.

The yt-dlp GraphQL search extractor can return an empty list for valid queries.
Keep yt-dlp for media extraction, but use catalog metadata for search cards.
"""
import json
import re
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from yt_dlp.utils import clean_html

FIELDS = 'id,title,description,thumbnail_480_url,duration,views_total,owner.screenname'


def search_videos(query, limit):
    params = urlencode({'search': query, 'sort': 'relevance', 'limit': limit, 'fields': FIELDS})
    request = Request(f'https://api.dailymotion.com/videos?{params}', headers={'Accept': 'application/json'})
    # Requests still pass through the worker's public-IP guard; ignore host proxy settings.
    with build_opener(ProxyHandler({})).open(request, timeout=12) as response:
        data = json.load(response)
    if not isinstance(data, dict) or data.get('error') or not isinstance(data.get('list'), list):
        raise ValueError('Réponse de recherche Dailymotion invalide.')
    items = []
    for entry in data['list'][:limit]:
        if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                or not re.fullmatch(r'[a-zA-Z0-9]+', entry['id'])
                or not isinstance(entry.get('title'), str)):
            raise ValueError('Métadonnées de recherche Dailymotion invalides.')
        items.append({
            'id': entry['id'], 'title': entry['title'],
            'webpage_url': f'https://www.dailymotion.com/video/{entry["id"]}',
            'thumbnail': entry.get('thumbnail_480_url'),
            'description': clean_html(entry.get('description') or ''),
            'uploader': entry.get('owner.screenname') or '',
            'duration': entry.get('duration'), 'view_count': entry.get('views_total'),
        })
    return items
