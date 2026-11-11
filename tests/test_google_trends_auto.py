"""Collecte Google Trends automatique (pytrends simulé : aucun appel réseau)."""
import pandas as pd

from flavortrends.collectors.google_trends import GoogleTrendsAuto
from flavortrends.http import HttpClient
from flavortrends.taxonomy import read_csv


class FakeConn:
    """Pas de collecte récente, pas d'historique : premier passage."""
    def execute(self, *a, **k):
        class R:
            def fetchone(self):
                return None

            def fetchall(self):
                return []
        return R()


class FakeTrendReq:
    def __init__(self, fail_with=None):
        self.calls, self.fail_with = [], fail_with

    def build_payload(self, kw_list, timeframe, geo):
        self.calls.append((list(kw_list), timeframe, geo))
        self.kw = list(kw_list)

    def interest_over_time(self):
        if self.fail_with:
            raise self.fail_with
        idx = pd.to_datetime(["2026-10-25", "2026-11-01", "2026-11-08"])
        data = {k: [10 + i, 20 + i, 30 + i] for i, k in enumerate(self.kw)}
        data["isPartial"] = [False, False, True]
        return pd.DataFrame(data, index=idx)


def test_groups_with_anchor_and_skips_partial_week(settings):
    flavors = [f for f in read_csv() if f.flavor_id in ("yuzu", "matcha", "ube", "vanilla", "kimchi", "mint")]
    fake = FakeTrendReq()
    col = GoogleTrendsAuto(conn=FakeConn(), settings=settings, http=HttpClient("t", min_interval=0))
    items = list(col.fetch(flavors=flavors, zones=[("WORLD", "en"), ("FR", "fr")], anchor="vanilla", trend_req=fake))
    assert len(fake.calls) == 4                                  # 5 arômes hors ancre -> 2 lots par zone
    assert all(c[0][-1] in ("vanilla", "vanille") for c in fake.calls)   # ancre dans chaque lot
    assert fake.calls[0][2] == "" and fake.calls[2][2] == "FR"   # WORLD -> geo vide pour Google
    assert all(i.payload["date"] != "2026-11-08" for i in items) # semaine en cours ignorée
    assert items[0].payload["batch_id"].startswith("pytrends:WORLD:") and items[0].payload["granularity"] == "week"


def test_stops_after_two_429(settings):
    class TooManyRequestsError(Exception):
        pass
    fake = FakeTrendReq(fail_with=TooManyRequestsError("The request failed: Google returned a response with code 429"))
    col = GoogleTrendsAuto(conn=FakeConn(), settings=settings, http=HttpClient("t", min_interval=0))
    assert list(col.fetch(flavors=read_csv(), zones=[("WORLD", "en")], trend_req=fake)) == []
    assert len(fake.calls) == 2 and col.truncated is True


def test_popularity_grouping_keeps_niche_flavors_together(settings):
    from flavortrends.collectors.google_trends import build_popularity_plan
    flavors = read_csv()
    pop = {f.flavor_id: 1000.0 for f in flavors}
    pop.update({"yuzu": 5, "hojicha": 4, "calamansi": 3, "ube": 6, "dragon_fruit": 7, "vanilla": 1e6, "chocolate": 9e5})
    plan = build_popularity_plan(flavors, "en", pop)
    assert plan[0][:2] == ["vanilla", "chocolate"]                      # les plus populaires ensemble
    last = set(plan[-2]) | set(plan[-1])                                # 102 arômes : 20 lots de 5 + 1 lot de 2
    # (en anglais, la pitaya est cherchée sous son premier synonyme : « dragon fruit »)
    assert {"dragon fruit", "ube", "yuzu", "hojicha", "calamansi"} <= last and "vanilla" not in last
    assert all(len(b) <= 5 for b in plan) and sum(len(b) for b in plan) == len(flavors)
