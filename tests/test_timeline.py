import unittest
from reserve_odometry.core import Sample
from reserve_odometry.timeline import Timeline


class TimelineTests(unittest.TestCase):
    def test_rejects_unknown_channel(self):
        with self.assertRaises(ValueError):
            Timeline().ingest(3, Sample(1, 0))

    def test_bounded_queue(self):
        t = Timeline()
        for i in range(300):
            t.ingest(1, Sample(i * .01 + 1, 4))
        self.assertEqual(len(t.queues[1]), 128)
        self.assertEqual(t.dropped, 172)

    def test_duplicate_does_not_replace_value(self):
        t = Timeline()
        self.assertTrue(t.ingest(1, Sample(1, 4)))
        self.assertFalse(t.ingest(1, Sample(1, 99)))
        self.assertEqual(t.queues[1][0].value, 4)

    def test_future_inputs_are_not_used_at_earlier_tick(self):
        t = Timeline(delay_s=0)
        for ch, value in ((0, 0), (1, 4), (2, 4)):
            t.ingest(ch, Sample(10, value))
        list(t.advance(10))
        t.ingest(1, Sample(10.2, 12))
        output = list(t.advance(10.1))
        self.assertTrue(output)
        for e, held in output:
            self.assertLessEqual(held[1].t, e.t)
            self.assertEqual(held[1].value, 4)

    def test_clock_paused_does_not_integrate(self):
        t = Timeline(delay_s=0)
        for ch, value in ((0, 0), (1, 4), (2, 4)):
            t.ingest(ch, Sample(1, value))
        list(t.advance(1))
        self.assertEqual(list(t.advance(1)), [])
        self.assertEqual(t.observer.s, 0)

    def test_out_of_order_inputs_sorted_before_use(self):
        t = Timeline(delay_s=0)
        t.ingest(0, Sample(1, 0))
        t.ingest(1, Sample(1.1, 5))
        t.ingest(1, Sample(1, 4))
        t.ingest(2, Sample(1, 4))
        list(t.advance(1))
        self.assertEqual(t.held[1], Sample(1, 4))

    def test_reset_clears_all_input_state(self):
        t = Timeline()
        t.ingest(1, Sample(1, 4))
        t.reset()
        self.assertEqual(t.queues, [[], [], []])
        self.assertIsNone(t.latest)

    def test_old_sample_cannot_rewrite_estimated_past(self):
        t = Timeline(delay_s=0)
        for ch, value in ((0, 0), (1, 4), (2, 4)):
            t.ingest(ch, Sample(2, value))
        list(t.advance(2))
        self.assertFalse(t.ingest(1, Sample(1.9, 99)))
        self.assertEqual(t.observer.v, 4)
