// Conjugate gradient on the 2D Poisson matrix: a small, fixed sparse benchmark for NumericOS.
//
// The matrix is the 5-point Laplacian on an n x n grid of unknowns with Dirichlet boundary
// (4 on the diagonal, -1 for each neighbour), stored in CSR. It is symmetric positive
// definite. The right-hand side is built from a known solution x*, b = A x*, so the error of
// the computed solution can be measured and not only its residual.
//
// The working precision is a parameter: `--precision single` runs the same algorithm in
// float. What was achieved is always measured in double precision: the true residual
// ||b - A x|| / ||b|| and the error ||x - x*|| / ||x*||. The residual that CG updates by
// recurrence keeps decreasing after the true one has stalled, so the two must not be confused.
//
//   c++ -O2 -std=c++17 -o cg cg.cpp
//   ./cg --n 128 --tol 1e-10 --max-iter 2000 --precision double

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "numericos_metrics.hpp"

template <typename Real>
struct Csr {
    int rows = 0;
    std::vector<int> start;   // row i owns entries start[i] .. start[i+1]-1
    std::vector<int> column;
    std::vector<Real> value;
};

template <typename Real>
Csr<Real> poisson2d(int n) {
    Csr<Real> a;
    a.rows = n * n;
    a.start.reserve(a.rows + 1);
    a.start.push_back(0);
    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            const int row = i * n + j;
            if (i > 0) { a.column.push_back(row - n); a.value.push_back(Real(-1)); }
            if (j > 0) { a.column.push_back(row - 1); a.value.push_back(Real(-1)); }
            a.column.push_back(row);
            a.value.push_back(Real(4));
            if (j < n - 1) { a.column.push_back(row + 1); a.value.push_back(Real(-1)); }
            if (i < n - 1) { a.column.push_back(row + n); a.value.push_back(Real(-1)); }
            a.start.push_back(static_cast<int>(a.column.size()));
        }
    }
    return a;
}

template <typename Real>
void multiply(const Csr<Real>& a, const std::vector<Real>& x, std::vector<Real>& y) {
    for (int row = 0; row < a.rows; ++row) {
        Real sum = 0;
        for (int k = a.start[row]; k < a.start[row + 1]; ++k) {
            sum += a.value[k] * x[a.column[k]];
        }
        y[row] = sum;
    }
}

template <typename Real>
Real dot(const std::vector<Real>& x, const std::vector<Real>& y) {
    Real sum = 0;
    for (std::size_t k = 0; k < x.size(); ++k) {
        sum += x[k] * y[k];
    }
    return sum;
}

// The known solution: smooth enough to be representable, not an eigenvector of the matrix.
inline double exact_solution(int k) { return 1.0 + (k % 7) / 7.0; }

template <typename Real>
int solve(int n, double tolerance, int max_iterations, int report_every) {
    const Csr<Real> a = poisson2d<Real>(n);
    const int size = a.rows;
    std::vector<Real> x_exact(size), b(size), x(size, Real(0)), r(size), p(size), ap(size);
    for (int k = 0; k < size; ++k) {
        x_exact[k] = static_cast<Real>(exact_solution(k));
    }
    multiply(a, x_exact, b);
    r = b;
    p = r;
    Real rr = dot(r, r);
    const double norm_b = std::sqrt(static_cast<double>(dot(b, b)));

    int iterations = 0;
    bool converged = false;
    const auto began = std::chrono::steady_clock::now();
    while (iterations < max_iterations) {
        multiply(a, p, ap);
        const Real alpha = rr / dot(p, ap);
        for (int k = 0; k < size; ++k) {
            x[k] += alpha * p[k];
            r[k] -= alpha * ap[k];
        }
        const Real rr_next = dot(r, r);
        ++iterations;
        const double residual = std::sqrt(static_cast<double>(rr_next)) / norm_b;
        converged = residual <= tolerance;
        if (iterations % report_every == 0 || converged) {
            // The residual CG maintains by recurrence. It is not ||b - A x||.
            numericos::metric("residual_rel", residual, iterations);
        }
        if (converged || !std::isfinite(residual)) {
            break;
        }
        const Real beta = rr_next / rr;
        for (int k = 0; k < size; ++k) {
            p[k] = r[k] + beta * p[k];
        }
        rr = rr_next;
    }
    const double seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count();

    // What was achieved, measured in double precision whatever the working precision.
    const Csr<double> a_double = poisson2d<double>(n);
    std::vector<double> x_double(size), b_double(size), ax(size), exact(size);
    for (int k = 0; k < size; ++k) {
        x_double[k] = static_cast<double>(x[k]);
        exact[k] = exact_solution(k);
    }
    multiply(a_double, exact, b_double);
    multiply(a_double, x_double, ax);
    double residual_squared = 0, b_squared = 0, error_squared = 0, exact_squared = 0;
    for (int k = 0; k < size; ++k) {
        const double residual_k = b_double[k] - ax[k];
        const double error_k = x_double[k] - exact[k];
        residual_squared += residual_k * residual_k;
        b_squared += b_double[k] * b_double[k];
        error_squared += error_k * error_k;
        exact_squared += exact[k] * exact[k];
    }
    const double true_residual = std::sqrt(residual_squared / b_squared);
    const double error = std::sqrt(error_squared / exact_squared);

    numericos::metric("iterations", iterations);
    numericos::metric("converged", converged ? 1.0 : 0.0);
    numericos::metric("solve_seconds", seconds);
    numericos::metric("true_residual_rel", true_residual);
    numericos::metric("error_rel", error);
    std::printf(
        "cg: n=%d unknowns=%d precision=%s iterations=%d converged=%s solve_seconds=%.6f "
        "true_residual_rel=%.3e error_rel=%.3e\n",
        n, size, sizeof(Real) == sizeof(float) ? "single" : "double", iterations,
        converged ? "yes" : "no", seconds, true_residual, error);
    return 0;
}

int main(int argc, char** argv) {
    int n = 64, max_iterations = 2000, report_every = 10;
    double tolerance = 1e-10;
    std::string precision = "double";
    for (int k = 1; k + 1 < argc; k += 2) {
        const std::string option = argv[k];
        const char* value = argv[k + 1];
        if (option == "--n") n = std::atoi(value);
        else if (option == "--tol") tolerance = std::atof(value);
        else if (option == "--max-iter") max_iterations = std::atoi(value);
        else if (option == "--report-every") report_every = std::atoi(value);
        else if (option == "--precision") precision = value;
        else { std::fprintf(stderr, "cg: unknown option %s\n", option.c_str()); return 2; }
    }
    if (argc % 2 == 0 || n < 2 || max_iterations < 1 || report_every < 1 || tolerance <= 0) {
        std::fprintf(stderr, "usage: cg --n N --tol T --max-iter M --precision double|single\n");
        return 2;
    }
    if (precision == "double") return solve<double>(n, tolerance, max_iterations, report_every);
    if (precision == "single") return solve<float>(n, tolerance, max_iterations, report_every);
    std::fprintf(stderr, "cg: --precision must be double or single\n");
    return 2;
}
