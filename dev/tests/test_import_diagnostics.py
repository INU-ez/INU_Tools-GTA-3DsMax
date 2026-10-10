"""Import diagnostics must never start an asynchronous Python frame walker."""
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import inu_boot
from inu_max import diag
from inu_max.ops.inu_import import _logged_files


class ImportDiagnosticsTests(unittest.TestCase):
    def tearDown(self):
        diag.stop()

    def test_trace_logs_progress_without_faulthandler(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(diag, 'path', return_value=str(Path(folder)/'trace.txt')), \
                patch('faulthandler.dump_traceback_later') as schedule, \
                patch('faulthandler.cancel_dump_traceback_later') as cancel, \
                patch('sys.stdout', new=io.StringIO()):
            generation = diag.start('import 80 file(s)')
            self.assertEqual(generation, diag.generation())
            diag.mark('DFF 80/80: model_80.dff')
            logfile = diag._FILE
            diag.stop(generation)
            self.assertTrue(logfile.closed)
            text = Path(folder, 'trace.txt').read_text(encoding='utf-8')
            self.assertIn('import 80 file(s)', text)
            self.assertIn('DFF 80/80: model_80.dff', text)
            schedule.assert_not_called()
            cancel.assert_not_called()

    def test_stale_timer_cannot_close_a_new_import_log(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(diag, 'path', return_value=str(Path(folder)/'trace.txt')):
            previous = diag.start('old')
            old_file = diag._FILE
            current = diag.start('new')
            self.assertTrue(old_file.closed)
            diag.stop(previous)
            self.assertFalse(diag._FILE.closed)
            diag.stop(current)
            self.assertIsNone(diag._FILE)

    def test_reload_stops_previous_diagnostics_before_removing_modules(self):
        def stop():
            self.assertIs(sys.modules['inu_max.diag'], previous)
        previous = SimpleNamespace(stop=Mock(side_effect=stop))
        with patch.dict(sys.modules, {'inu_max.diag': previous}):
            inu_boot._reload_inu_max()
            previous.stop.assert_called_once_with()
            self.assertNotIn('inu_max.diag', sys.modules)

    def test_file_progress_preserves_order_and_paths(self):
        paths = ['models/first.dff', 'models/second.dff']
        with patch.object(diag, 'mark') as mark:
            self.assertEqual(list(_logged_files('DFF', paths)), paths)
            self.assertEqual([call.args[0] for call in mark.call_args_list],
                             ['DFF 1/2: first.dff', 'DFF 2/2: second.dff'])

    def test_progress_spans_formats_and_reaches_completion(self):
        state = {'done': 0, 'total': 3, 'cancelled': False}
        progress = Mock(return_value=True)
        with patch.object(diag, 'mark'):
            self.assertEqual(list(_logged_files('TXD', ['a.txd'], progress, state)), ['a.txd'])
            self.assertEqual(list(_logged_files('DFF', ['a.dff', 'b.dff'], progress, state)),
                             ['a.dff', 'b.dff'])
        self.assertEqual([call.args[0] for call in progress.call_args_list], [0,1,1,2,2,3])
        self.assertEqual(state['done'], 3)
        self.assertFalse(state['cancelled'])

    def test_cancel_keeps_completed_file_and_skips_later_formats(self):
        state = {'done': 0, 'total': 3, 'cancelled': False}
        progress = Mock(side_effect=[True, False])
        with patch.object(diag, 'mark'):
            self.assertEqual(list(_logged_files('DFF', ['a.dff', 'b.dff'], progress, state)),
                             ['a.dff'])
            self.assertEqual(list(_logged_files('COL', ['a.col'], progress, state)), [])
        self.assertEqual(state['done'], 1)
        self.assertTrue(state['cancelled'])

    def test_cancel_before_first_file_and_at_completion(self):
        with patch.object(diag, 'mark'):
            self.assertEqual(list(_logged_files('DFF', ['a.dff'], lambda *args: False)), [])
            state = {'done': 0, 'total': 1, 'cancelled': False}
            self.assertEqual(list(_logged_files('DFF', ['a.dff'],
                                               Mock(side_effect=[True, False]), state)), ['a.dff'])
            self.assertFalse(state['cancelled'])
