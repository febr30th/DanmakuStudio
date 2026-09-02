"""GUI 后台任务取消测试。"""

from danmakustudio.batch import BatchJob
from danmakustudio.config.models import EncodeMode
from danmakustudio.ui.worker import BatchWorker


def test_request_cancel_notifies_active_burner():
    worker = BatchWorker([], EncodeMode.AUTO, None, False)

    class FakeBurner:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    burner = FakeBurner()
    worker._burner = burner

    worker.request_cancel()

    assert worker._cancel_event.is_set()
    assert burner.cancelled


def test_cancel_requested_before_run_emits_cancelled_summary(qapp, tmp_path):
    job = BatchJob.single(tmp_path / "video.mp4", tmp_path / "video.xml")
    worker = BatchWorker([job], EncodeMode.AUTO, None, False)
    summaries = []
    worker.summary.connect(lambda *values: summaries.append(values))
    worker.request_cancel()

    worker.run()

    assert summaries == [(1, 0, 0, 0, True)]
