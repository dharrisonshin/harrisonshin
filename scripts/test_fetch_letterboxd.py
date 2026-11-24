#!/usr/bin/env python3
"""Parser and merge tests for the Letterboxd sync. No network."""

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_letterboxd as lb

DIARY_ROW = """
<tr class="diary-entry-row">
  <td class="col-month"><a class="month" href="/smackushin/diary/films/for/2026/11/">Nov</a>
  <a class="year" href="/smackushin/diary/films/for/2026/">2026</a></td>
  <td class="col-daydate"><a class="daydate" href="/smackushin/diary/films/for/2026/11/23/">23</a></td>
  <td class="col-production">
    <div data-item-name="Tony (2026)" data-item-slug="tony-2026" data-item-link="/film/tony-2026/"
      data-postered-identifier='{"uid":"film:1209001"}'></div>
  </td>
  <td class="col-rating"><span class="rating rated-7">★★★½</span></td>
  <td class="col-like"><span class="has-icon icon-16 icon-liked"></span></td>
  <td class="col-rewatch icon-status-off"><span class="icon-rewatch"></span></td>
</tr>
<tr class="diary-entry-row">
  <td class="col-daydate"><a class="daydate" href="/smackushin/diary/films/for/2026/11/22/">22</a></td>
  <td class="col-production">
    <div data-item-name="Mercy (2026)" data-item-slug="mercy-2026" data-item-link="/film/mercy-2026/"
      data-postered-identifier='{"uid":"film:1119565"}'></div>
  </td>
  <td class="col-rating"><span class="rating rated-5">★★½</span></td>
  <td class="col-like"></td>
  <td class="col-rewatch js-td-rewatch"><span class="icon-rewatch"></span></td>
</tr>
"""

FILM_ITEM = """
<li class="griditem">
  <div data-item-name="Thelma (2024)" data-item-slug="thelma-2024" data-item-link="/film/thelma-2024/"
    data-postered-identifier='{"uid":"film:42"}'></div>
  <p class="poster-viewingdata"><span class="rating rated-8">★★★★</span></p>
</li>
<li class="griditem">
  <div data-item-name="Thelma (2017)" data-item-slug="thelma-2017" data-item-link="/film/thelma-2017/"
    data-postered-identifier='{"uid":"film:43"}'></div>
  <p class="poster-viewingdata"><span class="rating rated-6">★★★</span>
  <span class="icon-liked"></span></p>
</li>
"""

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:letterboxd="https://letterboxd.com">
  <channel>
    <title>Letterboxd</title>
    <item>
      <title>Tony, 2026</title>
      <link>https://letterboxd.com/smackushin/film/tony-2026/</link>
      <letterboxd:watchedDate>2026-11-23</letterboxd:watchedDate>
      <letterboxd:rewatch>No</letterboxd:rewatch>
      <letterboxd:filmTitle>Tony</letterboxd:filmTitle>
      <letterboxd:filmYear>2026</letterboxd:filmYear>
      <letterboxd:memberRating>3.5</letterboxd:memberRating>
      <letterboxd:memberLike>Yes</letterboxd:memberLike>
      <description><![CDATA[<p><img src="https://a.ltrbxd.com/resized/tony.jpg"/></p>]]></description>
    </item>
    <item>
      <title>Coming of Age</title>
      <link>https://letterboxd.com/smackushin/list/coming-of-age/</link>
      <description>a list</description>
    </item>
    <item>
      <title>Review only</title>
      <link>https://letterboxd.com/smackushin/film/some-review/</link>
      <letterboxd:filmTitle>Some Review</letterboxd:filmTitle>
      <letterboxd:filmYear>2020</letterboxd:filmYear>
      <letterboxd:memberRating>5</letterboxd:memberRating>
    </item>
    <item>
      <link>https://letterboxd.com/smackushin/film/tony-2026/</link>
      <letterboxd:watchedDate>2026-01-01</letterboxd:watchedDate>
      <letterboxd:rewatch>Yes</letterboxd:rewatch>
      <letterboxd:filmTitle>Tony</letterboxd:filmTitle>
      <letterboxd:filmYear>2026</letterboxd:filmYear>
      <letterboxd:memberRating>2</letterboxd:memberRating>
    </item>
  </channel>
</rss>
"""


class ParseTests(unittest.TestCase):
    def test_diary_keeps_like_rewatch_and_date(self):
        rows = lb.parse_diary_html(DIARY_ROW)
        self.assertEqual(len(rows), 2)
        tony, mercy = rows
        self.assertEqual(tony["title"], "Tony")
        self.assertEqual(tony["year"], 2026)
        self.assertEqual(tony["rating"], 3.5)
        self.assertEqual(tony["last_watched"], "2026-11-23")
        self.assertTrue(tony["liked"])
        self.assertFalse(tony["rewatch"])
        self.assertEqual(tony["link"], "https://letterboxd.com/film/tony-2026/")
        self.assertFalse(mercy["liked"])
        self.assertTrue(mercy["rewatch"])
        self.assertEqual(mercy["rating"], 2.5)

    def test_films_keep_distinct_years(self):
        films = lb.parse_films_html(FILM_ITEM)
        self.assertEqual([film["slug"] for film in films], ["thelma-2024", "thelma-2017"])
        self.assertEqual(films[0]["rating"], 4)
        self.assertTrue(films[1]["liked"])

    def test_rss_skips_lists_and_reviews_without_a_watch(self):
        films = lb.parse_rss(RSS)
        self.assertEqual(len(films), 2)
        self.assertTrue(all(film["slug"] == "tony-2026" for film in films))
        merged = lb.rss_as_films(films)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["last_watched"], "2026-11-23")
        self.assertEqual(merged[0]["rating"], 3.5)
        self.assertTrue(merged[0]["rewatch"])
        self.assertTrue(merged[0]["poster_url"].endswith("tony.jpg"))

    def test_short_pages_do_not_replace_the_file(self):
        page = '<span class="tooltip" title="125&nbsp;films">Diary</span>' + DIARY_ROW
        self.assertIsNone(lb.combine_letterboxd([page], [], []))

    def test_merge_keeps_site_films_and_letterboxd_wins(self):
        catalog = [
            {
                "title": "Tony",
                "year": 2026,
                "director": "Ada",
                "genres": ["Drama"],
                "rating": 5,
                "last_watched": "2020-01-01",
                "takeaway": "keep this",
            },
            {
                "title": "Thelma",
                "year": 2017,
                "director": None,
                "genres": [],
                "rating": 2,
                "last_watched": None,
                "takeaway": None,
            },
            {
                "title": "Only On Site",
                "year": 1999,
                "director": "Bea",
                "genres": ["Comedy"],
                "rating": 3,
                "last_watched": None,
                "takeaway": "site only",
            },
        ]
        films = lb.parse_films_html(FILM_ITEM)
        films.append({
            "title": "Tony",
            "year": 2026,
            "slug": "tony-2026",
            "film_id": "1209001",
            "rating": 3.5,
            "last_watched": "2026-11-23",
            "liked": True,
            "rewatch": False,
            "link": "https://letterboxd.com/film/tony-2026/",
            "poster_url": "",
        })
        merged = lb.sort_entries(lb.merge_library([], catalog, films))
        titles = [(item["title"], item["year"]) for item in merged]
        self.assertIn(("Only On Site", 1999), titles)
        self.assertIn(("Thelma", 2024), titles)
        self.assertIn(("Thelma", 2017), titles)
        tony = next(item for item in merged if item["title"] == "Tony")
        self.assertEqual(tony["rating"], 3.5)
        self.assertEqual(tony["last_watched"], "2026-11-23")
        self.assertEqual(tony["director"], "Ada")
        self.assertEqual(tony["takeaway"], "keep this")
        self.assertTrue(tony["liked"])
        site = next(item for item in merged if item["title"] == "Only On Site")
        self.assertFalse(site["from_letterboxd"])
        self.assertEqual(merged[0]["title"], "Tony")

    def test_same_film_matches_alternate_titles_only(self):
        pairs = [
            ("Dune (1984)", 1984, "Dune", 1984, True),
            ("Super (2010 American film)", 2010, "Super", 2010, True),
            ("Star Wars: Episode IV – A New Hope", 1977, "Star Wars", 1977, True),
            ("Star Wars: Episode V – The Empire Strikes Back", 1980, "The Empire Strikes Back", 1980, True),
            ("Rogue One", 2016, "Rogue One: A Star Wars Story", 2016, True),
            ("Gretel and Hansel", 2020, "Gretel & Hansel", 2020, True),
            ("Thelma", 2017, "Thelma", 2024, False),
            ("Dune", 2021, "Dune", 1984, False),
        ]
        for left, left_year, right, right_year, expected in pairs:
            self.assertEqual(
                lb.same_film({"title": left, "year": left_year}, {"title": right, "year": right_year}),
                expected,
                left,
            )

    def test_rss_failure_leaves_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "library").mkdir()
            (root / "library" / "movies.json").write_text("[]\n", encoding="utf-8")
            (root / "library" / "letterboxd.json").write_text('[{"title":"Kept"}]\n', encoding="utf-8")

            def boom(url):
                raise urllib.error.URLError("down")

            code = lb.update(root, fetch=boom, download_posters=False)
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads((root / "library" / "letterboxd.json").read_text(encoding="utf-8")),
                [{"title": "Kept"}],
            )


if __name__ == "__main__":
    unittest.main()
