# test_smoke.py
import time, threading

import server


def test_calc_simple_expression():
    cache = server.LRUCache(capacity=10)

    request = {
        "mode": "calc",
        "data": {"expr": "2+2"},
        "options": {"cache": True}
    }

    response = server.handle_request(request, cache)

    assert response["ok"] is True
    assert response["result"] == 4.0
    assert "meta" in response
    assert response["meta"]["from_cache"] is False


def test_calc_cache_hit():
    cache = server.LRUCache(capacity=10)

    request = {
        "mode": "calc",
        "data": {"expr": "5*3"},
        "options": {"cache": True}
    }

    # First request → cache MISS
    first_response = server.handle_request(request, cache)

    assert first_response["ok"] is True
    assert first_response["result"] == 15.0
    assert first_response["meta"]["from_cache"] is False

    # Second request → cache HIT
    second_response = server.handle_request(request, cache)

    assert second_response["ok"] is True
    assert second_response["result"] == 15.0
    assert second_response["meta"]["from_cache"] is True


if __name__ == "__main__":
    test_calc_simple_expression()
    print("test_calc_simple_expression OK")
    test_calc_cache_hit()
    print("test_calc_cache_hit OK")
