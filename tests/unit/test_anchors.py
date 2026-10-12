"""Finding a passage again in a text: exactly, by its context, or not at all."""

from __future__ import annotations

from numericos.core.anchors import CONTEXT, Located, NotLocated, context, locate, occurrences

TEXT = "The scheme is stable when r <= 1/2. In two dimensions the scheme is stable when r <= 1/4."


def test_a_passage_that_occurs_once_is_found_where_it_is() -> None:
    assert locate(TEXT, "two dimensions") == Located(39, 53)
    assert TEXT[39:53] == "two dimensions"
    assert locate(TEXT, "three dimensions") == NotLocated("missing")
    assert locate(TEXT, "") == NotLocated("missing")


def test_equal_passages_are_told_apart_by_what_surrounds_them() -> None:
    quote = "scheme is stable when r <= 1/"
    first, second = occurrences(TEXT, quote)

    assert locate(TEXT, quote) == NotLocated("ambiguous")  # nothing to tell them apart
    assert locate(TEXT, quote, prefix="The ", suffix="2. In two") == Located(
        first, first + len(quote)
    )
    assert locate(TEXT, quote, prefix="dimensions the ", suffix="4.") == Located(
        second, second + len(quote)
    )
    # A context that fits both equally, or neither, decides nothing: no guess is made.
    assert locate(TEXT, quote, prefix="xyz", suffix="xyz") == NotLocated("ambiguous")


def test_the_context_survives_a_text_rewritten_around_the_passage() -> None:
    quote = "stable when r <= 1/4"
    prefix, suffix = context(TEXT, TEXT.index(quote), TEXT.index(quote) + len(quote))
    rewritten = "Stability. " + TEXT.replace("In two dimensions", "On a square grid") + " See (2)."

    found = locate(rewritten, quote, prefix, suffix)

    assert isinstance(found, Located)
    assert rewritten[found.start : found.end] == quote


def test_context_is_bounded_and_stops_at_the_ends_of_the_text() -> None:
    assert context("abc", 1, 2) == ("a", "c")
    long = "x" * 200 + "PASSAGE" + "y" * 200
    prefix, suffix = context(long, 200, 207)
    assert (len(prefix), len(suffix)) == (CONTEXT, CONTEXT)


def test_offsets_are_unicode_code_points() -> None:
    text = "Errore 😀 dell'ordine di Δt² — già"
    found = locate(text, "Δt²")

    assert found == Located(24, 27)  # the emoji before it counts as one
    assert text[24:27] == "Δt²"
