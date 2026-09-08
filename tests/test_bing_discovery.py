import asyncio
import html
import json
import unittest
from unittest.mock import AsyncMock,patch
from app.html_search import extract,infer,video_page_evidence,search_destination
from app.source_assistant import verify
from app.connectors import Connector


ROOT='https://www.bing.com/videos/search?q={query}'


def card(number):
    url=f'https://www.youtube.com/watch?v=example{number}'
    mid=f'{number:040X}'
    meta=html.escape(json.dumps({'murl':url,'mid':mid,'turl':'https://example.org/thumb.jpg'}),quote=True)
    detail=html.escape(json.dumps({'murl':url,'mid':mid,'vt':f'Science {number}','du':'2:30'}),quote=True)
    return f'<div class="mc_vtvc" mmeta="{meta}"><div vrhm="{detail}"></div></div>'


class BingTests(unittest.TestCase):
    def test_related_queries_are_never_video_results(self):
        markup='<video class="smtplayer"></video>'+''.join(f'<div class="slide"><a href="/videos/search?q=related{i}">Related {i}</a></div>' for i in range(3))
        c=Connector(kind='html',search_url=ROOT,pagination={'mode':'single'},html={'items':'div.slide'}).model_dump()
        with self.assertRaisesRegex(ValueError,'recherches associées'):extract(markup,ROOT.replace('{query}','science'),c)
        self.assertEqual(infer(markup,ROOT.replace('{query}','science'),ROOT),[])

    def test_empty_players_and_unbound_jsonld_are_not_proof(self):
        for markup in ['<video class="preview"></video>','<video src=""></video>',
                       '<video src="javascript:bad"></video>','<meta property="og:video" content="">',
                       '<script type="application/ld+json">{"@type":"VideoObject","name":"empty"}</script>']:
            self.assertFalse(video_page_evidence(markup,'https://example.org/watch/1'))
        self.assertTrue(video_page_evidence('<video><source src="/media.mp4"></video>','https://example.org/watch/1'))

    def test_bing_cards_use_external_destination_not_wrapper(self):
        candidates=infer(card(1)+card(2),ROOT.replace('{query}','science'),ROOT)
        self.assertEqual(len(candidates),1)
        items,_=extract(card(1)+card(2),ROOT.replace('{query}','science'),candidates[0])
        self.assertEqual(items[0]['url'],'https://www.youtube.com/watch?v=example1')
        self.assertEqual(items[0]['title'],'Science 1')
        self.assertEqual(items[0]['duration'],150)
        self.assertEqual(items[0]['_listing_evidence']['method'],'bing_video_card')
        tampered=card(1).replace('example1','example9',1)
        items,_=extract(tampered,ROOT.replace('{query}','science'),candidates[0])
        self.assertIsNone(items[0]['_listing_evidence'])

    def test_other_sites_cannot_claim_bing_card_proof(self):
        c=infer(card(1)+card(2),ROOT.replace('{query}','science'),ROOT)[0]
        c['search_url']='https://example.org/search?q={query}'
        rows,_=extract(card(1),'https://example.org/search?q=science',c)
        self.assertIsNone(rows[0]['_listing_evidence'])

    def test_single_explicit_card_can_be_a_candidate(self):
        self.assertEqual(len(infer(card(1),ROOT.replace('{query}','science'),ROOT)),1)

    def test_malformed_metadata_is_not_proof(self):
        from app.html_search import bing_card_evidence,document
        node=document('<div mmeta="[]"><div vrhm="[]"></div></div>').div
        self.assertIsNone(bing_card_evidence(node,ROOT,'https://example.org/video','Video'))

    def test_same_endpoint_even_with_form_and_tracking(self):
        self.assertTrue(search_destination('https://www.bing.com/videos/search?q=other&&FORM=VRMHRS',ROOT))
        self.assertFalse(search_destination('https://www.youtube.com/watch?v=abc',ROOT))


class VerificationRegression(unittest.IsolatedAsyncioTestCase):
    async def test_verifier_rejects_related_queries_even_if_worker_supplies_them(self):
        c=Connector(kind='html',search_url=ROOT,pagination={'mode':'single'},html={}).model_dump()
        async def worker(payload,**kwargs):
            return {'items':[] if payload['query'].startswith('anytube-no-result') else [{'title':'related','url':ROOT.replace('{query}',payload['query']+'-related')}]}
        with patch('app.main.run_worker',side_effect=worker),patch('app.source_assistant.http',new=AsyncMock(return_value={'text':'<video src="https://example.org/movie.mp4"></video>'})):
            with self.assertRaisesRegex(ValueError,'recherches associées'):await verify(c,['science','music'])
