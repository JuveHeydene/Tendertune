from app.config import Settings


def test_gpu_off_by_default():
    s = Settings(use_gpu=False)
    assert s.device == "cpu"


def test_gpu_on_sets_cuda():
    s = Settings(use_gpu=True)
    assert s.device == "cuda"
