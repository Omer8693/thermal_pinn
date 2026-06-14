# Neural Architecture Search Guided Physics Informed Neural Networks for Finite Element Method Anchored Transient Heat Transfer Simulation

**Step Optimization in Thermal Simulation Using Selective Finite Element Method Step Skipping**

*Master's Thesis — Ömer Cetinkaya, University of Agder, 2026*

**[Project Website](https://omer8693.github.io/thermal_pinn/)** — results, figures, and method overview

This repository contains the code, metrics, and results for the thesis. It extends the NAS-PINN framework of Wang & Zhong (2024) to FEM-anchored transient heat transfer simulation using a Multi-Step Window Prediction (MSWP) strategy.

## Motivation

Water quenching of A356 aluminium castings produces non-uniform temperature fields that drive residual stress and shape distortion. Finite Element Method (FEM) simulation is accurate but expensive — repeated design studies multiply the cost quickly.

This work asks: **how many FEM solver calls can be replaced by PINN predictions without losing useful accuracy?**

## Approach

The framework divides the 30-second quench into short prediction windows. At the start of each window, FEM provides the current temperature field as a fixed anchor. The PINN then predicts the field over the rest of the window. This strategy is called **Multi-Step Window Prediction (MSWP)**.

A skip factor `k ∈ {1, 2, 3, 4, 5}` controls how many FEM calls are used:
- `k=1` → FEM at every step (0% saving, baseline)
- `k=5` → FEM at 4 of 20 steps (80% saving)

Three architectures were found via NAS and compared across ten benchmark geometries in 2D, 3D, and a 3D Thermal Fin:
- **Bayesian/TPE** — large ReLU network (5×151), Fourier embedding
- **NSGA-II** — compact tanh network (3×153)
- **NSGA-III** — compact tanh network (3×75)

An **adaptive-k controller** adjusts the skip factor dynamically based on per-window prediction error.

## Key Results

Two separate 2D studies were conducted, followed by 3D and Thermal Fin benchmarks.

| Study | Domains | Best architecture | Best MAE | FEM saving |
|---|---|---|---:|---:|
| 2D Adaptive-k (NAS transfer comparison) | 4 domains: Square, Circle, L-Shape, Flower | Bayesian/TPE | < 2.5°C | 83–85% |
| 2D Canonical fixed-k sweep | 3 domains: Rectangle, Circle, L-Shape | Bayesian/TPE | < 5°C | up to 80% |
| 3D Canonical fixed-k sweep | 4 domains: Cylinder, L-Shape, Rectangular, Stacked | Bayesian/TPE | < 14°C | up to 80% |
| Thermal Fin (3D) | 1 domain (3D fin geometry) | Bayesian/TPE + Fourier | < 13°C | up to 80% |

- PINN-only (no FEM anchoring) fails on all complex geometries — errors reach 60–217°C
- FEM anchoring is a structural requirement, not an optional component
- Bayesian/TPE achieves the lowest error across nearly all benchmarks

## Repository Structure

```
thermal_pinn/
├── network/          # PINN network architectures (Fourier, standard MLP)
├── physics/          # Domain definitions (2D, 3D, Thermal Fin)
├── training/         # Training loops and MSWP framework
├── plots/            # Plotting scripts for results
├── checkpoints/      # Experiment metrics (JSON) — .pt model files excluded
├── results/          # Generated figures and tables
└── quenching_mswp/   # Quenching MSWP experiments (4 geometries, 10 seeds)
```

## Physical Setup

| Parameter | Value |
|---|---|
| Material | A356 aluminium |
| Initial temperature | 540°C |
| Quench bath | 20°C |
| Simulation time | 30 s |
| Convection coefficient h (2D) | 5000 W/(m²K) |
| Convection coefficient h (3D/Fin) | 4000 W/(m²K) |
| FEM solver | Crank–Nicolson (Δt = 0.5 s) |
| Acceptance threshold | MAE ≤ 15°C |

## References

**NAS-PINN (original framework this work extends):**

> Wang, Y. & Zhong, L. (2024). NAS-PINN: Neural architecture search-guided physics-informed neural network for solving PDEs. *Journal of Computational Physics*, 496, 112603. https://doi.org/10.1016/j.jcp.2023.112603

**Physical parameters and engineering motivation:**

> Mortensen et al. (2026). *FEM-based thermomechanical simulation of water quenching for A356 aluminium subframes.*
