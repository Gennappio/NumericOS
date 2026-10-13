"""Formulas whose backslashes a model doubled once too often, and what is left alone."""

from __future__ import annotations

from numericos.core.formulas import repair_formulas


def test_a_formula_with_every_backslash_doubled_is_written_once() -> None:
    assert repair_formulas(r"The ratio $r=\\alpha\\,\\Delta t/h^2$ decides.") == (
        r"The ratio $r=\alpha\,\Delta t/h^2$ decides."
    )
    assert repair_formulas("$$\\\\frac{\\\\alpha\\\\,\\\\Delta t}{\\\\Delta x^2} \\\\le 1$$") == (
        "$$\\frac{\\alpha\\,\\Delta t}{\\Delta x^2} \\le 1$$"
    )
    # A line break that was doubled with the rest is a line break again.
    assert repair_formulas("$$\\\\begin{aligned} a &= b \\\\\\\\ c &= d \\\\end{aligned}$$") == (
        "$$\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}$$"
    )


def test_each_formula_is_judged_on_its_own() -> None:
    text = r"Good $\alpha$, doubled $\\beta$, good again $\gamma \le 1$."

    assert repair_formulas(text) == r"Good $\alpha$, doubled $\beta$, good again $\gamma \le 1$."


def test_a_formula_written_normally_keeps_its_line_breaks() -> None:
    aligned = "$$\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}$$"
    matrix = "$$\\begin{pmatrix} 1 & 0 \\\\ 0 & 1 \\end{pmatrix}$$"
    breaks_only = "$$a + b \\\\ c + d$$"  # no command at all: nothing says it was doubled

    assert repair_formulas(aligned) == aligned
    assert repair_formulas(matrix) == matrix
    assert repair_formulas(breaks_only) == breaks_only


def test_nothing_outside_a_formula_is_touched() -> None:
    text = (
        "A path `C:\\\\data\\\\run` and a pattern `\\\\d+` in code, a break\\\\\n"
        "```\nprint('$\\\\alpha$')\n```\n"
        "and prices of $5 and $10."
    )

    assert repair_formulas(text) == text
    assert repair_formulas("") == ""
    assert repair_formulas("No formula, no backslash.") == "No formula, no backslash."


def test_code_between_formulas_does_not_hide_them() -> None:
    text = "With `u` as $\\\\alpha$ and `v` as $\\\\beta$."

    assert repair_formulas(text) == "With `u` as $\\alpha$ and `v` as $\\beta$."
