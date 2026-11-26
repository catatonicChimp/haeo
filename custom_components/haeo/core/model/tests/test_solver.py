"""Tests for the solver's cached solution."""

from highspy import HighsModelStatus, HighsVarType
import numpy as np
import pytest

from custom_components.haeo.core.model.linear import LinearArray
from custom_components.haeo.core.model.solver import Solver
from custom_components.haeo.core.model.util.solver_rows import add_rows


def test_feasibility_relaxation_replaces_the_cached_solution() -> None:
    """The solution a feasibility relaxation finds is the one read after it, not the solve before."""
    solver = Solver()
    solver.setOptionValue("output_flag", False)
    x = solver.add_variables(1, name="x", upper=10.0)
    add_rows(solver, x >= 6.0)
    add_rows(solver, x <= 4.0)
    solver.run()
    before = solver.column_values().copy()
    solver.row_values()
    solver.row_duals()

    solver.feasibilityRelaxation(1.0, 1.0, 1.0, None, None, None)

    solution = solver.getSolution()
    np.testing.assert_allclose(solver.column_values(), solution.col_value)
    np.testing.assert_allclose(solver.row_values(), solution.row_value)
    np.testing.assert_allclose(solver.row_duals(), solution.row_dual)
    assert not np.allclose(solver.column_values(), before)


def test_binary_variables_are_integer_and_zero_one_bounded() -> None:
    """Binary variables are marked integer and bounded between 0 and 1."""
    solver = Solver()
    solver.setOptionValue("output_flag", False)
    b = solver.add_binary_variables(3, name="b")

    assert solver.has_integer_columns
    np.testing.assert_array_equal(solver.integer_columns, [0, 1, 2])
    for col in range(3):
        assert solver.getColIntegrality(col)[1] == HighsVarType.kInteger
    _, _, _, lower, upper, _ = solver.getCols(3, np.arange(3, dtype=np.int32))
    np.testing.assert_array_equal(lower, [0.0, 0.0, 0.0])
    np.testing.assert_array_equal(upper, [1.0, 1.0, 1.0])
    assert len(b) == 3


def test_mip_solve_finds_integer_solution_not_relaxed_lp() -> None:
    """A binary variable forces a choice that the LP relaxation makes fractionally."""
    solver = Solver()
    solver.setOptionValue("output_flag", False)
    solver.setOptionValue("mip_rel_gap", 0.0)
    b = int(solver.add_binary_variables(1, name="b").cols[0, 0])
    x = int(solver.add_variables(1, name="x", upper=10.0).cols[0, 0])
    # x >= 4.5 - 10*b, so b=1 lets x be 0 cheaply, b=0 requires x >= 4.5
    add_rows(solver, LinearArray.columns(x, 1) >= 4.5 - 10.0 * LinearArray.columns(b, 1))
    # minimize x + 3*b: b=1 costs 1+3=4, b=0 costs 4.5, so MIP picks b=1
    solver.changeColsCost(2, np.arange(2, dtype=np.int32), np.array([1.0, 3.0]))
    solver.run()
    assert solver.getModelStatus() == HighsModelStatus.kOptimal
    mip_value = solver.getObjectiveValue()
    np.testing.assert_allclose(solver.column_values()[[b, x]], [1.0, 0.0], atol=1e-9)
    assert mip_value == pytest.approx(1.0)

    # The LP relaxation chooses b=0.45 and x=0, with a lower objective
    solver.relax_integrality()
    solver.run()
    assert solver.getModelStatus() == HighsModelStatus.kOptimal
    lp_value = solver.getObjectiveValue()
    assert lp_value < mip_value - 0.5


def test_fixing_and_restoring_integer_columns() -> None:
    """Fixing integer columns makes them continuous and equal, and restoring brings back integrality."""
    solver = Solver()
    solver.setOptionValue("output_flag", False)
    solver.setOptionValue("mip_rel_gap", 0.0)
    b = solver.add_binary_variables(2, name="b")
    add_rows(solver, b[0] + b[1] >= 1.0)
    solver.changeColsCost(2, np.arange(2, dtype=np.int32), np.array([2.0, 1.0]))
    solver.run()
    assert solver.getModelStatus() == HighsModelStatus.kOptimal
    values = solver.column_values().copy()

    solver.fix_integer_columns(values)
    for col in solver.integer_columns:
        assert solver.getColIntegrality(col)[1] == HighsVarType.kContinuous
    _, _, _, lower, upper, _ = solver.getCols(2, np.arange(2, dtype=np.int32))
    np.testing.assert_array_equal(lower, values[:2])
    np.testing.assert_array_equal(upper, values[:2])

    solver.restore_integrality()
    for col in solver.integer_columns:
        assert solver.getColIntegrality(col)[1] == HighsVarType.kInteger
    _, _, _, lower, upper, _ = solver.getCols(2, np.arange(2, dtype=np.int32))
    np.testing.assert_array_equal(lower, [0.0, 0.0])
    np.testing.assert_array_equal(upper, [1.0, 1.0])
