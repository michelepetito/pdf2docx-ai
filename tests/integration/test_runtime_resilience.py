"""Restricted macOS environments can deny process-tree enumeration."""
from types import SimpleNamespace

from pdf2docx_ai import pipeline


def test_memory_sampling_retains_own_rss_when_children_are_denied(monkeypatch):
    class RestrictedProcess:
        def memory_info(self):
            return SimpleNamespace(rss=1024 * 1024)

        def children(self, recursive=True):
            raise PermissionError("sysctl denied by macOS sandbox")

    class OneIteration:
        def __init__(self):
            self.done = False

        def is_set(self):
            return self.done

        def wait(self, timeout):
            self.done = True

    monkeypatch.setattr(pipeline.psutil, "Process", RestrictedProcess)
    sampler = pipeline.MemorySampler()
    sampler.stop = OneIteration()
    sampler.run()
    assert sampler.peak >= 1024 * 1024
