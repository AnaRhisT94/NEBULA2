import os

def test_PYTHONPATH():
    os.environ.get('PYTHONPATH')
    assert os.environ.get('PYTHONPATH') == "/home/ilan/git/NEBULA2"