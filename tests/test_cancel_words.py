"""스레드에서 코더를 멈추는 말 인식 검증.

실제로 벌어진 사고(2026-07-28): README는 "취소: 스레드에 `stop`을 보냅니다"라고
안내하는데 코드는 `!stop`만 인정했다. 사용자가 `stop`을 치자 취소가 아니라
**코더에게 보내는 지시**로 전달돼, 그 지시를 받은 코더가 "중단했습니다. 파일
변경은 하지 않았습니다"라고 답했다. 정작 원래 실행은 멈춘 적이 없어서 계속
돌았고 파일까지 만들었다. 취소 실패보다 나쁜 **거짓 확인**이 만들어진 것.

그래서 인식 목록은 문서와 어긋나면 안 되고, 사용자가 실제로 칠 만한 말
(한국어 포함)을 받아야 한다.
"""
import pytest

from agent_company.delegate_background import is_cancel_command


@pytest.mark.parametrize("word", [
    # 느낌표 형태 — 원래부터 있던 것, 계속 지원
    "!stop", "!cancel",
    # README가 줄곧 안내해온 형태 — 이게 안 먹어서 사고가 났다
    "stop", "cancel",
    # 한국어 — 사용자가 한국어로 쓰므로 실제로 칠 가능성이 가장 높다
    "그만", "멈춰", "중단", "취소",
])
def test_cancel_words_recognized(word):
    assert is_cancel_command(word) is True


@pytest.mark.parametrize("word", [
    "STOP", "Stop", "  stop  ", "!STOP", "그만 ", " 취소",
])
def test_recognition_ignores_case_and_padding(word):
    assert is_cancel_command(word) is True


@pytest.mark.parametrize("text", [
    # 멈추라는 뜻이 아닌, 진짜 후속 지시 — 코더에게 그대로 가야 한다
    "stop the dev server and restart it",
    "취소 버튼 동작을 고쳐줘",
    "그만두는 흐름도 테스트에 넣어줘",
    "add a cancel button",
    "",
    None,
])
def test_ordinary_followups_are_not_cancels(text):
    assert is_cancel_command(text) is False


def test_thread_anchor_tells_the_user_how_to_cancel():
    """앵커 메시지가 취소 방법을 알려줘야 한다.

    안내가 없으면 사용자는 문서를 안 보고 떠오르는 말을 친다. 인식 못 한 말은
    코더에게 가는 지시가 되므로, 안내 문구가 곧 사고 예방책이다. 여기 적힌
    말은 반드시 실제로 인식되는 말이어야 한다.
    """
    import inspect

    from agent_company import discord_overlay

    src = inspect.getsource(discord_overlay.create_coder_thread)
    assert "멈추려면" in src, "앵커에 취소 안내가 없다"
    assert is_cancel_command("그만") is True, "안내한 말이 정작 인식되지 않는다"
