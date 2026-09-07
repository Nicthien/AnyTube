"""Keep public post metadata when browsing Patreon campaigns."""
from urllib.parse import urljoin, urlsplit

from yt_dlp.extractor.patreon import PatreonCampaignIE, PatreonIE
from yt_dlp.utils import unified_strdate


class AnyTubePatreonCampaignIE(PatreonCampaignIE):
    def _entries(self, campaign_id):
        params = {
            'fields[post]': 'patreon_url,url,title,published_at,post_type,current_user_can_view',
            'filter[campaign_id]': campaign_id,
            'filter[is_draft]': 'false',
            'sort': '-published_at',
            'json-api-use-default-includes': 'false',
        }
        seen_cursors = set()
        while True:
            data = self._call_api('posts', campaign_id, query=dict(params))
            for post in data.get('data') or []:
                attributes = post.get('attributes') or {}
                path = attributes.get('url') or attributes.get('patreon_url')
                if not isinstance(path, str):
                    continue
                url = urljoin('https://www.patreon.com/', path)
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or parsed.hostname not in ('patreon.com', 'www.patreon.com'):
                    continue
                yield self.url_result(
                    url, PatreonIE, video_id=post.get('id'),
                    video_title=attributes.get('title'),
                    upload_date=unified_strdate(attributes.get('published_at')),
                    anytube_non_media=attributes.get('post_type') in ('text_only', 'image_file', 'link'),
                    anytube_access_required=attributes.get('current_user_can_view') is False,
                )
            cursor = ((data.get('meta') or {}).get('pagination') or {}).get('cursors', {}).get('next')
            if not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)
            params['page[cursor]'] = cursor
