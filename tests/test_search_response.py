import unittest
from unittest.mock import patch, AsyncMock
from app.search_response import classify, require_usable
from app.source_diagnostics import ControlError, sink
from app.html_search import infer, extract
from app import source_assistant as sa
from test_source_assistant import config

BASE='https://example.org'

class Responses(unittest.TestCase):
    def test_json_error_cannot_hide_behind_results(self):
        self.assertEqual(classify('{"error":"invalid search","items":[{"title":"Film"}]}',BASE,200)[0],'error_page')
        self.assertEqual(classify('{broken',BASE,200)[0],'ambiguous')

    def test_error_routes_with_rotating_recommendations(self):
        for suffix in ('/errors/invalid_search_type','/errors.php','/404'):
            for item in range(3):
                with self.assertRaises(ControlError):
                    require_usable(f'<article><a href="/watch/{item}">Film {item}</a></article>',BASE+suffix,200)

    def test_dominant_error_and_access(self):
        for html,expected in [('<h1>Page not found</h1>','error_page'),('<main>Invalid search type</main>','error_page'),('<h1>Verify you are human</h1>','access_required'),('<article><h2>404 explained</h2></article>','usable')]:
            self.assertEqual(classify(html,BASE,200)[0],expected)

    def test_image_link_then_title_and_attributes(self):
        for body in ('<div class="thumb"><a href="/watch/{i}"><img></a></div><div class="caption"><a href="/watch/{i}">Film {i}</a></div>', '<a href="/watch/{i}"><img></a><a href="/watch/{i}">Film {i}</a>',
                     '<a href="/watch/{i}" title="Film {i}"><img></a>',
                     '<a href="/watch/{i}"><img alt="Film {i}"></a>',
                     '<a href="/watch/{i}"><img></a><h3><a href="/watch/{i}">Film {i}</a></h3>'):
            html=''.join('<div class="card">'+body.format(i=i)+'</div>' for i in range(4))
            candidates=infer(html,BASE,BASE+'/search?q={query}')
            self.assertTrue(candidates,body)
            rows,_=extract(html,BASE,candidates[0])
            self.assertEqual([r['title'] for r in rows],['Film '+str(i) for i in range(4)])

    def test_ambiguous_cards_not_silently_discarded(self):
        html='<article><a href="/watch/1">One</a><a href="/watch/2">Two</a></article>'*3
        self.assertFalse(infer(html,BASE,BASE+'/search?q={query}'))

    def test_missing_field_counts_inspected_cards(self):
        c={'search_url':BASE+'/search?q={query}','html':{'items':'article','title':{'selector':'h2'},'link':{'selector':'a','attribute':'href'}}}
        rows=[];token=sink.set(rows.append)
        try:
            with self.assertRaises(ControlError):extract('<article><a href="/watch/1">One</a></article>'*25,BASE,c)
        finally:sink.reset(token)
        self.assertEqual((rows[-1]['selected_count'],rows[-1]['inspected_count'],rows[-1]['missing_field']),(25,1,'title'))


class SearchControls(unittest.IsolatedAsyncioTestCase):
    async def test_stability_and_nonempty_witness(self):
        def items(ids):return {'items':[{'title':'Film','url':BASE+'/watch/'+str(i)} for i in ids]}
        cases=[([range(20),range(30,50),[],range(10,30)],None),
               ([range(20),range(30,50),[],range(15,35)],'unstable_results'),
               ([range(20),range(30,50),range(60,80)],'witness_repeated')]
        c=config();c['pagination']['mode']='single'
        for responses,error in cases:
            worker=AsyncMock(side_effect=[items(ids) for ids in responses])
            with patch('app.main.run_worker',worker):
                if error:
                    with self.assertRaises(ControlError) as raised:await sa.verify(c,['science','music'])
                    self.assertEqual(raised.exception.code,error)
                else:self.assertEqual((await sa.verify(c,['science','music']))['search'],'verified')
            self.assertEqual(worker.await_count,len(responses))
            self.assertEqual(worker.call_args_list[0].args[0]['limit'],20)

    async def test_error_page_never_reaches_video_check(self):
        from app.html_search import search
        c={'kind':'html','search_url':BASE+'/search?q={query}','html':{'items':'article'},'pagination':{'mode':'single'}}
        response={'text':'<article><a href="/watch/1">Film</a></article>','url':BASE+'/errors/missing','status':200}
        with patch.object(sa,'http',AsyncMock(return_value=response)),patch.object(sa,'confirm_video_page',AsyncMock()) as video:
            with self.assertRaises(ControlError):await search({'connector':c,'query':'science'})
            video.assert_not_called()
