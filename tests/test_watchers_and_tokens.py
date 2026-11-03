"""
Tests for Price Watchers, Flagship Alert, and Token Metering.
From YOUR_FRIEND_FULL_SETUP.pdf (§12, §16, §19.5).
"""

from pico.watchers import PriceWatcher, PriceWatcherEngine
from pico.tokens import TokenManager, FREE_MONTHLY_TOKEN_QUOTA


def test_flagship_price_alert_format():
    engine = PriceWatcherEngine()

    watcher = PriceWatcher(
        id="w_btc_01",
        user_id="ayush_01",
        symbol="BTCUSDT",
        target_level=68000.0,
        direction="below"
    )
    engine.add_watcher(watcher)

    # Simulate price drop to 67800
    alerts = engine.evaluate_watchers(current_prices={"BTCUSDT": 67800.0})
    assert len(alerts) == 1
    alert = alerts[0]

    # Rule 1: Push <= 12 words, NO amounts (§19.5)
    push_words = alert.push_notification.split()
    assert len(push_words) <= 12
    assert "$" not in alert.push_notification
    assert "₹" not in alert.push_notification
    assert "WAKE UP — BTC fell through your level." in alert.push_notification

    # Rule 2: In-app card contains details and open question
    assert "crossed below your level" in alert.in_app_card["headline"]
    assert "68,000.00" in alert.in_app_card["user_level"]
    assert "Want the 1-hour chart?" in alert.in_app_card["open_question"]
    # Rule 3: SEBI compliance - tap is always human
    assert "tap is always human" in alert.in_app_card["action_rule"]


def test_token_metering_and_low_power_mode():
    mgr = TokenManager()
    user_id = "test_user_tok"
    account = mgr.get_or_create_account(user_id)

    assert account.monthly_allowance == FREE_MONTHLY_TOKEN_QUOTA
    assert account.tokens_remaining == FREE_MONTHLY_TOKEN_QUOTA
    assert account.is_low_power is False

    # Exempt usage (Heartbeats/Watchers)
    mgr.record_usage(user_id, tokens=50_000, is_exempt=True)
    assert account.tokens_used == 0

    # Normal usage
    mgr.record_usage(user_id, tokens=20_000_000)
    assert account.tokens_used == 20_000_000
    assert account.usage_percentage == 50.0

    # Exhaust all tokens -> Low Power Mode
    mgr.record_usage(user_id, tokens=20_000_000)
    assert account.tokens_remaining == 0
    assert account.is_low_power is True


def test_lock_in_trial_sessions():
    mgr = TokenManager()
    account = mgr.get_or_create_account("tester_pro", tier="free")

    assert account.lock_in_sessions_left == 3

    # Session 1
    success1, msg1 = mgr.enter_lock_in_mode(account)
    assert success1 is True
    assert account.lock_in_sessions_left == 2

    # Session 2 & 3
    mgr.enter_lock_in_mode(account)
    mgr.enter_lock_in_mode(account)
    assert account.lock_in_sessions_left == 0

    # Session 4 (Should fail gracefully without locking user out of friend)
    success4, msg4 = mgr.enter_lock_in_mode(account)
    assert success4 is False
    assert "used your 3 free Lock In trial sessions" in msg4
