from __future__ import annotations


def test_stale_write_cannot_overwrite_state(tmp_path, scenario) -> None:
    from adaptive_trip.storage.repository import Repository

    repository = Repository(tmp_path / "trip.db")
    state = scenario("rain").state
    repository.create(state)
    newer = state.model_copy(update={"version": state.version + 1})

    assert repository.compare_and_swap(newer, expected_version=state.version)
    assert not repository.compare_and_swap(newer, expected_version=state.version)
    assert repository.get(state.id).version == state.version + 1


def test_duplicate_event_fingerprint_is_rejected(tmp_path, scenario) -> None:
    from adaptive_trip.storage.repository import Repository

    repository = Repository(tmp_path / "trip.db")
    loaded = scenario("rain")
    repository.create(loaded.state)

    assert repository.save_event(loaded.event)
    assert not repository.save_event(loaded.event)
