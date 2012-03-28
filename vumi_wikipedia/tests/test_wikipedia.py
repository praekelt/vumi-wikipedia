"""Tests for vumi.demos.wikipedia."""

import json
from functools import wraps
from pkg_resources import resource_stream

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import Protocol, Factory
from twisted.trial.unittest import TestCase

from vumi.tests.fake_amqp import FakeAMQPBroker
from vumi.tests.utils import get_stubbed_worker
from vumi.message import TransportUserMessage

from vumi_wikipedia.wikipedia import WikipediaAPI, WikipediaWorker
from vumi_wikipedia.tests.test_wikipedia_api import FakeHTTPTestCaseMixin, WIKIPEDIA_RESPONSES, debug_api_call

class WikipediaWorkerTestCase(TestCase, FakeHTTPTestCaseMixin):
    transport_name = 'sphex'

    timeout = 10

    @inlineCallbacks
    def setUp(self):
        yield self.start_webserver(WIKIPEDIA_RESPONSES)
        self.broker = FakeAMQPBroker()
        self._workers = []
        yield self.get_worker()

    @inlineCallbacks
    def tearDown(self):
        for w in self._workers:
            yield w.stopWorker()
        yield self.stop_webserver()

    @inlineCallbacks
    def get_worker(self, **config_extras):
        if hasattr(self, 'worker'):
            self._workers.remove(self.worker)
            yield self.worker.stopWorker()
        config = {
            'transport_name': self.transport_name,
            'worker_name': 'wikitest',
            'sms_transport': 'sphex',
            'api_url': self.url,
            }
        config.update(config_extras)
        self.worker = get_stubbed_worker(WikipediaWorker, config, self.broker)
        self._workers.append(self.worker)
        yield self.worker.startWorker()
        self.wikipedia = self.worker.wikipedia
        returnValue(self.worker)

    def mkmsg_in(self, content):
        return TransportUserMessage(
            from_addr='+41791234567',
            to_addr='9292',
            message_id='abc',
            transport_name=self.transport_name,
            transport_type='ussd',
            transport_metadata={},
            content=content,
            )

    def rkey(self, name):
        return "%s.%s" % (self.transport_name, name)

    def dispatch(self, message, rkey=None, exchange='vumi'):
        if rkey is None:
            rkey = self.rkey('inbound')
        self.broker.publish_message(exchange, rkey, message)
        return self.broker.kick_delivery()

    def get_dispatched_messages(self):
        return self.broker.get_messages('vumi', self.rkey('outbound'))

    @inlineCallbacks
    def search_for_content(self, search, result=1, section=1):
        yield self.dispatch(self.mkmsg_in(None))  # Start session.
        yield self.dispatch(self.mkmsg_in(search))  # Search keyword.
        yield self.dispatch(self.mkmsg_in(str(result)))  # Select result.
        yield self.dispatch(self.mkmsg_in(str(section)))  # Select section.

    def test_make_options(self):
        self.assertEqual((2, "1. foo\n2. bar"),
                         self.worker.make_options(['foo', 'bar']))

    @inlineCallbacks
    def test_happy_flow(self):
        yield self.dispatch(self.mkmsg_in(None))
        self.assertEqual('What would you like to search Wikipedia for?',
                         self.get_dispatched_messages()[-1]['content'])

        yield self.dispatch(self.mkmsg_in('cthulhu'))
        self.assertEqual('\n'.join([
                    u'1. Cthulhu',
                    u'2. Call of Cthulhu (role-playing game)',
                    u'3. Cthulhu (2007 film)',
                    u'4. Cthulhu (2000 film)',
                    u'5. Cthulhu Mythos',
                    u'6. The Call of Cthulhu',
                    ]),
                         self.get_dispatched_messages()[-1]['content'])

        yield self.dispatch(self.mkmsg_in('1'))
        self.assertEqual('\n'.join([
                    u'1. Cthulhu',
                    u'2. History',
                    u'3. Geography',
                    u'4. Mountains of Madness',
                    u'5. Lulz',
                    ]),
                         self.get_dispatched_messages()[-1]['content'])

        yield self.dispatch(self.mkmsg_in('2'))
        content = (
            u'The first half of the principal manuscript told a very peculiar tale. '
            u'It appears that on 1 March 1925, a thin, dark young man of neurotic and '
            u'excited aspect had called upon Professor Angell bearing the singular clay '
            u'bas-relief, which was then exceedingly damp and fresh.')
        self.assertEqual(
            "%s...\n(Full content sent by SMS.)" % (content[:100],),
            self.get_dispatched_messages()[-2]['content'])
        self.assertEqual(content[:250],
                         self.get_dispatched_messages()[-1]['content'])

