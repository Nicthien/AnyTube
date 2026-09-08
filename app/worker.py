"""Killable yt-dlp process. JSON protocol, public network only, no shell."""
import ipaddress
import json
import socket
import shutil
import sys
import time
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlencode, quote
from yt_dlp import YoutubeDL
from app.catalog import SEARCH
from app.dailymotion import search_videos as search_dailymotion
from app.connectors import Connector, search_json
from app.access import attach_access
from app.failures import SourceFailure


def protect_network():
    original = socket.getaddrinfo

    def public_addresses(host, port, *args, **kwargs):
        addresses = original(host, port, *args, **kwargs)
        proxy=urlsplit(os.environ.get('ANYTUBE_PROXY',''))
        if proxy.hostname and host==proxy.hostname and int(port)==proxy.port:
            return addresses
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0].split('%')[0])
            mapped = getattr(ip, 'ipv4_mapped', None)
            if not ip.is_global or (mapped and not mapped.is_global):
                raise OSError('Les adresses réseau privées ne sont pas autorisées.')
        return addresses
    socket.getaddrinfo = public_addresses


def web_url(value):
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    if parts.scheme in ('http', 'https') and parts.hostname and not parts.username:
        return value
    return None


def normalize(info):
    target = info.get('webpage_url') or info.get('url')
    # Flat NRK collections contain internal yt-dlp locators, not browser URLs.
    if isinstance(target, str) and re.fullmatch(r'nrk:[A-Za-z]{4}\d{8}', target):
        target = 'https://tv.nrk.no/program/' + target[4:]
    thumbs = info.get('thumbnails') or []
    published = info.get('upload_date') or info.get('timestamp')
    try:
        if isinstance(published, (int, float)):
            published = datetime.fromtimestamp(published, timezone.utc).date().isoformat()
        elif isinstance(published, str):
            published = (datetime.strptime(published, '%Y%m%d') if len(published) == 8 else datetime.fromisoformat(published)).date().isoformat()
        else:
            published = None
    except (ValueError, OverflowError, OSError):
        published = None
    return {
        'id': str(info.get('id', '')),
        'title': info.get('title') or 'Sans titre',
        'url': web_url(target),
        'thumbnail': web_url(info.get('thumbnail') or (thumbs[-1].get('url') if thumbs else None)),
        'description': (info.get('description') or '')[:3000],
        'channel': info.get('channel') or info.get('uploader') or '',
        'duration': info.get('duration'), 'views': info.get('view_count'),
        'published': published,
        'non_media': info.get('anytube_non_media') is True,
        'access_required': info.get('anytube_access_required') is True,
    }


def run(payload):
    if payload['mode'] == 'fetch':
        from app.relay import fetch
        return fetch(payload)
    opts = {'quiet': True, 'noprogress': True, 'no_warnings': True, 'cachedir': False, 'socket_timeout': 12,
            'retries': 1, 'extractor_retries': 1, 'noplaylist': True,
            'proxy': os.environ.get('ANYTUBE_PROXY',''), 'js_runtimes': {'node': {}}, 'ignoreerrors': False}
    credential = payload.get('_credential')
    if payload['mode'] == 'search':
        config = Connector.model_validate(payload['connector']) if payload.get('connector') else None
        if config and config.kind == 'json':
            if 'page_size' in payload:
                from app.adapters import JsonAdapter, PageRequest
                page = JsonAdapter(config.model_dump(), payload.get('_credential')).search(PageRequest(
                    payload['query'], payload['page_size'], payload.get('offset', 0), payload.get('home', False)))
                return {**page, 'items': [normalize(entry) for entry in page['items']]}
            return {'items': [normalize(entry) for entry in search_json(config.model_dump(), payload['query'], payload['limit'], home=payload.get('home', False), credential=payload.get('_credential'))]}
        if config and config.kind != 'ytdlp':
            raise ValueError('Cette source ne propose pas de recherche.')
        key = config.prefix if config else SEARCH[payload['source']][1]
        query = payload['query']
        if key == 'dailymotion':
            return {'items': [normalize(entry) for entry in search_dailymotion(query, payload['limit'])]}
        target = f'{key}{payload["limit"]}:{query}'
        pattern = (config.home_url if payload.get('home') and config.home_url else config.search_url) if config else ''
        if pattern:
            target = pattern.format(query=quote(query, safe=''), limit=payload['limit'])
        elif key == 'ytsearch' and payload.get('home') and payload.get('ranking') == 'views':
            target = 'https://www.youtube.com/results?' + urlencode({'search_query': query, 'sp': 'CAMSAhAB'})
        # A listing never needs playable formats; posts without media must not abort the page.
        opts.update(extract_flat='in_playlist', playlistend=payload['limit'], ignore_no_formats_error=True)
        with YoutubeDL(opts) as ydl:
            attach_access(ydl, credential)
            data = ydl.extract_info(target, download=False)
            items, refused = [], None
            for entry in (data or {}).get('entries', []):
                if not entry:
                    continue
                if not entry.get('title'):
                    try:
                        with YoutubeDL({**opts, 'extract_flat': False}) as detail:
                            attach_access(detail, credential)
                            entry = detail.extract_info(entry['url'], download=False)
                    except Exception as exc:
                        # A listing whose every entry is refused is not an empty listing.
                        from app.failures import classify
                        refused = refused or classify(exc)
                        continue
                item = normalize(entry)
                if config and config.item_url and item['id']:
                    # Some listings inherit the search page as webpage_url; rebuild the item page.
                    item['url'] = config.item_url.format(id=quote(item['id'], safe=''))
                if item['url']:
                    items.append(item)
            if not items and refused:
                raise refused
            return {'items': items}
    if payload['mode'] in ('resolve', 'collection'):
        target = web_url(payload['url'])
        if not target:
            raise ValueError('URL HTTP(S) requise.')
        if payload['mode'] == 'collection':
            offset = payload.get('offset', 0)
            size = min(payload.get('limit', 20), 50)
            opts.update(noplaylist=False, extract_flat='in_playlist', playliststart=offset+1, playlistend=offset+size+1,
                        ignore_no_formats_error=True)
        with YoutubeDL(opts) as ydl:
            attach_access(ydl, credential)
            from app.toongoggles import register_episode
            from app.tubetugraz import register_episode as register_tugraz
            extractor_key = register_tugraz(ydl, target, register_episode(ydl, target, payload.get('extractor_key')))
            if payload['mode'] == 'collection':
                from app.microsoft import AnyTubeMicrosoftLearnPlaylistIE
                from app.arte import AnyTubeArteTVPlaylistIE
                from app.patreon import AnyTubePatreonCampaignIE
                from app.toongoggles import AnyTubeToonGogglesShowIE
                if AnyTubeMicrosoftLearnPlaylistIE.suitable(target):
                    ydl.add_info_extractor(AnyTubeMicrosoftLearnPlaylistIE())
                    extractor_key = AnyTubeMicrosoftLearnPlaylistIE.ie_key()
                elif AnyTubeArteTVPlaylistIE.suitable(target):
                    ydl.add_info_extractor(AnyTubeArteTVPlaylistIE())
                    extractor_key = AnyTubeArteTVPlaylistIE.ie_key()
                elif AnyTubePatreonCampaignIE.suitable(target):
                    ydl.add_info_extractor(AnyTubePatreonCampaignIE())
                    extractor_key = AnyTubePatreonCampaignIE.ie_key()
                elif AnyTubeToonGogglesShowIE.suitable(target):
                    ydl.add_info_extractor(AnyTubeToonGogglesShowIE())
                    extractor_key = AnyTubeToonGogglesShowIE.ie_key()
            info = ydl.extract_info(target, download=False, ie_key=extractor_key)
        if not info:
            raise SourceFailure('invalid_response')
        if payload['mode'] == 'collection':
            entries = list(info.get('entries') or [])
            if info.get('_type') not in ('playlist', 'multi_video'):
                raise ValueError('Cette URL ne désigne pas une collection.')
            items = [normalize(entry) for entry in entries if entry]
            return {'title': str(info.get('title') or 'Collection')[:500],
                    'items': [item for item in items[:size] if item['url']], 'has_more': len(entries) > size}
        if info.get('has_drm'):
            raise SourceFailure('drm_protected')
        formats = []
        for item in info.get('formats') or [info]:
            if item.get('has_drm') or not web_url(item.get('url')):
                continue
            formats.append({key: item.get(key) for key in ('format_id', 'url', 'manifest_url', 'ext', 'protocol',
                'width', 'height', 'vcodec', 'acodec', 'language', 'tbr', 'filesize', 'http_headers')})
        subtitles = {language: [{'url': entry['url'], 'ext': entry.get('ext')} for entry in entries
                                if web_url(entry.get('url')) and entry.get('ext') in ('vtt', 'srt')]
                     for language, entries in (info.get('subtitles') or {}).items()}
        return {'video': normalize(info), 'formats': formats, 'subtitles': subtitles,
                'is_live': bool(info.get('is_live')), 'live_status': info.get('live_status'),
                'http_headers': info.get('http_headers') or {}}
    if payload['mode'] == 'media':
        target = web_url(payload['url'])
        if not target:
            raise ValueError('URL HTTP(S) requise.')
        folder = Path(payload['folder'])
        max_bytes = min(payload.get('max_bytes',500*1024**2),10*1024**3)
        max_height = min(payload.get('max_height',720),2160)
        audio_only = payload.get('media_kind') == 'audio'

        downloaded = {}
        last_progress = 0

        def limit(progress):
            nonlocal last_progress
            downloaded[progress.get('filename', '')] = progress.get('downloaded_bytes', 0)
            if sum(downloaded.values()) > max_bytes:
                raise ValueError('Le média dépasse la limite de taille réservée.')
            if shutil.disk_usage(folder).free < 100*1024**2:
                raise ValueError('Espace disque insuffisant.')
            if time.monotonic()-last_progress > 1:
                total = progress.get('total_bytes') or progress.get('total_bytes_estimate') or max_bytes
                percent = min(99,int(progress.get('downloaded_bytes',0)*100/max(total,1)))
                temporary = folder / 'progress.tmp'
                temporary.write_text(json.dumps({'percent':percent}))
                temporary.replace(folder / 'progress.json')
                last_progress = time.monotonic()

        # Native HTTP/HLS/DASH only. Even HlsFD's implicit FFmpeg fallback is blocked.
        from yt_dlp.downloader.external import FFmpegFD
        def forbid_network_downloader(*args, **kwargs):
            raise SourceFailure('unavailable_format')
        FFmpegFD.real_download = forbid_network_downloader
        protocol = '[protocol~="^(https?|m3u8_native|m3u8|http_dash_segments)$"]'
        progressive = f'best[ext=mp4][vcodec^=avc][acodec!=none]{protocol}[height<={max_height}]'
        separate = f'bestvideo[ext=mp4][vcodec^=avc]{protocol}[height<={max_height}]+bestaudio[ext=m4a]{protocol}'
        if audio_only and not shutil.which('ffmpeg'):
            raise SourceFailure('unavailable_format')
        opts.update(format=f'{separate}/{progressive}' if shutil.which('ffmpeg') else progressive,
                    outtmpl=str(folder / 'video.%(ext)s'), max_filesize=max_bytes,
                    progress_hooks=[limit], continuedl=False, skip_unavailable_fragments=False, merge_output_format='mp4',
                    external_downloader={'default':'native'}, hls_prefer_native=True,
                    postprocessor_args={'Merger+ffmpeg_o': ['-movflags', '+faststart'],
                                        'ffmpeg_i': ['-protocol_whitelist', 'file,pipe']})
        if audio_only:
            opts.update(format=f'bestaudio{protocol}/best{protocol}', outtmpl=str(folder/'audio.%(ext)s'),
                        postprocessors=[{'key':'FFmpegExtractAudio','preferredcodec':'m4a'}])
        def reject_live(info, *, incomplete=False):
            if info.get('is_live'):
                return 'L’enregistrement du direct n’est pas encore disponible. Utilisez la lecture en direct.'
            if info.get('has_drm'):
                return 'Média protégé par DRM.'
        opts['match_filter'] = reject_live
        with YoutubeDL(opts) as ydl:
            attach_access(ydl, credential)
            from app.toongoggles import register_episode
            from app.tubetugraz import register_episode as register_tugraz
            info = ydl.extract_info(target, download=True,
                                    ie_key=register_tugraz(ydl, target, register_episode(ydl, target, payload.get('extractor_key'))))
        filename = 'audio.m4a' if audio_only else 'video.mp4'
        if not (folder / filename).is_file():
            raise SourceFailure('unavailable_format')
        if (folder / filename).stat().st_size > max_bytes:
            raise ValueError('Le fichier final dépasse le quota réservé.')
        probe = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                '-show_entries', 'format=duration:stream=codec_type,codec_name',
                                '-of', 'json', str(folder / filename)], capture_output=True, timeout=30)
        if probe.returncode:
            raise SourceFailure('unavailable_format')
        metadata = json.loads(probe.stdout)
        kinds = {stream.get('codec_type') for stream in metadata.get('streams', [])}
        if float(metadata.get('format', {}).get('duration', 0)) <= 0 or 'audio' not in kinds or (not audio_only and 'video' not in kinds):
            raise SourceFailure('unavailable_format')
        return {'video': normalize(info), 'filename':filename, 'media_type':'audio/mp4' if audio_only else 'video/mp4'}
    raise ValueError('Opération inconnue.')


if __name__ == '__main__':
    protect_network()
    from app.source_diagnostics import sink,ControlError
    diagnostics=[]
    payload=json.load(sys.stdin)
    if payload.get('_discovery_diagnostics'):sink.set(lambda row: diagnostics.append(row) if len(diagnostics)<20 else None)
    try:
        result=run(payload)
        if payload.get('_discovery_diagnostics'):result['_diagnostics']=diagnostics
        print(json.dumps(result, ensure_ascii=True))
    except Exception as exc:
        from app.failures import classify
        failure = classify(exc)
        print(json.dumps({'error': str(failure), 'code': failure.code, 'retry_after': failure.retry_after,'_diagnostics':diagnostics,'control_error':{'code':exc.code,'message':str(exc),'correctable':exc.correctable} if isinstance(exc,ControlError) else None}))
        sys.exit(1)
