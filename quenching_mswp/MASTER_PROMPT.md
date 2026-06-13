# MASTER PROMPT FOR CLAUDE CODE
# ===============================
# Paste this entire content into Claude Code as the FIRST message.
# Do not paraphrase, do not summarize, paste verbatim.

# ============================================================
# PROJECT: NAS-PINN benchmark domains under Mortensen aluminum
#          quenching physics, evaluated with MSWP framework
#
# ADVISOR REQUIREMENTS (highest priority):
#   1. k=1 must give PINN approximately equal to FEM (sanity check)
#   2. Use NAS-PINN paper benchmark geometries (not invented ones)
#   3. Apply Mortensen physical parameters
#   4. Use thesis MSWP framework logic
#   5. Three-method comparison ONLY: FEM, PINN-only, NAS-PINN
#   6. NAS-PINN itself has two variants tested CONDITIONALLY:
#        C1: Original NAS-PINN algorithm (Wang and Zhong 2023)
#        C2: Thesis NAS variants (Bayesian/TPE, NSGA-II, NSGA-III)
#      C2 is required ONLY if C1 fails acceptance criteria.
#      If C1 passes, C2 becomes optional ablation study.
# ============================================================

You are helping me implement a research codebase for a master's thesis
in physics-informed neural networks (PINNs) applied to aluminum
quenching simulation. Read this entire specification carefully before
writing any code. Do NOT skip ahead. Do NOT add features I did not
ask for. Do NOT add manual baseline architectures (no Giant, Dumpy,
Slender). Architectures must be discovered by NAS algorithms only.


# === REFERENCE PAPERS ===

PAPER 1 (industrial physics source):
  Mortensen et al. (2026) "Mitigating distortions in cast automotive
  subframes: A finite element simulation approach."
  Int J Adv Manuf Technol. DOI: 10.1007/s00170-026-17515-w

PAPER 2 (NAS algorithm and benchmark geometries):
  Wang Y and Zhong L (2023) "NAS-PINN: Neural architecture search-
  guided physics-informed neural network for solving PDEs."
  J Comp Physics 496:112603. arXiv:2305.10127

PAPER 3 (improved NAS algorithm, read for context only):
  Wang Y and Zhong L (2025) "NAS-PINNv2..." arXiv:2501.15160

We do NOT implement plasma equations from paper 3. We only borrow
algorithmic ideas (sigmoid relaxation, 0-1 loss term) if needed
during C2 implementation.


# === THREE-LAYER LOGIC ===

GEOMETRY  = Wang and Zhong 2023 (literature validated)
PHYSICS   = Mortensen 2026 (industrial validated)
METHOD    = MSWP framework (thesis original contribution)


# === BENCHMARK GEOMETRIES ===

WHICH BENCHMARKS WE USE (and why):

Source: Wang and Zhong 2023, Table 2 ("Poisson equation: L2 error in
different computational domains"). The original paper uses these
geometries for steady-state Poisson with NAS-PINN. We adopt the SAME
geometries but apply Mortensen transient heat conduction physics
under Robin boundary conditions. This gives us:
  - Literature-validated geometric benchmarks (defensible to reviewers)
  - Industrial physics setup (defensible to reviewers)
  - MSWP framework (thesis contribution)

The four geometries (2D only for primary results):

  G1. Square: [0,1] x [0,1]
      Simplest baseline. Smooth, convex, no corner singularities.

  G2. Circle: center (0.5, 0.5), radius 0.5
      Smooth boundary. Tests how PINN handles curved Robin BC.

  G3. L-shape: ([0,2] x [0,2]) minus ([1,2] x [1,2])
      Non-convex with reentrant corner. Tests handling of geometric
      singularity, which historically challenges PINNs.

  G4. Flower: r(theta) = 0.5 + 0.2*sin(5*theta) in polar coords
      High-curvature oscillating boundary. Hardest geometry in the
      Wang and Zhong 2023 set.

EXPECTED DIFFICULTY ORDERING (from easiest to hardest):
  Square < Circle < L-shape < Flower

This ordering matches Wang and Zhong 2023 Table 2 L2 errors and
gives us four difficulty tiers to test method robustness.


CURRENT SCOPE (Phase 1) vs FUTURE PHASES:

PHASE 1 (this codebase, NOW):
  Only the four 2D NAS-PINN geometries (G1-G4 above).
  Focus exclusively here. Get acceptance criteria passing.
  Do NOT implement other geometries in Phase 1.

PHASE 2 (after Phase 1 passes, NOT YET):
  Thermal Fin (rbniCS Tutorial-01, from thesis):
    Will be re-introduced with transient Mortensen physics.
    Codebase should be structured so adding Thermal Fin later
    requires only a new geometry module, no framework changes.

PHASE 3 (after Phase 2 passes, NOT YET):
  3D extensions (cube, cylinder, L-prism, from thesis):
    Will be re-introduced with same Mortensen physics.
    Codebase architecture should anticipate 3D extension:
    - Geometry modules should not hardcode 2D assumptions
    - FEM solver should support 3D meshes (scikit-fem does)
    - PINN network input layer must scale to (t, x, y) or (t, x, y, z)
    - Visualization needs 3D plotting hooks (placeholders only now)

DESIGN PRINCIPLE:
  Build Phase 1 NOW with the architecture that anticipates
  Phases 2 and 3. Do NOT implement Phases 2 and 3 yet, but DO
  leave the doors open. Specifically:
    - Use abstract base classes for Geometry
    - Use dimension-agnostic tensor operations in PINN
    - Use config-driven dimensionality (dim: 2 in YAML, switchable later)
    - Document where 3D additions will hook in

PLASMA EQUATIONS (Wang and Zhong 2025):
  NOT implemented in any phase. We borrow algorithmic ideas
  only (sigmoid relaxation, 0-1 loss) if needed during NAS-PINN
  C2 work.

ARCHIVE NOTE:
  Existing thesis results on Thermal Fin and 3D geometries should
  be PRESERVED in a separate archive folder. Do NOT delete prior
  work. They remain available for later comparison once Phase 2
  and Phase 3 results come in.


# === PHYSICAL PARAMETERS (from Mortensen 2026 + thesis Table 3.9) ===

  Material:          A356 aluminum
  T_0:               540 degC (initial)
  T_w:               20 degC (water bath)
  Duration:          30 s
  k_T:               150 W/(m K)
  rho * c_p:         2.4e6 J/(m^3 K)
  h:                 5000 W/(m^2 K) (constant for now)
  BC:                Robin: -k_T * grad(T) . n = h * (T - T_w)
  IC:                T(x, 0) = T_0 everywhere


# === NUMERICAL SETUP ===

  FEM time step dt_fem:     0.5 s
  Total FEM steps:          60 (for 30 s)
  FEM scheme:               implicit (backward Euler)
  PINN anchor base spacing: 1.5 s (3 x dt_fem)
  MSWP window count k:      1, 2, 3, 4, 5

  k=1: anchor every 1.5s -> 21 FEM solves
  k=2: anchor every 3.0s -> 11 FEM solves
  k=3: anchor every 4.5s ->  8 FEM solves
  k=4: anchor every 6.0s ->  6 FEM solves
  k=5: anchor every 7.5s ->  5 FEM solves
  Pure FEM baseline:        60 FEM solves

PHYSICAL JUSTIFICATION (cite in code comments):
  Fourier number Fo = alpha * dt / L^2 with
    alpha = k_T / (rho*cp) = 6.25e-5 m^2/s
    L = 0.01 m (thin wall characteristic length)
    Fo(0.5s) = 0.31  -> stable for implicit FEM
  Boiling regime transitions (Mortensen Fig 6) take 1-3 s,
  resolved by dt=0.5s with at least 3 samples.
  Anchor 1.5s captures one physical phase of cooling curve.


# === METHOD LAYERS ===

LAYER A: FEM (reference solution)
  Pure FEM at dt=0.5s for full 30s.
  Used as ground truth.

LAYER B: PINN-only
  Single PINN window covering full 30s.
  Fixed architecture: [input, 50, 50, 50, 50, output]
  (This is NOT optimized -- tests if PINN can solve full window.)
  Expected to underperform. Demonstrates why MSWP is needed.

LAYER C: NAS-PINN
  Architecture discovered by NAS algorithm.
  Then MSWP framework applied.

  C1: ORIGINAL NAS-PINN (Wang and Zhong 2023)
    Search space:
      Hidden layers: 1 to 7
      Neurons per layer candidates: {10, 30, 50, 70, 90, 110}
      Activation: tanh
      Skip operations allowed (residual)
    Algorithm (from paper Section 3, Algorithm 1):
      Continuous relaxation, softmax-weighted alpha
      One-zero tensor masks for neuron count
      Bi-level optimization:
        Inner: optimize theta with PINN loss
        Outer: optimize alpha with MSE against reference
      Adam for both loops

  C2: THESIS NAS VARIANTS (run conditionally, see decision points)
    Same search space as C1.

    C2a: TPE via optuna, 50 trials, minimize MAE
    C2b: NSGA-II via pymoo, population 20, generations 25,
         minimize (MAE, parameter count)
    C2c: NSGA-III via pymoo, same as NSGA-II with reference dirs


# === ACCEPTANCE CRITERIA ===

For C1 (and later C2) to be "accepted", ALL must hold:

  k=1 sanity MAE         < 1.0 degC (advisor requirement)
  k=5 MAE                < 15 degC  (3% of 540-20 range)
  k=5 L2 error           < 0.05 (normalized)
  FEM saving at k=5      > 85%
  Reproducibility (3 seeds) standard deviation < 2 degC

If C1 passes for all four geometries: C2 becomes OPTIONAL ablation.
If C1 fails any criterion: C2 becomes REQUIRED.


# === IMPLEMENTATION STAGES WITH DECISION POINTS ===

We work in STAGES. After each stage, STOP and let me review.

----------------------------------------------------------------
STAGE 0: Project scaffold
  - Directory structure
  - requirements.txt with pinned versions
  - README.md
  - Logging utility (rotating file + console)
  - YAML config system
  STOP for review

----------------------------------------------------------------
STAGE 1: FEM reference solver
  - Transient heat equation, implicit Euler
  - scikit-fem library
  - All four geometries
  - Proper Robin BC weak form
  - Save snapshots every dt=0.5s
  - Measure and log runtime
  STOP for review

----------------------------------------------------------------
STAGE 2: Pure FEM baseline run
  - All four geometries
  - Heat maps at t = 0, 0.5, 1, 3, 10, 30 s
  - Runtime CSV
  - Jupyter notebook with all four solutions
  STOP for review

----------------------------------------------------------------
STAGE 3: PINN-only (Layer B)
  - Fixed architecture [50, 50, 50, 50]
  - Single window for full 30s
  - PDE + BC + IC losses
  - Self-adaptive loss weighting
  - Adam 5000 + L-BFGS 1000
  - Compare to FEM, expect underperformance
  STOP for review

----------------------------------------------------------------
STAGE 4: NAS-PINN C1 (original Wang and Zhong 2023)
  - Implement bi-level optimization
  - Search architecture per geometry under Mortensen physics
  - Train discovered architecture from scratch
  - Compare to FEM and PINN-only
  - Report discovered architectures and metrics
  STOP for review

----------------------------------------------------------------
STAGE 5: MSWP k=1 sanity check on C1 architectures
  - Apply MSWP framework, k=1 only
  - Check acceptance criteria:
      MAE < 1.0 degC
      L2 ratio <= 1.1
      Max err < 5 degC
  - If FAIL: debug (BC weight, capacity, collocation, epochs)
  - If PASS: proceed to Stage 6
  STOP for review

----------------------------------------------------------------
STAGE 6: MSWP k=2,3,4,5 sweep with C1 architectures
  - All four geometries
  - Three seeds per (geometry, k)
  - Runtime breakdown: fem_portion, pinn_train, pinn_infer, total
  - Compare to pure FEM runtime
  - Generate full results table and figures
  STOP for review

----------------------------------------------------------------
DECISION POINT 1: Does C1 pass all acceptance criteria?

  CASE A: C1 PASSES for all four geometries
    -> Original NAS-PINN architecture is sufficient under MSWP.
    -> Thesis contribution: NAS-PINN benchmarks adapted to
       industrial physics via MSWP framework.
    -> Stage 7 becomes OPTIONAL ablation study.
    -> Ask user whether to continue with C2 or skip to Stage 8.

  CASE B: C1 FAILS one or more criteria
    -> Original NAS-PINN insufficient for quenching.
    -> Thesis contribution: improved NAS for quenching.
    -> Stage 7 becomes REQUIRED.
    -> Proceed automatically to Stage 7.

----------------------------------------------------------------
STAGE 7: Thesis NAS variants (Layer C2)
  Run conditionally based on Decision Point 1.

  - C2a: TPE search per geometry, apply MSWP k=1 to 5
  - C2b: NSGA-II search per geometry, apply MSWP k=1 to 5
  - C2c: NSGA-III search per geometry, apply MSWP k=1 to 5
  - Three seeds per configuration
  - Compare against C1 results
  STOP for review

----------------------------------------------------------------
DECISION POINT 2: Did any C2 variant beat C1?

  CASE I: C2 beats C1
    -> Thesis contribution validated as improvement.
    -> Report which variant best, on which geometry.

  CASE II: C2 matches C1
    -> Confirms C1 was already near-optimal.
    -> Frame as "validation that simpler NAS suffices".

  CASE III: C2 underperforms C1
    -> Report honestly as negative result.
    -> Discuss why (search budget, multi-objective penalty).

----------------------------------------------------------------
STAGE 8: Final aggregation and reporting
  - Combine all results
  - Generate publication-ready figures
  - Write summary report
  - Generate appendix with hyperparameters, seeds, runtimes


# === DIRECTORY STRUCTURE ===

quenching_mswp/
|-- README.md
|-- requirements.txt
|-- configs/
|   |-- material_a356.yaml
|   |-- geometry_square.yaml
|   |-- geometry_circle.yaml
|   |-- geometry_lshape.yaml
|   |-- geometry_flower.yaml
|   |-- nas_original.yaml
|   |-- nas_tpe.yaml
|   |-- nas_nsga2.yaml
|   |-- nas_nsga3.yaml
|   `-- experiment_default.yaml
|-- src/
|   |-- geometries/    (square, circle, lshape, flower)
|   |-- physics/       (heat_equation, boundary_conditions)
|   |-- fem/           (solver, mesh)
|   |-- pinn/          (network, loss, trainer)
|   |-- nas/
|   |   |-- search_space.py
|   |   |-- nas_pinn_original.py   (C1)
|   |   |-- nas_tpe.py             (C2a)
|   |   |-- nas_nsga2.py           (C2b)
|   |   `-- nas_nsga3.py           (C2c)
|   |-- mswp/          (framework, runner)
|   `-- utils/         (logging, metrics, visualization)
|-- experiments/
|   |-- stage1_fem_solver.py
|   |-- stage2_fem_baseline.py
|   |-- stage3_pinn_only.py
|   |-- stage4_nas_original.py
|   |-- stage5_mswp_k1_sanity.py
|   |-- stage6_mswp_k_sweep.py
|   |-- stage7_thesis_nas.py
|   `-- stage8_final_report.py
|-- notebooks/
|   |-- 01_fem_reference.ipynb
|   |-- 02_pinn_only_validation.ipynb
|   |-- 03_nas_original_results.ipynb
|   |-- 04_mswp_results.ipynb
|   |-- 05_thesis_nas_comparison.ipynb
|   `-- 06_final_aggregation.ipynb
|-- results/
|   |-- fem/
|   |-- pinn_only/
|   |-- nas_original/  (one folder per geometry, per k)
|   |-- nas_tpe/
|   |-- nas_nsga2/
|   |-- nas_nsga3/
|   `-- summary.csv
|-- figures/
|   |-- heat_maps/
|   |-- error_plots/
|   |-- training_history/
|   |-- runtime_comparison/
|   `-- nas_comparison/
`-- tests/
    |-- test_geometries.py
    |-- test_physics.py
    `-- test_metrics.py


# === OUTPUTS PER EXPERIMENT ===

For each (geometry, method, k) combination:

1. Heat maps PNG (300 DPI):
   - At t = 0, 0.5, 1, 3, 10, 30 s
   - Three columns: FEM, method, abs(FEM - method)
   - viridis colormap, consistent scale

2. Error metrics CSV columns:
   geometry, method, nas_variant, k, seed, t,
   MAE, L2, max_err,
   runtime_total, runtime_fem_portion,
   runtime_pinn_train, runtime_pinn_infer,
   num_fem_solves, fem_saving_pct

3. Training history PNG:
   - X: epoch
   - Y: loss (log scale)
   - Lines: total, PDE, BC, IC
   - One subplot per anchor window

4. Runtime comparison PNG:
   - Bar chart: pure FEM vs k=1,2,3,4,5
   - Stacked: FEM portion vs PINN portion

5. k vs error PNG:
   - X: k
   - Y: MAE with error bars from 3 seeds
   - One line per geometry, four geometries on one plot

6. NAS comparison PNG (Stage 7 only):
   - Bar chart per geometry
   - Bars: C1, C2a, C2b, C2c
   - Y axis: best MAE at k=5

7. Discovered architectures JSON:
   geometry -> {nas_variant -> architecture list}

8. Summary table (markdown + CSV):
   All results aggregated


# === MY ADDITIONS / SUGGESTIONS ===

A. Linear interpolation baseline (no PINN, just FEM anchor interp).
   This addresses thesis Limitation 7. Include in every comparison.

B. Dimensionless validation: solve once dimensional, once dimensionless,
   check they match. Catches BC bugs.

C. JSON metadata per experiment:
   git_hash, all_hyperparameters, seeds, env_versions, hardware,
   wall_clock_time, peak_memory.

D. YAML config for everything. No hardcoded numbers in Python.

E. Unit tests for geometry boundary detection and metric computation.

F. Save trained PINN weights to disk for reproducibility.

G. Logging: always include experiment ID, geometry, method, k, seed
   in every log line.


# === STARTING INSTRUCTION ===

Begin with STAGE 0 only. Create the directory structure,
requirements.txt, README.md, and the logging utility. Then STOP
and let me review before proceeding to STAGE 1.

For each file you create:
  - Module docstring explaining purpose
  - Type hints on function signatures
  - At least one usage example in docstring

Use Python 3.10+. Suggested libraries:
  numpy, scipy, matplotlib       (always)
  torch                          (PINN)
  scikit-fem                     (FEM, pure Python, no FEniCS pain)
  optuna                         (TPE, C2a)
  pymoo                          (NSGA-II/III, C2b/c)
  pyyaml                         (config)
  pytest                         (tests)
  pandas                         (results CSV)
  tqdm                           (progress)
  matplotlib                     (figures)

Do not use libraries not in this list without asking me first.

Now begin STAGE 0.
