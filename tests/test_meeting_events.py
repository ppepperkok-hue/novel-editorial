"""Meeting event hub tests: subscribe, fan-out, unsubscribe."""

import unittest

from tools import meeting_events


class MeetingEventHubTests(unittest.TestCase):
    def setUp(self):
        self.hub = meeting_events.MeetingEventHub()

    def test_publish_fans_out_to_subscribers(self):
        q1 = self.hub.subscribe(1)
        q2 = self.hub.subscribe(1)
        self.hub.publish(1, {"type": "message", "agent": "planner"})
        self.assertEqual(q1.get(timeout=1), '{"type": "message", "agent": "planner"}')
        self.assertEqual(q2.get(timeout=1), '{"type": "message", "agent": "planner"}')

    def test_unsubscribe_stops_delivery(self):
        q1 = self.hub.subscribe(2)
        self.hub.unsubscribe(2, q1)
        self.hub.publish(2, {"type": "message"})
        self.assertEqual(self.hub.subscriber_count(2), 0)
        self.assertTrue(q1.empty())

    def test_publish_to_empty_session_is_noop(self):
        self.hub.publish(99, {"type": "heartbeat"})
        self.assertEqual(self.hub.subscriber_count(99), 0)


if __name__ == "__main__":
    unittest.main()
