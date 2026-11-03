"""
Tests for Two-Tier Memory Store and What-I-Know-About-You API.
"""

from pico.models import Fact, FactStatus, FactSource, Sensitivity, UserProfile
from pico.memory import MemoryStore


def test_staging_and_committed_facts():
    store = MemoryStore(":memory:")
    user_id = "user_test"

    fact1 = Fact(
        key="favorite_food",
        value="paneer tikka",
        source=FactSource.USER_SAID,
        status=FactStatus.COMMITTED,
        mode="shared"
    )

    fact2 = Fact(
        key="temporary_mood",
        value="sleepy",
        source=FactSource.INFERRED,
        status=FactStatus.STAGING,
        mode="shared"
    )

    store.store_fact(user_id, fact1)
    store.store_fact(user_id, fact2)

    facts = store.get_facts_for_mode(user_id, mode="chill")
    assert len(facts) == 2

    # Verify What-I-Know returns both
    what_i_know = store.get_what_i_know(user_id)
    assert len(what_i_know) == 2
    keys = [f["key"] for f in what_i_know]
    assert "favorite_food" in keys
    assert "temporary_mood" in keys


def test_fact_deletion():
    store = MemoryStore(":memory:")
    user_id = "user_del"

    fact = Fact(
        key="home_city",
        value="Mumbai",
        source=FactSource.USER_SAID,
        status=FactStatus.COMMITTED,
        mode="shared"
    )

    fact_id = store.store_fact(user_id, fact)
    assert len(store.get_what_i_know(user_id)) == 1

    # Real deletion (§9)
    deleted = store.delete_fact(user_id, fact_id)
    assert deleted is True
    assert len(store.get_what_i_know(user_id)) == 0


def test_mode_fact_isolation():
    store = MemoryStore(":memory:")
    user_id = "user_iso"

    shared_fact = Fact(key="pet_name", value="Bruno", mode="shared", status=FactStatus.COMMITTED)
    gym_fact = Fact(key="bench_pr", value="75kg", mode="gym", status=FactStatus.COMMITTED)
    trading_fact = Fact(key="crypto_wallet", value="0x123", mode="trading", status=FactStatus.COMMITTED)

    store.store_fact(user_id, shared_fact)
    store.store_fact(user_id, gym_fact)
    store.store_fact(user_id, trading_fact)

    # In gym mode, see shared + gym, but NEVER trading
    gym_facts = store.get_facts_for_mode(user_id, mode="gym")
    gym_keys = [f.key for f in gym_facts]
    assert "pet_name" in gym_keys
    assert "bench_pr" in gym_keys
    assert "crypto_wallet" not in gym_keys
