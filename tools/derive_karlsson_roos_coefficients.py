"""
Derive default Karlsson-Roos angular coefficients for clear float glazing.

WHY THIS SCRIPT EXISTS
----------------------
The Karlsson & Roos (2000) paper gives the functional form

    g(theta) / g(0) = 1 - a*z**alpha - b*z**beta - c*z**gamma,   z = theta / 90

together with a table of fitted (a, b, c, alpha, beta, gamma) per glazing
category. That table is behind a paywall and could not be consulted, so the
coefficients shipped as defaults in the engine are NOT reproduced from it.

Instead they are fitted here to a first-principles Fresnel + Beer-Lambert
reference curve for uncoated clear float glass, subject to the Roos constraint
a + b + c = 1 (which forces g(90 deg) = 0). The functional form is Karlsson-Roos;
the numbers are ours and are reproducible by running this script.

For coated or solar-control glazing the published coefficients should be
supplied explicitly through ``window_angular_coefficients`` rather than relying
on these defaults.

Usage
-----
    python tools/derive_karlsson_roos_coefficients.py
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

# --- Optical constants for clear soda-lime float glass ----------------------
N_GLASS = 1.52          # refractive index, solar-averaged [-]
THICKNESS_M = 0.004     # single pane thickness [m]
K_EXTINCTION = 26.0     # extinction coefficient [1/m], clear float glass

def single_pane_tau_rho(theta_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Angular transmittance and reflectance of one clear pane, averaged over
    polarisation, including multiple internal reflections and bulk absorption.
    """
    theta = np.radians(np.asarray(theta_deg, dtype=float))
    sin_r = np.sin(theta) / N_GLASS
    sin_r = np.clip(sin_r, -1.0, 1.0)
    theta_r = np.arcsin(sin_r)

    cos_i = np.cos(theta)
    cos_r = np.cos(theta_r)

    # Fresnel interface reflectance, per polarisation
    with np.errstate(divide="ignore", invalid="ignore"):
        r_s = ((cos_i - N_GLASS * cos_r) / (cos_i + N_GLASS * cos_r)) ** 2
        r_p = ((cos_r - N_GLASS * cos_i) / (cos_r + N_GLASS * cos_i)) ** 2

    # At exactly 90 deg the beam is parallel to the surface: total reflection.
    r_s = np.where(cos_i <= 1e-12, 1.0, r_s)
    r_p = np.where(cos_i <= 1e-12, 1.0, r_p)

    # Bulk (Beer-Lambert) transmittance along the refracted path
    path = THICKNESS_M / np.maximum(cos_r, 1e-12)
    tau_a = np.exp(-K_EXTINCTION * path)

    def _slab(r):
        denom = 1.0 - (r ** 2) * (tau_a ** 2)
        tau = ((1.0 - r) ** 2) * tau_a / np.maximum(denom, 1e-12)
        rho = r * (1.0 + tau * tau_a)
        return tau, rho

    tau_s, rho_s = _slab(r_s)
    tau_p, rho_p = _slab(r_p)
    return 0.5 * (tau_s + tau_p), 0.5 * (rho_s + rho_p)


def multi_pane_tau(theta_deg: np.ndarray, n_panes: int) -> np.ndarray:
    """
    Transmittance of n identical panes in series, using the standard two-flux
    net-layer combination (multiple inter-pane reflections retained).
    """
    tau1, rho1 = single_pane_tau_rho(theta_deg)
    tau, rho = tau1.copy(), rho1.copy()
    for _ in range(n_panes - 1):
        denom = np.maximum(1.0 - rho * rho1, 1e-12)
        tau_new = tau * tau1 / denom
        rho_new = rho + (tau ** 2) * rho1 / denom
        tau, rho = tau_new, rho_new
    return tau


def roos_polynomial(
    theta_deg: np.ndarray,
    a: float,
    b: float,
    c: float,
    alpha: float,
    beta: float,
    gamma: float,
) -> np.ndarray:
    z = np.clip(np.asarray(theta_deg, dtype=float) / 90.0, 0.0, 1.0)
    return 1.0 - a * z ** alpha - b * z ** beta - c * z ** gamma


def fit_for_panes(n_panes: int) -> tuple[tuple[float, ...], float]:
    """
    Fit (a, b, c, alpha, beta, gamma) with a + b + c = 1 enforced, so the curve
    passes exactly through F(0)=1 and F(90)=0.

    Returns ((a, b, c, alpha, beta, gamma), max_abs_error).
    """
    theta = np.linspace(0.0, 90.0, 181)
    tau = multi_pane_tau(theta, n_panes)
    target = tau / tau[0]

    # Exponents are parametrised as gamma, beta = gamma + d1, alpha = beta + d2
    # with d1, d2 >= 1. Keeping them well separated stops (a, b) from becoming
    # a pair of huge cancelling numbers when two exponents collide, which is
    # numerically fragile even when the residual is small.
    def unpack(p):
        a, b, gamma, d1, d2 = p
        beta = gamma + d1
        alpha = beta + d2
        return a, b, 1.0 - a - b, alpha, beta, gamma

    def residual(p):
        a, b, c, alpha, beta, gamma = unpack(p)
        return roos_polynomial(theta, a, b, c, alpha, beta, gamma) - target

    best = None
    for a0 in (0.2, 0.5, 0.8):
        for ga0, d1_0, d2_0 in ((1.0, 3.0, 4.0), (2.0, 4.0, 8.0), (2.5, 5.0, 20.0)):
            try:
                sol = least_squares(
                    residual,
                    x0=[a0, 1.0 - a0 - 0.05, ga0, d1_0, d2_0],
                    bounds=([-3.0, -3.0, 0.5, 1.0, 1.0], [3.0, 3.0, 6.0, 20.0, 60.0]),
                    method="trf",
                )
            except Exception:
                continue
            err = float(np.max(np.abs(residual(sol.x))))
            if best is None or err < best[1]:
                best = (sol.x, err)

    p, max_err = best
    a, b, c, alpha, beta, gamma = unpack(p)
    return (float(a), float(b), float(c), float(alpha), float(beta), float(gamma)), max_err


def diffuse_factor(a: float, b: float, c: float, alpha: float, beta: float, gamma: float) -> float:
    """
    Isotropic-hemispherical average of the angular factor:

        F_diff = 2 * integral_0^{pi/2} F(theta) cos(theta) sin(theta) d(theta)

    This is the diffuse counterpart F_W,diff, derived from the same curve rather
    than assumed.
    """
    theta = np.linspace(0.0, 90.0, 4001)
    rad = np.radians(theta)
    f = roos_polynomial(theta, a, b, c, alpha, beta, gamma)
    return float(2.0 * np.trapezoid(f * np.cos(rad) * np.sin(rad), rad))


def main() -> None:
    print(f"Glass: n={N_GLASS}, d={THICKNESS_M*1000:.1f} mm, K={K_EXTINCTION} 1/m\n")
    header = (
        f"{'panes':>5} {'a':>9} {'b':>9} {'c':>9} "
        f"{'alpha':>7} {'beta':>7} {'gamma':>7} {'maxerr':>9} {'F_diff':>7} {'tau(0)':>7}"
    )
    print(header)
    print("-" * len(header))
    fits = {}
    for n in (1, 2, 3):
        (a, b, c, al, be, ga), err = fit_for_panes(n)
        fits[n] = (a, b, c, al, be, ga)
        f_diff = diffuse_factor(a, b, c, al, be, ga)
        tau0 = float(multi_pane_tau(np.array([0.0]), n)[0])
        print(
            f"{n:>5} {a:>9.5f} {b:>9.5f} {c:>9.5f} {al:>7.3f} {be:>7.3f} {ga:>7.3f} "
            f"{err:>9.2e} {f_diff:>7.4f} {tau0:>7.4f}"
        )

    print("\nSpot values of F_W,dir(theta) for the 2-pane fit:")
    a, b, c, al, be, ga = fits[2]
    tau0 = float(multi_pane_tau(np.array([0.0]), 2)[0])
    for t in (0, 30, 45, 60, 70, 80, 90):
        exact = float(multi_pane_tau(np.array([float(t)]), 2)[0] / tau0)
        fit = float(roos_polynomial(np.array([float(t)]), a, b, c, al, be, ga)[0])
        print(f"  theta={t:>2} deg  fit={fit:.4f}  fresnel={exact:.4f}  diff={fit-exact:+.4f}")

    print("\nPaste-ready defaults for utils.py:")
    print("_WINDOW_ANGULAR_COEFFS_DEFAULT = {")
    for n in (1, 2, 3):
        a, b, c, al, be, ga = fits[n]
        print(
            f"    {n}: ({a:.5f}, {b:.5f}, {c:.5f}, {al:.4f}, {be:.4f}, {ga:.4f}),"
        )
    print("}")
    print("_WINDOW_ANGULAR_DIFFUSE_DEFAULT = {")
    for n in (1, 2, 3):
        print(f"    {n}: {diffuse_factor(*fits[n]):.5f},")
    print("}")


if __name__ == "__main__":
    main()
