"""hermes 0.18+ 지연 플랫폼 등록에서 Discord 오버레이가 살아 있는지 검증.

hermes 0.18이 번들 플랫폼 플러그인을 deferred로 바꾸면서
(``platform_registry.register_deferred``), Discord 어댑터 모듈은 게이트웨이가
그 플랫폼을 실제로 요청할 때까지 import되지 않는다. 플러그인 discovery는 그보다
한참 앞서 돌기 때문에, ``register(ctx)`` 시점엔 감쌀 DiscordAdapter 클래스가
아예 없다 → 오버레이가 조용히 no-op → ``/code``·코더 스레드·진행상황 중계가
전부 사라진다(0.18 업그레이드 후 실제로 벌어진 일).

``_arm_discord_overlay_on_adapter_create``가 create_adapter를 감싸서, 어댑터를
만드는 그 순간에 (1) deferred 로더를 돌려 모듈을 올리고 (2) 오버레이를 설치한
뒤 (3) 인스턴스를 만들게 한다.
"""
import sys
import types

from unittest.mock import MagicMock, patch

import agent_company


def _make_fake_registry():
    """create_adapter / get 을 가진 fake platform_registry."""
    registry = types.SimpleNamespace()
    registry.resolved = []
    registry.created = []

    def _get(name):
        registry.resolved.append(name)
        return f"entry-{name}"

    def _create_adapter(name, config, *args, **kwargs):
        registry.created.append((name, config))
        return f"adapter-{name}"

    registry.get = _get
    registry.create_adapter = _create_adapter
    return registry


def _install_fake_registry(monkeypatch, registry):
    """gateway.platform_registry 를 fake로 갈아끼운다."""
    mod = types.ModuleType("gateway.platform_registry")
    mod.platform_registry = registry
    monkeypatch.setitem(sys.modules, "gateway.platform_registry", mod)
    return mod


def test_arm_wraps_create_adapter(monkeypatch):
    registry = _make_fake_registry()
    _install_fake_registry(monkeypatch, registry)
    orig = registry.create_adapter

    agent_company._arm_discord_overlay_on_adapter_create()

    assert registry.create_adapter is not orig
    assert registry._agent_company_create_adapter_wrapped is True


def test_overlay_installed_before_discord_adapter_is_built(monkeypatch):
    """핵심: discord 어댑터를 만들 때 deferred 로더 → 오버레이 → 생성 순서."""
    registry = _make_fake_registry()
    _install_fake_registry(monkeypatch, registry)
    agent_company._arm_discord_overlay_on_adapter_create()

    calls = []
    registry.get = lambda name: calls.append(("resolve", name))

    def _spy_install():
        calls.append(("install_overlay", None))

    _orig_create = registry.create_adapter

    with patch("agent_company.discord_overlay.install_discord_coder_overlay",
               _spy_install):
        result = registry.create_adapter("discord", {"token": "x"})

    assert result == "adapter-discord"
    # 생성보다 먼저 해석하고, 해석보다 먼저는 아니게 오버레이를 설치해야 한다
    assert calls == [("resolve", "discord"), ("install_overlay", None)]
    assert registry.created == [("discord", {"token": "x"})]


def test_non_discord_platform_untouched(monkeypatch):
    """텔레그램 등 다른 플랫폼엔 오버레이를 건드리지 않는다."""
    registry = _make_fake_registry()
    _install_fake_registry(monkeypatch, registry)
    agent_company._arm_discord_overlay_on_adapter_create()

    with patch("agent_company.discord_overlay.install_discord_coder_overlay") as inst:
        result = registry.create_adapter("telegram", {})

    inst.assert_not_called()
    assert registry.resolved == []
    assert result == "adapter-telegram"


def test_arm_is_idempotent(monkeypatch):
    registry = _make_fake_registry()
    _install_fake_registry(monkeypatch, registry)

    agent_company._arm_discord_overlay_on_adapter_create()
    wrapped_once = registry.create_adapter
    agent_company._arm_discord_overlay_on_adapter_create()

    assert registry.create_adapter is wrapped_once  # 이중 wrap 안 함


def test_overlay_failure_does_not_block_adapter(monkeypatch):
    """오버레이가 터져도 Discord 자체는 떠야 한다(코더 기능만 빠진 채로)."""
    registry = _make_fake_registry()
    _install_fake_registry(monkeypatch, registry)
    agent_company._arm_discord_overlay_on_adapter_create()

    with patch("agent_company.discord_overlay.install_discord_coder_overlay",
               side_effect=RuntimeError("boom")):
        result = registry.create_adapter("discord", {})

    assert result == "adapter-discord"


def test_arm_noop_without_platform_registry(monkeypatch):
    """hermes <0.18 (platform_registry 없음)에서는 조용히 넘어간다."""
    monkeypatch.setitem(sys.modules, "gateway.platform_registry", None)
    # import 자체가 실패하는 상황을 만든다
    with patch.dict(sys.modules, {"gateway.platform_registry": None}):
        agent_company._arm_discord_overlay_on_adapter_create()  # 예외 없이 통과
