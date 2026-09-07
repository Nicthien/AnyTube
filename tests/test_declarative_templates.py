"""Adding declarative source data must not invalidate unrelated connector evidence."""
import copy
import unittest
from unittest.mock import patch
from app.catalog import declarative_templates
from app.connectors import Connector, default_connector
from app.verification import revision


class DeclarativeTemplateTests(unittest.TestCase):
    def test_every_delivered_template_validates_and_retains_identity(self):
        for name, entry in declarative_templates().items():
            with self.subTest(name=name):
                config = Connector.model_validate(entry['connector'])
                self.assertEqual(config.extractor, name)
                self.assertEqual(config.model_dump(), default_connector(name))

    def test_template_change_invalidates_only_its_configuration(self):
        before = {name: revision(default_connector(name)) for name in ('NRKTV', 'Wikimedia')}
        changed = copy.deepcopy(declarative_templates())
        changed['NRKTV']['connector']['home_query'] = 'musikk'
        with patch('app.catalog.declarative_templates', return_value=changed):
            self.assertNotEqual(revision(default_connector('NRKTV')), before['NRKTV'])
            self.assertEqual(revision(default_connector('Wikimedia')), before['Wikimedia'])

    def test_editorial_label_does_not_change_execution_revision(self):
        before = revision(default_connector('NRKTV'))
        changed = copy.deepcopy(declarative_templates())
        changed['NRKTV']['name'] = 'Updated label'
        with patch('app.catalog.declarative_templates', return_value=changed):
            self.assertEqual(revision(default_connector('NRKTV')), before)
