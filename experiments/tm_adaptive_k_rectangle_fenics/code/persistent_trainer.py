"""
experiments/tm_adaptive_k_rectangle_fenics/persistent_trainer.py
=====================================================================
Experiment-local fork of thermal_pinn.training.trainer.train_window that
tests a hypothesis raised while reading rectangle_loss_curves.png: the
model WEIGHTS already warm-start across windows (never reset - see
[[thermal_pinn_adaptive_k_warmstart]] memory), but trainer.py's optimizer
does not - every train_window() call builds a brand new
optim.Adam(model.parameters(), lr=1e-3) and a fresh
CosineAnnealingLR(T_max=n_epochs), so Adam's momentum/variance buffers
are wiped and the learning rate jumps straight back up to 1e-3 at the
start of every window. That is exactly the sawtooth spike visible at
every window boundary in rectangle_loss_curves.png: converged weights
from the end of window i get "kicked" by the sudden high LR at the start
of window i+1, which is most damaging exactly when it matters most (right
after k increases and the window becomes physically harder).

This module is NOT a change to the shared trainer.py (fixed-k sweeps, the
original adaptive-k v1, and every existing thesis number all depend on
that file's current behaviour) - it is a local variant, scoped to this
experiment, so the two can be compared head-to-head.

What's different from train_window
-----------------------------------
- The Adam optimizer instance is created ONCE per run (per controller)
  and passed back in via `opt_state["optimizer"]`, so its momentum
  carries over between windows instead of being wiped.
- Windows after the first do not reset the learning rate all the way
  back to `lr` (1e-3 by default). Instead the optimizer's LR is set to
  `continuation_lr` (default 1e-4, roughly the geometric mean of lr and
  lr_min) before that window's own CosineAnnealingLR anneals it down to
  lr_min again over the window's epoch budget - a softer "continue
  fine-tuning" restart instead of a full "re-search" restart.
- Everything else (PDE residual, Robin BC, IC loss, end-supervision,
  L-BFGS refinement phase) is untouched, imported directly from
  trainer.py so the physics cannot drift out of sync with the original.
"""

from __future__ import annotations

import time
from typing import Callable

import torch
import torch.optim as optim

from thermal_pinn.training.trainer import (
    DELTA_T, H_CONV, T_WATER, W_BC, W_END, W_IC, W_PDE,
    _coord_lengths, _normalise_coords, _pde_residual, _robin_bc_loss,
)

import numpy as np


def train_window_persistent(
    model,
    domain,
    t_start: float,
    t_end: float,
    theta_ic_fn: Callable,
    theta_end_fn: Callable | None,
    opt_state: dict,
    n_domain: int = 1500,
    n_bc: int = 300,
    n_epochs: int = 800,
    lr: float = 1e-3,
    lr_min: float = 1e-5,
    continuation_lr: float = 1e-4,
    lbfgs_iters: int = 50,
    use_end_supervision: bool = True,
    w_end: float = W_END,
    device: torch.device | None = None,
    rng_seed: int = 0,
) -> dict:
    """Same contract as trainer.train_window, plus `opt_state` - a dict the
    caller keeps alive across the whole run (one per controller). On the
    first call opt_state["optimizer"] is absent/None and a fresh Adam is
    created; on every later call the SAME Adam instance (with its
    momentum/variance state intact) is reused, with its LR reset to
    `continuation_lr` (not `lr`) before this window's cosine anneal."""
    device = device or next(model.parameters()).device
    dim = model.dim
    rng = np.random.default_rng(rng_seed)
    alpha = getattr(domain, "alpha", 6.25e-5)
    h = getattr(domain, "h", H_CONV)
    dt_window = t_end - t_start
    coord_lengths_t = None

    if dim == 2:
        xi, yi = domain.sample_interior(n_domain, rng=rng)
        coords_np = np.stack([xi, yi], axis=1)
        bx, by, nx_, ny_ = domain.sample_boundary(n_bc, rng=rng)
        bc_np = np.stack([bx, by], axis=1)
        norms_np = np.stack([nx_, ny_], axis=1)
    else:
        xi, yi, zi = domain.sample_interior(n_domain, rng=rng)
        coords_np = np.stack([xi, yi, zi], axis=1)
        bx, by, bz, nx_, ny_, nz_ = domain.sample_boundary(n_bc, rng=rng)
        bc_np = np.stack([bx, by, bz], axis=1)
        norms_np = np.stack([nx_, ny_, nz_], axis=1)

    def to_t(a):
        return torch.tensor(a, dtype=torch.float32, device=device)

    coords_norm = _normalise_coords(coords_np, domain)
    bc_norm = _normalise_coords(bc_np, domain)
    tau_np = rng.uniform(0, 1, (n_domain, 1)).astype(np.float32)
    tau_bc = rng.uniform(0, 1, (n_bc, 1)).astype(np.float32)
    theta_ic_vals = theta_ic_fn(coords_np).reshape(-1, 1).astype(np.float32)
    theta_ic_bc = theta_ic_fn(bc_np).reshape(-1, 1).astype(np.float32)

    coords_t = to_t(coords_norm).requires_grad_(True)
    tau_t = to_t(tau_np).requires_grad_(True)
    theta_ic_t = to_t(theta_ic_vals)
    bc_t = to_t(bc_norm).requires_grad_(True)
    tau_bc_t = to_t(tau_bc).requires_grad_(True)
    theta_ic_bc_t = to_t(theta_ic_bc)
    norms_t = to_t(norms_np)

    theta_end_t = None
    if use_end_supervision and theta_end_fn is not None:
        theta_end_vals = theta_end_fn(coords_np).reshape(-1, 1).astype(np.float32)
        theta_end_t = to_t(theta_end_vals)
        tau_end_t = torch.ones(n_domain, 1, device=device)

    # ── Persistent Adam: create once, reuse (with momentum) every window ──
    first_window = "optimizer" not in opt_state
    if first_window:
        optimizer = optim.Adam(model.parameters(), lr=lr)
        opt_state["optimizer"] = optimizer
    else:
        optimizer = opt_state["optimizer"]
        for group in optimizer.param_groups:
            group["lr"] = continuation_lr

    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs, eta_min=lr_min)

    loss_history, loss_pde_hist, loss_bc_hist, loss_ic_hist, loss_end_hist = [], [], [], [], []
    t0 = time.time()
    model.train()

    for epoch in range(n_epochs):
        optimizer.zero_grad()
        loss_pde = _pde_residual(model, coords_t, tau_t, theta_ic_t, dt_window, alpha, lengths=coord_lengths_t)
        tau_zero = torch.zeros(n_domain, 1, device=device)
        pred_ic = model(coords_t, tau_zero, theta_ic_t)
        loss_ic = ((pred_ic - theta_ic_t) ** 2).mean()
        loss_bc = _robin_bc_loss(model, bc_t, norms_t, tau_bc_t, theta_ic_bc_t, h, lengths=coord_lengths_t)
        loss = W_PDE * loss_pde + W_IC * loss_ic + W_BC * loss_bc

        l_end_val = 0.0
        if theta_end_t is not None:
            pred_end = model(coords_t, tau_end_t, theta_ic_t)
            loss_end = ((pred_end - theta_end_t) ** 2).mean()
            loss = loss + w_end * loss_end
            l_end_val = float(loss_end.detach())

        loss.backward()
        optimizer.step()
        scheduler.step()
        loss_history.append(float(loss.detach()))
        loss_pde_hist.append(float(loss_pde.detach()))
        loss_bc_hist.append(float(loss_bc.detach()))
        loss_ic_hist.append(float(loss_ic.detach()))
        loss_end_hist.append(l_end_val)

    if lbfgs_iters > 0:
        lbfgs = optim.LBFGS(model.parameters(), max_iter=lbfgs_iters,
                             line_search_fn="strong_wolfe", tolerance_grad=1e-7, tolerance_change=1e-9)

        def closure():
            lbfgs.zero_grad()
            lp = _pde_residual(model, coords_t, tau_t, theta_ic_t, dt_window, alpha, lengths=coord_lengths_t)
            pred_ic_ = model(coords_t, torch.zeros(n_domain, 1, device=device), theta_ic_t)
            li = ((pred_ic_ - theta_ic_t) ** 2).mean()
            lb = _robin_bc_loss(model, bc_t, norms_t, tau_bc_t, theta_ic_bc_t, h, lengths=coord_lengths_t)
            total = W_PDE * lp + W_IC * li + W_BC * lb
            if theta_end_t is not None:
                total = total + w_end * ((model(coords_t, tau_end_t, theta_ic_t) - theta_end_t) ** 2).mean()
            total.backward()
            return total

        try:
            lbfgs.step(closure)
        except RuntimeError:
            pass

    return {
        "loss_history": loss_history, "loss_pde_history": loss_pde_hist,
        "loss_bc_history": loss_bc_hist, "loss_ic_history": loss_ic_hist,
        "loss_end_history": loss_end_hist, "runtime_s": time.time() - t0,
    }
