from unittest.mock import patch

from app.services.websocket_push_service import WebSocketPushService


def test_push_news_skips_when_no_real_news_source():
    service = WebSocketPushService()

    with patch.object(service, "_get_news_payload", return_value=[]), \
         patch("app.services.websocket_push_service.broadcast_news") as broadcast_news:
        service._push_news()

    broadcast_news.assert_not_called()
