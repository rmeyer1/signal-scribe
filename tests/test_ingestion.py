from types import SimpleNamespace

from signal_scribe.config import Settings
from signal_scribe.ingestion import IngestionService


class _FakeClient:
    def __init__(self, universe_names: set[str]) -> None:
        self._universe_names = universe_names

    def table(self, name: str) -> "_FakeQuery":
        return _FakeQuery(name, self._universe_names)


class _FakeQuery:
    def __init__(self, table_name: str, universe_names: set[str]) -> None:
        self._table_name = table_name
        self._universe_names = universe_names
        self._filters: dict[str, str] = {}

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, column: str, value: str) -> "_FakeQuery":
        self._filters[column] = value
        return self

    def limit(self, _count: int) -> "_FakeQuery":
        return self

    def execute(self) -> SimpleNamespace:
        if (
            self._table_name == "universes"
            and self._filters.get("name") in self._universe_names
        ):
            return SimpleNamespace(data=[{"id": "universe-id"}])
        return SimpleNamespace(data=[])


def _service_with_universes(universe_names: set[str]) -> IngestionService:
    store = SimpleNamespace(_client=_FakeClient(universe_names))
    return IngestionService(Settings(), store)  # type: ignore[arg-type]


def test_universe_exists_returns_true_for_existing_universe():
    service = _service_with_universes({"nasdaq"})

    assert service.universe_exists("nasdaq") is True


def test_universe_exists_returns_false_for_missing_universe():
    service = _service_with_universes({"nasdaq-test"})

    assert service.universe_exists("nasdaq") is False
