"""Tests for src/mahlzeit/model.py (unified schema + validation, PROJECT.md §4)."""

import copy
from typing import Any, Dict

import pytest

from mahlzeit.model import Menu

EXAMPLE_DATA: Dict[str, Any] = {
    "generated_at": "2026-08-07T22:00:00+02:00",
    "restaurants": [
        {
            "id": "roland",
            "name": "Rolands Kantine",
            "source_url": "https://rolandsmaultaschen.de/Im-Rolands/",
            "weeks": [
                {
                    "from": "2026-08-03",
                    "to": "2026-08-07",
                    "days": [
                        {
                            "date": "2026-08-03",
                            "weekday": "Montag",
                            "meals": [
                                {
                                    "type": "Menü 1",
                                    "name": "Hackbällchen Ragout mit Paprika, Zucchini, Tomatensauce und Kichererbsen",
                                    "price_internal": 6.0,
                                    "price_external": 8.0,
                                    "allergens": "2, 4, 7, 8, a1|2, c, d, k, m",
                                    "vegan": False,
                                    "sonderessen": False,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "id": "vaihingen",
            "name": "Naherholungsgebiet",
            "source_url": "https://naherholungsgebiet-vaihingen.de/mittagskarte/Wochenkarte.pdf",
            "weeks": [
                {
                    "from": "2026-08-03",
                    "to": "2026-08-07",
                    "days": [
                        {
                            "date": "2026-08-03",
                            "weekday": "Montag",
                            "meals": [
                                {"type": "Standard", "name": "Maultaschen mit Pilzrahmsoße und Salat", "vegan": False},
                                {"type": "Standard", "name": "Pasta mit Zitronenmelissen Pesto", "vegan": True},
                            ],
                        }
                    ],
                }
            ],
        },
    ],
}


def round_trip(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize an object back out: dict → object → dict. Validates along the way."""
    menu = Menu.from_dict(data)
    menu.validate()
    return menu.to_dict()


def test_section4_example_validates_and_round_trips():
    menu = Menu.from_dict(EXAMPLE_DATA)
    menu.validate()
    assert menu.to_dict() == round_trip(EXAMPLE_DATA)


def test_round_trip_is_stable():
    data = round_trip(EXAMPLE_DATA)
    assert round_trip(data) == data


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0]["days"][0].__setitem__(
                "date", "2026-13-99"
            ),
            id="invalid day date",
        ),
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0].__setitem__("from", "garbage"),
            id="invalid week.from",
        ),
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0]["days"][0].__setitem__(
                "meals", []
            ),
            id="empty meals",
        ),
        pytest.param(
            lambda d: d["restaurants"].append(copy.deepcopy(d["restaurants"][0])),
            id="duplicate restaurant id",
        ),
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0].__setitem__("from", "2026-08-10"),
            id="week.to before week.from",
        ),
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0]["days"][0].__setitem__(
                "date", "2026-08-10"
            ),
            id="day outside week",
        ),
        pytest.param(
            lambda d: d["restaurants"][0]["weeks"][0]["days"][0].__setitem__(
                "weekday", ""
            ),
            id="empty weekday",
        ),
        pytest.param(
            lambda d: d["restaurants"][0].__setitem__("id", ""),
            id="empty restaurant id",
        ),
    ],
)
def test_validation_rejects_malformed_data(mutate):
    data = copy.deepcopy(EXAMPLE_DATA)
    mutate(data)
    with pytest.raises(ValueError):
        round_trip(data)
