import asyncio
import json
import unittest
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch, AsyncMock
from app.html_search import HtmlSpec, extract, infer, template_from_example, duration, search
from app.connectors import Connector
from app import source_assistant as sa
import test_source_assistant as existing


ROOT='https://example.org'


def cards(query, page=1):
    if query.startswith('anytube-no-result-'):
        return '<main>Aucun résultat</main>'
    rows=''.join(f'<article class="video"><h2><a href="/watch/{query}-{page}-{i}">{query} épisode {i}</a></h2><time>01:25</time></article>' for i in range(3))
    return rows+(f'<a rel="next" href="/search?q={query}&page=2">Suivant</a>' if page==1 else '')


def config(rendering='http'):
    return Connector(kind='html',search_url=ROOT+'/search?q={query}',pagination={'mode':'page'},
        html={'rendering':rendering,'items':'article.video','title':{'selector':'h2 a'},
              'link':{'selector':'h2 a','attribute':'href'},'duration':{'selector':'time'},'next_selector':'a[rel="next"]'}).model_dump()


async def fetch(url, **kwargs):
    parts=urlsplit(url)
    if parts.path=='/observe':
        body=kwargs['body']
        parsed=urlsplit(body['url']);q=parse_qs(parsed.query).get('q',[body['query']])[0]
        return {'text':json.dumps({'url':body['url'],'html':cards(q),'samples':[]})}
    if '/watch/' in parts.path:
        return {'url':url,'text':'<meta property="og:video" content="https://example.org/media.mp4">'}
    if parts.path=='/search':
        params=parse_qs(parts.query)
        return {'url':url,'text':cards(params['q'][0],int(params.get('page',['1'])[0]))}
    if parts.path.endswith('/config'):
        return {'url':url,'text':'{}'}
    return {'url':url,'text':'<form action="/search"><input type="search" name="q"></form>'}


class HtmlTests(unittest.TestCase):
    def test_inference_and_relative_urls(self):
        candidates=infer(cards('science'),ROOT+'/search?q=science',ROOT+'/search?q={query}')
        self.assertTrue(candidates)
        entries,next_url=extract(cards('science'),ROOT,candidates[0])
        self.assertEqual(len(entries),3)
        self.assertEqual(entries[0]['url'],ROOT+'/watch/science-1-0')
        self.assertEqual(entries[0]['duration'],85)
        self.assertTrue(next_url.endswith('page=2'))

    def test_missing_required_and_optional_fields(self):
        with self.assertRaises(ValueError):extract('<article class="video">Absent</article>',ROOT,config())
        entries,_=extract(cards('music'),ROOT,config())
        self.assertIsNone(entries[0]['thumbnail'])

    def test_selectors_bounded_and_not_executable(self):
        for value in ('article:has(a)', 'a[', 'a'*201):
            with self.assertRaises(ValueError):HtmlSpec(items=value)

    def test_secret_and_private_links_rejected(self):
        for url in ('http://127.0.0.1/x','https://example.org/watch?token=secret'):
            with self.assertRaises(ValueError):extract(f'<article class="video"><h2><a href="{url}">title</a></h2></article>',ROOT,config())

    def test_durations(self):
        self.assertEqual(duration('01:02:03'),3723)
        self.assertEqual(duration('85000','milliseconds'),85)
        self.assertIsNone(duration('missing'))

    def test_examples_and_ambiguous_query(self):
        self.assertEqual(template_from_example(ROOT+'/search?q=chat+noir','chat noir'),ROOT+'/search?q={query}')
        with self.assertRaises(ValueError):template_from_example(ROOT+'/search?q=a&other=a','a')
        with self.assertRaises(ValueError):sa.Start(target=ROOT,video_examples=['http://localhost/a'])
        with self.assertRaises(ValueError):sa.Start(target=ROOT,search_example_url=ROOT+'/search?q=a')
        with self.assertRaises(ValueError):sa.Start(target=ROOT,video_examples=[ROOT+f'/{i}' for i in range(6)])

    def test_navigation_links_not_inferred_as_video(self):
        self.assertEqual(infer('<nav><a href="/about">About</a><a href="/contact">Contact</a></nav>',ROOT,ROOT+'/search?q={query}'),[])


class HtmlAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_normal_page_and_second_page(self):
        with patch.object(sa,'http',side_effect=fetch):
            first=await search({'connector':config(),'query':'science','page_size':3})
            second=await search({'connector':config(),'query':'science','page_size':3,'offset':3})
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertTrue(set(i['url'] for i in first['items']).isdisjoint(i['url'] for i in second['items']))

    async def test_repeated_page_rejected(self):
        with patch.object(sa,'http',new=AsyncMock(return_value={'text':cards('same'),'url':ROOT})):
            with self.assertRaises(ValueError):await search({'connector':config(),'query':'science','page_size':3,'offset':3})

    async def test_browser_absent(self):
        with patch.object(sa,'settings',return_value=sa.Settings()):
            with self.assertRaisesRegex(Exception,'navigateur'):await search({'connector':config('chromium'),'query':'science'})

    async def test_all_video_pages_checked(self):
        with patch.object(sa,'http',side_effect=fetch):
            proof=await sa.verify(config(),['science','music'])
        self.assertEqual(proof['pagination'],'verified')
        self.assertIn('browser_playback',proof['unverified'])

    async def test_nonvideo_pages_block_autoadd(self):
        async def ordinary(url,**kwargs):
            if '/watch/' in url:return {'text':'<h1>ordinary article</h1>'}
            return await fetch(url,**kwargs)
        with patch.object(sa,'http',side_effect=ordinary):
            with self.assertRaisesRegex(ValueError,'vidéo non confirmées'):await sa.verify(config(),['science','music'])

    async def test_cancel_network(self):
        event=asyncio.Event()
        async def hanging(*args,**kwargs):
            event.set();await asyncio.sleep(100)
        with patch.object(sa,'http',side_effect=hanging):
            task=asyncio.create_task(search({'connector':config(),'query':'science'}))
            await event.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task


class HtmlAPITests(unittest.TestCase):
    setUp=existing.AssistantAPITests.setUp
    tearDown=existing.AssistantAPITests.tearDown
    start=existing.AssistantAPITests.start

    def test_full_discovery_then_normal_search_and_resume(self):
        job=self.start(video_examples=[ROOT+'/watch/science-1-0',ROOT+'/watch/science-1-1'],search_example_url=ROOT+'/search?q=science',search_example_query='science')
        with patch.object(sa,'http',side_effect=fetch):
            asyncio.run(sa.execute(job['id']))
            saved=sa.load(job['id'])
            self.assertEqual(saved['status'],'added',saved)
            response=self.client.post('/api/search',headers=self.headers,json={'query':'science','sources':[saved['added_source']],'limit':3})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(response.json()['items']),3)
            next_page=self.client.post('/api/search',headers=self.headers,json={'query':'science','sources':[saved['added_source']],'limit':3,'cursors':response.json()['next_cursors']})
            self.assertEqual(len(next_page.json()['items']),3)
            with patch.object(sa,'launch'):
                retry=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',headers=self.headers,json={})
            self.assertEqual(retry.status_code,201,retry.text)
            self.assertEqual(retry.json()['parent_job'],job['id'])
            asyncio.run(sa.execute(retry.json()['id']))
            self.assertEqual(sa.load(retry.json()['id'])['added_source'],saved['added_source'])

    def test_active_resume_refused(self):
        job=self.start()
        response=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',headers=self.headers,json={})
        self.assertEqual(response.status_code,409)

    def test_resume_owner_isolation(self):
        from app.store import current_user
        job=self.start();sa.update(job['id'],'interrupted')
        token=current_user.set('another-user')
        try:
            with self.assertRaises(Exception):asyncio.run(sa.resume(job['id'],sa.Resume()))
        finally:current_user.reset(token)
